"""
Site Isolation / BackForwardCache 비활성화 플래그가 실제로 먹히는지 확인하는 진단 스크립트.

mem 로그(app/memlog.py)에서 --disable-features=BackForwardCache,IsolateOrigins,
site-per-process 를 이미 적용했는데도 renderer 프로세스가 검색 1건마다 수십 개로
급증하는 패턴이 관찰됐다(docs/memory-oom-mitigation.md). 이 스크립트는 그 원인이
① 플래그가 실제 브라우저 프로세스에 안 실렸는지, ② 조직 Chrome 정책이 Site
Isolation 을 강제로 덮어쓰고 있는지, ③ 아니면 플래그는 정상 적용됐는데도 여전히
renderer 가 느는 건지(=플래그 자체가 이 케이스엔 효과가 없는 것)를 구분한다.

실행 (google_news 워커가 실제로 도는 서버에서 — Chrome 설치·Xvfb 필요):
  cd discovery-worker
  .venv/bin/python scripts/check_chrome_isolation.py

--worker-id 로 실제 운영 워커와 다른 Chrome 프로필을 쓰게 할 수 있다(기본값
"chrome-check-diag"). config.py 가 .env.{APP_ENV} 를 override=True 로 로드해서
.env 파일에 WORKER_ID 가 명시돼 있으면 쉘 환경변수(WORKER_ID=... 접두사)는
무시되므로, 반드시 이 CLI 옵션으로 지정해야 실제 운영 워커의 프로필 락과
충돌하지 않는다:
  .venv/bin/python scripts/check_chrome_isolation.py --worker-id chrome-check-diag

출력: 표준출력 텍스트 + chrome_policy_screenshot.png (chrome://policy 스크린샷,
페이지가 shadow DOM 기반이라 텍스트 추출이 비어있을 수 있어 스크린샷을 보조로 남김)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import psutil

from app import config
from app.adapters.google_news import UCGoogleNewsAdapter


def _section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def _renderer_count(driver) -> int:
    """driver 의 browser_pid 자식들 중 --type=renderer 개수를 센다."""
    browser_pid = getattr(driver, "browser_pid", None)
    if not browser_pid:
        return -1
    try:
        parent = psutil.Process(browser_pid)
    except psutil.NoSuchProcess:
        return -1
    count = 0
    for child in parent.children(recursive=True):
        try:
            if any(arg.startswith("--type=renderer") for arg in child.cmdline()):
                count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return count


def main() -> None:
    p = argparse.ArgumentParser(description="Site Isolation/BackForwardCache 플래그 진단")
    p.add_argument(
        "--worker-id", default="chrome-check-diag",
        help="이 진단용 Chrome 프로필 식별자 (기본: chrome-check-diag). "
             "실제 운영 워커와 같은 값을 쓰면 프로필 락이 충돌한다.",
    )
    args = p.parse_args()

    # __main__.py 와 동일한 패턴 — .env 의 WORKER_ID 를 코드에서 명시적으로 덮어써야
    # 실제로 반영된다(config.py 가 .env.{APP_ENV} 를 override=True 로 로드하기 때문에
    # 쉘 환경변수만으로는 안 먹힌다).
    config.WORKER_ID = args.worker_id
    print(f"[진단용 WORKER_ID = {config.WORKER_ID}] (실제 운영 워커와 별도 Chrome 프로필 사용)")

    adapter = UCGoogleNewsAdapter()
    try:
        driver = adapter._ensure_driver()

        # --- 1. 실제 브라우저 프로세스에 실린 커맨드라인 ---
        # CDP Browser.getBrowserCommandLine 은 --enable-automation 이 있어야 응답하는데,
        # undetected_chromedriver 가 탐지 회피를 위해 그 플래그를 일부러 빼기 때문에 막힌다.
        # 대신 chrome://version 페이지의 #command_line 요소를 직접 읽는다.
        _section("1. 실제 커맨드라인 (chrome://version)")
        driver.get("chrome://version")
        time.sleep(0.5)
        cmdline_text = driver.execute_script(
            "return document.querySelector('#command_line')?.innerText || ''"
        )
        print(cmdline_text or "  (command_line 요소를 못 찾음 — 이 Chrome 버전에서 구조가 다를 수 있음)")
        disable_features_arg = next(
            (part for part in cmdline_text.split() if part.startswith("--disable-features=")),
            None,
        )
        print(f"\n→ --disable-features 인자: {disable_features_arg or '(없음! 플래그가 아예 안 실림)'}")
        if disable_features_arg:
            for needed in ("BackForwardCache", "IsolateOrigins", "site-per-process"):
                print(f"   - {needed}: {'포함' if needed in disable_features_arg else '누락'}")

        # --- 2. 조직 Chrome 정책이 Site Isolation 을 강제하는지 ---
        _section("2. chrome://policy (조직 정책이 덮어쓰는지 확인)")
        driver.get("chrome://policy")
        time.sleep(1.5)  # Polymer 렌더링 대기
        policy_text = driver.execute_script("return document.body.innerText || ''")
        if policy_text.strip():
            print(policy_text[:3000])
        else:
            print("  (innerText 비어있음 — shadow DOM 때문일 수 있음. 스크린샷 참고)")
        screenshot_path = Path(__file__).parent / "chrome_policy_screenshot.png"
        driver.save_screenshot(str(screenshot_path))
        print(f"\n→ 스크린샷 저장: {screenshot_path}")

        # --- 3. 실제 검색 1건으로 renderer 급증 재현 ---
        _section("3. 검색 1건 전후 renderer 프로세스 수 (실측 재현)")
        before = _renderer_count(driver)
        print(f"검색 전: renderer={before}")

        driver.get("https://www.google.com/search?q=test&tbm=nws&tbs=qdr:d&hl=ko&gl=KR")
        time.sleep(3)
        after = _renderer_count(driver)
        print(f"검색 1건 후: renderer={after}")

        if disable_features_arg and after - before <= 2:
            print("\n결론: 플래그 정상 적용 + renderer 도 안정적 — 이 서버에선 문제 재현 안 됨.")
        elif disable_features_arg:
            print("\n결론: 플래그는 실제로 적용됐는데도 renderer 가 급증함 —")
            print("       플래그 자체가 이 Chrome 버전/이 케이스엔 효과가 없다는 뜻.")
        else:
            print("\n결론: 플래그가 애초에 브라우저 프로세스에 안 실림 — 배포/버전 문제부터 확인 필요.")

    finally:
        adapter.close()


if __name__ == "__main__":
    main()
