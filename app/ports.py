"""
포트(Port) 인터페이스.

모든 구현체는 여기 정의된 Protocol을 만족해야 한다.
구현체끼리는 서로를 직접 임포트하지 않고 이 포트를 통해서만 소통한다.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.types import DiscoverResult


@runtime_checkable
class SourceAdapter(Protocol):
    """
    소스별 발견 어댑터.
    검색 결과 페이지를 스크래핑해 콘텐츠 URL 목록과 다음 cursor를 반환한다.
    본문은 건드리지 않는다.
    """
    source_type: str

    def discover(self, keyword: str, cursor: str | None) -> DiscoverResult:
        """
        keyword를 검색해 콘텐츠 URL 목록을 반환.
        cursor: 이전 호출의 next_cursor (첫 호출은 None).
        """
        ...
