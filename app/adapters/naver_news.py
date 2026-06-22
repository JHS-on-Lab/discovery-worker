"""
네이버 뉴스 발견 어댑터.

전략:
  search.naver.com/search.naver?start=N 으로 풀 HTML 반복 요청.
  - start 파라미터가 공개 URL이라 구조가 안정적.
  - 스크롤 JSON API(tab/more)는 내부 API로 파라미터가 동적 생성되어 불안정.
  - 응답 크기 차이(300KB vs 130KB)는 크롤러 관점에서 유의미하지 않음.

커서: start 오프셋 (1→11→21→...). None이면 첫 페이지.
중단 조건: 결과 10개 미만 or max_pages 도달.

셀렉터 전략:
  부모 클래스가 sds-comps-base-layout 인 <a href> 를 추출한다.
  sds-comps-* 는 네이버 디자인 시스템(SDS) 클래스로, fender-ui_ 해시보다 안정적이며
  콘텐츠당 정확히 1개의 링크만 선택된다.
  0개이면 셀렉터 파손으로 간주하고 WARNING 을 남긴다.
"""

from __future__ import annotations

import logging
from selectolax.parser import HTMLParser
from urllib.parse import urlparse

from app import config
from app.adapters._base import PaginatedAdapter
from app.fetch._client import make_client
from app.types import BotBlockedError, DiscoverResult, SourceType

_log = logging.getLogger(__name__)

_SEARCH_URL = "https://search.naver.com/search.naver"

_BLOCKED_HOSTS = {
    "search.naver.com", "help.naver.com", "mkt.naver.com",
    "keep.naver.com", "shopping.naver.com", "search.shopping.naver.com",
    "news.naver.com", "media.naver.com",
}

# pd 파라미터 (실측값): 1=1주, 2=1개월, 3=오늘, 4=1일
_DEFAULT_PERIOD   = "4"
_DEFAULT_DELAY_MS = 800


class NaverNewsAdapter(PaginatedAdapter):
    source_type: str = SourceType.NAVER_NEWS

    def __init__(
        self,
        period: str    = _DEFAULT_PERIOD,
        max_pages: int | None = None,
        delay_ms: int  = _DEFAULT_DELAY_MS,
    ) -> None:
        super().__init__(period, max_pages or config.NAVER_MAX_PAGES, delay_ms)

    def discover(self, keyword: str, cursor: str | None) -> DiscoverResult:
        start    = int(cursor) if cursor else 1
        page_num = (start - 1) // 10 + 1

        if result := self._exceeded(page_num):
            return result

        self._delay(is_first=(start == 1))

        params = {
            "where": "news",
            "query": keyword,
            "sort": "1",        # 최신순
            "pd": self._period,
            "start": str(start),
        }

        with make_client(referer="https://www.naver.com/") as client:
            resp = client.get(_SEARCH_URL, params=params)
            resp.raise_for_status()

        urls, is_genuine_empty = _parse_urls(resp.text)

        if not urls:
            if is_genuine_empty:
                _log.debug(
                    f"naver_news empty keyword='{keyword}' page={page_num} — 검색 결과 없음",
                    extra={"component": "adapter"},
                )
            else:
                _log.warning(
                    f"naver_news blocked keyword='{keyword}' page={page_num} "
                    f"— bot detection or sds-comps-base-layout change",
                    extra={"component": "adapter"},
                )
                raise BotBlockedError(f"naver_news keyword='{keyword}' page={page_num}")

        has_more = len(urls) >= 10 and page_num < self._max_pages
        next_cursor = str(start + 10) if has_more else None

        return DiscoverResult(urls=urls, next_cursor=next_cursor, has_more=has_more)


def _parse_urls(html: str) -> tuple[list[str], bool]:
    """sds-comps-base-layout 부모 기반으로 콘텐츠 URL 추출.

    반환: (urls, is_genuine_empty)
      is_genuine_empty=True  → 네이버가 "검색 결과 없음" 페이지를 정상 반환한 것
      is_genuine_empty=False → 봇 차단 또는 셀렉터 파손 의심
    """
    tree = HTMLParser(html)
    urls: list[str] = []

    for node in tree.css("a[href]"):
        href = node.attributes.get("href", "")
        if not href.startswith("http"):
            continue

        parent = node.parent
        if parent is None:
            continue
        if "sds-comps-base-layout" not in (parent.attributes.get("class") or ""):
            continue

        parsed = urlparse(href)
        host = parsed.netloc.lower()

        if any(host == b or host.endswith("." + b) for b in _BLOCKED_HOSTS):
            continue
        if not parsed.path or parsed.path in ("", "/"):
            continue

        urls.append(href)

    is_genuine_empty = (not urls) and bool(tree.css_first("#notfound, [class*='not_found']"))
    return urls, is_genuine_empty
