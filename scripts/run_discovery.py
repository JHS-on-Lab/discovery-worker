"""
단일 키워드 수동 발견 → article_url + collection_log 저장.
dispatcher 없이 특정 키워드만 즉시 수집할 때 사용.

실행:
  python scripts/run_discovery.py --keyword "삼성전자" --portal NAVER_NEWS
  python scripts/run_discovery.py --keyword "삼성전자" --portal DAUM   --pages 5
  python scripts/run_discovery.py --keyword "삼성전자" --portal GOOGLE  --pages 3
  python scripts/run_discovery.py --keyword "005930"   --portal NAVER_STOCK --pages 5
"""

import sys, argparse, time
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import logging_setup
logging_setup.setup("run_discovery")  # app.log + error.log + 콘솔

from app.adapters import make_adapter
from app.repository.db import db_context
from app.repository.keyword_repo import KeywordRepo
from app.repository.article_url_repo import ArticleUrlRepo
from app.repository.collection_log_repo import CollectionLogRepo, DiscoveryLog

KST = timezone(timedelta(hours=9))

p = argparse.ArgumentParser()
p.add_argument("--keyword", required=True)
p.add_argument("--portal",  required=True, choices=["NAVER_NEWS", "DAUM_NEWS", "GOOGLE_NEWS", "WEIBO", "NAVER_STOCK"])
p.add_argument("--pages",   type=int, default=3, help="최대 페이지 수 (NAVER_NEWS/DAUM)")
p.add_argument("--period",  default="",   help="기간 (NAVER_NEWS: 4=1일 / DAUM: d=1일)")
p.add_argument("--worker-id", default="manual")
args = p.parse_args()

# 포털별 기본 기간 설정
if not args.period:
    args.period = {"NAVER_NEWS": "4", "DAUM_NEWS": "d"}.get(args.portal, "")

# 어댑터 생성 (portal + period 반영)
if args.portal == "NAVER_NEWS":
    from app.adapters.naver_news import NaverNewsAdapter
    adapter = NaverNewsAdapter(period=args.period, max_pages=args.pages)
elif args.portal == "DAUM_NEWS":
    from app.adapters.daum_news import DaumAdapter
    adapter = DaumAdapter(period=args.period, max_pages=args.pages)
elif args.portal == "GOOGLE_NEWS":
    from app.adapters.google_news import UCGoogleAdapter
    adapter = UCGoogleAdapter(max_pages=args.pages)
elif args.portal == "NAVER_STOCK":
    from app.adapters.naver_stock import NaverStockAdapter
    adapter = NaverStockAdapter(max_pages=args.pages)
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
