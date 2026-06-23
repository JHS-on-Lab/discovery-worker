"""create trendtracker.t_di_config_v1

rescrape-dispatcher 가 Solr 접속·쿼리 설정을 조회하는 테이블.
crawlerdb 가 아닌 trendtracker 스키마에 생성한다.

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-06-23

"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import text

revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'c0d1e2f3a4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS `trendtracker`.`t_di_config_v1` (
            `id`           BIGINT       NOT NULL AUTO_INCREMENT COMMENT '행 ID (PK)',
            `tnt_id`       VARCHAR(50)  NOT NULL                COMMENT '테넌트 ID',
            `project_id`   VARCHAR(50)  NOT NULL                COMMENT '프로젝트 ID',
            `di_server_ip` VARCHAR(50)  NOT NULL                COMMENT 'DI 서버 IP',
            `solr_url`     VARCHAR(500) NOT NULL                COMMENT 'Solr 코어 URL',
            `filter_query` VARCHAR(500) NULL                    COMMENT 'Solr fq 파라미터. NULL = 필터 없음',
            `use_yn`       ENUM('Y','N') NOT NULL DEFAULT 'Y'   COMMENT '활성화 여부',
            `created_at`   DATETIME     NOT NULL DEFAULT NOW()  COMMENT '등록일시',
            `updated_at`   DATETIME     NOT NULL DEFAULT NOW()  COMMENT '수정일시',
            PRIMARY KEY (`id`),
            UNIQUE KEY `uq_di_config` (`tnt_id`, `project_id`, `di_server_ip`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS `trendtracker`.`t_di_config_v1`"))
