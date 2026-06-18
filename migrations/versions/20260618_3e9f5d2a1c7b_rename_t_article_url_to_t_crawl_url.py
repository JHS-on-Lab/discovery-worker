"""rename t_article_url to t_crawl_url

Revision ID: 3e9f5d2a1c7b
Revises: 2f8a4c1b9d3e
Create Date: 2026-06-18

"""
from typing import Sequence, Union
from alembic import op

revision: str = '3e9f5d2a1c7b'
down_revision: Union[str, None] = '2f8a4c1b9d3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table('t_article_url', 't_crawl_url')

    # 구 인덱스 제거 (RENAME TABLE 은 인덱스명을 바꾸지 않음)
    op.drop_constraint('uq_article_url_hash',          't_crawl_url', type_='unique')
    op.drop_index('ix_t_article_url_status',           table_name='t_crawl_url')
    op.drop_index('ix_t_article_url_collected_date',   table_name='t_crawl_url')
    op.drop_index('ix_article_url_claim',              table_name='t_crawl_url')
    op.drop_index('ix_article_url_host',               table_name='t_crawl_url')
    op.drop_index('ix_article_url_keyword',            table_name='t_crawl_url')

    # 신규 인덱스 생성
    op.create_unique_constraint('uq_crawl_url_hash',       't_crawl_url', ['url_hash'])
    op.create_index('ix_crawl_url_status',                 't_crawl_url', ['status'])
    op.create_index('ix_crawl_url_collected_date',         't_crawl_url', ['collected_date'])
    op.create_index('ix_crawl_url_claim',                  't_crawl_url', ['status', 'next_retry_at', 'priority'])
    op.create_index('ix_crawl_url_host',                   't_crawl_url', ['host'])
    op.create_index('ix_crawl_url_keyword',                't_crawl_url', ['keyword_id'])


def downgrade() -> None:
    op.drop_index('ix_crawl_url_keyword',      table_name='t_crawl_url')
    op.drop_index('ix_crawl_url_host',         table_name='t_crawl_url')
    op.drop_index('ix_crawl_url_claim',        table_name='t_crawl_url')
    op.drop_index('ix_crawl_url_collected_date', table_name='t_crawl_url')
    op.drop_index('ix_crawl_url_status',       table_name='t_crawl_url')
    op.drop_constraint('uq_crawl_url_hash',    't_crawl_url', type_='unique')

    op.create_index('ix_article_url_keyword',          't_crawl_url', ['keyword_id'])
    op.create_index('ix_article_url_host',             't_crawl_url', ['host'])
    op.create_index('ix_article_url_claim',            't_crawl_url', ['status', 'next_retry_at', 'priority'])
    op.create_index('ix_t_article_url_collected_date', 't_crawl_url', ['collected_date'])
    op.create_index('ix_t_article_url_status',         't_crawl_url', ['status'])
    op.create_unique_constraint('uq_article_url_hash', 't_crawl_url', ['url_hash'])

    op.rename_table('t_crawl_url', 't_article_url')
