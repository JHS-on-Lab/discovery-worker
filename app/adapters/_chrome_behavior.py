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
    close()/__del__() 공용 구현. 이 믹스인을 쓰는 클래스는 __init__ 에서
    self._driver / self._user_data_dir / self._profile_lock_file 를 설정해야 한다
    (google_news.py/baidu_news.py 둘 다 이미 그렇게 하고 있음).
    """

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
