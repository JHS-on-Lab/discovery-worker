"""
구글 뉴스 발견 어댑터.

GOOGLE_DISCOVERY_MODE 환경변수로 수집 방식을 선택한다.

  search (기본): google.com/search?tbm=nws 스크랩
    - 언론사 직접 URL 반환, 페이지네이션 가능
    - undetected-chromedriver 필요

  rss: Google News RSS + Chrome CBMi URL 변환
    - RSS 최대 ~100건을 HTTP로 가져온 뒤 Chrome으로 실제 URL 변환
    - 봇 감지로 search 모드가 막혔을 때 대안
    - 동일 Chrome 드라이버 재사용, 페이지네이션 없음

GOOGLE_DISCOVERY_MODE=search(기본)일 때, 실제 봇 차단(캡차/챌린지 페이지, 단순
결과 소진과 구분됨)이 감지되면 GOOGLE_BLOCK_COOLDOWN_SEC 동안 이 어댑터
인스턴스(워커 프로세스 수명 동안 키워드 간 공유)가 자동으로 rss 모드로
전환되고, 쿨다운이 지나면 자동으로 search 모드로 복귀를 시도한다.

headless 모드는 Google Bot 감지에 걸리므로 headless=False 로 실행.
  Windows: 창을 화면 밖으로 이동
  Linux:   Xvfb 가상 디스플레이 사용 (deployment.md 참고)

행동 자연화(behavioral naturalization) — IP 로테이션 없이 탐지 신호를 줄이기 위한 조치:
  - 영구 Chrome 프로필(GOOGLE_CHROME_PROFILE_DIR, WORKER_ID별 분리): 매 실행마다
    빈 세션이 아니라 쿠키·로컬스토리지가 누적된 상태로 접속.
  - 요청 간격에 랜덤 지터(_jitter_sleep) — 고정 간격은 그 자체로 자동화 신호.
    페이지 번호와 무관하게 매 요청 전 적용해 키워드 전환 시에도 딜레이 없이
    바로 이어지지 않게 한다.
  - 결과 페이지 로드 후 스크롤 시뮬레이션(_simulate_reading) 후 DOM 파싱.
  - Chrome 창 크기를 무작위 해상도 중에서 선택 — 워커 전체가 동일 해상도면 지문이 됨.
"""

from __future__ import annotations

import logging
import os
import random
import sys
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode
from xml.etree import ElementTree as ET

from app import config
from app.types import BotBlockedError, DiscoverResult, SourceType

_log = logging.getLogger(__name__)

_SEARCH_URL = "https://www.google.com/search"
_RSS_URL    = "https://news.google.com/rss/search"

_GOOGLE_HOSTS = {
    "google.com", "www.google.com", "news.google.com",
    "googleapis.com", "gstatic.com", "google.co.kr",
}

_DEFAULT_MAX_PAGES = 5
_DEFAULT_DELAY_SEC = 1.5

# 창 크기를 워커마다 고정값으로 통일하면 그 자체가 지문이 되므로 흔한 해상도 중 무작위 선택
_WINDOW_SIZES = ("1366,768", "1440,900", "1536,864", "1600,900", "1920,1080")


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
    import shutil, os

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
        # Windows: 레지스트리에서 버전 읽기
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


class UCGoogleNewsAdapter:
    """
    GOOGLE_DISCOVERY_MODE 에 따라 search / rss 방식으로 동작하는 Google 뉴스 어댑터.
    두 모드 모두 undetected-chromedriver 를 사용한다.
    """

    source_type: str = SourceType.GOOGLE_NEWS

    def __init__(
        self,
        max_pages: int | None = None,
        delay_sec: float = _DEFAULT_DELAY_SEC,
    ) -> None:
        self._max_pages = max_pages or config.GOOGLE_MAX_PAGES
        self._delay_sec = delay_sec
        self._driver = None
        self._search_blocked_until: datetime | None = None  # 봇 차단 감지 시 rss 폴백 만료 시각

    def _ensure_xvfb(self) -> None:
        """Linux 서버에 디스플레이가 없으면 Xvfb 가상 디스플레이를 시작한다."""
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
            opts.add_argument("--lang=ko-KR,ko")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-software-rasterizer")
            opts.add_argument(f"--window-size={random.choice(_WINDOW_SIZES)}")
            if sys.platform == "win32":
                opts.add_argument("--window-position=-32000,-32000")

            user_data_dir = None
            if config.GOOGLE_CHROME_PROFILE_DIR:
                # 워커마다 독립된 프로필 디렉터리 — 매 실행마다 새 세션이 아니라
                # 쿠키·로컬스토리지가 누적된 "돌아오는 사용자"처럼 보이게 한다.
                # WORKER_ID 로 분리해 동시에 여러 워커가 같은 프로필을 잠그는 것을 방지.
                profile_dir = Path(config.GOOGLE_CHROME_PROFILE_DIR) / (config.WORKER_ID or "default")
                profile_dir.mkdir(parents=True, exist_ok=True)
                user_data_dir = str(profile_dir.resolve())

            self._driver = uc.Chrome(
                options=opts,
                headless=False,
                use_subprocess=True,
                version_main=_detect_chrome_major(),
                user_data_dir=user_data_dir,
            )
            self._driver.set_page_load_timeout(config.GOOGLE_PAGE_LOAD_TIMEOUT_SEC)
            # set_page_load_timeout 은 "탐색(navigation)" 명령에만 적용된다. chromedriver
            # 자체가 응답 불능이 되면(브라우저 크래시/좀비 프로세스 등) current_url 읽기
            # 같은 다른 명령들은 이 상한의 영향을 받지 않고 HTTP 클라이언트의 기본
            # 소켓 타임아웃(환경에 따라 매우 길거나 없을 수 있음)에 그대로 노출된다.
            # 모든 webdriver 명령에 동일한 상한을 명시적으로 강제한다.
            self._driver.command_executor.client_config.timeout = config.GOOGLE_PAGE_LOAD_TIMEOUT_SEC
        return self._driver

    def discover(self, keyword: str, cursor: str | None) -> DiscoverResult:
        mode = config.GOOGLE_DISCOVERY_MODE.lower()
        if mode == "rss":
            return self._discover_rss(keyword, cursor)

        if self._search_blocked_until is not None:
            if datetime.now(timezone.utc) < self._search_blocked_until:
                # 최근 봇 차단 감지 — 쿨다운 동안 rss 로 임시 폴백
                return self._discover_rss(keyword, cursor)
            # 쿨다운 만료 — search 모드로 자동 복귀
            _log.info(
                "google search 모드 쿨다운 만료 — search 재시도",
                extra={"component": "adapter"},
            )
            self._search_blocked_until = None

        return self._discover_search(keyword, cursor)

    # ------------------------------------------------------------------
    # search 모드
    # ------------------------------------------------------------------

    def _discover_search(self, keyword: str, cursor: str | None) -> DiscoverResult:
        page = int(cursor) if cursor else 1

        if page > self._max_pages:
            return DiscoverResult(urls=[], next_cursor=None, has_more=False)

        # 페이지 번호와 무관하게 매 요청 전 지터 — page==1(새 키워드 시작)에서도
        # 적용해야 이전 키워드 처리 직후 딜레이 없이 바로 이어지는 걸 막는다.
        _jitter_sleep(self._delay_sec)

        params = urlencode({
            "q":     keyword,
            "tbm":   "nws",
            "start": (page - 1) * 10,
            "tbs":   "qdr:d",
            "hl":    "ko",
            "gl":    "KR",
        })

        driver = self._ensure_driver()
        try:
            driver.get(f"{_SEARCH_URL}?{params}")
        except Exception as exc:
            # TimeoutException/WebDriverException 뿐 아니라, chromedriver 커맨드
            # 채널 자체가 죽으면 urllib3.exceptions.ReadTimeoutError 등이 selenium을
            # 거치지 않고 그대로 올라온다 — 넓게 잡아 이 driver 를 무조건 폐기한다.
            # 이 driver 는 이후에도 계속 멈춰있을 수 있으므로 폐기하고, 다음 호출에서
            # _ensure_driver() 가 새 인스턴스를 띄우게 한다.
            _log.warning(
                f"google page load hung keyword='{keyword}' page={page} — resetting driver ({exc})",
                extra={"component": "adapter"},
            )
            self.close()
            raise

        _jitter_sleep(self._delay_sec)
        _simulate_reading(driver)

        urls = _extract_search_urls(driver)

        if not urls:
            if _is_bot_block_page(driver):
                self._search_blocked_until = (
                    datetime.now(timezone.utc) + timedelta(seconds=config.GOOGLE_BLOCK_COOLDOWN_SEC)
                )
                _log.warning(
                    f"google blocked keyword='{keyword}' page={page} — bot detection, "
                    f"rss 로 {config.GOOGLE_BLOCK_COOLDOWN_SEC}s 동안 폴백",
                    extra={"component": "adapter"},
                )
                raise BotBlockedError(f"google_news keyword='{keyword}' page={page}")

            # 캡차/차단 신호 없이 결과만 없는 경우 — tbs=qdr:d(최근 1일) 필터상
            # 해당 페이지 깊이까지 결과가 실제로 소진된 정상적인 상황. 차단이 아니므로
            # 여기서 조용히 페이지네이션을 끝낸다 (봇 차단 백오프를 소비하지 않음).
            _log.debug(
                f"google no more results keyword='{keyword}' page={page}",
                extra={"component": "adapter"},
            )
            return DiscoverResult(urls=[], next_cursor=None, has_more=False)

        has_more = len(urls) >= 8 and page < self._max_pages
        next_cursor = str(page + 1) if has_more else None

        return DiscoverResult(urls=urls, next_cursor=next_cursor, has_more=has_more)

    # ------------------------------------------------------------------
    # rss 모드
    # ------------------------------------------------------------------

    def _discover_rss(self, keyword: str, cursor: str | None) -> DiscoverResult:
        """RSS 피드 수집 후 Chrome으로 CBMi URL → 실제 언론사 URL 변환."""
        if cursor is not None:
            return DiscoverResult(urls=[], next_cursor=None, has_more=False)

        from app.fetch._client import make_client

        params = {"q": keyword, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
        with make_client() as client:
            resp = client.get(_RSS_URL, params=params)
            resp.raise_for_status()

        cbmi_urls = _parse_rss(resp.content, cutoff_days=1)
        _log.info(f"rss mode: {len(cbmi_urls)} cbmi urls, resolving via Chrome")

        urls = self._resolve_cbmi(cbmi_urls)
        _log.info(f"rss mode: resolved {len(urls)}/{len(cbmi_urls)}")

        return DiscoverResult(urls=urls, next_cursor=None, has_more=False)

    def _resolve_cbmi(self, cbmi_urls: list[str]) -> list[str]:
        """Chrome으로 CBMi URL 탐색 → 최종 언론사 URL 수집.

        중간에 하나라도 hang/실패하면 driver 를 폐기하고 남은 URL 은 포기한다 —
        이미 좀비가 된 driver 로 나머지 수십 건을 하나씩 타임아웃날 때까지
        기다리는 건 시간 낭비이자, 다음 키워드까지 워커를 묶어두는 원인이 된다.
        """
        driver = self._ensure_driver()
        resolved = []
        total = len(cbmi_urls)
        for i, url in enumerate(cbmi_urls, start=1):
            try:
                driver.get(url)
                _jitter_sleep(self._delay_sec)
                final = driver.current_url
                if "google.com" not in urlparse(final).netloc:
                    resolved.append(final)
                else:
                    _log.warning(
                        f"cbmi unresolved: {url[:80]}",
                        extra={"component": "adapter"},
                    )
            except Exception as exc:
                _log.warning(
                    f"cbmi navigate hung at {i}/{total} — resetting driver, "
                    f"남은 {total - i}건 포기 (url={url[:60]} err={exc})",
                    extra={"component": "adapter"},
                )
                self.close()
                break

            if i % 5 == 0 or i == total:
                _log.debug(
                    f"cbmi progress {i}/{total} — resolved {len(resolved)}",
                    extra={"component": "adapter"},
                )
        return resolved

    # ------------------------------------------------------------------
    # 공통
    # ------------------------------------------------------------------

    def close(self) -> None:
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            try:
                self._driver.quit = lambda *a, **kw: None
            except Exception:
                pass
            self._driver = None

    def __del__(self) -> None:
        self.close()


_BLOCK_PAGE_MARKERS = (
    "unusual traffic",                          # "Our systems have detected unusual traffic ..."
    "비정상적인 트래픽",                          # 위 문구의 한국어(hl=ko) 버전
    "g-recaptcha",
    "detected unusual traffic from your computer network",
)


def _is_bot_block_page(driver) -> bool:
    """결과 0건이 실제 구글 봇 차단(캡차/챌린지 페이지)인지 확인한다.

    tbs=qdr:d(최근 1일) 필터 특성상 페이지 깊이가 늘수록 결과가 정상적으로
    소진돼 URL이 0개가 되는 경우가 흔하다. 이걸 전부 BotBlockedError로
    처리하면 오탐이 쌓여 불필요한 백오프·키워드 포기가 발생하므로,
    실제 차단 신호(리다이렉트 /sorry/, 캡차 문구)가 있을 때만 True.
    """
    try:
        if "/sorry/" in (driver.current_url or ""):
            return True
        page_source = (driver.page_source or "").lower()
    except Exception:
        return False
    return any(marker.lower() in page_source for marker in _BLOCK_PAGE_MARKERS)


def _extract_search_urls(driver) -> list[str]:
    """Google 뉴스 검색 결과에서 언론사 직접 URL 추출."""
    from selenium.webdriver.common.by import By

    urls = []
    seen: set[str] = set()

    elements = driver.find_elements(
        By.XPATH, "//a[.//h3 or .//div[@role='heading']]"
    )

    for el in elements:
        href = el.get_attribute("href") or ""
        if not href.startswith("http"):
            continue

        if "google.com/url" in href:
            qs = parse_qs(urlparse(href).query)
            href = qs.get("q", [""])[0] or href

        if not href.startswith("http"):
            continue

        parsed = urlparse(href)
        if any(g in parsed.netloc.lower() for g in _GOOGLE_HOSTS):
            continue
        if not parsed.path or parsed.path == "/":
            continue

        if href not in seen:
            seen.add(href)
            urls.append(href)

    return urls


def _parse_rss(content: bytes, cutoff_days: int) -> list[str]:
    """RSS XML 파싱 → CBMi URL 목록. pubDate 기준 cutoff_days 이내만 포함."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
    root = ET.fromstring(content)
    channel = root.find("channel")
    if channel is None:
        return []

    urls: list[str] = []
    for item in channel.findall("item"):
        link   = item.findtext("link", "").strip()
        pubdate = item.findtext("pubDate", "").strip()
        if not link:
            continue
        if pubdate:
            try:
                if parsedate_to_datetime(pubdate) < cutoff:
                    continue
            except Exception:
                pass
        urls.append(link)
    return urls
