"""rename portal_type WEIBO to BAIDU_NEWS

Revision ID: a1b2c3d4e5f6
Revises: d4385ad5ebc0
Create Date: 2026-06-03
"""

from alembic import op

revision = 'a1b2c3d4e5f6'
down_revision = 'd4385ad5ebc0'
branch_labels = None
depends_on = None

_TABLES = ("keyword", "article_url", "collection_log")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"UPDATE {table} SET portal_type = 'BAIDU_NEWS' WHERE portal_type = 'WEIBO'")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"UPDATE {table} SET portal_type = 'WEIBO' WHERE portal_type = 'BAIDU_NEWS'")
