"""
DuckDuckGo(베트남어) 발견 어댑터.

전략:
  DuckDuckGo 뉴스 탭(iar=news)이 쓰는 내부 JSON API를 그대로 호출한다.
  html.duckduckgo.com/html/ 의 일반 웹검색 대신 이 방식을 쓰는 이유:
    - 일반 웹검색은 홈페이지/카테고리 루트 URL(예: vietnamnet.vn/)이 섞여 나와
      추출 대상으로 쓸모없는 경우가 많다.
    - 뉴스 탭은 Bing 뉴스 인덱스 기반이라 개별 기사 URL만 나오고 광고도 없다.

  1) https://duckduckgo.com/?q=<keyword>&t=h_&ia=news&iar=news 로 페이지를 받아
     본문에 박혀있는 vqd 토큰(쿼리별 1회성 세션 토큰)을 추출한다.
  2) https://duckduckgo.com/news.js?q=<keyword>&vqd=<token>&l=vn-vi&df=<period>&p=-1&s=<offset>&o=json
     을 호출해 뉴스 결과 JSON을 받는다. 응답의 "next" 필드에 다음 페이지 쿼리스트링이
     그대로 들어있어 그 안의 s 값을 그대로 다음 요청에 쓴다 (오프셋을 직접 계산하지 않음).

  df 파라미터: d=1일, w=1주, m=1개월 (Naver/Daum 어댑터와 동일 관례).

주의:
  vqd는 비공개 내부 토큰이라 DuckDuckGo가 API를 바꾸면 이 어댑터도 깨진다.
  1)단계 응답에 vqd가 없으면(페이지 구조 변경 또는 차단) BotBlockedError를 던진다.

커서: "페이지번호:오프셋:vqd" 형식 문자열. None이면 첫 페이지(vqd 새로 발급).
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import parse_qs, urlparse

from app.adapters._base import PaginatedAdapter
from app.fetch._client import make_client
from app.types import BotBlockedError, DiscoverResult, SourceType

_log = logging.getLogger(__name__)

_NEWS_TAB_URL = "https://duckduckgo.com/"
_NEWS_API_URL = "https://duckduckgo.com/news.js"

_REGION = "vn-vi"  # 베트남 / 베트남어

_VQD_RE = re.compile(r'vqd="([\d-]+)"')

# df 파라미터: d=1일, w=1주, m=1개월
_DEFAULT_PERIOD   = "d"
_DEFAULT_DELAY_MS = 1000


class DuckDuckGoNewsAdapter(PaginatedAdapter):
    source_type: str = SourceType.DUCKDUCKGO_NEWS

    def __init__(
        self,
        period: str    = _DEFAULT_PERIOD,
        max_pages: int | None = None,
        delay_ms: int  = _DEFAULT_DELAY_MS,
    ) -> None:
        from app import config
        super().__init__(period, max_pages or config.DUCKDUCKGO_MAX_PAGES, delay_ms)
        # df 로 결과 풀이 좁을 때 DDG가 다음 페이지에 같은 항목을 반복 반환하는 경우가 있어
        # 이미 본 URL을 추적해 조기 종료한다. 인스턴스는 키워드마다 재사용되므로
        # discover()에서 cursor=None(새 키워드 시작)마다 초기화한다.
        self._seen_urls: set[str] = set()

    def discover(self, keyword: str, cursor: str | None) -> DiscoverResult:
        if cursor is None:
            # 어댑터 인스턴스는 워커 루프에서 키워드마다 재사용되므로(dispatcher.py 참고),
            # cursor=None(새 키워드 발견 시작)마다 초기화해야 이전 키워드의 URL이
            # 이번 키워드의 결과를 오탐 중복으로 걸러내지 않는다.
            self._seen_urls = set()

        page_num, offset, vqd = _split_cursor(cursor)

        if result := self._exceeded(page_num):
            return result

        self._delay(is_first=(page_num == 1))

        with make_client(
            referer="https://duckduckgo.com/",
            extra_headers={"Accept-Language": "vi-VN,vi;q=0.9"},
        ) as client:
            if vqd is None:
                vqd = _fetch_vqd(client, keyword)
                if vqd is None:
                    _log.warning(
                        f"duckduckgo blocked keyword='{keyword}' — vqd 토큰을 찾을 수 없음"
                        f" (차단 또는 페이지 구조 변경)",
                        extra={"component": "adapter"},
                    )
                    raise BotBlockedError(f"duckduckgo_news keyword='{keyword}' — no vqd")

            resp = client.get(_NEWS_API_URL, params={
                "q": keyword, "vqd": vqd, "l": _REGION, "df": self._period,
                "p": "-1", "s": str(offset), "o": "json",
            })
            resp.raise_for_status()

        try:
            data = json.loads(resp.text)
        except json.JSONDecodeError:
            _log.warning(
                f"duckduckgo blocked keyword='{keyword}' page={page_num} — news.js 응답이 JSON이 아님",
                extra={"component": "adapter"},
            )
            raise BotBlockedError(f"duckduckgo_news keyword='{keyword}' page={page_num}")

        page_urls = [r["url"] for r in data.get("results", []) if r.get("url")]
        urls = [u for u in page_urls if u not in self._seen_urls]
        self._seen_urls.update(urls)

        if not page_urls:
            _log.warning(
                f"duckduckgo empty keyword='{keyword}' page={page_num} — 검색 결과 없음",
                extra={"component": "adapter"},
            )

        if page_urls and not urls:
            # 결과 풀이 좁아 DDG가 이전 페이지와 동일한 항목을 반복 반환 — 여기서 소진 처리.
            _log.debug(
                f"duckduckgo exhausted keyword='{keyword}' page={page_num} — 신규 URL 없음(반복 감지)",
                extra={"component": "adapter"},
            )
            return DiscoverResult(urls=[], next_cursor=None, has_more=False)

        next_offset = _next_offset(data.get("next"))
        has_more    = next_offset is not None and page_num < self._max_pages
        next_cursor = f"{page_num + 1}:{next_offset}:{vqd}" if has_more else None

        return DiscoverResult(urls=urls, next_cursor=next_cursor, has_more=has_more)


def _split_cursor(cursor: str | None) -> tuple[int, int, str | None]:
    """cursor("페이지번호:오프셋:vqd")를 (page_num, offset, vqd)로 분리한다. None이면 (1, 0, None)."""
    if not cursor:
        return 1, 0, None
    page_str, offset_str, vqd = cursor.split(":", 2)
    return int(page_str), int(offset_str), (vqd or None)


def _next_offset(next_qs: str | None) -> int | None:
    """news.js 응답의 "next" 쿼리스트링에서 다음 페이지 s(오프셋) 값을 추출한다."""
    if not next_qs:
        return None
    s = parse_qs(urlparse(next_qs).query).get("s", [None])[0]
    return int(s) if s is not None else None


def _fetch_vqd(client, keyword: str) -> str | None:
    """뉴스 탭 페이지에서 쿼리별 vqd 세션 토큰을 추출한다."""
    resp = client.get(_NEWS_TAB_URL, params={"q": keyword, "t": "h_", "ia": "news", "iar": "news"})
    resp.raise_for_status()
    m = _VQD_RE.search(resp.text)
    return m.group(1) if m else None
