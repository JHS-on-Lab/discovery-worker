"""
Solr 싱크 — Article 을 Solr 에 upsert 한다.

url_hash 를 Solr 문서 id 로 사용한다 (같은 URL 을 다시 넣어도 안전하게 덮어써짐).

설정 (.env):
  SINK_TYPE=solr
  SOLR_URL=http://localhost:8983/solr/news
  SOLR_BATCH_SIZE=100  (선택, 기본 100)

Solr 스키마에 다음 필드가 필요하다:
  id, title, body, portal_type, keyword, url,
  author, press, published_at, collected_at, extraction_method, body_len
"""

from __future__ import annotations

import dataclasses
import json

import httpx

from app import config
from app.types import Article


class SolrSink:
    """Article 을 Solr 코어에 JSON 으로 upsert 한다."""

    def __init__(self) -> None:
        self._url        = config.SOLR_URL.rstrip("/")
        self._batch_size = config.SOLR_BATCH_SIZE
        self._buffer: list[dict] = []

        if not self._url:
            raise ValueError("SOLR_URL 이 설정되지 않았습니다. .env 에 SOLR_URL 을 추가하세요.")

    def write(self, article: Article) -> None:
        """Article 을 버퍼에 추가하고 batch_size 에 도달하면 Solr 에 전송한다."""
        self._buffer.append(_to_solr_doc(article))
        if len(self._buffer) >= self._batch_size:
            self.flush()

    def flush(self) -> None:
        """버퍼의 모든 문서를 Solr 에 전송하고 커밋한다."""
        if not self._buffer:
            return
        resp = httpx.post(
            f"{self._url}/update",
            params={"commit": "true"},
            content=json.dumps(self._buffer, ensure_ascii=False, default=str),
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        self._buffer.clear()

    # 컨텍스트 매니저로 사용하면 with 블록 종료 시 남은 버퍼가 자동 flush 된다.
    def __enter__(self) -> "SolrSink":
        return self

    def __exit__(self, *_) -> None:
        self.flush()


def _to_solr_doc(article: Article) -> dict:
    """Article 을 Solr 문서 dict 로 변환한다."""
    d = dataclasses.asdict(article)
    d["id"] = d.pop("url_hash")  # url_hash → Solr 문서 id

    if d.get("published_at") is not None:
        d["published_at"] = d["published_at"].isoformat() + "Z"
    if d.get("collected_at") is not None:
        d["collected_at"] = d["collected_at"].isoformat() + "Z"

    return d
