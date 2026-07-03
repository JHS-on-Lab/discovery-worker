"""
keyword 테이블 접근.

keyword 는 수집 스케줄을 담당한다.
next_discover_at 이 현재 시각보다 과거이면 "수집할 때가 됐다"는 뜻이다.

claim_next() 의 동작 원리 (낙관적 클레임, MariaDB 10.5 호환 — SKIP LOCKED 미지원):
  1. next_discover_at <= NOW() 인 후보를 잠금 없이 조회한다.
  2. 각 후보에 대해 UPDATE ... WHERE 조건(원래 상태 재확인)으로 선점을 시도하고 rowcount 를 확인한다.
     → rowcount=1 이면 이 워커가 점유 성공, 0 이면 다른 워커가 이미 가져간 것이므로 다음 후보로 넘어간다.
  3. 점유 성공 시, 같은 UPDATE 안에서 next_discover_at 을 24시간 뒤로 밀어둔다.
     → 다른 워커가 다시 집어가지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Engine, text


class KeywordRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def claim_next(self, source: str, worker_id: str) -> dict | None:
        """
        due 상태(enabled + next_discover_at <= NOW())인 키워드를 원자적으로 점유한다.

        낙관적 클레임 패턴 (MariaDB 10.5 호환):
          1. 후보 N개를 조회 (잠금 없음)
          2. 각 후보에 대해 UPDATE WHERE 조건으로 선점 시도
          3. rowcount=1 → 내가 가져간 것 / rowcount=0 → 다른 워커가 먼저 가져간 것 → 다음 후보 시도

        반환: {id, keyword, source_type, interval_seconds} 또는 None(없으면)
        """
        source_filter = "" if source.upper() == "ALL" else "AND source_type = :source"

        with self._engine.begin() as conn:
            rows = conn.execute(
                text(f"""
                    SELECT id, keyword, source_type, interval_seconds, retry_pending
                    FROM t_keyword
                    WHERE enabled = true
                      AND (next_discover_at IS NULL OR next_discover_at <= NOW())
                      {source_filter}
                    ORDER BY priority DESC, next_discover_at ASC
                    LIMIT 20
                """),
                {"source": source.upper()},
            ).fetchall()

            for row in rows:
                kw = dict(row._mapping)
                result = conn.execute(
                    text("""
                        UPDATE t_keyword
                        SET next_discover_at = NOW() + INTERVAL :sec SECOND
                        WHERE id = :kid
                          AND enabled = true
                          AND (next_discover_at IS NULL OR next_discover_at <= NOW())
                    """),
                    {"sec": kw["interval_seconds"], "kid": kw["id"]},
                )
                if result.rowcount == 1:
                    return kw

        return None

    def reschedule(self, keyword_id: int, next_at: datetime) -> None:
        """next_discover_at 을 지정 시각으로 갱신한다. 403 재시도 등에 사용."""
        with self._engine.begin() as conn:
            conn.execute(
                text("UPDATE t_keyword SET next_discover_at = :next_at WHERE id = :kid"),
                {"next_at": next_at, "kid": keyword_id},
            )

    def set_retry_pending(self, keyword_id: int, pending: bool) -> None:
        """retry_pending 을 갱신한다.
        - 수집 중단(403 등) 시: True → 다음 수집은 full scan 모드
        - 성공 완료 시: False → 다음 수집은 early-stop 포함 정상 모드
        """
        with self._engine.begin() as conn:
            conn.execute(
                text("UPDATE t_keyword SET retry_pending = :pending WHERE id = :kid"),
                {"pending": int(pending), "kid": keyword_id},
            )

    def list_all(self, source: str = "ALL") -> list[dict]:
        """전체 키워드 목록 조회 (운영 확인용)."""
        source_filter = "" if source.upper() == "ALL" else "WHERE k.source_type = :source"
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(f"""
                    SELECT k.id, k.keyword, k.display_name, k.source_type,
                           k.enabled, k.disabled_reason,
                           k.next_discover_at, k.priority,
                           MAX(CASE WHEN cl.error_msg IS NULL THEN cl.started_at END) AS last_discovered_at
                    FROM t_keyword k
                    LEFT JOIN t_collection_log cl
                           ON cl.keyword_id = k.id AND cl.run_type = 'discovery'
                    {source_filter}
                    GROUP BY k.id
                    ORDER BY k.source_type, k.keyword
                """),
                {"source": source.upper()},
            ).fetchall()
        return [dict(r._mapping) for r in rows]
