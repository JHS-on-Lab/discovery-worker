# discovery-worker 운영 명령어

## 워커 실행

```bash
# 소스별 독립 실행 (권장 — 소스마다 차단 양상이 다름)
python -m app --source naver_news
python -m app --source naver_stock
python -m app --source daum_news
python -m app --source google_news

# 단일 프로세스로 전체 소스 처리 (소규모 운영)
python -m app --source all

# 워커 ID 명시 (같은 소스 여러 개 띄울 때)
python -m app --source naver_news --worker-id disc-naver-1
python -m app --source naver_news --worker-id disc-naver-2
```

## Docker 실행

```bash
# 이미지 빌드
./deploy/build.sh

# 워커 시작
./deploy/run.sh naver_news disc-naver-1
./deploy/run.sh daum_news  disc-daum-1
./deploy/run.sh all        disc-all-1

# 로그 확인
docker logs -f disc-naver-1
```

## 수동 발견 스크립트

```bash
# 특정 키워드 테스트 — DB 미기록
python scripts/run_discovery.py --source naver_news --keyword 삼성전자 --dry-run

# 특정 키워드 실행 + DB 저장
python scripts/run_discovery.py --source naver_news --keyword 삼성전자

# DB 에서 due 키워드 자동 선택
python scripts/run_discovery.py --source naver_news

# 페이지 수 제한
python scripts/run_discovery.py --source naver_news --keyword 삼성전자 --max-pages 2
```

## DB / 마이그레이션

`crawlerdb`(t_domain, t_crawl_url, t_keyword, t_collection_log) 스키마 마이그레이션은
이 프로젝트가 아니라 별도 저장소 `../crawlerdb-migrations`에서 관리한다.
discovery-worker는 더 이상 alembic을 포함하지 않는다.

```bash
cd ../crawlerdb-migrations
alembic upgrade head

alembic current
alembic history --verbose
alembic downgrade -1
```

## 유틸리티

```bash
# 스키마 검증
python scripts/verify_schema.py
python scripts/verify_schema.py --direct  # SSH 터널 없이 RDS에 직접 접속(같은 네트워크의 서버에서)

# DB 연결 상태 확인
python scripts/healthcheck.py
python scripts/healthcheck.py --direct
```

## Docker Compose 예시

```yaml
services:
  disc-naver-news:
    image: discovery-worker:latest
    command: ["--source", "naver_news"]
    env_file: .env.dev

  disc-naver-stock:
    image: discovery-worker:latest
    command: ["--source", "naver_stock"]
    env_file: .env.dev

  disc-daum:
    image: discovery-worker:latest
    command: ["--source", "daum_news"]
    env_file: .env.dev

  disc-google:
    image: discovery-worker:latest
    command: ["--source", "google_news"]
    env_file: .env.dev
```

## t_crawl_url 상태 참조

```sql
-- 상태별 현황
SELECT source_type, status, COUNT(*) AS cnt
FROM t_crawl_url
GROUP BY source_type, status
ORDER BY source_type, status;

-- due 키워드 현황
SELECT source_type, COUNT(*) AS total,
       SUM(enabled = 1) AS enabled,
       SUM(next_discover_at IS NULL OR next_discover_at <= NOW()) AS due_now
FROM t_keyword
GROUP BY source_type;
```
