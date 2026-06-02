"""
발견 디스패처: 키워드 스케줄을 돌면서 URL 을 수집한다.

전체 흐름:
  keyword 테이블에서 수집할 키워드 꺼내기
    → 포털 어댑터로 검색 결과 페이지 스크래핑
    → 발견한 URL 을 article_url 테이블에 저장
    → 결과를 collection_log 에 기록
    → 처리할 키워드 없으면 60초 대기 후 반복

여러 워커를 동시에 띄워도 괜찮은 이유:
  keyword_repo.claim_next() 가 'FOR UPDATE SKIP LOCKED' 를 사용한다.
  쉽게 말해, 한 워커가 키워드를 집어 드는 순간 다른 워커는 그 키워드를 볼 수 없다.
  또한 집어 드는 즉시 next_discover_at 을 24시간 뒤로 밀어두기 때문에
  이 워커가 작업을 마치기 전에 다른 워커가 같은 키워드를 다시 가져가는 일이 없다.

  URL 중복은 article_url.url_hash 에 걸린 UNIQUE 제약으로 DB 레벨에서 차단한다.
"""

from __future__ import annotations

import time
import logging
from datetime import datetime, timezone, timedelta

from news_crawler import config
from news_crawler.worker import _healthcheck
from news_crawler.adapters import make_adapter
from news_crawler.repository.db import db_context
from news_crawler.repository.keyword_repo import KeywordRepo
from news_crawler.repository.article_url_repo import ArticleUrlRepo
from news_crawler.repository.collection_log_repo import CollectionLogRepo, DiscoveryLog

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
_IDLE_SLEEP_SEC  = 60
_ERROR_SLEEP_SEC = 10


def run_discovery_loop(portal: str, worker_id: str) -> None:
    """발견 워커 메인 루프. __main__.py에서 호출."""
    logger.info(
        "discovery loop started",
        extra={"phase": "startup", "worker_id": worker_id, "component": "dispatcher"},
    )

    # adapter 는 루프 레벨에서 한 번 생성해 키워드마다 재사용한다.
    # UCGoogleAdapter 처럼 브라우저를 초기화하는 경우 매 키워드마다 재생성하면 낭비가 크다.
    adapter = make_adapter(portal) if portal.upper() != "ALL" else None

    heartbeat_interval = config.HEARTBEAT_INTERVAL_SECONDS
    last_heartbeat = time.monotonic()
    processed = 0

    with db_context() as engine:
        kw_repo   = KeywordRepo(engine)
        url_repo  = ArticleUrlRepo(engine)
        log_repo  = CollectionLogRepo(engine)

        try:
            while True:
                now = time.monotonic()
                if now - last_heartbeat >= heartbeat_interval:
                    logger.info(
                        f"heartbeat processed={processed}",
                        extra={"phase": "heartbeat", "worker_id": worker_id, "component": "dispatcher"},
                    )
                    last_heartbeat = now
                    _healthcheck.write()

                try:
                    kw = kw_repo.claim_next(portal=portal, worker_id=worker_id)
                except Exception:
                    logger.exception(
                        f"claim_next failed, sleeping {_ERROR_SLEEP_SEC}s",
                        extra={"phase": "claim", "worker_id": worker_id, "component": "dispatcher"},
                    )
                    time.sleep(_ERROR_SLEEP_SEC)
                    continue

                if kw is None:
                    logger.debug(
                        f"no due keywords for portal={portal}, sleeping {_IDLE_SLEEP_SEC}s",
                        extra={"phase": "idle", "worker_id": worker_id, "component": "dispatcher"},
                    )
                    time.sleep(_IDLE_SLEEP_SEC)
                    continue

                _run_one(kw, kw_repo, url_repo, log_repo, worker_id, adapter)
                processed += 1
        finally:
            if adapter and hasattr(adapter, "close"):
                adapter.close()


def _run_one(
    kw: dict,
    kw_repo: KeywordRepo,
    url_repo: ArticleUrlRepo,
    log_repo: CollectionLogRepo,
    worker_id: str,
    adapter=None,
) -> None:
    """키워드 하나를 발견한다. 실패해도 예외를 밖으로 올리지 않아 루프가 멈추지 않는다."""
    keyword    = kw["keyword"]
    portal     = kw["portal_type"]
    keyword_id = kw["id"]

    extra = {"phase": "discover", "worker_id": worker_id, "item": str(keyword_id), "component": "dispatcher"}
    logger.info(f"start keyword='{keyword}' portal={portal}", extra=extra)

    started_at   = datetime.now(KST)
    started_mono = time.monotonic()
    total_found = total_ins = total_skp = 0

    try:
        if adapter is None:
            adapter = make_adapter(portal)
        cursor, page = None, 1

        while True:
            result = adapter.discover(keyword, cursor)
            ins, skp = url_repo.bulk_insert_discovered(result.urls, keyword_id, portal)
            total_found += len(result.urls)
            total_ins   += ins
            total_skp   += skp

            logger.info(
                f"p{page}: found={len(result.urls)} inserted={ins} skipped={skp}",
                extra={**extra, "phase": "discover_page"},
            )

            if not result.has_more:
                break
            cursor, page = result.next_cursor, page + 1

        duration_ms = int((time.monotonic() - started_mono) * 1000)

        kw_repo.complete(keyword_id)

        # 이번 수집 결과를 collection_log 에 한 줄로 남긴다 (나중에 SQL 로 추이 조회 가능).
        log_repo.insert_discovery(DiscoveryLog(
            keyword_id    = keyword_id,
            portal_type   = portal,
            worker_id     = worker_id,
            started_at    = started_at,
            duration_ms   = duration_ms,
            urls_found    = total_found,
            urls_inserted = total_ins,
            urls_skipped  = total_skp,
        ))

        logger.info(
            f"done keyword='{keyword}' found={total_found} "
            f"inserted={total_ins} skipped={total_skp} duration={duration_ms}ms",
            extra={**extra, "phase": "discover_done"},
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - started_mono) * 1000)
        error_msg = f"{type(exc).__name__}: {exc}"

        logger.exception(
            f"error keyword='{keyword}' portal={portal}",
            extra={**extra, "phase": "discover_error"},
        )

        try:
            log_repo.insert_discovery(DiscoveryLog(
                keyword_id    = keyword_id,
                portal_type   = portal,
                worker_id     = worker_id,
                started_at    = started_at,
                duration_ms   = duration_ms,
                urls_found    = total_found,
                urls_inserted = total_ins,
                urls_skipped  = total_skp,
                error_msg     = error_msg[:500],
            ))
        except Exception:
            logger.exception(
                "failed to write error log",
                extra={**extra, "phase": "discover_error"},
            )

        time.sleep(_ERROR_SLEEP_SEC)
