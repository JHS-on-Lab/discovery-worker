"""
실패 URL 재투입 — failed_permanent / dead / failed_transient → discovered.

실행:
  # 전체 failed_permanent 재투입
  python scripts/requeue_failed.py --status failed_permanent

  # 특정 호스트의 dead URL 재투입
  python scripts/requeue_failed.py --status dead --host www.example.com

  # 특정 에러 코드만 재투입
  python scripts/requeue_failed.py --status failed_permanent --error-code PARSE_ERROR

  # 현황 조회 (재투입 없이)
  python scripts/requeue_failed.py --show
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.repository.db import db_context
from app.repository.article_url_repo import ArticleUrlRepo

_REQUEUE_STATUSES = ["failed_permanent", "dead", "failed_transient"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--status",
                   choices=_REQUEUE_STATUSES,
                   help="재투입할 status (미지정 시 --show 만 동작)")
    p.add_argument("--host",       help="특정 도메인만 (예: www.example.com)")
    p.add_argument("--error-code", help="특정 에러 코드만 (예: PARSE_ERROR, BODY_TOO_SHORT)")
    p.add_argument("--show",       action="store_true", help="현황만 조회")
    args = p.parse_args()

    with db_context() as engine:
        # 현황 출력
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT status, last_error_code, COUNT(*) AS cnt
                    FROM article_url
                    WHERE status IN ('failed_permanent', 'dead', 'failed_transient')
                    GROUP BY status, last_error_code
                    ORDER BY status, cnt DESC
                """)
            ).fetchall()

        if rows:
            print("현재 실패 URL 현황:")
            for r in rows:
                print(f"  {r.status:20s}  {(r.last_error_code or '-'):20s}  {r.cnt}건")
        else:
            print("실패 URL 없음.")

        if args.show or not args.status:
            return

        # 재투입
        url_repo = ArticleUrlRepo(engine)
        n = url_repo.requeue(
            statuses=[args.status],
            host=args.host,
            error_code=args.error_code,
        )

        filters = [f"status={args.status}"]
        if args.host:
            filters.append(f"host={args.host}")
        if args.error_code:
            filters.append(f"error_code={args.error_code}")

        print(f"\n재투입 완료: {n}건  ({', '.join(filters)})")


if __name__ == "__main__":
    main()
