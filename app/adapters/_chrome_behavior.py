"""
Chrome 기반 어댑터(google_news/baidu_news) 공용 — 행동 자연화 헬퍼 + 종료 처리.

_chrome_detect.py 가 "Chrome 실행 전 탐지"를 담당한다면, 이 파일은 "띄운 뒤의
행동/종료"를 담당한다.
"""

from __future__ import annotations

import random
import time

from app.adapters import _profile_lock
from app.adapters._process_kill import kill_process_tree

# 창 크기를 워커마다 고정값으로 통일하면 그 자체가 지문이 되므로 흔한 해상도 중 무작위 선택
WINDOW_SIZES = ("1366,768", "1440,900", "1536,864", "1600,900", "1920,1080")

# 컴포넌트 업데이터(인증서 폐기 목록, 최적화 가이드 모델 등)와 Safe Browsing DB
# 자동 갱신을 끈다 — 스크래핑 봇 동작과 무관한 Chrome 자체의 전역 참조 데이터가
# 영구 프로필 디렉터리에 계속 쌓이는 걸 막는다(사이트별 쿠키/로컬스토리지 등
# "돌아오는 사용자" 신호에는 영향 없음 — 이 데이터들은 사이트 방문 이력이 아니라
# Chrome 배포판 자체가 받는 공용 참조 데이터라서다). 그래도 이미 받아진 것과
# 순수 디스크 캐시(Cache/Code Cache 등)는 계속 쌓이므로 _profile_cleanup.py 의
# 허용 목록 기반 정리가 별도로 필요하다.
PROFILE_DISK_USAGE_ARGS = (
    "--disable-component-update",
    "--safe-browsing-disable-auto-update",
)


def jitter_sleep(base_sec: float, spread: float = 0.4) -> None:
    """고정 간격 대신 자연스러운 편차를 준 대기. spread=0.4 → base의 ±40% 범위."""
    time.sleep(max(0.1, random.uniform(base_sec * (1 - spread), base_sec * (1 + spread))))


def simulate_reading(driver) -> None:
    """사람이 결과 페이지를 훑어보는 것처럼 스크롤 + 짧은 대기를 흉내낸다."""
    try:
        for _ in range(random.randint(1, 3)):
            driver.execute_script(f"window.scrollBy(0, {random.randint(200, 600)});")
            time.sleep(random.uniform(0.3, 0.9))
    except Exception:
        pass


class ChromeLifecycleMixin:
    """
    Chrome 기반 어댑터 공용 생성자 + close()/__del__() + 드라이버 기동 실패 처리.
    """

    def __init__(self, max_pages: int, delay_sec: float) -> None:
        self._max_pages = max_pages
        self._delay_sec = delay_sec
        self._driver = None
        self._user_data_dir: str | None = None  # close() 에서 PID 재사용 방지 확인에 사용
        self._profile_lock_file = None  # WORKER_ID 중복 감지용 flock 파일 핸들

    def _build_driver_or_release(self, build):
        """build() 로 드라이버를 생성해 self._driver 에 저장한다.

        락을 잡은 뒤(self._profile_lock_file) Chrome 기동 자체가 실패하면, 락을
        안 풀고 두면 같은 프로세스의 다음 재시도(_ensure_driver 재호출)가 자기
        자신의 flock 에 걸려 self-lockout 난다(flock 은 파일이 아니라 open file
        description 단위라 같은 프로세스라도 다시 열면 막힌다). 반드시 풀어준다.
        """
        try:
            self._driver = build()
        except Exception:
            _profile_lock.release(self._profile_lock_file)
            self._profile_lock_file = None
            raise
        return self._driver

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
