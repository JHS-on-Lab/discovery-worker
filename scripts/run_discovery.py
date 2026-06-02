"""
단일 키워드 수동 발견 → article_url + collection_log 저장.
dispatcher 없이 특정 키워드만 즉시 수집할 때 사용.

실행:
  python scripts/run_discovery.py --keyword "삼성전자" --portal NAVER
  python scripts/run_discovery.py --keyword "삼성전자" --portal DAUM  --pages 5
  python scripts/run_discovery.py --keyword "삼성전자" --portal GOOGLE --pages 3
"""

import sys, argparse, time
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from news_crawler import logging_setup
logging_setup.setup("run_discovery")  # app.log + error.log + 콘솔

from news_crawler.adapters import make_adapter
from news_crawler.repository.db import db_context
from news_crawler.repository.keyword_repo import KeywordRepo
from news_crawler.repository.article_url_repo import ArticleUrlRepo
from news_crawler.repository.collection_log_repo import CollectionLogRepo, DiscoveryLog

KST = timezone(timedelta(hours=9))

p = argparse.ArgumentParser()
p.add_argument("--keyword", required=True)
p.add_argument("--portal",  required=True, choices=["NAVER", "DAUM", "GOOGLE", "WEIBO"])
p.add_argument("--pages",   type=int, default=3, help="최대 페이지 수 (NAVER/DAUM)")
p.add_argument("--period",  default="",   help="기간 (NAVER: 4=1일 / DAUM: d=1일)")
p.add_argument("--worker-id", default="manual")
args = p.parse_args()

# 포털별 기본 기간 설정
if not args.period:
    args.period = {"NAVER": "4", "DAUM": "d"}.get(args.portal, "")

# 어댑터 생성 (portal + period 반영)
if args.portal == "NAVER":
    from news_crawler.adapters.naver import NaverAdapter
    adapter = NaverAdapter(period=args.period, max_pages=args.pages)
elif args.portal == "DAUM":
    from news_crawler.adapters.daum import DaumAdapter
    adapter = DaumAdapter(period=args.period, max_pages=args.pages)
elif args.portal == "GOOGLE":
    from news_crawler.adapters.google import UCGoogleAdapter
    adapter = UCGoogleAdapter(max_pages=args.pages)
else:
    adapter = make_adapter(args.portal)

with db_context() as engine:
    kw_repo  = KeywordRepo(engine)
    url_repo = ArticleUrlRepo(engine)
    log_repo = CollectionLogRepo(engine)

    # keyword_id 조회
    from sqlalchemy import text
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM keyword WHERE keyword=:kw AND portal_type=:portal"),
            {"kw": args.keyword, "portal": args.portal},
        ).fetchone()

    if not row:
        print(f"[오류] '{args.keyword}'[{args.portal}]가 keyword 테이블에 없습니다.")
        print(f"  먼저: python scripts/add_keyword.py --keyword \"{args.keyword}\" --portal {args.portal}")
        sys.exit(1)

    keyword_id = row[0]
    started_at = datetime.now(KST)
    started_mono = time.monotonic()
    total_found = total_ins = total_skp = 0
    cursor, page = None, 1

    print(f"[발견] '{args.keyword}' [{args.portal}]  pages≤{args.pages}")

    while True:
        result = adapter.discover(args.keyword, cursor)
        ins, skp = url_repo.bulk_insert_discovered(result.urls, keyword_id, args.portal)
        total_found += len(result.urls)
        total_ins   += ins
        total_skp   += skp
        print(f"  p{page}: {len(result.urls)}개 발견  신규 {ins}  중복 {skp}")

        if not result.has_more:
            break
        cursor, page = result.next_cursor, page + 1

    duration_ms = int((time.monotonic() - started_mono) * 1000)

    kw_repo.complete(keyword_id)

    # collection_log 기록
    log_repo.insert_discovery(DiscoveryLog(
        keyword_id    = keyword_id,
        portal_type   = args.portal,
        worker_id     = args.worker_id,
        started_at    = started_at,
        duration_ms   = duration_ms,
        urls_found    = total_found,
        urls_inserted = total_ins,
        urls_skipped  = total_skp,
    ))

    print(f"\n[완료] 신규 {total_ins}개  중복 {total_skp}개  소요 {duration_ms/1000:.1f}초")

if hasattr(adapter, "close"):
    adapter.close()
