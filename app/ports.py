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


@runtime_checkable
class SourceOptionsAware(Protocol):
    """
    t_keyword.source_options_json 오버라이드를 지원하는 어댑터용 선택적 포트.
    구현하는 어댑터만 이 Protocol을 만족한다(현재는 google_news 뿐) — dispatcher 는
    isinstance(adapter, SourceOptionsAware) 로 지원 여부를 확인하고, discover() 호출
    직전에 키워드별 source_options_json 을 전달한다.
    """

    def apply_source_options(self, options: dict | None) -> None:
        """
        이번 키워드의 source_options_json(dict, 없으면 None)을 반영한다.
        같은 어댑터 인스턴스가 여러 키워드를 연속 처리하므로, 매 호출마다 값이
        없으면 이전 키워드의 설정이 새어 들어가지 않도록 기본값으로 리셋해야 한다.
        """
        ...
