"""
Solr 더미 데이터 투입 테스트 스크립트.

SolrSink 를 통해 CollectedContent 더미 데이터를 Solr 에 저장하고
실제 문서가 인덱싱됐는지 확인한다.

사용법:
  python scripts/test_solr_sink.py

환경변수 (.env 또는 실제 환경변수):
  SINK_TYPE=solr
  SOLR_DIRECT_ENABLED=true
  SOLR_URL=http://localhost:8983/solr/<core>
  SOLR_CRAWLER_TYPE=test_crawler      (선택, 기본 "test")
  SOLR_RUNTIME_NAME=test              (선택)
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 프로젝트 루트를 sys.path 에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from app import config
from app.domain_logic.url_normalizer import normalize, url_hash
from app.sink import make_sink
from app.repository.db import db_context
from app.types import CollectedContent

KST = timezone(timedelta(hours=9))

_DUMMY_ITEMS = [
    {
        "url":        "https://example.com/post/1",
        "source_type": "DAUM_NEWS",
        "keyword":    "테스트",
        "keyword_id": 1,
        "title":      "테스트 문서 1",
        "body":       "이것은 Solr 싱크 테스트를 위한 더미 본문입니다. " * 10,
        "author":     "테스터",
    },
    {
        "url":        "https://example.com/post/2",
        "source_type": "NAVER_NEWS",
        "keyword":    "키워드",
        "keyword_id": 2,
        "title":      "테스트 문서 2",
        "body":       "두 번째 더미 콘텐츠입니다. Solr 인덱싱을 검증합니다. " * 10,
        "author":     None,
    },
    {
        "url":        "https://example.com/post/3",
        "source_type": "GOOGLE_NEWS",
        "keyword":    "검색어",
        "keyword_id": None,
        "title":      "테스트 문서 3 — keyword_id 없음",
        "body":       "keyword_id 가 None 인 경우를 검증합니다. " * 10,
        "author":     None,
    },
]


def _make_content(item: dict) -> CollectedContent:
    norm = normalize(item["url"])
    return CollectedContent(
        url=norm,
        url_hash=url_hash(norm),
        source_type=item["source_type"],
        keyword=item["keyword"],
        keyword_id=item["keyword_id"],
        title=item["title"],
        body=item["body"],
        published_at=None,
        author=item["author"],
        collected_at=datetime.now(KST),
        extraction_method="test",
    )


def _verify(solr_url: str, url_hashes: list[str]) -> None:
    ids = " OR ".join(url_hashes)
    resp = httpx.get(
        f"{solr_url.rstrip('/')}/select",
        params={"q": f"id:({ids})", "fl": "id,title,crawler_type,keyword_id", "wt": "json"},
        timeout=10,
    )
    resp.raise_for_status()
    docs = resp.json()["response"]["docs"]
    print(f"\n[검증] 조회된 문서 수: {len(docs)} / {len(url_hashes)}")
    for doc in docs:
        print(f"  id={doc['id'][:16]}  title={doc.get('title','')[:30]}  "
              f"crawler_type={doc.get('crawler_type')}  keyword_id={doc.get('keyword_id')}")


def main() -> None:
    config.validate()

    contents = [_make_content(item) for item in _DUMMY_ITEMS]

    with db_context() as engine:
        sink = make_sink(engine)

    print(f"[투입] {len(contents)}건 → Solr")
    for content in contents:
        sink.write(content)
    sink.flush()
    print("[완료] flush 성공")

    if config.SOLR_DIRECT_ENABLED and config.SOLR_URL:
        _verify(config.SOLR_URL, [c.url_hash for c in contents])


if __name__ == "__main__":
    main()
