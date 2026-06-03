"""rename_portal_type_daum_google_to_daum_news_google_news

Revision ID: d4385ad5ebc0
Revises: f2a4d8e1c9b7
Create Date: 2026-06-03 18:14:42.935337
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'd4385ad5ebc0'
down_revision: Union[str, None] = 'f2a4d8e1c9b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE keyword     SET portal_type = 'DAUM_NEWS'   WHERE portal_type = 'DAUM'")
    op.execute("UPDATE keyword     SET portal_type = 'GOOGLE_NEWS' WHERE portal_type = 'GOOGLE'")
    op.execute("UPDATE article_url SET portal_type = 'DAUM_NEWS'   WHERE portal_type = 'DAUM'")
    op.execute("UPDATE article_url SET portal_type = 'GOOGLE_NEWS' WHERE portal_type = 'GOOGLE'")
    op.execute("UPDATE collection_log SET portal_type = 'DAUM_NEWS'   WHERE portal_type = 'DAUM'")
    op.execute("UPDATE collection_log SET portal_type = 'GOOGLE_NEWS' WHERE portal_type = 'GOOGLE'")


def downgrade() -> None:
    op.execute("UPDATE keyword     SET portal_type = 'DAUM'   WHERE portal_type = 'DAUM_NEWS'")
    op.execute("UPDATE keyword     SET portal_type = 'GOOGLE' WHERE portal_type = 'GOOGLE_NEWS'")
    op.execute("UPDATE article_url SET portal_type = 'DAUM'   WHERE portal_type = 'DAUM_NEWS'")
    op.execute("UPDATE article_url SET portal_type = 'GOOGLE' WHERE portal_type = 'GOOGLE_NEWS'")
    op.execute("UPDATE collection_log SET portal_type = 'DAUM'   WHERE portal_type = 'DAUM_NEWS'")
    op.execute("UPDATE collection_log SET portal_type = 'GOOGLE' WHERE portal_type = 'GOOGLE_NEWS'")
