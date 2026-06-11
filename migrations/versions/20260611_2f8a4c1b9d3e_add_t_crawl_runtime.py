"""add_t_crawl_runtime

Revision ID: 2f8a4c1b9d3e
Revises: 7631cbde8ede
Create Date: 2026-06-11

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '2f8a4c1b9d3e'
down_revision: Union[str, None] = '7631cbde8ede'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        't_crawl_runtime',
        sa.Column('runtime_name',    sa.String(50),   primary_key=True,
                  comment='런타임 식별자 (PK)'),
        sa.Column('crawler_type',    sa.String(50),   nullable=True,
                  comment='크롤러 유형'),
        sa.Column('country_code',    sa.CHAR(3),      nullable=True,
                  comment='국가 코드'),
        sa.Column('language',        sa.String(20),   nullable=True,
                  comment='언어'),
        sa.Column('solr_url',        sa.String(100),  nullable=True,
                  comment='Solr 접속 URL'),
        sa.Column('use_yn',          sa.Enum('Y', 'N'), nullable=False,
                  comment='사용 여부'),
        sa.Column('service_name',    sa.String(20),   nullable=True,
                  comment='서비스명'),
        sa.Column('thread_count',    sa.SmallInteger(), nullable=True,
                  comment='스레드 수'),
        sa.Column('registered_name', sa.String(20),  nullable=True,
                  comment='등록자'),
        sa.Column('registered_date', sa.DateTime(),  nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP'),
                  comment='등록일시'),
        sa.Column('last_run_date',   sa.DateTime(),  nullable=True,
                  comment='마지막 실행일시'),
        sa.Column('CHKTM',           sa.Integer(),   nullable=True,
                  comment='체크 타임스탬프'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )


def downgrade() -> None:
    op.drop_table('t_crawl_runtime')
