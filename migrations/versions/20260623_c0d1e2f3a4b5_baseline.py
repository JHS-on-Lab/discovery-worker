"""baseline — 현재 스키마 전체

Revision ID: c0d1e2f3a4b5
Revises:
Create Date: 2026-06-23

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c0d1e2f3a4b5'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        't_keyword',
        sa.Column('id',               sa.BigInteger(),    primary_key=True, autoincrement=True),
        sa.Column('keyword',          sa.String(255),     nullable=False,
                  comment='검색어 또는 식별자. NAVER_STOCK 은 종목코드 (예: 005930)'),
        sa.Column('source_type',      sa.String(20),      nullable=False,
                  comment='NAVER_NEWS | DAUM_NEWS | GOOGLE_NEWS | BAIDU_NEWS | NAVER_STOCK'),
        sa.Column('display_name',     sa.String(100),     nullable=True,
                  comment='사람이 읽기 쉬운 라벨. NAVER_STOCK: 종목명, GOOGLE: 다국어 키워드 설명 등'),
        sa.Column('enabled',          sa.Boolean(),       nullable=False, server_default=sa.text('1'),
                  comment='false = 비활성화. disabled_reason 컬럼에 이유 기록'),
        sa.Column('disabled_reason',  sa.String(200),     nullable=True,
                  comment='비활성화 이유. 예: 수동 중지 | 상장폐지 | 연속 5회 403'),
        sa.Column('priority',         sa.Integer(),       nullable=False, server_default=sa.text('0'),
                  comment='수집 우선순위. 높을수록 먼저 처리'),
        sa.Column('interval_seconds', sa.Integer(),       nullable=False, server_default=sa.text('86400'),
                  comment='수집 주기(초). 기본 86400 = 24시간'),
        sa.Column('next_discover_at', sa.DateTime(),      nullable=True),
        sa.Column('retry_pending',    sa.SmallInteger(),  nullable=False, server_default=sa.text('0'),
                  comment='다음 수집 시 full scan 필요 여부. 수집 중단(403 등) 시 1, 성공 완료 시 0'),
        sa.UniqueConstraint('keyword', 'source_type', name='uq_keyword_portal'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_keyword_next_discover_at', 't_keyword', ['next_discover_at'])

    op.create_table(
        't_crawl_url',
        sa.Column('id',                sa.BigInteger(),  primary_key=True, autoincrement=True),
        sa.Column('url',               sa.Text(),        nullable=False),
        sa.Column('url_hash',          sa.String(64),    nullable=False),
        sa.Column('host',              sa.String(255),   nullable=False),
        sa.Column('keyword_id',        sa.BigInteger(),  nullable=True),
        sa.Column('source_type',       sa.String(20),    nullable=False),
        sa.Column('status',            sa.String(30),    nullable=False, server_default='discovered'),
        sa.Column('attempt_count',     sa.Integer(),     nullable=False, server_default=sa.text('0')),
        sa.Column('last_error_code',   sa.String(50),    nullable=True),
        sa.Column('last_error_msg',    sa.String(500),   nullable=True),
        sa.Column('next_retry_at',     sa.DateTime(),    nullable=True),
        sa.Column('claimed_at',        sa.DateTime(),    nullable=True),
        sa.Column('claimed_by',        sa.String(100),   nullable=True),
        sa.Column('is_manual',         sa.Boolean(),     nullable=False, server_default=sa.text('0')),
        sa.Column('priority',          sa.Integer(),     nullable=False, server_default=sa.text('0')),
        sa.Column('extraction_method', sa.String(50),    nullable=True),
        sa.Column('collected_date',    sa.Date(),        nullable=True),
        sa.Column('created_at',        sa.DateTime(),    nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at',        sa.DateTime(),    nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('url_hash', name='uq_crawl_url_hash'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_crawl_url_status',         't_crawl_url', ['status'])
    op.create_index('ix_crawl_url_collected_date', 't_crawl_url', ['collected_date'])
    op.create_index('ix_crawl_url_claim',          't_crawl_url', ['status', 'next_retry_at', 'priority'])
    op.create_index('ix_crawl_url_host',           't_crawl_url', ['host'])
    op.create_index('ix_crawl_url_keyword',        't_crawl_url', ['keyword_id'])

    op.create_table(
        't_domain',
        sa.Column('host',              sa.String(255),  primary_key=True),
        sa.Column('rules_json',        sa.JSON(),       nullable=True),
        sa.Column('rules_enabled',     sa.Boolean(),    nullable=False, server_default=sa.text('1')),
        sa.Column('rules_version',     sa.Integer(),    nullable=False, server_default=sa.text('1')),
        sa.Column('crawl_delay_ms',    sa.Integer(),    nullable=True),
        sa.Column('render_mode',       sa.String(20),   nullable=True),
        sa.Column('proxy_tier',        sa.String(50),   nullable=True),
        sa.Column('cooldown_until',    sa.DateTime(),   nullable=True),
        sa.Column('recent_fail_count', sa.Integer(),    nullable=False, server_default=sa.text('0')),
        sa.Column('success_rate',      sa.Float(),      nullable=True),
        sa.Column('avg_body_len',      sa.Integer(),    nullable=True),
        sa.Column('updated_at',        sa.DateTime(),   nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_by',        sa.String(100),  nullable=True),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )

    op.create_table(
        't_collection_log',
        sa.Column('id',             sa.BigInteger(),  primary_key=True, autoincrement=True),
        sa.Column('run_type',       sa.String(20),    nullable=False),
        sa.Column('run_date',       sa.Date(),        nullable=False),
        sa.Column('keyword_id',     sa.BigInteger(),  nullable=True),
        sa.Column('source_type',    sa.String(20),    nullable=False),
        sa.Column('worker_id',      sa.String(100),   nullable=False),
        sa.Column('started_at',     sa.DateTime(),    nullable=False),
        sa.Column('duration_ms',    sa.Integer(),     nullable=False),
        sa.Column('urls_found',     sa.Integer(),     nullable=True),
        sa.Column('urls_inserted',  sa.Integer(),     nullable=True),
        sa.Column('urls_skipped',   sa.Integer(),     nullable=True),
        sa.Column('urls_attempted', sa.Integer(),     nullable=True),
        sa.Column('urls_success',   sa.Integer(),     nullable=True),
        sa.Column('urls_failed',    sa.Integer(),     nullable=True),
        sa.Column('error_msg',      sa.String(500),   nullable=True),
        sa.Column('created_at',     sa.DateTime(),    nullable=False, server_default=sa.text('NOW()')),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_collection_log_date_type',    't_collection_log', ['run_date', 'run_type'])
    op.create_index('ix_collection_log_keyword_date', 't_collection_log', ['keyword_id', 'run_date'])

    op.create_table(
        't_crawl_runtime',
        sa.Column('runtime_name',    sa.String(50),          primary_key=True,
                  comment='런타임 식별자 (PK)'),
        sa.Column('crawler_type',    sa.String(50),          nullable=True,
                  comment='크롤러 유형'),
        sa.Column('country_code',    sa.CHAR(3),             nullable=True,
                  comment='국가 코드'),
        sa.Column('language',        sa.String(20),          nullable=True,
                  comment='언어'),
        sa.Column('solr_url',        sa.String(100),         nullable=True,
                  comment='Solr 접속 URL'),
        sa.Column('use_yn',          sa.Enum('Y', 'N'),      nullable=False,
                  comment='사용 여부'),
        sa.Column('service_name',    sa.String(20),          nullable=True,
                  comment='서비스명'),
        sa.Column('thread_count',    sa.SmallInteger(),      nullable=True,
                  comment='스레드 수'),
        sa.Column('registered_name', sa.String(20),          nullable=True,
                  comment='등록자'),
        sa.Column('registered_date', sa.DateTime(),          nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP'),
                  comment='등록일시'),
        sa.Column('last_run_date',   sa.DateTime(),          nullable=True,
                  comment='마지막 실행일시'),
        sa.Column('CHKTM',           sa.Integer(),           nullable=True,
                  comment='체크 타임스탬프'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )


def downgrade() -> None:
    op.drop_table('t_crawl_runtime')
    op.drop_table('t_collection_log')
    op.drop_table('t_domain')
    op.drop_table('t_crawl_url')
    op.drop_table('t_keyword')
