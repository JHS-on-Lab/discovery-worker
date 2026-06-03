"""
Alembic env.py — SSH 터널을 열고 RDS에 연결한 뒤 마이그레이션을 실행한다.
"""

import sys
from pathlib import Path
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, create_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import config as app_config
from app.repository.db import db_context

alembic_config = context.config
if alembic_config.config_file_name:
    fileConfig(alembic_config.config_file_name)

# SQLAlchemy MetaData — 모델 정의 후 여기에 연결
from migrations.models import metadata
target_metadata = metadata


def run_migrations_online() -> None:
    """SSH 터널(옵션)을 열고 온라인 마이그레이션 실행."""
    with db_context() as engine:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()


def run_migrations_offline() -> None:
    """오프라인 모드(SQL 파일 출력)."""
    if app_config.TUNNEL_ENABLED:
        dsn = (
            f"mysql+pymysql://{app_config.RDS_USER}:{app_config.RDS_PASSWORD}"
            f"@127.0.0.1:{app_config.TUNNEL_LOCAL_PORT}/{app_config.RDS_DB}"
            f"?charset=utf8mb4"
        )
    else:
        dsn = (
            f"mysql+pymysql://{app_config.RDS_USER}:{app_config.RDS_PASSWORD}"
            f"@{app_config.RDS_HOST}:{app_config.RDS_PORT}/{app_config.RDS_DB}"
            f"?charset=utf8mb4"
        )
    context.configure(
        url=dsn,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
