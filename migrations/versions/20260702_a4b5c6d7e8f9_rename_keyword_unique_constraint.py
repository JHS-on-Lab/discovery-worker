"""rename t_keyword unique constraint: uq_keyword_portal → uq_keyword_source_type

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-07-02
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import text

revision: str = 'a4b5c6d7e8f9'
down_revision: Union[str, None] = 'f3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(conn, table: str, index: str) -> bool:
    r = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE table_schema = DATABASE() AND table_name = :t AND index_name = :i"
    ), {"t": table, "i": index})
    return r.scalar() > 0


def upgrade() -> None:
    conn = op.get_bind()
    if _index_exists(conn, 't_keyword', 'uq_keyword_portal'):
        conn.execute(text("ALTER TABLE `t_keyword` RENAME INDEX `uq_keyword_portal` TO `uq_keyword_source_type`"))


def downgrade() -> None:
    conn = op.get_bind()
    if _index_exists(conn, 't_keyword', 'uq_keyword_source_type'):
        conn.execute(text("ALTER TABLE `t_keyword` RENAME INDEX `uq_keyword_source_type` TO `uq_keyword_portal`"))
