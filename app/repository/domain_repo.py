"""
domain 테이블 조회 전용 접근.

t_domain.excluded 는 해당 host 를 수집 파이프라인에서 완전히 제외한다는 의미다.
discovery 단계에서 걸러내면 extraction-worker 까지 URL 이 넘어가지 않아
가장 비용이 큰 fetch/렌더링 시도 자체를 막을 수 있다.
"""

from __future__ import annotations

from sqlalchemy import Engine, bindparam, text


class DomainRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_excluded_hosts(self, hosts: list[str]) -> set[str]:
        """주어진 host 목록 중 excluded=1 인 것만 골라 반환한다."""
        if not hosts:
            return set()

        stmt = text(
            "SELECT host FROM t_domain WHERE excluded = 1 AND host IN :hosts"
        ).bindparams(bindparam("hosts", expanding=True))

        with self._engine.begin() as conn:
            rows = conn.execute(stmt, {"hosts": list(set(hosts))}).fetchall()

        return {row.host for row in rows}
