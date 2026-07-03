"""
discovery-worker 진입점.

실행 예:
  python -m app --source naver_news
  python -m app --source all
  python -m app --source naver_news --worker-id disc-naver-1

소스(--source):
  naver_news | daum_news | google_news | baidu_news | naver_stock | duckduckgo_news | all
  같은 소스로 워커를 여러 개 띄워도 서로 다른 키워드를 나눠 처리한다 (낙관적 클레임)
"""

from __future__ import annotations

import argparse
import signal
import sys

from app import logging_setup
from app import config

_SOURCES = ("naver_news", "daum_news", "google_news", "baidu_news", "naver_stock", "duckduckgo_news", "all")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="discovery-worker")
    p.add_argument("--source",    required=True, choices=_SOURCES, help="처리할 소스")
    p.add_argument("--worker-id", default=None,  help="워커 식별자 (기본: 환경변수 WORKER_ID)")
    return p.parse_args()


def _handle_signal(signum: int, frame: object) -> None:
    logger = logging_setup.setup("main")
    logger.info("shutdown", extra={"phase": "shutdown", "worker_id": config.WORKER_ID})
    sys.exit(0)


def main() -> None:
    args = _parse_args()
    config.validate()

    worker_id = args.worker_id or config.WORKER_ID
    config.WORKER_ID = worker_id

    logger = logging_setup.setup("discovery", worker_id=worker_id,
                                 log_name=f"discovery-{args.source}-{worker_id}")

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT,  _handle_signal)

    try:
        from app.scheduling.dispatcher import run_discovery_loop
        run_discovery_loop(source=args.source, worker_id=worker_id)
    except Exception:
        logger.exception(
            "unhandled exception — worker stopping",
            extra={"phase": "main", "worker_id": worker_id},
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
