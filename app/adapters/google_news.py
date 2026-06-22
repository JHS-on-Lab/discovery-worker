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

headless 모드는 Google Bot 감지에 걸리므로 headless=False 로 실행.
  Windows: 창을 화면 밖으로 이동
  Linux:   Xvfb 가상 디스플레이 사용 (deployment.md 참고)
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
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
            if sys.platform == "win32":
                opts.add_argument("--window-position=-32000,-32000")
            self._driver = uc.Chrome(
                options=opts,
                headless=False,
                version_main=_detect_chrome_major(),
            )
        return self._driver

    def discover(self, keyword: str, cursor: str | None) -> DiscoverResult:
        mode = config.GOOGLE_DISCOVERY_MODE.lower()
        if mode == "rss":
            return self._discover_rss(keyword, cursor)
        return self._discover_search(keyword, cursor)

    # ------------------------------------------------------------------
    # search 모드
    # ------------------------------------------------------------------

    def _discover_search(self, keyword: str, cursor: str | None) -> DiscoverResult:
        page = int(cursor) if cursor else 1

        if page > self._max_pages:
            return DiscoverResult(urls=[], next_cursor=None, has_more=False)

        if page > 1:
            time.sleep(self._delay_sec)

        params = urlencode({
            "q":     keyword,
            "tbm":   "nws",
            "start": (page - 1) * 10,
            "tbs":   "qdr:d",
            "hl":    "ko",
            "gl":    "KR",
        })

        driver = self._ensure_driver()
        driver.get(f"{_SEARCH_URL}?{params}")
        time.sleep(self._delay_sec)

        urls = _extract_search_urls(driver)

        if not urls:
            _log.warning(
                f"google blocked keyword='{keyword}' page={page} — bot detection or page structure change",
                extra={"component": "adapter"},
            )
            raise BotBlockedError(f"google_news keyword='{keyword}' page={page}")

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
        """Chrome으로 CBMi URL 탐색 → 최종 언론사 URL 수집."""
        driver = self._ensure_driver()
        resolved = []
        for url in cbmi_urls:
            try:
                driver.get(url)
                time.sleep(self._delay_sec)
                final = driver.current_url
                if "google.com" not in urlparse(final).netloc:
                    resolved.append(final)
                else:
                    _log.warning(
                        f"cbmi unresolved: {url[:80]}",
                        extra={"component": "adapter"},
                    )
            except Exception as exc:
                _log.debug(f"cbmi navigate failed url={url[:60]} err={exc}")
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
