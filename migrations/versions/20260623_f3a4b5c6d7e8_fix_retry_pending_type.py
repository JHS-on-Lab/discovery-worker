"""fix t_keyword.retry_pending type: SMALLINT → BOOLEAN (TINYINT(1))

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-06-23
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        't_keyword', 'retry_pending',
        existing_type=sa.SmallInteger(),
        type_=sa.Boolean(),
        existing_nullable=False,
        existing_server_default=sa.text('0'),
    )


def downgrade() -> None:
    op.alter_column(
        't_keyword', 'retry_pending',
        existing_type=sa.Boolean(),
        type_=sa.SmallInteger(),
        existing_nullable=False,
        existing_server_default=sa.text('0'),
    )
