"""
키워드 등록 스크립트.

사용법:
  # 단건 등록
  python scripts/add_keyword.py --portal naver_news --keyword 삼성전자

  # 표시명·우선순위·수집주기 지정
  python scripts/add_keyword.py --portal naver_stock --keyword 005930 --display-name 삼성전자 --priority 10 --interval 3600

  # 여러 키워드를 한 번에 (공백 구분)
  python scripts/add_keyword.py --portal naver_news --keyword 삼성전자 LG전자 현대차

  # 파일에서 읽기 (한 줄에 키워드 하나)
  python scripts/add_keyword.py --portal daum_news --file keywords.txt

  # 현재 등록된 키워드 목록 확인
  python scripts/add_keyword.py --list
  python scripts/add_keyword.py --list --portal naver_news
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.repository.db import db_context

_PORTALS = ("naver_news", "daum_news", "google_news", "baidu_news", "naver_stock")


def _insert(conn, keyword: str, portal_type: str, display_name: str | None,
            priority: int, interval_seconds: int) -> str:
    """중복이면 SKIP, 아니면 INSERT. 결과 문자열 반환."""
    result = conn.execute(
        text("""
            INSERT INTO t_keyword
                (keyword, portal_type, display_name, enabled, priority, interval_seconds)
            VALUES
                (:kw, :portal, :display_name, 1, :priority, :interval)
            ON DUPLICATE KEY UPDATE
                id = id
        """),
        {
            "kw":           keyword,
            "portal":       portal_type.upper(),
            "display_name": display_name,
            "priority":     priority,
            "interval":     interval_seconds,
        },
    )
    # rowcount=1: 신규 INSERT, rowcount=0: 중복 스킵
    return "추가" if result.rowcount == 1 else "중복(스킵)"


def _list(engine, portal: str | None) -> None:
    portal_filter = "" if not portal else f"WHERE k.portal_type = '{portal.upper()}'"
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT k.id, k.portal_type, k.keyword, k.display_name,
                       k.enabled, k.priority, k.interval_seconds,
                       k.next_discover_at
                FROM t_keyword k
                {portal_filter}
                ORDER BY k.portal_type, k.priority DESC, k.keyword
            """)
        ).fetchall()

    if not rows:
        print("등록된 키워드가 없습니다.")
        return

    print(f"{'ID':>6}  {'포털':<14}  {'키워드':<20}  {'표시명':<20}  {'활성':>4}  {'우선순위':>6}  {'주기(초)':>8}")
    print("-" * 90)
    for r in rows:
        enabled = "O" if r.enabled else "X"
        display = r.display_name or ""
        print(f"{r.id:>6}  {r.portal_type:<14}  {r.keyword:<20}  {display:<20}  {enabled:>4}  {r.priority:>6}  {r.interval_seconds:>8}")
    print(f"\n총 {len(rows)}개")


def main() -> None:
    p = argparse.ArgumentParser(description="t_keyword 테이블 키워드 등록")
    p.add_argument("--portal",       choices=_PORTALS, metavar="PORTAL",
                   help=f"포털 종류: {' | '.join(_PORTALS)}")
    p.add_argument("--keyword",      nargs="+", metavar="KW",
                   help="등록할 키워드 (복수 가능)")
    p.add_argument("--file",         metavar="FILE",
                   help="키워드 목록 파일 (한 줄에 하나)")
    p.add_argument("--display-name", metavar="NAME",
                   help="사람이 읽기 쉬운 표시명 (단건 등록 시)")
    p.add_argument("--priority",     type=int, default=0,
                   help="수집 우선순위 (기본값: 0, 높을수록 먼저 처리)")
    p.add_argument("--interval",     type=int, default=86400,
                   help="수집 주기 초 (기본값: 86400 = 24시간)")
    p.add_argument("--list",         action="store_true",
                   help="등록된 키워드 목록 출력")
    args = p.parse_args()

    if args.list:
        with db_context() as engine:
            _list(engine, args.portal)
        return

    if not args.portal:
        p.error("--portal 은 필수입니다.")

    keywords: list[str] = []
    if args.keyword:
        keywords.extend(args.keyword)
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"파일을 찾을 수 없습니다: {args.file}", file=sys.stderr)
            sys.exit(1)
        keywords.extend(line.strip() for line in path.read_text().splitlines() if line.strip())

    if not keywords:
        p.error("--keyword 또는 --file 로 키워드를 지정하세요.")

    if args.display_name and len(keywords) > 1:
        p.error("--display-name 은 키워드가 하나일 때만 사용할 수 있습니다.")

    with db_context() as engine:
        with engine.begin() as conn:
            for kw in keywords:
                status = _insert(
                    conn, kw, args.portal,
                    args.display_name if len(keywords) == 1 else None,
                    args.priority, args.interval,
                )
                print(f"  [{status}] {args.portal.upper()} / {kw}")


if __name__ == "__main__":
    main()
