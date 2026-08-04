"""어댑터 팩토리 — source_type 문자열로 SourceAdapter 구현체를 반환."""

from __future__ import annotations

from app.ports import SourceAdapter


def make_adapter(source_type: str, max_pages: int | None = None) -> SourceAdapter:
    """source_type 에 맞는 어댑터를 생성한다. max_pages 를 넘기면 어댑터 기본값
    (config.*_MAX_PAGES) 대신 그 값을 쓴다 — scripts/run_discovery.py 의 CLI
    오버라이드 등에서 사용."""
    pt = source_type.upper()
    kwargs = {"max_pages": max_pages} if max_pages else {}
    if pt == "NAVER_NEWS":
        from app.adapters.naver_news import NaverNewsAdapter
        return NaverNewsAdapter(**kwargs)
    if pt == "DAUM_NEWS":
        from app.adapters.daum_news import DaumNewsAdapter
        return DaumNewsAdapter(**kwargs)
    if pt == "GOOGLE_NEWS":
        from app.adapters.google_news import UCGoogleNewsAdapter
        return UCGoogleNewsAdapter(**kwargs)
    if pt == "BAIDU_NEWS":
        from app.adapters.baidu_news import BaiduNewsAdapter
        return BaiduNewsAdapter(**kwargs)
    if pt == "NAVER_STOCK":
        from app.adapters.naver_stock import NaverStockAdapter
        return NaverStockAdapter(**kwargs)
    if pt == "DUCKDUCKGO_NEWS":
        from app.adapters.duckduckgo_news import DuckDuckGoNewsAdapter
        return DuckDuckGoNewsAdapter(**kwargs)
    if pt == "BAOMOI_NEWS":
        from app.adapters.baomoi_news import BaomoiNewsAdapter
        return BaomoiNewsAdapter(**kwargs)
    if pt == "TINHTE_FORUM":
        from app.adapters.tinhte_forum import TinhteForumAdapter
        return TinhteForumAdapter(**kwargs)
    raise ValueError(f"알 수 없는 source_type: {source_type}")
