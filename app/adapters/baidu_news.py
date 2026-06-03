"""바이두 뉴스 발견 어댑터 (전략 미확정 — 구현 전 decisions/baidu-discovery.md 먼저 작성)."""

from __future__ import annotations

from app.types import DiscoverResult, PortalType


class BaiduNewsAdapter:
    portal_type: str = PortalType.BAIDU_NEWS

    def discover(self, keyword: str, cursor: str | None) -> DiscoverResult:
        raise NotImplementedError
