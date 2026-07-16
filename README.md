# discovery-worker

크롤러 파이프라인의 **URL 발견 단계**를 담당하는 워커다. 기사 본문을 직접 가져오지
않고, 각 소스의 검색/목록 페이지를 훑어 URL만 찾아 공유 MariaDB 큐 테이블에 적재한다.

- `t_keyword` 테이블에서 활성화된 키워드(`source_type`별)를 읽어 해당 소스를 스크래핑하고,
  발견한 URL을 `t_crawl_url`에 `status=discovered`로 삽입(`url_hash` UNIQUE로 중복 방지,
  `INSERT ... ON DUPLICATE KEY UPDATE`).
- 지원 소스(어댑터 `app/adapters/`): `naver_news`, `naver_stock`, `daum_news`,
  `google_news`, `baidu_news`, `duckduckgo_news`(운영상 비활성 — 아래 참고)
- 이후 단계(본문 추출/저장)는 별도 프로젝트인 `extraction-worker`가 담당한다. 이 저장소는
  Fetcher/Extractor/Sink 로직을 갖지 않는다(구글/바이두 어댑터 자체 브라우저 자동화 제외).
- 상시 실행되는 워커 루프(`app/scheduling/dispatcher.py: run_discovery_loop`)로, `t_keyword`에서
  "실행 시각이 된"(`next_discover_at <= now`) 키워드를 폴링하며 낙관적 UPDATE로 하나씩 선점,
  발견 후 `t_collection_log`에 실행 기록을 남기고, 처리할 게 없으면 60초 대기 후 반복한다.
  `SIGTERM`/`SIGINT` 시 정상 종료.

DB 스키마 마이그레이션은 이 저장소가 아니라 별도 저장소 `../crawlerdb-migrations`(Alembic)에서
관리한다. 스키마 참고용 사본은 `docs/db/schema.sql`.

자세한 설계는 [docs/discovery-worker-design.md](docs/discovery-worker-design.md),
운영 커맨드는 [docs/ops-commands.md](docs/ops-commands.md),
로컬 셋업은 [docs/python-setup.md](docs/python-setup.md) 참고.

## 설치

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 실행 방법

### 로컬

```bash
python -m app --source <SOURCE> [--worker-id <ID>]

# 예시
python -m app --source naver_news
python -m app --source naver_stock
python -m app --source daum_news
python -m app --source google_news
python -m app --source baidu_news
python -m app --source all
python -m app --source naver_news --worker-id disc-naver-1
```

### CLI 인자

| 인자 | 설명 | 값 범위 | 기본값 |
|---|---|---|---|
| `--source` | 어떤 소스를 처리할지 (claim 쿼리의 `source_type` 필터) | `naver_news` \| `daum_news` \| `google_news` \| `baidu_news` \| `naver_stock` \| `duckduckgo_news`(운영상 비활성) \| `all` | 필수 (기본값 없음) |
| `--worker-id` | claim 소유권(`claimed_by`)/로그 상관관계용 워커 식별자. 같은 소스의 여러 레플리카를 띄울 때는 서로 다른 값 사용 (예: `disc-naver-1`, `disc-naver-2`) | 문자열 | env `WORKER_ID` (기본 `worker-1`) |

`--source all`은 한 프로세스에서 모든 소스를 처리(소규모 운영용)하며, 운영 환경에서는
소스별로 별도 프로세스를 띄워 개별적으로 스케일하는 것을 권장한다.

> **`duckduckgo_news`는 어댑터/CLI 옵션이 코드에 남아있지만 현재 실제 운영 대상
> 키워드는 없다(비활성 상태로 유지).** `baidu_news`는 활성 대상이다.

### Docker

```bash
./deploy/build.sh            # discovery-worker:latest 빌드
./deploy/build.sh v1.0.0     # 버전 태그 지정 (선택)

./deploy/run.sh naver_news disc-naver-1
./deploy/run.sh all disc-all-1
```

`deploy/run.sh <source> <worker_id>` 형태. `APP_ENV`(기본 `dev`) 기준 `.env.${APP_ENV}`를
로드하고, `~/apps/data/discovery-worker/{logs,output,chrome_profile_google,chrome_profile_baidu}`를
볼륨 마운트하며 `python -m app --source "${SOURCE}"`를 `--restart unless-stopped`로 실행한다.

베이스 이미지는 `mcr.microsoft.com/playwright/python:v1.59.0-noble` + `google-chrome-stable`
+ `xvfb`(구글/바이두 어댑터의 `undetected-chromedriver`용). Dockerfile에 `CMD`/`ENTRYPOINT`는
없으며 실행 커맨드는 `docker run`/compose 시점에 주입한다.

컨테이너 헬스체크: 백그라운드 스레드가 `HEARTBEAT_INTERVAL_SECONDS`마다 `/tmp/healthcheck`에
타임스탬프를 기록하며, `time.time() - mtime(/tmp/healthcheck) < 120`으로 판정한다. 같은 스레드가
좀비 Chrome 프로세스도 정리한다.

## 환경 변수

`.env`(공통) 로드 후 `.env.{APP_ENV}` 로 override (`APP_ENV` 기본값 `local`). 필수 항목
누락 시 `config.validate()`가 에러를 출력하고 종료한다.

**필수 (항상)**

| 변수 | 설명 | 예시 |
|---|---|---|
| `RDS_HOST` | MariaDB 호스트 | `db.internal.example.com` |
| `RDS_USER` | DB 사용자 | - |
| `RDS_PASSWORD` | DB 비밀번호 | - |
| `RDS_DB` | 스키마 이름 | `crawlerdb` |

**필수 (`TUNNEL_ENABLED=true`일 때만)**: `TUNNEL_SSH_HOST`, `TUNNEL_SSH_KEY_PATH`

| 변수 | 설명 | 값 범위 / 기본값 |
|---|---|---|
| `RDS_PORT` | MariaDB 포트 | 정수, 기본 `3306` |
| `WORKER_ID` | `--worker-id` 미지정 시 기본 워커 식별자 | 문자열, 기본 `worker-1` |
| `TUNNEL_ENABLED` | SSH 터널로 RDS 접속 (로컬 개발용) | bool, 기본 `false` |
| `TUNNEL_SSH_HOST` | bastion 호스트 | - |
| `TUNNEL_SSH_PORT` | SSH 포트 | 정수, 기본 `22` |
| `TUNNEL_SSH_USER` | SSH 사용자 | 기본 `ubuntu` |
| `TUNNEL_SSH_KEY_PATH` | 개인키 경로 | - |
| `TUNNEL_LOCAL_PORT` | 터널 로컬 포트 | 정수, 기본 `13306` |
| `HTTP_VERIFY_SSL` | TLS 인증서 검증 (사내 프록시 등에서 `false`) | bool, 기본 `true` |
| `DEFAULT_CRAWL_DELAY_MS` | 도메인별 기본 요청 간격 | 정수(ms), 기본 `1000` |
| `DEFAULT_RENDER_MODE` | 기본 페치 모드 | `static` \| `headless`, 기본 `static` |
| `PROXY_PROVIDER` | 프록시 백엔드 (현재 direct/단일 IP만 구현) | 기본 `direct` |
| `GOOGLE_DISCOVERY_MODE` | 구글 뉴스 탐색 전략 | `search`(기본) \| `rss`(봇 차단 시 폴백) |
| `GOOGLE_BLOCK_COOLDOWN_SEC` | 캡차/챌린지 감지 후 `rss` 모드 유지 시간 | 정수(s), 기본 `3600` |
| `GOOGLE_CHROME_PROFILE_DIR` | 구글 어댑터용 영속 Chrome 프로필 경로 (빈 문자열=휘발성) | 경로, 기본 `./chrome_profile_google` |
| `GOOGLE_PAGE_LOAD_TIMEOUT_SEC` | 구글 헤드리스 페이지 로드 타임아웃 | 정수(s), 기본 `30` |
| `BAIDU_CHROME_PROFILE_DIR` | 바이두 어댑터용 영속 Chrome 프로필 경로 | 경로, 기본 `./chrome_profile_baidu` |
| `BAIDU_PAGE_LOAD_TIMEOUT_SEC` | 바이두 헤드리스 페이지 로드 타임아웃 | 정수(s), 기본 `30` |
| `DAUM_NEWS_ALL` | 제휴 언론사만/전체 수집 여부 | bool, 기본 `true` |
| `NAVER_MAX_PAGES` | 네이버 뉴스 키워드당 최대 페이지 수 | 정수, 기본 `10` |
| `DAUM_MAX_PAGES` | 다음 최대 페이지 수 | 정수, 기본 `10` |
| `GOOGLE_MAX_PAGES` | 구글 최대 페이지 수 | 정수, 기본 `5` |
| `BAIDU_MAX_PAGES` | 바이두 최대 페이지 수 | 정수, 기본 `5` |
| `NAVER_STOCK_MAX_PAGES` | 네이버 종목토론방 최대 페이지 수 | 정수, 기본 `5` |
| `DUCKDUCKGO_MAX_PAGES` | DuckDuckGo(베트남어) 최대 페이지 수 | 정수, 기본 `5` |
| `LOG_DIR` | 로그 디렉토리 | 경로, 기본 `./logs` |
| `LOG_LEVEL` | 로그 레벨 | `INFO`\|`DEBUG`\|`WARNING` 등, 기본 `INFO` |
| `LOG_ROTATION` | 로테이션 방식 | `daily`\|`size`, 기본 `daily` |
| `LOG_RETAIN_DAYS` | 보관 일수 (daily) | 정수, 기본 `30` |
| `LOG_BACKUP_COUNT` | 보관 파일 개수 (size) | 정수, 기본 `10` |
| `HEARTBEAT_INTERVAL_SECONDS` | 하트비트 로그 + 헬스체크 파일 갱신 주기 | 정수(s), 기본 `60` |
| `DISCOVERY_403_RESCHEDULE_SEC` | HTTP 403 발생 시 키워드 재시도 지연 | 정수(s), 기본 `1800` |
| `BOT_DETECT_RETRY_SEC` | 봇 차단/캡차 감지 시 재시도 지연 | 정수(s), 기본 `1800` |

`SINK_TYPE`, `FILE_SINK_DIR`, `SOLR_*`, `RULES_CACHE_TTL_SECONDS`, `CLAIM_TIMEOUT_SECONDS`,
`MAX_ATTEMPTS`, `BACKOFF_*` 등은 `extraction-worker` 소관이며 이 저장소는 읽지 않는다.

## 유틸리티 스크립트 (`scripts/`)

| 스크립트 | 용도 | 인자 예시 |
|---|---|---|
| `run_discovery.py` | 워커 루프를 거치지 않고 수동으로 발견 실행 | `--source naver_news --keyword 삼성전자 --dry-run` \| `--source naver_news` (키워드 생략 시 DB에서 due한 키워드 자동 선택) \| `--max-pages 2` |
| `healthcheck.py` | DB 연결 확인 | 인자 없음/`--db`(둘 다 동일, 설정된 터널 경유) \| `--direct`(터널 생략, RDS 직접 접속) |
| `verify_schema.py` | 기대 테이블/컬럼/인덱스 존재 여부 검증 (`t_keyword`, `t_crawl_url`, `t_domain`, `t_collection_log`) | 인자 없음 \| `--direct` |

`run_discovery.py` 전체 인자: `--source`(필수), `--keyword`(생략 가능), `--max-pages`(정수),
`--dry-run`(DB 쓰기 없이 조회만), `--worker-id`(기본 `"script"`).

## 주요 라이브러리

`SQLAlchemy`/`PyMySQL`(DB, `SKIP LOCKED` 미사용 — MariaDB 10.5 대상), `sshtunnel`/`paramiko`(SSH 터널),
`httpx`(정적 페치), `selectolax`(HTML 파싱), `undetected-chromedriver`/`selenium`/`psutil`(구글·바이두
브라우저 자동화 및 좀비 프로세스 정리), `python-dotenv`(설정).

## masking_list.json

전화번호/이메일 마스킹 규칙 정의 파일이 남아있으나, 현재 이 저장소 코드에서는 참조되지
않는 레거시 파일이다(마스킹은 추출된 본문에 적용되므로 `extraction-worker`로 이관됨).
