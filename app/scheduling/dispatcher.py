"""
발견 디스패처: 키워드 스케줄을 돌면서 URL 을 수집한다.

전체 흐름:
  keyword 테이블에서 수집할 키워드 꺼내기
    → 소스 어댑터로 검색 결과 페이지 스크래핑
    → 발견한 URL 을 crawl_url 테이블에 저장
    → 결과를 collection_log 에 기록
    → 처리할 키워드 없으면 60초 대기 후 반복

여러 워커를 동시에 띄워도 괜찮은 이유:
  keyword_repo.claim_next() 가 낙관적 클레임(조건부 UPDATE + rowcount 확인)을 사용한다.
  쉽게 말해, 한 워커가 키워드를 집어 드는 순간 다른 워커는 같은 row 의 UPDATE 에서 rowcount=0 을 받아 넘어간다.
  또한 집어 드는 즉시 next_discover_at 을 24시간 뒤로 밀어두기 때문에
  이 워커가 작업을 마치기 전에 다른 워커가 같은 키워드를 다시 가져가는 일이 없다.

  URL 중복은 crawl_url.url_hash 에 걸린 UNIQUE 제약으로 DB 레벨에서 차단한다.
"""

from __future__ import annotations

import threading
import time
import logging
from datetime import datetime, timezone, timedelta

import httpx

from app import config
from app.worker import _healthcheck
from app.adapters import make_adapter
from app.repository.db import db_context
from app.repository.keyword_repo import KeywordRepo
from app.repository.crawl_url_repo import CrawlUrlRepo
from app.repository.collection_log_repo import CollectionLogRepo, DiscoveryLog
from app.types import BotBlockedError

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

_MAX_403_RETRIES      = 5
_MAX_BOT_DETECT_RETRIES = 5
_IDLE_SLEEP_SEC  = 60
_403_SLEEP_SEC   = 60   # 403 후 다음 키워드 요청 전 IP 레벨 냉각
_ERROR_SLEEP_SEC = 10   # 그 외 예외 후 빠른 루프 방지


def _start_healthcheck_thread(interval: float) -> threading.Event:
    """healthcheck 파일을 별도 스레드에서 주기적으로 갱신한다.

    기존에는 메인 루프 상단(다음 키워드를 집기 직전)에서만 갱신했는데, google 뉴스
    RSS 폴백처럼 한 키워드 안에서 URL 수십~백 개를 순차적으로 처리하는 경우 실제로
    다음 키워드로 넘어가기까지 수 분이 걸릴 수 있다. 그 사이엔 healthcheck 파일이
    안 갱신돼 Docker HEALTHCHECK(120초 기준)가 정상 동작 중인 컨테이너를 hang으로
    오판해 강제 재시작시킬 수 있었다.

    메인 스레드가 실제로 멈춰도(예: 네트워크 응답 대기, subprocess 대기) I/O 대기
    중에는 GIL이 풀리므로 이 백그라운드 스레드는 계속 돈다 — 그래서 "진짜 데드락"과
    "오래 걸리지만 진행 중인 작업"을 구분하는 효과가 있다. 또한 google_news/baidu_news
    어댑터에는 이미 page-load 타임아웃이 걸려 있어(별도 수정) 메인 스레드가 무한정
    멈추는 경우 자체가 없으므로, 이 분리가 진짜 hang을 놓치는 위험은 낮다.
    """
    stop_event = threading.Event()
    _healthcheck.write()

    def _loop() -> None:
        while not stop_event.wait(interval):
            _healthcheck.write()

    threading.Thread(target=_loop, daemon=True, name="healthcheck-writer").start()
    return stop_event


def run_discovery_loop(source: str, worker_id: str) -> None:
    """발견 워커 메인 루프. __main__.py에서 호출."""
    logger.info(
        "discovery loop started",
        extra={"phase": "startup", "worker_id": worker_id, "component": "dispatcher"},
    )

    # adapter 는 루프 레벨에서 한 번 생성해 키워드마다 재사용한다.
    # UCGoogleNewsAdapter 처럼 브라우저를 초기화하는 경우 매 키워드마다 재생성하면 낭비가 크다.
    is_all_mode = source.upper() == "ALL"
    adapter = None if is_all_mode else make_adapter(source)

    # ALL 모드 전용 — 키워드마다 source_type 이 달라지므로 source_type 별로 어댑터를
    # 캐시해 재사용한다. 이게 없으면 매 키워드마다 make_adapter() 를 새로 호출하게 되고,
    # google_news/baidu_news 처럼 브라우저를 띄우는 어댑터는 close() 도 안 된 채(_run_one
    # 안의 지역변수로만 남아 GC 에만 의존) 매번 새로 뜨는 셈이라 위 주석의 재사용 의도가
    # ALL 모드에서만 조용히 깨져 있었다.
    adapters_by_source: dict[str, object] = {}

    heartbeat_interval = config.HEARTBEAT_INTERVAL_SECONDS
    last_heartbeat = time.monotonic()
    processed = 0

    healthcheck_stop = _start_healthcheck_thread(heartbeat_interval)

    with db_context() as engine:
        kw_repo   = KeywordRepo(engine)
        url_repo  = CrawlUrlRepo(engine)
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

                try:
                    kw = kw_repo.claim_next(source=source, worker_id=worker_id)
                except Exception:
                    logger.exception(
                        f"claim_next failed, sleeping {_ERROR_SLEEP_SEC}s",
                        extra={"phase": "claim", "worker_id": worker_id, "component": "dispatcher"},
                    )
                    time.sleep(_ERROR_SLEEP_SEC)
                    continue

                if kw is None:
                    logger.debug(
                        f"no due keywords for source={source}, sleeping {_IDLE_SLEEP_SEC}s",
                        extra={"phase": "idle", "worker_id": worker_id, "component": "dispatcher"},
                    )
                    time.sleep(_IDLE_SLEEP_SEC)
                    continue

                if is_all_mode:
                    kw_source = kw["source_type"]
                    if kw_source not in adapters_by_source:
                        adapters_by_source[kw_source] = make_adapter(kw_source)
                    kw_adapter = adapters_by_source[kw_source]
                else:
                    kw_adapter = adapter

                _run_one(kw, kw_repo, url_repo, log_repo, worker_id, kw_adapter)
                processed += 1
        finally:
            healthcheck_stop.set()
            if adapter and hasattr(adapter, "close"):
                adapter.close()
            for kw_adapter in adapters_by_source.values():
                if hasattr(kw_adapter, "close"):
                    kw_adapter.close()


def _run_one(
    kw: dict,
    kw_repo: KeywordRepo,
    url_repo: CrawlUrlRepo,
    log_repo: CollectionLogRepo,
    worker_id: str,
    adapter,
) -> None:
    """adapter 는 항상 호출측(run_discovery_loop)이 이미 만들어서 넘겨준다 —
    이 함수 안에서 새로 만들면 ALL 모드에서 매 키워드마다 브라우저를 새로 띄우고도
    close() 를 안 하는 문제가 있었다(이제는 호출측 캐시가 재사용/close 를 책임진다)."""
    keyword    = kw["keyword"]
    source     = kw["source_type"]
    keyword_id = kw["id"]

    extra = {"phase": "discover", "worker_id": worker_id, "keyword_id": str(keyword_id), "component": "dispatcher"}
    logger.info(f"start keyword='{keyword}' source={source}", extra=extra)

    started_at   = datetime.now(KST)
    started_mono = time.monotonic()
    total_found = total_ins = total_skp = 0

    try:
        # retry_pending=True 면 이전 수집이 중단된 적 있음 (재시도 모드)
        # → 항상 1페이지부터 full scan: 대기 시간 중 올라온 신규 콘텐츠 누락 방지 + 미수집 구간 완성
        # → early-stop 비활성화: 1페이지 전부 중복이라도 뒤 페이지에 미수집 구간이 있을 수 있음
        is_retry = bool(kw.get("retry_pending"))
        cursor   = None
        page     = 1

        if is_retry:
            logger.info(
                "retry: scanning from page 1 without early-stop",
                extra={**extra, "phase": "discover_resume"},
            )

        while True:
            result = adapter.discover(keyword, cursor)
            ins, skp = url_repo.bulk_insert_discovered(result.urls, keyword_id, source)
            total_found += len(result.urls)
            total_ins   += ins
            total_skp   += skp

            logger.info(
                f"p{page}: found={len(result.urls)} inserted={ins} skipped={skp}",
                extra={**extra, "phase": "discover_page"},
            )

            if not result.has_more:
                break
            # 재시도 중에는 early-stop 비활성화 — 1~N 페이지 신규 콘텐츠와 미수집 구간 모두 확보
            if not is_retry and skp > 0 and ins == 0:
                logger.info(
                    f"p{page}: all duplicates, stopping early",
                    extra={**extra, "phase": "discover_page"},
                )
                break
            cursor, page = result.next_cursor, page + 1

        duration_ms = int((time.monotonic() - started_mono) * 1000)

        kw_repo.set_retry_pending(keyword_id, False)

        log_repo.insert_discovery(DiscoveryLog(
            keyword_id    = keyword_id,
            source_type   = source,
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
        error_msg   = f"{type(exc).__name__}: {exc}"
        is_403         = isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 403
        is_bot_blocked = isinstance(exc, BotBlockedError)

        if is_403:
            count    = log_repo.count_today_403(keyword_id)
            retry_at = datetime.now(KST) + timedelta(seconds=config.DISCOVERY_403_RESCHEDULE_SEC)
            if count < _MAX_403_RETRIES:
                kw_repo.reschedule(keyword_id, retry_at)
                logger.warning(
                    f"403 '{keyword}' cursor={cursor} {count+1}/{_MAX_403_RETRIES} retry={retry_at.astimezone(KST).strftime('%H:%M')}KST",
                    extra={**extra, "phase": "discover_error"},
                )
            else:
                logger.warning(
                    f"403 '{keyword}' cursor={cursor} gave_up={_MAX_403_RETRIES} next=24h",
                    extra={**extra, "phase": "discover_error"},
                )
        elif is_bot_blocked:
            count    = log_repo.count_today_bot_blocked(keyword_id)
            retry_at = datetime.now(KST) + timedelta(seconds=config.BOT_DETECT_RETRY_SEC)
            if count < _MAX_BOT_DETECT_RETRIES:
                kw_repo.reschedule(keyword_id, retry_at)
                logger.warning(
                    f"bot blocked '{keyword}' {count+1}/{_MAX_BOT_DETECT_RETRIES} retry={retry_at.astimezone(KST).strftime('%H:%M')}KST",
                    extra={**extra, "phase": "discover_error"},
                )
            else:
                logger.warning(
                    f"bot blocked '{keyword}' gave_up={_MAX_BOT_DETECT_RETRIES} next=24h",
                    extra={**extra, "phase": "discover_error"},
                )
        else:
            logger.exception(
                f"error keyword='{keyword}' source={source}",
                extra={**extra, "phase": "discover_error"},
            )

        try:
            kw_repo.set_retry_pending(keyword_id, True)
        except Exception:
            pass

        try:
            log_repo.insert_discovery(DiscoveryLog(
                keyword_id    = keyword_id,
                source_type   = source,
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

        time.sleep(_403_SLEEP_SEC if is_403 else _ERROR_SLEEP_SEC)
