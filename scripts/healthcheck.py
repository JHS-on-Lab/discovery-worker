"""
연결 상태 확인 스크립트.

실행:
  python scripts/healthcheck.py    # DB 연결 확인
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from sqlalchemy import text

from app.repository.db import db_context


def check_db() -> bool:
    print("[ DB ]")
    try:
        with db_context() as engine:
            with engine.connect() as conn:
                row = conn.execute(text("SELECT VERSION(), DATABASE()")).fetchone()
        print(f"  MySQL 버전 : {row[0]}")
        print(f"  현재 DB   : {row[1]}")
        print("  → OK\n")
        return True
    except Exception as e:
        print(f"  → 실패: {e}\n")
        return False


def main() -> None:
    p = argparse.ArgumentParser(description="연결 상태 확인")
    p.add_argument("--db", action="store_true", help="DB 연결 확인 (기본)")
    p.parse_args()

    ok = check_db()
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
