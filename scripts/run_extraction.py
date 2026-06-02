"""
article_url 테이블의 discovered URL 을 읽어 본문 추출 → FileSink 저장.
워커 루프 대신 지정한 건수만 처리하고 종료.

실행:
  python scripts/run_extraction.py                    # 기본: 최대 50건
  python scripts/run_extraction.py --limit 100
  python scripts/run_extraction.py --limit 0          # 0 = 남은 전체 처리
"""

import sys
import argparse
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from news_crawler import logging_setup, config
logging_setup.setup("run_extraction")
log = logging.getLogger("run_extraction")

from news_crawler.repository.db import db_context
from news_crawler.repository.article_url_repo import ArticleUrlRepo
from news_crawler.repository.domain_repo import DomainRepo
from news_crawler.domain_logic.backoff import next_retry_at
from news_crawler.domain_logic.failure_classifier import classify_http, classify_exception
from news_crawler.extraction.extractor import DefaultExtractor
from news_crawler.fetch.http_client import HttpFetcher
from news_crawler.sink import make_sink
from news_crawler.fetch.rate_limit import RateLimiter
from news_crawler.types import ExtractionFailure

p = argparse.ArgumentParser()
p.add_argument("--limit",     type=int, default=50,
               help="처리할 최대 건수. 0 = 전체 (기본: 50)")
p.add_argument("--worker-id", default="manual-extract")
args = p.parse_args()

limit     = args.limit or float("inf")
worker_id = args.worker_id

stored = failed = 0
t_start = time.monotonic()

with db_context() as engine:
    url_repo    = ArticleUrlRepo(engine)
    domain_repo = DomainRepo(engine)
    fetcher     = HttpFetcher()
    limiter     = RateLimiter(domain_repo)
    extractor   = DefaultExtractor(domain_repo=domain_repo)
    sink        = make_sink()  # SINK_TYPE 환경변수로 file / solr 선택

    i = 0
    while i < limit:
        item = url_repo.claim_next(worker_id=worker_id)
        if item is None:
            break

        i += 1
        url     = item["url"]
        host    = item["host"]
        portal  = item["portal_type"]
        keyword = item.get("keyword", "")
        attempt = item["attempt_count"]

        print(f"[{i:04d}] {url[:80]}")
        limiter.wait(host)

        # Fetch
        try:
            fr = fetcher.fetch(url)
        except Exception as exc:
            code, is_perm = classify_exception(exc)
            domain_repo.upsert_health(host, success=False, body_len=None)
            url_repo.mark_failed(item["id"], code, str(exc), is_perm,
                                  None if is_perm else next_retry_at(attempt))
            failed += 1
            print(f"       FETCH ERROR ({code.value}): {exc}")
            continue

        if fr.status_code >= 400:
            code, is_perm = classify_http(fr.status_code)
            domain_repo.upsert_health(host, success=False, body_len=None)
            url_repo.mark_failed(item["id"], code, f"HTTP {fr.status_code}", is_perm,
                                  None if is_perm else next_retry_at(attempt))
            failed += 1
            print(f"       HTTP {fr.status_code} ({code.value})")
            continue

        # Extract
        result = extractor.extract(url=fr.url, html=fr.html, host=host,
                                   portal_type=portal, keyword=keyword)
        if isinstance(result, ExtractionFailure):
            domain_repo.upsert_health(host, success=False, body_len=None)
            if attempt + 1 >= config.MAX_ATTEMPTS:
                url_repo.mark_dead(item["id"], result.error_code, result.error_msg)
            else:
                url_repo.mark_failed(item["id"], result.error_code, result.error_msg,
                                      result.is_permanent,
                                      None if result.is_permanent else next_retry_at(attempt))
            failed += 1
            print(f"       EXTRACT ({result.error_code.value}): {result.error_msg[:60]}")
            continue

        # Sink
        sink.write(result)
        url_repo.mark_stored(item["id"], result.extraction_method)
        domain_repo.upsert_health(host, success=True, body_len=result.body_len)
        stored += 1
        print(f"       OK [{result.extraction_method}] {result.title[:50]}  ({result.body_len}자)")

elapsed = time.monotonic() - t_start
print(f"\n완료: 저장 {stored}건  실패 {failed}건  소요 {elapsed:.1f}초")
