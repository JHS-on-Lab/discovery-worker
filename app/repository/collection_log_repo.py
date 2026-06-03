"""
collection_log 테이블 접근 — 발견·추출 실행 이력 기록.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Engine, text


@dataclass
class DiscoveryLog:
    keyword_id:    int
    portal_type:   str
    worker_id:     str
    started_at:    datetime
    duration_ms:   int
    urls_found:    int
    urls_inserted: int
    urls_skipped:  int
    error_msg:     str | None = None


@dataclass
class ExtractionLog:
    portal_type:    str
    worker_id:      str
    started_at:     datetime
    duration_ms:    int
    urls_attempted: int
    urls_success:   int
    urls_failed:    int


class CollectionLogRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def insert_discovery(self, log: DiscoveryLog) -> None:
        run_date = log.started_at.astimezone(timezone.utc).date()
        with self._engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO collection_log
                        (run_type, run_date, keyword_id, portal_type, worker_id,
                         started_at, duration_ms,
                         urls_found, urls_inserted, urls_skipped,
                         error_msg)
                    VALUES
                        ('discovery', :run_date, :kid, :portal, :worker,
                         :started_at, :duration_ms,
                         :urls_found, :urls_inserted, :urls_skipped,
                         :error_msg)
                """),
                {
                    "run_date":      run_date,
                    "kid":           log.keyword_id,
                    "portal":        log.portal_type,
                    "worker":        log.worker_id,
                    "started_at":    log.started_at,
                    "duration_ms":   log.duration_ms,
                    "urls_found":    log.urls_found,
                    "urls_inserted": log.urls_inserted,
                    "urls_skipped":  log.urls_skipped,
                    "error_msg":     log.error_msg,
                },
            )

    def insert_extraction(self, log: ExtractionLog) -> None:
        run_date = log.started_at.astimezone(timezone.utc).date()
        with self._engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO collection_log
                        (run_type, run_date, portal_type, worker_id,
                         started_at, duration_ms,
                         urls_attempted, urls_success, urls_failed)
                    VALUES
                        ('extraction', :run_date, :portal, :worker,
                         :started_at, :duration_ms,
                         :urls_attempted, :urls_success, :urls_failed)
                """),
                {
                    "run_date":      run_date,
                    "portal":        log.portal_type,
                    "worker":        log.worker_id,
                    "started_at":    log.started_at,
                    "duration_ms":   log.duration_ms,
                    "urls_attempted": log.urls_attempted,
                    "urls_success":   log.urls_success,
                    "urls_failed":    log.urls_failed,
                },
            )

    def count_today_403(self, keyword_id: int) -> int:
        """오늘(UTC) 해당 키워드의 403 실패 횟수를 반환한다."""
        with self._engine.connect() as conn:
            return conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM collection_log
                    WHERE keyword_id = :kid
                      AND error_msg LIKE '%403%'
                      AND run_date = CURDATE()
                """),
                {"kid": keyword_id},
            ).scalar() or 0

    def daily_summary(self, run_date: str | None = None) -> list[dict]:
        """일자별 요약. run_date=None이면 오늘(KST)."""
        date = run_date or datetime.now(timezone.utc).date().isoformat()
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        cl.run_type,
                        cl.portal_type,
                        k.keyword,
                        cl.started_at,
                        cl.duration_ms,
                        cl.urls_found,
                        cl.urls_inserted,
                        cl.urls_skipped,
                        cl.urls_attempted,
                        cl.urls_success,
                        cl.urls_failed
                    FROM collection_log cl
                    LEFT JOIN keyword k ON k.id = cl.keyword_id
                    WHERE cl.run_date = :date
                    ORDER BY cl.started_at
                """),
                {"date": date},
            ).fetchall()
        return [dict(r._mapping) for r in rows]
