"""
CollectedContent → dict 직렬화 — Solr 스키마 필드명 기준.

FileSink 와 SolrSink 가 동일한 키 이름을 쓰도록 공유한다.

Solr 문서 필드:
  id                — crawl_id(url) (lookup3ycs64 기반 16자 hex)
  crawler_type      — t_crawl_runtime.crawler_type
  crawl_runtime_key — {$HOSTNAME}_{runtime_name}
  host              — URL 의 netloc
  site              — host 와 동일
  url               — 수집 URL
  title             — 제목
  content           — 본문
  author            — 저자 (배열, 값이 있을 때만 포함)
  tstamp            — 수집 시각 (UTC)
  doc_version       — 1 고정
  keyword_id        — t_keyword.id 문자열 변환 (배열, 값이 있을 때만 포함)
  etc_exact1        — "1" 고정
"""

from __future__ import annotations

from datetime import timezone
from urllib.parse import urlparse

from app.domain_logic.url_normalizer import crawl_id
from app.types import CollectedContent

_UTC = timezone.utc


def to_doc(content: CollectedContent, crawler_type: str, crawl_runtime_key: str) -> dict:
    """CollectedContent 을 Solr 스키마 기준 dict 로 변환한다."""
    host = urlparse(content.url).netloc
    tstamp = content.collected_at.astimezone(_UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    doc: dict = {
        "id":                crawl_id(content.url),
        "crawler_type":      crawler_type,
        "crawl_runtime_key": crawl_runtime_key,
        "host":              host,
        "site":              host,
        "url":               content.url,
        "title":             content.title,
        "content":           content.body,
        "tstamp":            tstamp,
        "doc_version":       1,
        "etc_exact1":        "1",
    }

    if content.author:
        doc["author"] = [content.author]

    if content.keyword_id is not None:
        doc["keyword_id"] = [str(content.keyword_id)]

    return doc


# SolrSink 하위 호환용 별칭
to_solr_doc = to_doc
