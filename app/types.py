"""
핵심 데이터 타입 — 설계 문서 4절 포트 시그니처 기준.
모든 모듈은 이 타입만 임포트하고 서로를 직접 참조하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# 상수 / Enum
# ---------------------------------------------------------------------------

class SourceType(str, Enum):
    NAVER_NEWS      = "NAVER_NEWS"
    DAUM_NEWS       = "DAUM_NEWS"
    GOOGLE_NEWS     = "GOOGLE_NEWS"
    BAIDU_NEWS      = "BAIDU_NEWS"
    NAVER_STOCK     = "NAVER_STOCK"
    DUCKDUCKGO_NEWS = "DUCKDUCKGO_NEWS"
    BAOMOI_NEWS     = "BAOMOI_NEWS"


class DiscoverMode(str, Enum):
    """발견에 사용된 모드 — 현재는 google_news 전용(다른 소스는 구분 없음)."""
    SEARCH = "search"
    RSS    = "rss"


# ---------------------------------------------------------------------------
# Discovery 결과
# ---------------------------------------------------------------------------

@dataclass
class DiscoverResult:
    urls: list[str]
    next_cursor: str | None     # 다음 페이지/스크롤 커서. None이면 마지막 페이지.
    has_more: bool
    mode: DiscoverMode | None = None  # 기본값이 있어 다른 어댑터는 이 필드를 몰라도 됨
                                       # — DiscoverResult(...) 그대로 동작


class BotBlockedError(Exception):
    """디스커버리 어댑터가 봇 차단을 감지 — dispatcher 가 단기 재시도로 처리."""
