"""
연결 상태 확인 스크립트.

실행:
  python scripts/healthcheck.py           # DB 연결 확인 (.env.{APP_ENV} 설정대로 — TUNNEL_ENABLED=true 면 SSH 터널 경유)
  python scripts/healthcheck.py --direct  # SSH 터널 없이 RDS_HOST:RDS_PORT로 직접 접속 시도
                                           # (RDS와 같은 네트워크에 있는 서버, 예: dev-app-host에서 사용)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from app import config
from app.repository.db import db_context


def _print_result(row) -> None:
    print(f"  MySQL 버전 : {row[0]}")
    print(f"  현재 DB   : {row[1]}")
    print("  → OK\n")


def check_db() -> bool:
    """.env.{APP_ENV} 설정대로 접속 — TUNNEL_ENABLED=true 면 SSH 터널을 연다."""
    print("[ DB ]")
    try:
        with db_context() as engine:
            with engine.connect() as conn:
                row = conn.execute(text("SELECT VERSION(), DATABASE()")).fetchone()
        _print_result(row)
        return True
    except Exception as e:
        print(f"  → 실패: {e}\n")
        return False


def check_db_direct() -> bool:
    """SSH 터널 없이 RDS_HOST:RDS_PORT로 바로 접속 시도한다 (TUNNEL_ENABLED 설정은 무시).

    RDS와 같은 네트워크(VPC 등)에 있는 서버에서 실행할 때만 의미가 있다 —
    그렇지 않은 환경(예: 로컬)에서 돌리면 타임아웃/거부로 실패하는 게 정상이다.
    """
    print("[ DB — 직접 접속 (SSH 터널 미사용) ]")
    print(f"  대상: {config.RDS_USER}@{config.RDS_HOST}:{config.RDS_PORT}/{config.RDS_DB}")
    # URL.create() 는 username/password 를 자동으로 URL-encoding 한다.
    # f-string 조립은 비밀번호에 '@' 같은 특수문자가 있으면 DSN 파싱 자체가 깨진다.
    dsn = URL.create(
        "mysql+pymysql",
        username=config.RDS_USER,
        password=config.RDS_PASSWORD,
        host=config.RDS_HOST,
        port=config.RDS_PORT,
        database=config.RDS_DB,
        query={"charset": "utf8mb4"},
    )
    engine = create_engine(dsn, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT VERSION(), DATABASE()")).fetchone()
        _print_result(row)
        return True
    except Exception as e:
        print(f"  → 실패: {e}\n")
        return False
    finally:
        engine.dispose()


def main() -> None:
    p = argparse.ArgumentParser(description="연결 상태 확인")
    p.add_argument("--db", action="store_true", help="DB 연결 확인 (기본)")
    p.add_argument("--direct", action="store_true",
                   help="SSH 터널 없이 RDS에 직접 접속 시도 (TUNNEL_ENABLED 설정 무시)")
    args = p.parse_args()

    ok = check_db_direct() if args.direct else check_db()
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
