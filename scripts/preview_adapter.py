"""
포털 어댑터 URL 미리보기 — DB 저장 없이 발견 결과만 출력.

셀렉터 파손 확인, 새 어댑터 검증, 키워드 등록 전 확인 등에 사용.

실행:
  python scripts/preview_adapter.py --keyword "삼성전자" --portal NAVER_NEWS
  python scripts/preview_adapter.py --keyword "삼성전자" --portal DAUM   --pages 3
  python scripts/preview_adapter.py --keyword "삼성전자" --portal GOOGLE  --pages 2
  python scripts/preview_adapter.py --keyword "005930"   --portal NAVER_STOCK --pages 2
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.adapters.naver_news import NaverNewsAdapter
from app.adapters.daum_news import DaumAdapter
from app.adapters.google_news import UCGoogleAdapter
from app.domain_logic.url_normalizer import normalize, url_hash

p = argparse.ArgumentParser()
p.add_argument("--keyword", required=True)
p.add_argument("--portal",  required=True, choices=["NAVER_NEWS", "DAUM_NEWS", "GOOGLE_NEWS", "NAVER_STOCK"])
p.add_argument("--pages",   type=int, default=2, help="최대 페이지 수 (기본 2)")
p.add_argument("--period",  default="",          help="기간 오버라이드 (NAVER_NEWS: 4=1일 / DAUM: d=1일)")
args = p.parse_args()

portal = args.portal.upper()

if portal == "NAVER_NEWS":
    period = args.period or "4"
    adapter = NaverNewsAdapter(period=period, max_pages=args.pages)
    print(f"[NAVER_NEWS] keyword={args.keyword!r}  period=pd{period}  max_pages={args.pages}\n")
elif portal == "DAUM_NEWS":
    period = args.period or "d"
    adapter = DaumAdapter(period=period, max_pages=args.pages)
    print(f"[DAUM] keyword={args.keyword!r}  period={period}  max_pages={args.pages}\n")
elif portal == "GOOGLE_NEWS":
    adapter = UCGoogleAdapter(max_pages=args.pages)
    print(f"[GOOGLE] keyword={args.keyword!r}  max_pages={args.pages}\n")
else:
    from app.adapters.naver_stock import NaverStockAdapter
    adapter = NaverStockAdapter(max_pages=args.pages)
    print(f"[NAVER_STOCK] code={args.keyword!r}  max_pages={args.pages}\n")

try:
    cursor, page, total = None, 1, []
    while True:
        result = adapter.discover(args.keyword, cursor)
        print(f"--- p{page} ({len(result.urls)}개) ---")
        for url in result.urls:
            print(f"  [{url_hash(normalize(url))[:10]}] {url}")
        total.extend(result.urls)
        if not result.has_more:
            break
        cursor, page = result.next_cursor, page + 1

    print(f"\n합계: {len(total)}개  (중복 제거 전)")
finally:
    if hasattr(adapter, "close"):
        adapter.close()
