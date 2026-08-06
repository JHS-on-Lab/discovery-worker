"""
Báo Mới(baomoi.com, 베트남 뉴스 애그리게이터) 발견 어댑터.

전략 (docs/adapter-catalog.md 참고):
  baomoi.com/tim-kiem/{keyword}.epi 로 검색 결과 HTML을 스크랩한다.
  - 순수 HTTP로 접근 가능(Chrome 불필요). 봇 차단 신호는 아직 미검증.
  - 페이지네이션: 1페이지는 /tim-kiem/{keyword}.epi, 2페이지부터
    /tim-kiem/{keyword}/trang{N}.epi ("trang" = 페이지).
  - 결과는 .bm-card 컨테이너 단위 — 그 안의 <a href="...-c{id}.epi">가 기사 링크
    (태그/발행사 링크는 이 패턴이 아님), <time datetime="...+07:00">이 발행 시각(ISO
    8601, 베트남 시간대). 최신순으로 이미 정렬돼 있다.
  - 빈 결과: .bm-card 0개 + "không tìm thấy"(결과 없음) 문구 포함 → 진짜 빈 결과.

미검증 상태(운영 중 계속 확인 필요):
  - 봇 차단 시 실제로 어떤 신호(리다이렉트/캡차/다른 페이지 구조)가 뜨는지 아직 못 봤다.
  - 페이지당 결과 수가 불규칙(관찰된 범위 7~11건) — has_more 판단은 정확한 개수
    임계값이 아니라 "이 페이지에 결과가 있었는가"로 처리한다.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from selectolax.parser import HTMLParser

from app import config
from app.adapters._base import PaginatedAdapter
from app.fetch._client import make_client
from app.types import DiscoverResult, SourceType

_log = logging.getLogger(__name__)

_BASE_URL = "https://baomoi.com"

_ARTICLE_HREF_RE = re.compile(r"-c\d+\.epi$")

_DEFAULT_DELAY_MS = 800
_CUTOFF_DAYS = 1  # 최근 1일 — 다른 어댑터(naver "1일"/daum "d"/google tbs=qdr:d)와 동일 관례


class BaomoiNewsAdapter(PaginatedAdapter):
    source_type: str = SourceType.BAOMOI_NEWS

    def __init__(
        self,
        max_pages: int | None = None,
        delay_ms: int = _DEFAULT_DELAY_MS,
    ) -> None:
        super().__init__(period="", max_pages=max_pages or config.BAOMOI_MAX_PAGES, delay_ms=delay_ms)

    def discover(self, keyword: str, cursor: str | None) -> DiscoverResult:
        page = int(cursor) if cursor else 1

        if result := self._exceeded(page):
            return result

        self._delay(is_first=(page == 1))

        url = f"{_BASE_URL}/tim-kiem/{keyword}.epi" if page == 1 else f"{_BASE_URL}/tim-kiem/{keyword}/trang{page}.epi"

        with make_client(extra_headers={"Accept-Language": "vi-VN,vi;q=0.9"}) as client:
            resp = client.get(url)
            resp.raise_for_status()

        cards = _parse_cards(resp.text)

        if not cards:
            if _is_genuine_empty(resp.text):
                _log.debug(
                    f"baomoi empty keyword='{keyword}' page={page} — 검색 결과 없음",
                    extra={"component": "adapter"},
                )
            else:
                _log.warning(
                    f"baomoi no urls extracted keyword='{keyword}' page={page} "
                    f"— bot detection or .bm-card selector change",
                    extra={"component": "adapter"},
                )
            return DiscoverResult(urls=[], next_cursor=None, has_more=False)

        urls, cutoff_hit = _apply_cutoff(cards)

        has_more = (not cutoff_hit) and page < self._max_pages
        next_cursor = str(page + 1) if has_more else None

        return DiscoverResult(urls=urls, next_cursor=next_cursor, has_more=has_more)


def _is_genuine_empty(html: str) -> bool:
    """.bm-card 가 0개일 때, 진짜 "검색 결과 없음"인지(vs 봇 차단/셀렉터 파손 의심)
    구분한다. "không tìm thấy"(결과를 찾을 수 없습니다) 문구 포함 여부로 판단한다.
    봇 차단 시 실제로 어떤 페이지가 뜨는지는 아직 못 봐서(§미검증), 이 신호가
    없다고 바로 BotBlockedError로 단정하지 않고 경고만 남긴다(baidu_news.py와
    동일한 보수적 처리)."""
    return "không tìm thấy" in html.lower()


def _parse_cards(html: str) -> list[tuple[str, str]]:
    """.bm-card 컨테이너에서 (기사 URL, datetime 원본 문자열) 쌍을 추출한다.

    기사 링크는 -c{id}.epi 패턴만(태그/발행사 링크 제외). datetime 이 없으면
    빈 문자열로 남겨 fail-open(컷오프 판단 없이 그대로 포함, google_news RSS의
    pubDate 파싱 실패 처리와 동일 철학)."""
    tree = HTMLParser(html)
    seen: set[str] = set()
    cards: list[tuple[str, str]] = []

    for card in tree.css(".bm-card"):
        a = card.css_first("a[href]")
        if a is None:
            continue
        href = a.attributes.get("href", "")
        if not href or not _ARTICLE_HREF_RE.search(href):
            continue
        full_url = href if href.startswith("http") else f"{_BASE_URL}{href}"
        if full_url in seen:
            continue
        seen.add(full_url)

        time_el = card.css_first("time[datetime]")
        dt_str = (time_el.attributes.get("datetime") or "") if time_el else ""
        cards.append((full_url, dt_str))

    return cards


def _apply_cutoff(cards: list[tuple[str, str]]) -> tuple[list[str], bool]:
    """결과가 최신순으로 정렬돼 있다는 전제로, cutoff_days 보다 오래된 첫 항목을
    만나면 그 뒤(이번 페이지 나머지 + 이후 페이지 전부)를 잘라낸다.

    반환: (컷오프 이내 URL 목록, cutoff_hit) — cutoff_hit=True 면 이 페이지에서
    이미 기간을 벗어난 걸 만났다는 뜻이라 호출부가 has_more=False 로 강제한다.
    datetime 파싱 실패(빈 문자열/형식 오류)는 컷오프 판단을 못 하므로 포함시킨다
    (fail-open) — 정렬 신뢰도가 깨졌다는 신호는 아니므로 뒤 항목도 계속 확인한다.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=_CUTOFF_DAYS)
    urls: list[str] = []

    for url, dt_str in cards:
        if not dt_str:
            urls.append(url)
            continue
        try:
            published = datetime.fromisoformat(dt_str)
        except ValueError:
            urls.append(url)
            continue
        if published < cutoff:
            return urls, True
        urls.append(url)

    return urls, False
