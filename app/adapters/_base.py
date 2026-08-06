"""
페이지 단위로 검색 결과를 가져오는 어댑터의 공통 베이스.

period / max_pages / delay_ms 초기화, 페이지 한도 체크, 페이지 간 딜레이를
제공한다.
"""

from __future__ import annotations

import logging
import time

from app.types import DiscoverResult


def page_limit_exceeded(page_num: int, max_pages: int) -> bool:
    """공용 페이지 상한 체크. PaginatedAdapter._exceeded() 와, jitter 지연을 써서
    이 베이스를 상속하지 않는 google_news/baidu_news 양쪽에서 공유한다."""
    return page_num > max_pages


def is_own_host(netloc: str, own_hosts: set[str] | tuple[str, ...]) -> bool:
    """netloc 이 검색엔진 자체 도메인(그 서브도메인 포함)인지 확인한다.
    결과 링크에서 검색엔진 자체 UI/도움말 페이지를 걸러낼 때 쓴다. 단순
    부분 문자열 매칭("google.com" in netloc)은 "notgoogle.com" 같은 무관한
    도메인도 오탐할 수 있어 host 전체 일치 또는 ".{own_host}" 접미사로만
    판정한다."""
    host = netloc.lower()
    return any(host == h or host.endswith("." + h) for h in own_hosts)


def log_empty_or_blocked(
    logger: logging.Logger,
    source: str,
    keyword: str,
    page: int,
    is_genuine_empty: bool,
    block_reason: str,
) -> None:
    """빈 결과일 때 "진짜 검색 결과 없음"과 "차단/셀렉터 파손 의심"을 구분해 로그를
    남긴다. BotBlockedError 를 던질지는 소스마다 다르므로(어떤 소스는 차단 신호가
    불확실해 경고만 남기고 넘어간다 — docs/adapter-catalog.md "4. 새 어댑터 만들 때
    체크리스트" 5번 참고) 여기서는 판단하지 않고 로깅만 담당한다."""
    if is_genuine_empty:
        logger.debug(
            f"{source} empty keyword='{keyword}' page={page} — 검색 결과 없음",
            extra={"component": "adapter"},
        )
    else:
        logger.warning(
            f"{source} blocked keyword='{keyword}' page={page} — {block_reason}",
            extra={"component": "adapter"},
        )


class PaginatedAdapter:
    """max_pages / delay_ms 를 가지는 어댑터의 공통 베이스."""

    def __init__(self, period: str, max_pages: int, delay_ms: int) -> None:
        self._period    = period
        self._max_pages = max_pages
        self._delay_ms  = delay_ms

    def _exceeded(self, page_num: int) -> DiscoverResult | None:
        """max_pages 초과 시 빈 결과 반환, 아니면 None."""
        if page_limit_exceeded(page_num, self._max_pages):
            return DiscoverResult(urls=[], next_cursor=None, has_more=False)
        return None

    def _delay(self, is_first: bool) -> None:
        """첫 페이지가 아닐 때 딜레이를 적용한다."""
        if not is_first:
            time.sleep(self._delay_ms / 1000)
