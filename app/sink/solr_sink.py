"""
Solr 싱크 — CollectedContent 을 Solr 에 upsert 한다.

url_hash 를 Solr 문서 id 로 사용한다 (같은 URL 을 다시 넣어도 안전하게 덮어써짐).

설정 (.env):
  SINK_TYPE=solr
  SOLR_URL=http://localhost:8983/solr/news
  SOLR_BATCH_SIZE=100         (선택, 기본 100)
  SOLR_COMMIT_WITHIN_MS=5000  (선택, 기본 5000)

SOLR_COMMIT_WITHIN_MS:
  flush 마다 commit=true 를 보내면 다수 컨테이너가 동시에 flush 할 때 하드 커밋이
  직렬화되어 병목이 생긴다. commitWithin 으로 커밋 타이밍을 Solr 에 위임한다.
"""

from __future__ import annotations

import json

import httpx

from app import config
from app.sink.serialize import to_solr_doc
from app.types import CollectedContent


class SolrSink:
    """CollectedContent 을 Solr 코어에 JSON 으로 upsert 한다."""

    def __init__(self, solr_url: str, crawler_type: str, crawl_runtime_key: str) -> None:
        self._url                = solr_url.rstrip("/")
        self._crawler_type       = crawler_type
        self._crawl_runtime_key  = crawl_runtime_key
        self._batch_size         = config.SOLR_BATCH_SIZE
        self._buffer: list[dict] = []

    def write(self, content: CollectedContent) -> None:
        self._buffer.append(
            to_solr_doc(content, self._crawler_type, self._crawl_runtime_key)
        )
        if len(self._buffer) >= self._batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        resp = httpx.post(
            f"{self._url}/update",
            params={"commitWithin": str(config.SOLR_COMMIT_WITHIN_MS)},
            content=json.dumps(self._buffer, ensure_ascii=False, default=str),
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        self._buffer.clear()

    def __enter__(self) -> "SolrSink":
        return self

    def __exit__(self, *_) -> None:
        self.flush()
