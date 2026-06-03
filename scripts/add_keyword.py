"""
keyword 테이블에 키워드 추가.

실행:
  python scripts/add_keyword.py --keyword "삼성전자" --portal NAVER_NEWS
  python scripts/add_keyword.py --keyword "005930" --portal NAVER_STOCK --display-name "삼성전자"
  python scripts/add_keyword.py --keyword "三星电子" --portal GOOGLE_NEWS --display-name "삼성전자 (중문)"
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.repository.db import db_context


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--keyword",      required=True)
    p.add_argument("--portal",       default="naver_news",
                   choices=["naver_news", "daum_news", "google_news", "weibo", "naver_stock"])
    p.add_argument("--interval",     default=86400, type=int, help="수집 주기(초), 기본 1일")
    p.add_argument("--priority",     default=0, type=int)
    p.add_argument("--display-name", default=None, help="사람이 읽기 쉬운 라벨 (종목명, 검색어 설명 등)")
    args = p.parse_args()

    with db_context() as engine:
        with engine.begin() as conn:
            result = conn.execute(
                text("""
                    INSERT INTO keyword
                        (keyword, portal_type, interval_seconds, enabled, priority, display_name)
                    VALUES
                        (:kw, :portal, :interval, true, :priority, :display_name)
                    ON DUPLICATE KEY UPDATE
                        interval_seconds = VALUES(interval_seconds),
                        enabled          = true,
                        priority         = VALUES(priority),
                        display_name     = COALESCE(VALUES(display_name), display_name)
                """),
                {
                    "kw":           args.keyword,
                    "portal":       args.portal.upper(),
                    "interval":     args.interval,
                    "priority":     args.priority,
                    "display_name": args.display_name,
                },
            )
        label = f" ({args.display_name})" if args.display_name else ""
        print(f"등록 완료: '{args.keyword}'{label} [{args.portal}]  (affected rows: {result.rowcount})")


if __name__ == "__main__":
    main()
