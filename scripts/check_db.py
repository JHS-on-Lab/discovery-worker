"""
SSH 터널 + RDS 연결 확인 스크립트.
실행: python scripts/check_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.repository.db import db_context


def main():
    print("DB 연결 확인 중...")
    with db_context() as engine:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT VERSION(), DATABASE()")).fetchone()
            print(f"  MySQL 버전 : {row[0]}")
            print(f"  현재 DB   : {row[1]}")
            print("연결 성공.")


if __name__ == "__main__":
    main()
