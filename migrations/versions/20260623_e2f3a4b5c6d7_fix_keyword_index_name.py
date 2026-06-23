"""fix t_keyword next_discover_at index name

ix_t_keyword_next_discover_at → ix_keyword_next_discover_at
다른 인덱스 네이밍 규칙(t_ 접두사 없음)에 맞게 수정.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-23

"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import text

revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
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
    if _index_exists(conn, 't_keyword', 'ix_t_keyword_next_discover_at'):
        conn.execute(text("DROP INDEX `ix_t_keyword_next_discover_at` ON `t_keyword`"))
    if not _index_exists(conn, 't_keyword', 'ix_keyword_next_discover_at'):
        conn.execute(text("CREATE INDEX `ix_keyword_next_discover_at` ON `t_keyword` (`next_discover_at`)"))


def downgrade() -> None:
    conn = op.get_bind()
    if _index_exists(conn, 't_keyword', 'ix_keyword_next_discover_at'):
        conn.execute(text("DROP INDEX `ix_keyword_next_discover_at` ON `t_keyword`"))
    if not _index_exists(conn, 't_keyword', 'ix_t_keyword_next_discover_at'):
        conn.execute(text("CREATE INDEX `ix_t_keyword_next_discover_at` ON `t_keyword` (`next_discover_at`)"))
