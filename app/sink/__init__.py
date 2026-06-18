"""
Sink 팩토리.

.env 의 SINK_TYPE 값에 따라 FileSink 또는 SolrSink 를 반환한다.

  SINK_TYPE=file  (기본) → FileSink  — data/{날짜}/{소스}-{worker_id}.jsonl 에 저장
  SINK_TYPE=solr         → SolrSink  — t_crawl_runtime 에서 조회한 solr_url 로 upsert
"""

from __future__ import annotations

import socket

from sqlalchemy import Engine

from app import config
from app.ports import Sink


def make_sink(engine: Engine) -> Sink:
    """SINK_TYPE 환경변수에 따라 적절한 Sink 를 반환한다."""
    sink_type = config.SINK_TYPE.lower()

    if sink_type == "solr":
        from app.sink.solr_sink import SolrSink
        solr_url, crawler_type, crawl_runtime_key = _resolve_solr_config(engine)
        return SolrSink(solr_url, crawler_type, crawl_runtime_key)

    # 기본값: file
    from app.sink.file_sink import FileSink
    _, crawler_type, crawl_runtime_key = _resolve_solr_config(engine)
    return FileSink(crawler_type, crawl_runtime_key)


def _resolve_solr_config(engine: Engine) -> tuple[str, str, str]:
    """
    Solr 접속 정보와 런타임 메타를 반환한다.
    반환: (solr_url, crawler_type, crawl_runtime_key)
    """
    hostname = socket.gethostname()

    if config.SOLR_DIRECT_ENABLED:
        if not config.SOLR_URL:
            raise RuntimeError("SOLR_DIRECT_ENABLED=true 이지만 SOLR_URL 이 설정되지 않았습니다.")
        runtime_name = config.SOLR_RUNTIME_NAME
        crawl_runtime_key = f"{hostname}_{runtime_name}" if runtime_name else hostname
        return config.SOLR_URL, config.SOLR_CRAWLER_TYPE, crawl_runtime_key

    from app.repository.crawl_runtime_repo import CrawlRuntimeRepo
    runtime_name = config.SOLR_RUNTIME_NAME
    info = CrawlRuntimeRepo(engine).get_runtime(runtime_name)
    if not info:
        raise RuntimeError(
            f"t_crawl_runtime 에서 runtime_name='{runtime_name}' 을 찾을 수 없거나 "
            f"use_yn='N' 입니다."
        )
    crawl_runtime_key = f"{hostname}_{runtime_name}"
    return info.solr_url, info.crawler_type, crawl_runtime_key
