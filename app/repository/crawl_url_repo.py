"""
crawl_url 테이블 접근.

이 테이블은 수집할 URL 의 큐이자 처리 이력이다.
status 컬럼이 각 URL 의 현재 상태를 나타낸다:

  discovered      → 아직 처리 안 됨 (기본값)
  extracting      → 지금 어떤 워커가 처리 중
  stored          → 본문 추출 완료, JSONL 저장됨
  failed_transient→ 일시 오류로 실패. next_retry_at 이 지나면 자동 재시도
  failed_permanent→ 404 등 영구 오류. 재시도 안 함
  dead            → 재시도 횟수(MAX_ATTEMPTS) 초과. 포기

발견 단계(이 프로젝트 담당): bulk_insert_discovered
추출 단계(claim_next → mark_stored / mark_failed / mark_dead 등)는 extraction-worker 프로젝트 소관.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import Engine, text

from app.domain_logic.url_normalizer import normalize, url_hash

KST = timezone(timedelta(hours=9))


# ON DUPLICATE KEY UPDATE 는 url_hash 가 이미 있으면 아무것도 바꾸지 않는다.
# 중복 URL 을 조용히 무시하기 위한 관용구다.
_INSERT_SQL = text("""
    INSERT INTO t_crawl_url
        (url, url_hash, host, keyword_id, source_type, status,
         attempt_count, is_manual, priority,
         collected_date, created_at, updated_at)
    VALUES
        (:url, :hash, :host, :kid, :source, 'discovered',
         0, false, 0,
         :cdate, :created_at, :created_at)
    ON DUPLICATE KEY UPDATE
        updated_at = updated_at
""")


class CrawlUrlRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ------------------------------------------------------------------
    # 발견 단계
    # ------------------------------------------------------------------

    def bulk_insert_discovered(
        self,
        raw_urls: list[str],
        keyword_id: int,
        source_type: str,
    ) -> tuple[int, int]:
        """
        URL 목록을 discovered 상태로 bulk insert.
        중복(url_hash)은 ON DUPLICATE KEY UPDATE로 조용히 무시.
        반환: (inserted, skipped)
        """
        if not raw_urls:
            return 0, 0

        now = datetime.now(KST)
        rows = []
        for raw in raw_urls:
            norm = normalize(raw)
            rows.append({
                "url":        norm,
                "hash":       url_hash(norm),
                "host":       urlparse(norm).netloc,
                "kid":        keyword_id,
                "source":     source_type,
                "cdate":      now.date(),
                "created_at": now,
            })

        with self._engine.begin() as conn:
            result = conn.execute(_INSERT_SQL, rows)

        inserted = result.rowcount
        return inserted, len(rows) - inserted
