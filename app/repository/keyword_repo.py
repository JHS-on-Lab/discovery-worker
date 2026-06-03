"""
keyword 테이블 접근.

keyword 는 수집 스케줄을 담당한다.
next_discover_at 이 현재 시각보다 과거이면 "수집할 때가 됐다"는 뜻이다.

claim_next() 의 동작 원리:
  1. next_discover_at <= NOW() 인 키워드를 FOR UPDATE SKIP LOCKED 로 잠근다.
     → 다른 워커가 동시에 같은 키워드를 가져가는 것을 막는다.
  2. 잠그는 즉시, 같은 트랜잭션 안에서 next_discover_at 을 24시간 뒤로 밀어둔다.
     → 트랜잭션이 끝난 뒤에도 다른 워커가 다시 집어가지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Engine, text


class KeywordRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def claim_next(self, portal: str, worker_id: str) -> dict | None:
        """
        due 상태(enabled + next_discover_at <= NOW())인 키워드를
        SKIP LOCKED로 원자적으로 점유하고 next_discover_at을 즉시 갱신한다.

        반환: {id, keyword, portal_type, interval_seconds} 또는 None(없으면)
        """
        portal_filter = "" if portal.upper() == "ALL" else "AND portal_type = :portal"

        with self._engine.begin() as conn:
            row = conn.execute(
                text(f"""
                    SELECT id, keyword, portal_type, interval_seconds, last_cursor
                    FROM keyword
                    WHERE enabled = true
                      AND (next_discover_at IS NULL OR next_discover_at <= NOW())
                      {portal_filter}
                    ORDER BY priority DESC, next_discover_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                """),
                {"portal": portal.upper()},
            ).fetchone()

            if row is None:
                return None

            kw = dict(row._mapping)

            # 즉시 next_discover_at 갱신 → 다른 워커가 재점유 불가
            conn.execute(
                text("""
                    UPDATE keyword
                    SET next_discover_at = NOW() + INTERVAL :sec SECOND
                    WHERE id = :kid
                """),
                {"sec": kw["interval_seconds"], "kid": kw["id"]},
            )

        return kw

    def reschedule(self, keyword_id: int, next_at: datetime) -> None:
        """next_discover_at 을 지정 시각으로 갱신한다. 403 재시도 등에 사용."""
        with self._engine.begin() as conn:
            conn.execute(
                text("UPDATE keyword SET next_discover_at = :next_at WHERE id = :kid"),
                {"next_at": next_at, "kid": keyword_id},
            )

    def set_cursor(self, keyword_id: int, cursor: str | None) -> None:
        """last_cursor 를 갱신한다.
        - 403 실패 시: 실패한 cursor 저장 → 재시도 시 해당 페이지부터 재개
        - 성공 완료 시: None 으로 리셋 → 다음 수집은 첫 페이지부터
        """
        with self._engine.begin() as conn:
            conn.execute(
                text("UPDATE keyword SET last_cursor = :cursor WHERE id = :kid"),
                {"cursor": cursor, "kid": keyword_id},
            )

    def list_all(self, portal: str = "ALL") -> list[dict]:
        """전체 키워드 목록 조회 (운영 확인용)."""
        portal_filter = "" if portal.upper() == "ALL" else "WHERE k.portal_type = :portal"
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(f"""
                    SELECT k.id, k.keyword, k.display_name, k.portal_type,
                           k.enabled, k.disabled_reason,
                           k.next_discover_at, k.priority,
                           MAX(CASE WHEN cl.error_msg IS NULL THEN cl.started_at END) AS last_discovered_at
                    FROM keyword k
                    LEFT JOIN collection_log cl
                           ON cl.keyword_id = k.id AND cl.run_type = 'discovery'
                    {portal_filter}
                    GROUP BY k.id
                    ORDER BY k.portal_type, k.keyword
                """),
                {"portal": portal.upper()},
            ).fetchall()
        return [dict(r._mapping) for r in rows]
