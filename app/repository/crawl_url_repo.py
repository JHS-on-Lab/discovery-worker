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

from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy import Engine, bindparam, text

from app.config import KST
from app.domain_logic.url_normalizer import normalize, url_hash
from app.repository.domain_repo import DomainRepo


# ON DUPLICATE KEY UPDATE 는 url_hash 가 이미 있으면 아무것도 바꾸지 않는다.
# 중복 URL 을 조용히 무시하기 위한 관용구다 — 단, rowcount 는 이 판단에 안 쓴다
# (아래 SELECT_EXISTING_HASHES_SQL 참고).
_INSERT_SQL = text("""
    INSERT INTO t_crawl_url
        (url, url_hash, host, keyword_id, source_type, status,
         attempt_count, is_manual, priority,
         collected_date, created_at, updated_at, discovery_mode)
    VALUES
        (:url, :hash, :host, :kid, :source, 'discovered',
         0, false, 0,
         :cdate, :created_at, :created_at, :mode)
    ON DUPLICATE KEY UPDATE
        updated_at = updated_at
""")

# INSERT ... ON DUPLICATE KEY UPDATE 의 rowcount 는 "값이 안 바뀐 duplicate" 케이스를
# 드라이버/DB 엔진에 따라 다르게 보고한다 — dev MySQL 8.4 실측 결과 신규 insert와
# no-op duplicate 둘 다 rowcount=1로 나와 구분이 안 됨(2026-07-29). 그래서 신규/중복
# 판단은 rowcount 대신 INSERT 전에 기존 url_hash 를 직접 조회해서 한다.
_SELECT_EXISTING_HASHES_SQL = text(
    "SELECT url_hash FROM t_crawl_url WHERE url_hash IN :hashes"
).bindparams(bindparam("hashes", expanding=True))


class CrawlUrlRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._domain_repo = DomainRepo(engine)

    # ------------------------------------------------------------------
    # 발견 단계
    # ------------------------------------------------------------------

    def bulk_insert_discovered(
        self,
        raw_urls: list[str],
        keyword_id: int,
        source_type: str,
        mode: str | None = None,
    ) -> tuple[int, int]:
        """
        URL 목록을 discovered 상태로 bulk insert.
        중복(url_hash)은 ON DUPLICATE KEY UPDATE로 조용히 무시.
        t_domain.excluded=1 인 host 는 애초에 insert 대상에서 제외한다.
        mode: 발견에 사용된 모드(google_news 전용: "search"|"rss"). 최초 발견 시점의
        값만 저장되고(ON DUPLICATE KEY UPDATE 대상 아님) 재발견 시 덮어쓰지 않는다.
        반환: (inserted, skipped) — INSERT 전에 기존 url_hash 를 조회해서 직접 구분한다
        (rowcount 기반 판단은 DB 엔진에 따라 신뢰할 수 없어 안 씀. 위 SQL 상수 주석 참고).
        """
        if not raw_urls:
            return 0, 0

        now = datetime.now(KST)
        candidates = []
        for raw in raw_urls:
            norm = normalize(raw)
            candidates.append({
                "url":        norm,
                "hash":       url_hash(norm),
                "host":       urlparse(norm).netloc,
                "kid":        keyword_id,
                "source":     source_type,
                "cdate":      now.date(),
                "created_at": now,
                "mode":       mode,
            })

        excluded_hosts = self._domain_repo.get_excluded_hosts(
            list({row["host"] for row in candidates})
        )
        rows = [row for row in candidates if row["host"] not in excluded_hosts]
        if not rows:
            return 0, len(candidates)

        batch_hashes = {row["hash"] for row in rows}
        with self._engine.begin() as conn:
            existing_before = set(conn.execute(
                _SELECT_EXISTING_HASHES_SQL,
                {"hashes": list(batch_hashes)},
            ).scalars())
            conn.execute(_INSERT_SQL, rows)

        # 신규 = 이전에 없던 hash 중 이 배치에서 유일한 것들. batch_hashes 는 이미
        # 같은 배치 안의 중복(동일 URL 이 여러 번 들어온 경우)을 집합 연산으로 흡수한다.
        inserted = len(batch_hashes - existing_before)

        return inserted, len(candidates) - inserted
