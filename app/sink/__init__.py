"""
Sink 팩토리.

.env 의 SINK_TYPE 값에 따라 FileSink 또는 SolrSink 를 반환한다.

  SINK_TYPE=file  (기본) → FileSink  — data/{날짜}/{포털}-{worker_id}.jsonl 에 저장
  SINK_TYPE=solr         → SolrSink  — SOLR_URL 의 Solr 코어에 upsert
"""

from __future__ import annotations

from app import config
from app.ports import Sink


def make_sink() -> Sink:
    """SINK_TYPE 환경변수에 따라 적절한 Sink 를 반환한다."""
    sink_type = config.SINK_TYPE.lower()

    if sink_type == "solr":
        from app.sink.solr_sink import SolrSink
        return SolrSink()  # config.SOLR_URL 에서 URL 을 읽음

    # 기본값: file
    from app.sink.file_sink import FileSink
    return FileSink()  # config.FILE_SINK_DIR 에서 경로를 읽음
