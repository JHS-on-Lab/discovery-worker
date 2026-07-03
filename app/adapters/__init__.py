"""어댑터 팩토리 — source_type 문자열로 SourceAdapter 구현체를 반환."""

from __future__ import annotations

from app.ports import SourceAdapter


def make_adapter(source_type: str) -> SourceAdapter:
    pt = source_type.upper()
    if pt == "NAVER_NEWS":
        from app.adapters.naver_news import NaverNewsAdapter
        return NaverNewsAdapter()
    if pt == "DAUM_NEWS":
        from app.adapters.daum_news import DaumNewsAdapter
        return DaumNewsAdapter()
    if pt == "GOOGLE_NEWS":
        from app.adapters.google_news import UCGoogleNewsAdapter
        return UCGoogleNewsAdapter()
    if pt == "BAIDU_NEWS":
        from app.adapters.baidu_news import BaiduNewsAdapter
        return BaiduNewsAdapter()
    if pt == "NAVER_STOCK":
        from app.adapters.naver_stock import NaverStockAdapter
        return NaverStockAdapter()
    if pt == "DUCKDUCKGO_NEWS":
        from app.adapters.duckduckgo_news import DuckDuckGoNewsAdapter
        return DuckDuckGoNewsAdapter()
    raise ValueError(f"알 수 없는 source_type: {source_type}")
