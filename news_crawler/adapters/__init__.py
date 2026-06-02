"""어댑터 팩토리 — portal_type 문자열로 SourceAdapter 구현체를 반환."""

from __future__ import annotations

from news_crawler.ports import SourceAdapter


def make_adapter(portal_type: str) -> SourceAdapter:
    pt = portal_type.upper()
    if pt == "NAVER":
        from news_crawler.adapters.naver import NaverAdapter
        return NaverAdapter()
    if pt == "DAUM":
        from news_crawler.adapters.daum import DaumAdapter
        return DaumAdapter()
    if pt == "GOOGLE":
        from news_crawler.adapters.google import UCGoogleAdapter
        return UCGoogleAdapter()
    if pt == "WEIBO":
        from news_crawler.adapters.weibo import WeiboAdapter
        return WeiboAdapter()
    raise ValueError(f"알 수 없는 portal_type: {portal_type}")
