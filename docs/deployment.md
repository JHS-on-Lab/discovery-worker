# 컨테이너 배포 설계

> 단일 VM 위에 역할별 컨테이너를 Docker Compose 로 운영하는 방안을 정의한다.

---

## 목표

- **단일 VM** 에서 모든 컴포넌트 운영 (비용 최소화)
- 역할별로 컨테이너를 분리해 독립적으로 재시작·스케일 가능
- 추출 워커는 큐 적체에 따라 N대로 수평 확장 가능

---

## 기본 구성 (extractor 1대)

```
┌─────────────────────────────────────────────────────────────────┐
│                         단일 VM                                  │
│                                                                 │
│  ┌──────────────────┐  ┌────────────────┐  ┌──────────────────┐ │
│  │  discovery-naver_news │  │ discovery-daum │  │ discovery-google │ │
│  └──────────────────┘  └────────────────┘  └──────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────┐       │
│  │  extractor-1                                         │       │
│  │  --role extraction --worker-id extractor-1           │       │
│  │  (Reaper 데몬 스레드 내장)                             │      │
│  └──────────────────────────────────────────────────────┘       │
│                                                                 │
│  ┌──────────────────────────────────────────────────────┐       │
│  │  volume: ./data   volume: ./logs                     │       │
│  └──────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
         │  SSH Tunnel
         ▼
   AWS RDS (MySQL)
```

---

## 확장 구성 (extractor N대)

추출 큐(`article_url.status = discovered`)가 쌓이면 extractor 를 늘린다.  
**`FOR UPDATE SKIP LOCKED`** 덕분에 여러 extractor 가 동시에 돌아도 같은 URL 을 중복 처리하지 않는다.

```
┌─────────────────────────────────────────────────────────────┐
│                         단일 VM                              │
│                                                             │
│  [discovery 3대 — 동일]                                     │
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────┐  │
│  │  extractor-1    │  │  extractor-2    │  │ extractor-N│  │
│  │  worker-id: e-1 │  │  worker-id: e-2 │  │ worker-id: │  │
│  │  (Reaper 내장)  │  │  (Reaper 내장)   │  │ e-N        │  │
│  └────────┬────────┘  └────────┬────────┘  └─────┬──────┘  │
│           │                    │                  │         │
│           └────────────────────┼──────────────────┘         │
│                                │ FOR UPDATE SKIP LOCKED      │
│                                ▼                            │
│                    article_url 테이블                       │
│             (각 extractor 가 서로 다른 URL 처리)             │
└─────────────────────────────────────────────────────────────┘
```

### 언제 늘려야 하는가

```sql
-- 대기 중인 URL 건수 확인
SELECT status, COUNT(*) AS cnt
FROM article_url
WHERE status IN ('discovered', 'failed_transient')
GROUP BY status;
```

| 대기 건수 | 권장 extractor 수 |
|-----------|------------------|
| ~1,000    | 1대 (기본)        |
| ~5,000    | 2~3대            |
| ~10,000+  | 4~5대            |

---

## Docker Compose 설계

### 방법 A — `--scale` 플래그 (빠른 확장)

```yaml
# docker-compose.yml

services:

  discovery-naver_news:
    build: .
    command: python -m app --role discovery --portal naver_news --worker-id naver_news-1
    env_file: .env
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped

  discovery-daum:
    build: .
    command: python -m app --role discovery --portal daum_news --worker-id daum_news-1
    env_file: .env
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped

  discovery-google:
    build:
      context: .
      dockerfile: Dockerfile.google
    command: >
      xvfb-run --server-args="-screen 0 1920x1080x24"
      python -m app --role discovery --portal google_news --worker-id google-1
    env_file: .env
    volumes:
      - ./logs:/app/logs
    shm_size: 256mb
    restart: unless-stopped

  extractor:
    build: .
    # worker-id 를 hostname 으로 사용 → 컨테이너마다 자동으로 달라짐
    command: >
      sh -c "python -m app --role extraction --worker-id extractor-$$HOSTNAME"
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
```

실행:
```bash
# 기본 1대
docker compose up -d

# extractor 3대로 확장
docker compose up -d --scale extractor=3

# 다시 1대로 축소
docker compose up -d --scale extractor=1
```

### 방법 B — 명시적 서비스 정의 (권장, worker-id 명확)

```yaml
  extractor-1:
    build: .
    command: python -m app --role extraction --worker-id extractor-1
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped

  extractor-2:
    build: .
    command: python -m app --role extraction --worker-id extractor-2
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
```

평상시에는 `extractor-2` 를 주석 처리해두고 필요할 때만 활성화한다.

---

## Dockerfile 설계

### 기본 이미지 (naver_news / Daum / Extractor 공통)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini .

HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c \
    "import time, pathlib; t=float(pathlib.Path('/tmp/healthcheck').read_text()); exit(0 if time.time()-t < 120 else 1)" \
  || exit 1

CMD ["python", "-m", "app", "--role", "discovery", "--portal", "all"]
```

### Google Discovery 이미지 (Chrome + Xvfb 필요)

headless 모드(구형·신형 모두)는 Google Bot 감지에 걸린다.
`headless=False` 로 실제 브라우저로 실행하며, Linux 컨테이너에서는 Xvfb 가상 디스플레이가 필요하다.
Windows 로컬 개발에서는 창이 화면 밖으로 자동 이동된다.

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Chrome + Xvfb 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg xvfb \
    fonts-nanum \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub \
       | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] \
       http://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini .

HEALTHCHECK --interval=60s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c \
    "import time, pathlib; t=float(pathlib.Path('/tmp/healthcheck').read_text()); exit(0 if time.time()-t < 120 else 1)" \
  || exit 1

CMD ["xvfb-run", "--server-args=-screen 0 1920x1080x24", \
     "python", "-m", "app", "--role", "discovery", "--portal", "google"]
```

**`fonts-nanum` 설치 이유**: Chrome 이 한글을 렌더링할 때 폰트가 없으면 글자가 깨져
셀렉터가 예상치 못한 방식으로 동작할 수 있다.

**`--start-period=60s`**: Chrome 초기화가 일반 워커보다 오래 걸린다.

### docker-compose 서비스 분리 예시

```yaml
  discovery-naver_news:
    build:
      context: .
      dockerfile: Dockerfile          # 기본 이미지
    command: python -m app --role discovery --portal naver_news --worker-id naver_news-1
    env_file: .env.dev
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped

  discovery-google:
    build:
      context: .
      dockerfile: Dockerfile.google   # Chrome 이미지
    command: python -m app --role discovery --portal google_news --worker-id google-1
    env_file: .env.dev
    volumes:
      - ./logs:/app/logs
    shm_size: 256mb                   # Chrome 공유 메모리 부족 방지
    restart: unless-stopped
```

**`shm_size: 256mb`**: Chrome 은 `/dev/shm` 을 렌더링 버퍼로 사용한다.
Docker 기본값(64MB)으로는 부족해 크래시가 발생할 수 있다.

---

## 결정 사항

### 1. JSONL 동시 쓰기 — worker-id 별 파일 분리 (구현 완료)

FileSink 파일명: `data/{날짜}/{포털}-{worker_id}.jsonl`  
extractor 가 여러 대여도 각자 다른 파일에 쓰므로 충돌 없음.

- FileSink 는 테스트·일회성 용도가 주된 사용처이므로 충돌 가능성은 낮다.
- 실수로 동시에 돌리더라도 파일 수만 늘어날 뿐 데이터 손상은 없다.
- 운영에서 extractor N대를 상시 돌린다면 `SINK_TYPE=solr` 전환을 권장한다.

### 2. SSH 터널 — 환경별 분기 (기존 코드로 처리)

`TUNNEL_ENABLED` 환경변수로 이미 분기된다. 추가 코드 변경 없음.

| 환경 | 설정 방법 |
|------|-----------|
| **로컬 개발** | `.env` 에 `TUNNEL_ENABLED=true` + SSH 관련 변수 입력 |
| **개발·운영 서버** | `.env` 또는 환경변수에서 `TUNNEL_ENABLED` 미설정 (기본값 false) |

컨테이너 환경에서는 서버가 RDS 와 같은 VPC 안에 있으므로 SSH 터널 없이 직접 접속한다.  
`env_file: .env` 는 서버용 `.env` (TUNNEL_ENABLED 미포함)를 바라보게 한다.

### 3. Reaper — 각 extractor 에 내장 유지

별도 컨테이너 분리 시 구조 복잡도 증가 대비 이점이 없어 내장 방식 유지.

동시 UPDATE 성능 영향은 무시 가능:
- Reaper 대상은 300초 이상 방치된 좀비 rows — 정상 운영에서는 드물다.
- N개 Reaper 가 동시에 같은 WHERE 절로 UPDATE 해도 MySQL 이 row-level lock 으로 직렬화한다. 실질적으로 한 Reaper 만 rows 를 업데이트하고 나머지는 0건 UPDATE 로 반환.
- 5분마다 N번의 쿼리 — 부하 미미.

### 4. 로그 수집 — 현행 유지, error.log 필수

`app.log` (INFO 이상) + `error.log` (WARNING 이상) 이중 파일 구조를 유지한다.  
error.log 는 "왜 워커가 멈췄는가"를 추적하는 필수 파일이므로 반드시 보존한다.

모든 로그에 `worker_id` 필드가 포함되므로 컨테이너별 구분이 가능하다.  
컨테이너별 로그 경로를 분리하려면 `LOG_DIR=/app/logs/{worker_id}` 로 설정한다.

### 5. 헬스체크 — 파일 기반 heartbeat 추가 (구현 완료)

프로세스가 살아있어도 deadlock·hang 상태를 Docker 가 감지하지 못하므로 헬스체크는 필수.  
HTTP 엔드포인트 대신 파일 기반 방식 채택 (HTTP 서버 추가 불필요, 구조 단순).

**동작 방식**: 각 워커가 heartbeat 주기마다 `/tmp/healthcheck` 에 현재 타임스탬프를 기록.  
Docker healthcheck 가 파일 갱신 시각을 확인해 오래됐으면 컨테이너를 unhealthy 로 마킹.

Dockerfile 에 추가:
```dockerfile
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c \
    "import time, pathlib; t=float(pathlib.Path('/tmp/healthcheck').read_text()); exit(0 if time.time()-t < 120 else 1)" \
  || exit 1
```

- `--start-period=30s`: 워커 초기화 시간 허용
- `120s` 임계값: `HEARTBEAT_INTERVAL_SECONDS`(기본 60s) 의 2배 — 일시적 지연 허용

---

## 배포 순서 (구현 후 기준)

```bash
# 1. 이미지 빌드
docker compose build

# 2. DB 마이그레이션 (최초 1회)
docker compose run --rm extractor-1 python -m alembic upgrade head

# 3. 키워드 등록 (최초 1회)
docker compose run --rm extractor-1 python scripts/add_keyword.py --keyword "삼성전자" --portal naver_news

# 4. 전체 시작 (extractor 1대)
docker compose up -d

# 5. 큐 적체 시 extractor 증설
docker compose up -d --scale extractor=3   # 방법 A 사용 시
# 또는 docker-compose.yml 에서 extractor-2 주석 해제 후 up -d

# 6. 로그 확인
docker compose logs -f extractor-1
```

---

## 관련 문서

- [architecture.md](architecture.md) — 시스템 전체 구조
- [ops-commands.md](ops-commands.md) — 운영 명령어
- [quickstart.md](quickstart.md) — 로컬 개발 환경 시작
