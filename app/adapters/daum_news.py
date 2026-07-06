"""
다음 뉴스 발견 어댑터.

전략:
  search.daum.net/search?w=news&sort=recency&period=d&p=N 으로 풀 HTML 반복 요청.
  - p 파라미터로 페이지네이션 (1, 2, 3, ...)
  - SHOW_DNS 쿠키: 0=전체(기본), 1=뉴스제휴 언론사만. DAUM_NEWS_ALL 환경변수로 제어.
  - 콘텐츠 링크 두 종류:
      v.daum.net/v/{id}              — 제휴 언론사 (Daum 뷰어)
      cp.news.search.daum.net/p/{id} — 비제휴 언론사 (리다이렉트 → 실제 콘텐츠)
  - period 파라미터: d=1일, w=1주, m=1개월

리다이렉트 해석(cp.news.search.daum.net):
  extraction-worker 의 domain rule 조회는 fetch 이전, t_crawl_url 에 저장된
  원본 host 기준으로 render_mode 를 이미 결정해버린다. cp.news.search.daum.net
  URL 을 그대로 저장하면 httpx 가 리다이렉트는 따라가도(fetch 자체는 성공)
  최종 목적지 도메인의 domain rule(예: headless 필요 여부)은 절대 적용될 수
  없다 — 이미 늦었기 때문. 그래서 발견 단계에서 미리 실제 목적지로 해석해
  저장한다. HEAD 요청은 이 서비스에서 보안 경고 페이지로 리다이렉트되는 등
  신뢰할 수 없어(관찰됨) GET 을 사용한다.

커서: 페이지 번호 (1→2→3→...). None이면 첫 페이지.
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from selectolax.parser import HTMLParser

from app import config
from app.adapters._base import PaginatedAdapter
from app.fetch._client import make_client
from app.types import BotBlockedError, DiscoverResult, SourceType

_log = logging.getLogger(__name__)

_SEARCH_URL = "https://search.daum.net/search"

# period 파라미터: d=1일, w=1주, m=1개월
_DEFAULT_PERIOD   = "d"
_DEFAULT_DELAY_MS = 800


class DaumNewsAdapter(PaginatedAdapter):
    source_type: str = SourceType.DAUM_NEWS

    def __init__(
        self,
        period: str    = _DEFAULT_PERIOD,
        max_pages: int | None = None,
        delay_ms: int  = _DEFAULT_DELAY_MS,
    ) -> None:
        super().__init__(period, max_pages or config.DAUM_MAX_PAGES, delay_ms)

    def discover(self, keyword: str, cursor: str | None) -> DiscoverResult:
        page = int(cursor) if cursor else 1

        if result := self._exceeded(page):
            return result

        self._delay(is_first=(page == 1))

        params = {
            "w":      "news",
            "q":      keyword,
            "sort":   "recency",
            "period": self._period,
            "p":      str(page),
        }

        with make_client(referer="https://www.daum.net/") as client:
            client.cookies.set("SHOW_DNS", "0" if config.DAUM_NEWS_ALL else "1", domain="search.daum.net")
            resp = client.get(_SEARCH_URL, params=params)
            resp.raise_for_status()

        urls, is_genuine_empty = _parse_urls(resp.text)

        if not urls and not is_genuine_empty:
            _log.warning(
                f"daum blocked keyword='{keyword}' page={page} — bot detection or tit_main change",
                extra={"component": "adapter"},
            )
            raise BotBlockedError(f"daum_news keyword='{keyword}' page={page}")

        with make_client(referer="https://search.daum.net/") as resolve_client:
            urls = _resolve_cp_redirects(urls, resolve_client)

        has_more    = len(urls) >= 10 and page < self._max_pages
        next_cursor = str(page + 1) if has_more else None

        return DiscoverResult(urls=urls, next_cursor=next_cursor, has_more=has_more)


def _drop_f_param(url: str) -> str:
    """URL 에서 f 파라미터만 제거한다 (?f=o → 언론사 원본 리다이렉트 방지)."""
    p = urlparse(url)
    qs = [(k, v) for k, v in parse_qsl(p.query) if k != "f"]
    return urlunparse(p._replace(query=urlencode(qs)))


def _resolve_cp_redirects(urls: list[str], client) -> list[str]:
    """cp.news.search.daum.net URL 을 실제 언론사 URL 로 미리 해석한다.

    v.daum.net URL 은 이미 최종 목적지이므로 건드리지 않는다.
    해석 실패(네트워크 오류, 리다이렉트 안 됨 등) 시 원본 URL 을 그대로 둔다 —
    최종 목적지를 못 알아냈다고 발견 자체를 실패시키지 않고, extraction 단계의
    자체 재시도에 맡긴다.
    """
    resolved = []
    for url in urls:
        if "cp.news.search.daum.net/p/" not in url:
            resolved.append(url)
            continue
        try:
            resp = client.get(url)
            final = str(resp.url)
        except Exception:
            resolved.append(url)
            continue
        resolved.append(final if final and "cp.news.search.daum.net" not in final else url)
    return resolved


def _parse_urls(html: str) -> tuple[list[str], bool]:
    """a.tit_main 제목 링크에서 콘텐츠 URL 추출. v.daum ?f=o 파라미터 제거.

    반환: (urls, is_genuine_empty)
      is_genuine_empty=True  → 다음이 "검색 결과 없음" 페이지를 정상 반환한 것
      is_genuine_empty=False → 봇 차단 또는 셀렉터 파손 의심
    """
    tree = HTMLParser(html)
    seen: dict[str, None] = {}

    for node in tree.css("a.tit_main[href]"):
        href = node.attributes.get("href", "")
        if not href:
            continue
        if "v.daum.net/v/" in href:
            seen[_drop_f_param(href)] = None
        elif "cp.news.search.daum.net/p/" in href:
            seen[href] = None

    urls = list(seen)
    is_genuine_empty = (not urls) and bool(tree.css_first("p.desc_info"))
    return urls, is_genuine_empty
