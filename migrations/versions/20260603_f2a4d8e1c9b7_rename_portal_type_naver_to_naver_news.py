"""rename portal_type NAVER to NAVER_NEWS

Revision ID: f2a4d8e1c9b7
Revises: e7c9b4f2a1d6
Create Date: 2026-06-03
"""

from alembic import op

revision = 'f2a4d8e1c9b7'
down_revision = 'e7c9b4f2a1d6'
branch_labels = None
depends_on = None

_TABLES = ("keyword", "article_url", "collection_log")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"UPDATE {table} SET portal_type = 'NAVER_NEWS' WHERE portal_type = 'NAVER'")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"UPDATE {table} SET portal_type = 'NAVER' WHERE portal_type = 'NAVER_NEWS'")
