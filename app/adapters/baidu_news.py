"""
바이두 뉴스 발견 어댑터.

전략 (feasibility 테스트 단계 — decisions/baidu-discovery.md 참고):
  www.baidu.com/s?tn=news&cl=2&word=... 로 뉴스(资讯) 탭 결과를 스크랩한다.
  - pn 파라미터로 페이지네이션 (0, 10, 20, ...)
  - 결과 링크는 baijiahao.baidu.com(바이두 자체 게시 플랫폼) 링크가 대부분이며,
    daum 의 cp.news.search.daum.net 과 달리 이 자체가 최종 콘텐츠 페이지라
    리다이렉트 해석 없이 그대로 저장한다.

봇 차단 확인 결과 (2026-07-10):
  - 순수 HTTP 요청(httpx/curl)은 실서버 IP 에서도 100% wappass.baidu.com
    캡차 페이지로 리다이렉트됨 — daum/naver 식 httpx 접근 불가 확정.
  - undetected-chromedriver 로 실제 브라우저 JS 를 실행했을 때도 막히는지는
    아직 실서버에서 미검증 — 이 어댑터로 먼저 확인한다.
  - google_news.py 와 동일한 행동 자연화 기법(영구 프로필, 지터, 스크롤 시뮬레이션)을
    적용했다. 그래도 막히면 IP 평판 자체가 원인이므로 프록시 없이는 불가능하다고 판단.

파싱 셀렉터 미검증 경고:
  아래 _parse_urls 의 "#content_left" 기반 셀렉터는 바이두 일반 웹검색(SERP)의
  잘 알려진 마크업 구조를 기반으로 한 최선의 추정치이며, 뉴스(tn=news) 탭에서
  실제로 이 구조가 그대로 쓰이는지는 캡차를 통과한 real 페이지로 아직 확인하지
  못했다. 캡차를 통과하면 driver.page_source 를 캡처해서 셀렉터를 재검증해야 한다.
"""

from __future__ import annotations

import logging
import os
import random
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse

from app import config
from app.adapters import _profile_lock
from app.adapters._process_kill import kill_process_tree
from app.types import BotBlockedError, DiscoverResult, SourceType

_log = logging.getLogger(__name__)

_SEARCH_URL = "https://www.baidu.com/s"

_DEFAULT_DELAY_SEC = 1.5

_WINDOW_SIZES = ("1366,768", "1440,900", "1536,864", "1600,900", "1920,1080")

# 캡차/보안 확인 페이지 판별 시그니처 (2026-07-10 curl 테스트로 확인).
_BLOCK_HOST_MARKERS = ("wappass.baidu.com",)
_BLOCK_TITLE_MARKERS = ("百度安全验证",)


def _jitter_sleep(base_sec: float, spread: float = 0.4) -> None:
    """고정 간격 대신 자연스러운 편차를 준 대기. spread=0.4 → base의 ±40% 범위."""
    time.sleep(max(0.1, random.uniform(base_sec * (1 - spread), base_sec * (1 + spread))))


def _simulate_reading(driver) -> None:
    """사람이 결과 페이지를 훑어보는 것처럼 스크롤 + 짧은 대기를 흉내낸다."""
    try:
        for _ in range(random.randint(1, 3)):
            driver.execute_script(f"window.scrollBy(0, {random.randint(200, 600)});")
            time.sleep(random.uniform(0.3, 0.9))
    except Exception:
        pass


_LINUX_CHROME_BINARIES = (
    "google-chrome", "google-chrome-stable", "google-chrome-unstable",
    "chromium-browser", "chromium",
)
_LINUX_CHROME_PATHS = (
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/snap/bin/chromium",
)


def _detect_chrome_binary() -> str | None:
    """Chrome 실행 파일의 절대 경로를 반환한다. 못 찾으면 None."""
    import shutil

    if sys.platform == "win32":
        import winreg
        keys = [
            (winreg.HKEY_CURRENT_USER,  r"Software\Google\Chrome\BLBeacon", "version"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome", "DisplayVersion"),
        ]
        for hive, subkey, val in keys:
            try:
                with winreg.OpenKey(hive, subkey) as k:
                    path, _ = winreg.QueryValueEx(k, "InstallLocation")
                    candidate = os.path.join(path, "chrome.exe")
                    if os.path.isfile(candidate):
                        return candidate
            except Exception:
                continue
        return shutil.which("chrome") or shutil.which("chromium")

    for binary in _LINUX_CHROME_BINARIES:
        path = shutil.which(binary)
        if path:
            return path
    for path in _LINUX_CHROME_PATHS:
        if os.path.isfile(path):
            return path
    return None


def _detect_chrome_major() -> int | None:
    """설치된 Chrome 의 major 버전 반환. 감지 실패 시 None (uc 자동 감지에 위임)."""
    import subprocess, re

    binary = _detect_chrome_binary()
    if binary is None:
        return None

    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon") as k:
                version, _ = winreg.QueryValueEx(k, "version")
                m = re.match(r"(\d+)", version)
                return int(m.group(1)) if m else None
        except Exception:
            pass

    try:
        out = subprocess.check_output(
            [binary, "--version"],
            stderr=subprocess.DEVNULL, text=True,
        )
        m = re.search(r"(\d+)\.\d+\.\d+", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


class BaiduNewsAdapter:
    source_type: str = SourceType.BAIDU_NEWS

    def __init__(
        self,
        max_pages: int | None = None,
        delay_sec: float = _DEFAULT_DELAY_SEC,
    ) -> None:
        self._max_pages = max_pages or config.BAIDU_MAX_PAGES
        self._delay_sec = delay_sec
        self._driver = None
        self._user_data_dir: str | None = None  # close() 에서 PID 재사용 방지 확인에 사용
        self._profile_lock_file = None  # WORKER_ID 중복 감지용 flock 파일 핸들

    def _ensure_xvfb(self) -> None:
        if sys.platform == "win32":
            return
        if os.environ.get("DISPLAY"):
            return
        import subprocess
        display = ":99"
        subprocess.Popen(
            ["Xvfb", display, "-screen", "0", "1280x720x24"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.environ["DISPLAY"] = display
        time.sleep(0.5)
        _log.info("Xvfb 가상 디스플레이 시작 (DISPLAY=:99)", extra={"component": "adapter"})

    def _ensure_driver(self):
        if self._driver is None:
            import undetected_chromedriver as uc

            self._ensure_xvfb()

            chrome_binary = _detect_chrome_binary()
            if chrome_binary is None:
                raise RuntimeError(
                    "Chrome 바이너리를 찾을 수 없습니다. "
                    "google-chrome 또는 chromium 을 설치하세요."
                )

            opts = uc.ChromeOptions()
            opts.binary_location = chrome_binary
            opts.add_argument("--lang=zh-CN,zh")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-software-rasterizer")
            opts.add_argument(f"--window-size={random.choice(_WINDOW_SIZES)}")
            # 메모리 절감. 검색결과 페이지에서 XPath로 링크 텍스트만 읽고 이미지/시각적
            # 렌더링 결과는 안 쓰므로 기능상 리스크 없음(google_news.py와 동일 근거).
            #   - BackForwardCache: 뒤로가기 없이 앞으로만 이동하므로 순수 낭비
            #   - IsolateOrigins/site-per-process: 교차 출처 iframe(광고 등)마다 별도
            #     프로세스를 만드는 보안 격리 기능. DOM/렌더링 결과 자체는 안 바뀜.
            opts.add_argument("--disable-features=BackForwardCache,IsolateOrigins,site-per-process")
            opts.add_experimental_option("prefs", {
                "profile.managed_default_content_settings.images": 2,
            })
            if sys.platform == "win32":
                opts.add_argument("--window-position=-32000,-32000")

            user_data_dir = None
            if config.BAIDU_CHROME_PROFILE_DIR:
                profile_dir = Path(config.BAIDU_CHROME_PROFILE_DIR) / (config.WORKER_ID or "default")
                profile_dir.mkdir(parents=True, exist_ok=True)
                user_data_dir = str(profile_dir.resolve())
                # WORKER_ID 가 실수로 중복되면 위 분리만으로는 못 막는다 — flock 으로
                # 실제 배타적 잠금을 걸어, 이미 다른 프로세스가 쓰고 있으면 애매한
                # hang 대신 여기서 바로 명확하게 실패한다.
                self._profile_lock_file = _profile_lock.acquire(user_data_dir, config.WORKER_ID)

            self._user_data_dir = user_data_dir

            try:
                self._driver = uc.Chrome(
                    options=opts,
                    headless=False,
                    use_subprocess=True,
                    version_main=_detect_chrome_major(),
                    user_data_dir=user_data_dir,
                )
                self._driver.set_page_load_timeout(config.BAIDU_PAGE_LOAD_TIMEOUT_SEC)
                # set_page_load_timeout 은 탐색(navigation) 명령에만 적용된다. chromedriver
                # 자체가 응답 불능이 되면 다른 명령(current_url 읽기 등)은 이 상한과 무관하게
                # HTTP 클라이언트의 기본 소켓 타임아웃에 노출되므로, 모든 webdriver 명령에
                # 동일한 상한을 명시적으로 강제한다.
                self._driver.command_executor.client_config.timeout = config.BAIDU_PAGE_LOAD_TIMEOUT_SEC
            except Exception:
                # 락을 잡은 뒤 Chrome 기동 자체가 실패하면, 락을 안 풀고 두면 같은
                # 프로세스의 다음 재시도가 자기 자신의 flock 에 걸려 self-lockout
                # 난다(flock 은 open file description 단위라 같은 프로세스라도 다시
                # 열면 막힌다). 반드시 풀어준다.
                _profile_lock.release(self._profile_lock_file)
                self._profile_lock_file = None
                raise
        return self._driver

    def discover(self, keyword: str, cursor: str | None) -> DiscoverResult:
        pn = int(cursor) if cursor else 0
        page_num = pn // 10 + 1

        if page_num > self._max_pages:
            return DiscoverResult(urls=[], next_cursor=None, has_more=False)

        _jitter_sleep(self._delay_sec)

        params = urlencode({
            "rtt":  1,
            "bsst": 1,
            "cl":   2,
            "tn":   "news",
            "ie":   "utf-8",
            "word": keyword,
            "pn":   pn,
        })

        driver = self._ensure_driver()
        try:
            driver.get(f"{_SEARCH_URL}?{params}")
        except Exception as exc:
            # TimeoutException/WebDriverException 뿐 아니라 chromedriver 커맨드 채널
            # 자체가 죽으면 urllib3 저수준 예외가 selenium을 거치지 않고 그대로 올라온다
            # — 넓게 잡아 이 driver 를 무조건 폐기한다.
            _log.warning(
                f"baidu page load hung keyword='{keyword}' page={page_num} — resetting driver ({exc})",
                extra={"component": "adapter"},
            )
            self.close()
            raise

        _jitter_sleep(self._delay_sec)
        _simulate_reading(driver)

        if _is_blocked(driver):
            _log.warning(
                f"baidu blocked keyword='{keyword}' page={page_num} — 安全验证 감지",
                extra={"component": "adapter"},
            )
            raise BotBlockedError(f"baidu_news keyword='{keyword}' page={page_num}")

        urls = _extract_urls(driver)

        if not urls:
            # 바이두는 명확한 "검색 결과 없음" 신호가 없어(무의미한 키워드에도
            # 관련 콘텐츠를 대신 보여줌) 셀렉터 파손과 진짜 결과 없음을 구분하기
            # 어렵다. 우선 경고만 남기고 조용히 종료 — BotBlockedError 로
            # 취급하지 않는다(불필요한 백오프 소비 방지).
            _log.warning(
                f"baidu no urls extracted keyword='{keyword}' page={page_num} "
                f"— 셀렉터 확인 필요 (page_source 캡처 권장)",
                extra={"component": "adapter"},
            )
            return DiscoverResult(urls=[], next_cursor=None, has_more=False)

        has_more    = len(urls) >= 10 and page_num < self._max_pages
        next_cursor = str(pn + 10) if has_more else None

        return DiscoverResult(urls=urls, next_cursor=next_cursor, has_more=has_more)

    def close(self) -> None:
        if self._driver:
            browser_pid = getattr(self._driver, "browser_pid", None)
            try:
                self._driver.quit()
            except Exception:
                pass
            try:
                self._driver.quit = lambda *a, **kw: None
            except Exception:
                pass
            # uc.Chrome.quit() 은 브라우저에 SIGTERM 만 보내고 종료를 확인하지 않는다 —
            # 특히 hang 직후 정리하는 이 경로에서 응답 없이 orphan 으로 남기 쉽다.
            kill_process_tree(browser_pid, expected_user_data_dir=self._user_data_dir)
            _profile_lock.release(self._profile_lock_file)
            self._profile_lock_file = None
            self._driver = None

    def __del__(self) -> None:
        self.close()


def _is_blocked(driver) -> bool:
    """wappass.baidu.com 캡차/보안 확인 페이지로 리다이렉트됐는지 확인한다."""
    try:
        current_url = driver.current_url or ""
        title = driver.title or ""
    except Exception:
        return False
    if any(marker in current_url for marker in _BLOCK_HOST_MARKERS):
        return True
    return any(marker in title for marker in _BLOCK_TITLE_MARKERS)


def _extract_urls(driver) -> list[str]:
    """뉴스 검색 결과에서 콘텐츠 URL 추출.

    미검증 — #content_left 는 바이두 일반 웹검색(SERP)의 알려진 컨테이너 구조를
    기반으로 한 추정치. 캡차를 통과한 실제 페이지로 검증 후 필요하면 수정해야 한다.
    """
    from selenium.webdriver.common.by import By

    urls: list[str] = []
    seen: set[str] = set()

    try:
        container = driver.find_element(By.ID, "content_left")
        elements = container.find_elements(By.CSS_SELECTOR, "h3 a[href]")
    except Exception:
        elements = []

    if not elements:
        # 폴백: 컨테이너 구조가 다를 경우를 대비해 페이지 전체에서 h3 > a 를 시도.
        elements = driver.find_elements(By.CSS_SELECTOR, "h3 a[href]")

    for el in elements:
        href = el.get_attribute("href") or ""
        if not href.startswith("http"):
            continue
        parsed = urlparse(href)
        if "baidu.com" in parsed.netloc and "baijiahao.baidu.com" not in parsed.netloc:
            # www.baidu.com/link?... 같은 바이두 자체 검색 UI 링크는 제외.
            # baijiahao.baidu.com(콘텐츠 플랫폼)은 예외적으로 포함.
            continue
        if href not in seen:
            seen.add(href)
            urls.append(href)

    return urls
