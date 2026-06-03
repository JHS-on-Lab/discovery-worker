"""
article_url 테이블의 discovered URL 을 읽어 본문 추출 → FileSink 저장.
워커 루프 대신 지정한 건수만 처리하고 종료.

domain 테이블의 render_mode 를 참조해 static / headless / headless_with_iframe
를 자동으로 선택한다 (extraction_worker 와 동일한 로직).

실행:
  python scripts/run_extraction.py                         # 기본: 최대 50건
  python scripts/run_extraction.py --limit 100
  python scripts/run_extraction.py --limit 0               # 0 = 남은 전체 처리
  python scripts/run_extraction.py --portal NAVER_STOCK    # 특정 포털만
  python scripts/run_extraction.py --portal NAVER --limit 20
"""

import sys
import argparse
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import logging_setup, config
logging_setup.setup("run_extraction")
log = logging.getLogger("run_extraction")

from app.repository.db import db_context
from app.repository.article_url_repo import ArticleUrlRepo
from app.repository.domain_repo import DomainRepo
from app.domain_logic.backoff import next_retry_at
from app.domain_logic.failure_classifier import classify_http, classify_exception
from app.extraction.extractor import DefaultExtractor
from app.fetch.headless import HeadlessFetcher, fetch_by_render_mode
from app.fetch.http_client import HttpFetcher
from app.fetch.rate_limit import RateLimiter
from app.sink import make_sink
from app.types import ExtractionFailure, RenderMode

_PORTALS = ["NAVER_NEWS", "DAUM_NEWS", "GOOGLE_NEWS", "WEIBO", "NAVER_STOCK"]

p = argparse.ArgumentParser()
p.add_argument("--limit",     type=int, default=50,
               help="처리할 최대 건수. 0 = 전체 (기본: 50)")
p.add_argument("--portal",    choices=_PORTALS, default=None,
               help="특정 포털만 처리 (기본: 전체)")
p.add_argument("--worker-id", default="manual-extract")
args = p.parse_args()

limit     = args.limit or float("inf")
worker_id = args.worker_id

stored = failed = 0
t_start = time.monotonic()

with db_context() as engine:
    url_repo    = ArticleUrlRepo(engine)
    domain_repo = DomainRepo(engine)
    http_fetcher    = HttpFetcher()
    headless_fetcher = HeadlessFetcher()
    limiter     = RateLimiter(domain_repo)
    extractor   = DefaultExtractor(domain_repo=domain_repo)
    sink        = make_sink()

    i = 0
    while i < limit:
        item = url_repo.claim_next(worker_id=worker_id, portal=args.portal)
        if item is None:
            break

        i += 1
        url     = item["url"]
        host    = item["host"]
        portal  = item["portal_type"]
        keyword = item.get("keyword", "")
        attempt = item["attempt_count"]

        print(f"[{i:04d}] [{portal}] {url[:80]}")
        limiter.wait(host)

        domain      = domain_repo.get(host)
        render_mode = (domain or {}).get("render_mode", RenderMode.STATIC)

        try:
            fr = fetch_by_render_mode(url, render_mode, http_fetcher, headless_fetcher)
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

        sink.write(result)
        url_repo.mark_stored(item["id"], result.extraction_method)
        domain_repo.upsert_health(host, success=True, body_len=result.body_len)
        stored += 1
        print(f"       OK [{result.extraction_method}] {result.title[:50]}  ({result.body_len}자)")

    headless_fetcher.close()

elapsed = time.monotonic() - t_start
print(f"\n완료: 저장 {stored}건  실패 {failed}건  소요 {elapsed:.1f}초")
