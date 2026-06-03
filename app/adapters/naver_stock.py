"""
네이버 증권 종목토론 게시판 발견 어댑터.

키워드: 종목코드 (예: "005930")
수집 대상: https://finance.naver.com/item/board.naver?code={code}&page={N}
게시글 URL: https://finance.naver.com/item/board_read.naver?code={code}&nid={nid}

커서: 페이지 번호 (1→2→3→...). None이면 첫 페이지.
중단 조건: 게시글 0개 또는 max_pages 도달.
"""

from __future__ import annotations

import logging
from selectolax.parser import HTMLParser

from app import config
from app.adapters._base import PaginatedAdapter
from app.fetch._client import make_client
from app.types import DiscoverResult, PortalType

_log = logging.getLogger(__name__)

_BASE_URL   = "https://finance.naver.com"
_BOARD_URL  = f"{_BASE_URL}/item/board.naver"

_DEFAULT_DELAY_MS = 500


class NaverStockAdapter(PaginatedAdapter):
    """
    네이버 증권 종목토론 게시글 URL 수집.
    keyword 는 종목코드 (예: "005930").
    """

    portal_type: str = PortalType.NAVER_STOCK

    def __init__(
        self,
        max_pages: int | None = None,
        delay_ms: int  = _DEFAULT_DELAY_MS,
    ) -> None:
        super().__init__(period="", max_pages=max_pages or config.NAVER_STOCK_MAX_PAGES, delay_ms=delay_ms)

    def discover(self, keyword: str, cursor: str | None) -> DiscoverResult:
        code = keyword.strip()
        page = int(cursor) if cursor else 1

        if result := self._exceeded(page):
            return result

        self._delay(is_first=(page == 1))

        with make_client(referer=_BASE_URL + "/") as client:
            resp = client.get(_BOARD_URL, params={"code": code, "page": page})
            resp.raise_for_status()

        urls = _parse_board(resp.text, code)

        if not urls:
            _log.warning(f"naver_stock board returned 0 urls code={code} page={page}")
            return DiscoverResult(urls=[], next_cursor=None, has_more=False)

        has_more = page < self._max_pages
        next_cursor = str(page + 1) if has_more else None

        return DiscoverResult(urls=urls, next_cursor=next_cursor, has_more=has_more)


def _parse_board(html: str, code: str) -> list[str]:
    """게시판 목록에서 게시글 URL 추출. nid 기준으로 중복 제거."""
    tree = HTMLParser(html)
    seen: set[str] = set()
    urls: list[str] = []

    for a in tree.css("a[href*='board_read.naver']"):
        href = a.attributes.get("href", "")
        if not href or "nid=" not in href:
            continue

        # nid 추출해 중복 제거 (같은 게시글이 여러 <a>로 나올 수 있음)
        nid = ""
        for part in href.split("&"):
            if part.startswith("nid="):
                nid = part[4:]
                break

        if not nid or nid in seen:
            continue

        seen.add(nid)
        urls.append(f"{_BASE_URL}/item/board_read.naver?code={code}&nid={nid}")

    return urls
