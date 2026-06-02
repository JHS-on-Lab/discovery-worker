# 운영 명령어 모음

> 모든 명령은 프로젝트 루트(`c:\workspace\python\news-crawler`)에서 실행.  
> Python 실행: `.venv\Scripts\python.exe`

---

## 연결 / 스키마 확인

```bash
# SSH 터널 + RDS 연결 확인
.venv\Scripts\python.exe scripts\check_db.py

# 테이블·인덱스·SKIP LOCKED 지원 확인
.venv\Scripts\python.exe scripts\verify_schema.py
```

---

## 키워드 관리

### 등록 / 수정
```bash
# 기본 (1일 주기)
.venv\Scripts\python.exe scripts\add_keyword.py --keyword "삼성전자" --portal NAVER
.venv\Scripts\python.exe scripts\add_keyword.py --keyword "삼성전자" --portal DAUM
.venv\Scripts\python.exe scripts\add_keyword.py --keyword "삼성전자" --portal GOOGLE

# 주기 변경 (초 단위, 기본 86400=24시간)
.venv\Scripts\python.exe scripts\add_keyword.py --keyword "삼성전자" --portal NAVER --interval 43200

# 우선순위 설정 (높을수록 먼저 처리)
.venv\Scripts\python.exe scripts\add_keyword.py --keyword "삼성전자" --portal NAVER --priority 10
```

### 목록 / 상태 조회
```sql
SELECT id, keyword, portal_type, enabled, last_discovered_at, next_discover_at, priority
FROM keyword
ORDER BY portal_type, keyword;

-- 비활성 키워드
SELECT * FROM keyword WHERE enabled = false;
```

### 활성화 / 비활성화
```sql
UPDATE keyword SET enabled = false WHERE keyword = '삼성전자' AND portal_type = 'NAVER';
UPDATE keyword SET enabled = true  WHERE keyword = '삼성전자' AND portal_type = 'NAVER';
```

### 즉시 수집 예약
```sql
-- 특정 키워드 즉시 수집 (다음 루프 틱에 픽업됨)
UPDATE keyword SET next_discover_at = NOW() WHERE id = 1;

-- 포털 전체 즉시 수집
UPDATE keyword SET next_discover_at = NOW() WHERE portal_type = 'NAVER' AND enabled = true;
```

---

## 발견 (Discovery)

### 워커 실행 (자동 루프)
```bash
# 포털별 전용 워커
.venv\Scripts\python.exe -m news_crawler --role discovery --portal naver
.venv\Scripts\python.exe -m news_crawler --role discovery --portal daum
.venv\Scripts\python.exe -m news_crawler --role discovery --portal google

# 전체 포털 단일 워커
.venv\Scripts\python.exe -m news_crawler --role discovery --portal all

# worker-id 지정 (로그 식별, 멀티 인스턴스 시)
.venv\Scripts\python.exe -m news_crawler --role discovery --portal naver --worker-id naver-1
```

> **멀티 워커 안전성**: `FOR UPDATE SKIP LOCKED` 로 키워드 단위 잠금.  
> 같은 포털 워커 N대가 동시에 돌아도 같은 키워드를 중복 처리하지 않는다.  
> 점유 즉시 `next_discover_at` 을 `interval_seconds` 뒤로 갱신하므로 트랜잭션 완료 전에도 재점유 불가.

### Google 수집 모드 전환

봇 감지로 Google 검색 수집이 막혔을 때 RSS 모드로 전환한다.

```bash
# .env.local 또는 .env.dev 수정
GOOGLE_DISCOVERY_MODE=search   # 기본 — google.com/search 스크랩 (~50건/회)
GOOGLE_DISCOVERY_MODE=rss      # 대안 — RSS + Chrome CBMi 변환 (~100건/회)
```

변경 후 Google 워커를 재시작하면 즉시 적용된다.

### 수동 발견 (특정 키워드, 즉시)
```bash
# 기본 (1일치, 최대 3페이지)
.venv\Scripts\python.exe scripts\run_discovery.py --keyword "삼성전자" --portal NAVER
.venv\Scripts\python.exe scripts\run_discovery.py --keyword "삼성전자" --portal DAUM
.venv\Scripts\python.exe scripts\run_discovery.py --keyword "삼성전자" --portal GOOGLE

# 페이지 수 조정 (NAVER/DAUM)
.venv\Scripts\python.exe scripts\run_discovery.py --keyword "삼성전자" --portal NAVER --pages 10

# 기간 변경 (NAVER/DAUM 전용)
#   NAVER  pd: 4=1일(기본) 1=1주 2=1개월 3=오늘
#   DAUM period: d=1일(기본) w=1주 m=1개월
.venv\Scripts\python.exe scripts\run_discovery.py --keyword "삼성전자" --portal NAVER  --period 1
.venv\Scripts\python.exe scripts\run_discovery.py --keyword "삼성전자" --portal DAUM   --period w
```

### 어댑터 미리보기 (DB 저장 없음)
```bash
# 셀렉터 파손 확인, 키워드 등록 전 결과 검토
.venv\Scripts\python.exe scripts\preview_adapter.py --keyword "삼성전자" --portal NAVER
.venv\Scripts\python.exe scripts\preview_adapter.py --keyword "삼성전자" --portal DAUM   --pages 3
.venv\Scripts\python.exe scripts\preview_adapter.py --keyword "삼성전자" --portal GOOGLE --pages 2
```

### 발견 이력 조회
```sql
-- 오늘 발견 이력 전체 (실패 포함)
SELECT
    k.keyword, cl.portal_type,
    cl.started_at,
    ROUND(cl.duration_ms / 1000.0, 1) AS duration_sec,
    cl.urls_found, cl.urls_inserted, cl.urls_skipped,
    cl.error_msg
FROM collection_log cl
LEFT JOIN keyword k ON k.id = cl.keyword_id
WHERE cl.run_date = CURDATE() AND cl.run_type = 'discovery'
ORDER BY cl.started_at DESC;

-- 실패한 발견 런 (error_msg IS NOT NULL)
SELECT k.keyword, cl.portal_type, cl.started_at, cl.urls_found, cl.error_msg
FROM collection_log cl
LEFT JOIN keyword k ON k.id = cl.keyword_id
WHERE cl.run_date = CURDATE()
  AND cl.run_type = 'discovery'
  AND cl.error_msg IS NOT NULL;

-- 일자별 포털별 요약
SELECT
    run_date, portal_type,
    COUNT(*)                             AS runs,
    SUM(urls_found)                      AS total_found,
    SUM(urls_inserted)                   AS total_inserted,
    SUM(error_msg IS NOT NULL)           AS failed_runs,
    ROUND(AVG(duration_ms)/1000.0, 1)   AS avg_sec
FROM collection_log
WHERE run_type = 'discovery'
GROUP BY run_date, portal_type
ORDER BY run_date DESC, portal_type;
```

---

## 추출 (Extraction)

### Sink 선택 (.env)

```bash
# 파일 저장 (기본) — data/{날짜}/{포털}-{worker_id}.jsonl
# worker_id 는 --worker-id 인수 또는 WORKER_ID 환경변수 (기본값: worker-1)
SINK_TYPE=file

# Solr 저장
SINK_TYPE=solr
SOLR_URL=http://localhost:8983/solr/news
SOLR_BATCH_SIZE=100   # 선택, 기본 100
```

Solr 연결 확인:
```bash
.venv\Scripts\python.exe scripts\check_solr.py
```

### 워커 실행 (자동 루프)
```bash
# 자동 루프 — discovered + 재시도 대상 URL 을 계속 처리
.venv\Scripts\python.exe -m news_crawler --role extraction

# worker-id 지정
.venv\Scripts\python.exe -m news_crawler --role extraction --worker-id extractor-1
```

> 워커는 `discovered` 와 `failed_transient + next_retry_at <= NOW()` 를 모두 처리한다.  
> 처리할 URL 이 없으면 10초 sleep 후 재확인. 수동 개입 없이 재시도가 자동 처리된다.

### 수동 추출 (N건만 처리 후 종료)
```bash
# 기본: 50건
.venv\Scripts\python.exe scripts\run_extraction.py

# 건수 지정
.venv\Scripts\python.exe scripts\run_extraction.py --limit 100

# 전체 처리 (0 = 무제한)
.venv\Scripts\python.exe scripts\run_extraction.py --limit 0
```

### 추출 이력 조회
```sql
-- 오늘 추출 이력
SELECT portal_type, started_at,
       urls_attempted, urls_success, urls_failed
FROM collection_log
WHERE run_type = 'extraction' AND run_date = CURDATE()
ORDER BY started_at DESC;
```

### 저장 파일 구조
```
data/
  {YYYY-MM-DD}/
    NAVER-{worker_id}.jsonl
    DAUM-{worker_id}.jsonl
    GOOGLE-{worker_id}.jsonl
```

각 줄은 JSON 오브젝트 (Article 필드 전체 포함).  
extractor 를 여러 대 운영하면 worker-id 별로 파일이 분리된다.

---

## article_url 상태 관리

### 전체 현황
```sql
SELECT status, COUNT(*) AS cnt
FROM article_url
GROUP BY status
ORDER BY cnt DESC;
```

### 상태 흐름 요약

```
discovered → extracting → stored
                       → failed_permanent  (404·403 등 영구 오류)
                       → failed_transient  (429·5xx·timeout 등 일시 오류, 자동 재시도)
                       → dead              (attempt_count >= MAX_ATTEMPTS)
```

`failed_transient` 재시도 백오프: `30s * 2^attempt + jitter` (최대 3600s)

### 키워드·포털별 현황
```sql
SELECT k.keyword, k.portal_type, a.status, COUNT(*) AS cnt
FROM article_url a
JOIN keyword k ON a.keyword_id = k.id
GROUP BY k.keyword, k.portal_type, a.status
ORDER BY k.keyword, a.status;
```

### 실패 URL 조회
```sql
-- 일시 실패 (next_retry_at 도달 시 자동 재시도)
SELECT id, url, host, attempt_count, last_error_code, last_error_msg, next_retry_at
FROM article_url
WHERE status = 'failed_transient'
ORDER BY next_retry_at;

-- 영구 실패
SELECT id, url, host, last_error_code, last_error_msg
FROM article_url
WHERE status = 'failed_permanent'
ORDER BY updated_at DESC;

-- dead (최대 시도 횟수 초과)
SELECT id, url, host, attempt_count, last_error_code
FROM article_url
WHERE status = 'dead'
ORDER BY updated_at DESC;
```

### 실패 URL 재투입
```bash
# 현황 조회
.venv\Scripts\python.exe scripts\requeue_failed.py --show

# 전체 failed_permanent 재투입
.venv\Scripts\python.exe scripts\requeue_failed.py --status failed_permanent

# 특정 호스트의 dead URL 재투입 (도메인 규칙 수정 후)
.venv\Scripts\python.exe scripts\requeue_failed.py --status dead --host www.example.com

# 특정 에러 코드만 재투입
.venv\Scripts\python.exe scripts\requeue_failed.py --status failed_permanent --error-code PARSE_ERROR
```

SQL 직접 조작이 필요할 때:
```sql
UPDATE article_url
SET status = 'discovered', next_retry_at = NULL, attempt_count = 0
WHERE id = 123;
```

### 점유 중 멈춘 행 회수 (Reaper 자동 + 수동 확인)
```sql
-- 타임아웃 초과 extracting 행 확인
SELECT id, url, claimed_by, claimed_at,
       TIMESTAMPDIFF(SECOND, claimed_at, NOW()) AS elapsed_sec
FROM article_url
WHERE status = 'extracting'
  AND claimed_at < NOW() - INTERVAL 300 SECOND;

-- 강제 회수
UPDATE article_url
SET status = 'discovered', claimed_by = NULL, claimed_at = NULL
WHERE status = 'extracting'
  AND claimed_at < NOW() - INTERVAL 300 SECOND;
```

---

## 도메인 정책 관리

도메인별 오버라이드만 저장 (sparse). 행이 없으면 전역 기본값 사용.

### 조회
```sql
SELECT host, render_mode, crawl_delay_ms, rules_enabled, cooldown_until,
       success_rate, avg_body_len, recent_fail_count
FROM domain
ORDER BY host;
```

### 쿨다운 해제
```sql
UPDATE domain SET cooldown_until = NULL WHERE host = 'www.example.com';
```

### crawl_delay / render_mode 설정
```bash
# crawl_delay 설정 (ms)
.venv\Scripts\python.exe scripts\add_domain_rule.py --host www.example.com --delay 2000

# render_mode 설정
.venv\Scripts\python.exe scripts\add_domain_rule.py --host www.example.com --render headless

# 쿨다운 해제
.venv\Scripts\python.exe scripts\add_domain_rule.py --host www.example.com --cooldown-clear

# 현재 설정 조회
.venv\Scripts\python.exe scripts\add_domain_rule.py --host www.example.com --show
```

---

## 테이블 초기화

```bash
# 특정 테이블만 비우기
.venv\Scripts\python.exe scripts\truncate_table.py --table article_url
.venv\Scripts\python.exe scripts\truncate_table.py --table collection_log
.venv\Scripts\python.exe scripts\truncate_table.py --table domain
.venv\Scripts\python.exe scripts\truncate_table.py --table keyword

# 전체 테이블 한번에 비우기
.venv\Scripts\python.exe scripts\truncate_table.py --all
```

현재 행 수를 확인한 뒤 `yes` 입력 시 실행된다.

---

## 마이그레이션

```bash
# 현재 적용 버전 확인
.venv\Scripts\python.exe -m alembic current

# 최신 버전으로 업그레이드
.venv\Scripts\python.exe -m alembic upgrade head

# 한 단계 롤백
.venv\Scripts\python.exe -m alembic downgrade -1

# 이력 전체 조회
.venv\Scripts\python.exe -m alembic history --verbose
```

---

## 로그

```
logs/
  app.log    — INFO 이상 (진행·하트비트·정상 처리)
  error.log  — WARNING 이상 (실패·예외·경보)
```

로그 필드: `ts level [component] worker=X phase=Y item=Z host=W message`
