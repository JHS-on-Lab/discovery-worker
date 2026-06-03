"""
정적 HTTP Fetcher.

FetchResult 를 반환하며 예외를 던지지 않는다.
네트워크 오류는 status_code=-1 로 표현해 호출자가 failure_classifier 로 분류한다.
"""

from __future__ import annotations

import time

import httpx

from app.fetch._client import make_client
from app.types import FetchResult, RenderMode


class HttpFetcher:
    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    def fetch(self, url: str) -> FetchResult:
        """
        URL 을 GET 으로 가져와 FetchResult 반환.
        - 리다이렉트 자동 추적 (구글 RSS 중간 URL 처리)
        - HTTP 오류(4xx/5xx)는 예외 없이 FetchResult(status_code=N, html="") 반환
        - 네트워크 오류(timeout, connect)는 재raise — 호출자가 classify_exception 으로 처리
        """
        start = time.monotonic()
        with make_client(timeout=self._timeout) as client:
            resp = client.get(url)

        elapsed_ms = (time.monotonic() - start) * 1000
        html = "" if resp.status_code >= 400 else resp.text

        return FetchResult(
            url=str(resp.url),          # 리다이렉트 최종 URL
            html=html,
            status_code=resp.status_code,
            render_mode=RenderMode.STATIC,
            elapsed_ms=elapsed_ms,
        )
