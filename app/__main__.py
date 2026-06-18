"""
워커 프로세스 진입점.

실행 예:
  python -m app --role discovery  --source naver_news
  python -m app --role extraction

역할(--role):
  discovery  → 키워드 스케줄을 돌면서 URL 을 수집한다 (dispatcher.py)
  extraction → 수집된 URL 에서 본문을 추출해 파일 또는 Solr 에 저장한다 (extraction_worker.py)
              + Reaper 를 daemon 스레드로 함께 시작한다

소스(--source):
  naver_news / daum_news / google_news / naver_stock / all — discovery 워커가 어떤 소스 키워드를 처리할지 지정
  같은 소스로 워커를 여러 개 띄워도 서로 다른 키워드를 나눠 처리한다 (SKIP LOCKED)
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading

from app import logging_setup
from app import config

_ROLES   = ("discovery", "extraction")
_PORTALS = ("naver_news", "daum_news", "google_news", "baidu_news", "naver_stock", "all")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="keyword-crawler 워커")
    p.add_argument("--role",   required=True, choices=_ROLES,   help="실행 역할")
    p.add_argument("--source", default="all", choices=_PORTALS, help="소스 필터 (기본: all)")
    p.add_argument("--worker-id", default=None, help="워커 식별자 (기본: 환경변수 WORKER_ID)")
    return p.parse_args()


def _handle_signal(signum: int, frame: object) -> None:
    logger = logging_setup.setup("main")
    logger.info("shutdown", extra={"phase": "shutdown", "worker_id": config.WORKER_ID})
    sys.exit(0)


def main() -> None:
    args = _parse_args()
    config.validate()

    worker_id = args.worker_id or config.WORKER_ID
    config.WORKER_ID = worker_id  # FileSink 등 config를 직접 읽는 컴포넌트에 반영

    if args.role == "discovery":
        log_name = f"discovery-{args.source}-{worker_id}"
    else:
        log_name = f"extraction-{worker_id}"
    logger = logging_setup.setup(args.role, worker_id=worker_id, log_name=log_name)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT,  _handle_signal)

    if config.MASKING_ENABLED:
        from app.sink.serialize import init_masker
        init_masker()

    try:
        if args.role == "discovery":
            from app.scheduling.dispatcher import run_discovery_loop
            run_discovery_loop(source=args.source, worker_id=worker_id)
        else:
            from app.worker.extraction_worker import run_extraction_loop
            from app.worker.reaper import run_reaper

            # daemon=True: 메인 루프(추출 워커)가 끝나면 Reaper 도 함께 종료된다.
            reaper = threading.Thread(
                target=run_reaper,
                args=(worker_id,),
                daemon=True,
                name="reaper",
            )
            reaper.start()
            run_extraction_loop(source=args.source, worker_id=worker_id)
    except Exception:
        logger.exception(
            "unhandled exception — worker stopping",
            extra={"phase": "main", "worker_id": worker_id},
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
