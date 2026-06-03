# 아키텍처 개요

## 한 문장 요약

키워드를 DB에 등록하면, 발견 워커가 포털·소스에서 콘텐츠 URL을 수집하고, 추출 워커가 각 URL의 본문을 스크랩해 파일(또는 Solr)로 저장하는 2단계 파이프라인.

---

## 전체 데이터 흐름

```
[운영자]
    │
    │  add_keyword.py
    ▼
┌──────────┐      ┌──────────────┐      ┌────────────────┐
│ keyword  │      │  Discovery   │      │  article_url   │
│  테이블  │─────▶│   Worker     │─────▶│    테이블      │
│          │      │ (dispatcher) │      │ status=        │
│ 검색어 + │      │              │      │ discovered     │
│ 스케줄   │      │ 포털·소스   │      └───────┬────────┘
└──────────┘      │ 스크래핑    │              │
                  └──────────────┘              │
                                                │ claim_next()
                                                ▼
                                    ┌──────────────────────┐
                                    │  Extraction Worker   │
                                    │                      │
                                    │ fetch (HTTP/headless)│
                                    │   → extract          │
                                    │   → sink             │
                                    └──────────┬───────────┘
                                               │
                        ┌──────────────────────┼──────────────────────┐
                        ▼                      ▼                      ▼
                   status=stored       status=failed_*         status=dead
                        │
               ┌────────┴────────┐
               ▼                 ▼
          FileSink           SolrSink
       (.jsonl 파일)      (Solr 코어)
```

---

## 핵심 테이블 3개

### `keyword` — 수집 스케줄 관리

무엇을, 어느 포털에서, 얼마 주기로 수집할지 설정한다.

```
id │ keyword  │ portal_type │ interval_seconds │ next_discover_at
───┼──────────┼─────────────┼──────────────────┼──────────────────
 1 │ 삼성전자 │ naver_news       │ 86400 (1일)      │ 2026-06-01 09:00
 2 │ 삼성전자 │ DAUM        │ 86400            │ 2026-06-01 09:10
```

`next_discover_at <= NOW()` 가 되면 발견 워커가 그 키워드를 가져간다.

### `article_url` — 수집 큐 + 처리 이력

발견된 URL이 들어오고, 추출 워커가 처리하면서 상태가 바뀐다.

```
status 흐름:
  discovered → extracting → stored         (정상)
                          → failed_transient → (재시도)
                          → failed_permanent  (포기)
                          → dead             (최대 시도 초과)
```

### `collection_log` — 실행 이력

워커가 한 번 실행될 때마다 1행씩 기록된다. `run_type` 에 따라 쓰이는 컬럼이 다르다.

```
run_type=discovery  : keyword_id, urls_found, urls_inserted, urls_skipped, error_msg
run_type=extraction : urls_attempted, urls_success, urls_failed
```

`error_msg IS NOT NULL` 이면 해당 런이 예외(403 등)로 중단됐음을 의미한다.  
`keyword.last_discovered_at` 은 삭제됐고, 마지막 성공 수집 시각은 이 테이블에서 조회한다:

```sql
SELECT MAX(started_at) FROM collection_log
WHERE keyword_id = :kid AND run_type = 'discovery' AND error_msg IS NULL;
```

---

## 컴포넌트 맵

```
app/
│
├── adapters/          ← 소스별 콘텐츠 URL 수집 (HTTP 스크랩)
│   ├── naver_news.py         (sds-comps-base-layout 셀렉터)
│   ├── daum_news.py     (v.daum.net/v/ URL 패턴)
│   ├── google_news.py   (undetected-chromedriver, search/rss 모드)
│   ├── naver_stock.py   (네이버 증권 종목토론, 종목코드 키워드)
│   └── weibo_news.py    (전략 미확정 — 미구현)
│
├── scheduling/        ← 발견 워커 루프
│   └── dispatcher.py
│
├── fetch/             ← URL → HTML
│   ├── http_client.py   (정적 HTTP, 리다이렉트 자동 추적)
│   └── headless.py      (Playwright Chromium, JS 렌더링 필요 시)
│
├── extraction/        ← HTML → 제목·본문 (콘텐츠 타입 무관)
│   ├── extractor.py     (진입점: 규칙 우선, 폴백 LibraryChain)
│   ├── rule_engine.py   (도메인별 CSS/XPath 규칙, TTL 캐시 60s)
│   └── library_chain.py (trafilatura → readability 폴백)
│
├── sink/              ← 결과 저장
│   ├── file_sink.py     (data/{날짜}/{포털}-{worker_id}.jsonl)
│   └── solr_sink.py     (Solr 코어 upsert, url_hash → doc id)
│
├── worker/            ← 추출 워커 루프
│   ├── extraction_worker.py
│   ├── reaper.py        (5분 주기로 타임아웃 extracting 행 회수)
│   └── _healthcheck.py  (heartbeat 시 /tmp/healthcheck 갱신)
│
├── repository/        ← DB 접근
│   ├── keyword_repo.py
│   ├── article_url_repo.py
│   ├── domain_repo.py
│   └── collection_log_repo.py
│
└── domain_logic/      ← 순수 도메인 로직 (DB·네트워크 없음)
    ├── url_normalizer.py  (HTTP→HTTPS, 추적파라미터 제거, SHA256)
    ├── failure_classifier.py (HTTP 코드·예외 → ErrorCode, is_permanent)
    └── backoff.py         (지수 백오프 + jitter)
```

---

## 멀티 워커가 안전한 이유

같은 역할의 워커를 여러 개 동시에 띄워도 같은 작업을 중복 처리하지 않는다.

**발견 워커**: `keyword` 테이블에서 `FOR UPDATE SKIP LOCKED` 로 키워드를 가져간다.  
→ 워커 A가 "삼성전자/naver_news" 를 처리 중이면, 워커 B는 다른 키워드를 가져간다.

**추출 워커**: `article_url` 테이블에서 동일한 방식으로 URL을 하나씩 점유한다.  
→ 여러 워커가 동시에 돌아도 같은 URL을 중복 처리하지 않는다.

---

## 구현 현황

| 기능 | 상태 |
|------|------|
| discovery (naver_news / daum / google) | 완료 |
| discovery (naver_stock — 네이버 증권 종목토론) | 완료 — 종목코드를 keyword 로 등록 |
| extraction (FileSink / SolrSink) | 완료 |
| headless 렌더링 (Playwright) | 완료 — `domain.render_mode=headless` 설정 필요 |
| 도메인 규칙 엔진 (CSS/XPath, TTL 캐시) | 완료 |
| Reaper (좀비 extracting 자동 회수) | 완료 — extraction 워커 시작 시 daemon 스레드 자동 시작 |
| Docker healthcheck | 완료 — heartbeat마다 `/tmp/healthcheck` 갱신 |
| Weibo discovery | **미구현** — 전략 결정 후 `adapters/weibo_news.py` 구현 |

---

## 향후 과제

### [ ] RDB 데이터 보관 정책 구현

`article_url` 테이블은 현재 삭제 정책 없이 무한 누적된다.  
**방침: `stored` 상태 레코드는 수집일(`collected_date`) 기준 1개월 후 삭제.**

구현 시 결정해야 할 사항:
- 삭제 단위: `collected_date < NOW() - INTERVAL 1 MONTH` + `status = 'stored'`
- 실행 주체: 별도 cron 스크립트(`scripts/purge_old_articles.py`) 또는 DB 이벤트 스케줄러
- `collection_log`도 동일 기준으로 정리할지 여부
- `url_hash` UNIQUE 제약 — 삭제 후 같은 URL이 재수집되면 다시 `discovered`로 들어옴 (의도된 동작인지 확인)

> `collected_date` 컬럼과 `ix_article_url_claim` 인덱스가 이미 있어 대량 삭제 쿼리 효율은 확보돼 있다.

---

## 기술 스택

컴포넌트별로 사용하는 라이브러리와 그 이유를 정리한다.

### 어댑터별 fetch 전략 한눈에 보기

어댑터는 두 단계에서 HTTP를 사용한다. **Discovery**(URL 목록 수집)와 **Extraction**(콘텐츠 본문 렌더링)이 독립적이며 각각 다른 전략을 쓴다.

```
포털          Discovery fetch          Extraction fetch
─────────     ──────────────────────   ──────────────────────────────────────
naver_news         httpx (정적 HTTP)        httpx (정적, domain 기본값)
DAUM          httpx (정적 HTTP)        httpx (정적, domain 기본값)
GOOGLE        undetected-chromedriver  httpx (정적, 언론사마다 다를 수 있음)
NAVER_STOCK   httpx (정적 HTTP)        Playwright headless_with_iframe
                                        └─ finance.naver.com 에 domain 규칙 등록
WEIBO         미구현                   미구현
```

**Discovery fetch** — 각 어댑터에 고정 내장. 코드에서 직접 선택.

**Extraction fetch** — `domain` 테이블의 `render_mode` 로 도메인별 동적 결정.
도메인 행이 없으면 `static`(httpx) 이 기본값이다.

```bash
# 특정 도메인의 현재 fetch 전략 조회
.venv\Scripts\python.exe scripts\add_domain_rule.py --host finance.naver.com --show

# 전체 도메인 현황 (render_mode 포함)
SELECT host, render_mode, rules_enabled FROM domain ORDER BY host;
```

---

### Discovery (URL 수집)

| 포털 | 방식 | 라이브러리 | 엔드포인트 |
|------|------|-----------|-----------|
| naver_news | 정적 HTTP | **httpx** | `search.naver.com/search.naver?start=N` |
| DAUM | 정적 HTTP | **httpx** | `search.daum.net/search?w=news&p=N` |
| GOOGLE | 실제 브라우저 | **undetected-chromedriver** + Selenium | `google.com/search?tbm=nws` (search 모드) |
| NAVER_STOCK | 정적 HTTP | **httpx** | `finance.naver.com/item/board.naver?code={code}&page=N` |

**Google 특이사항**: `GOOGLE_DISCOVERY_MODE` 환경변수로 두 가지 모드 전환 가능
- `search` (기본) — `google.com/search?tbm=nws` 직접 스크랩, undetected-chromedriver 필요
- `rss` — `news.google.com/rss` 를 httpx로 가져오고, CBMi URL 변환에만 Chrome 사용

---

### Extraction (본문 추출)

#### Fetch 단계 — HTML 가져오기

| render_mode | 라이브러리 | 사용 조건 |
|-------------|-----------|---------|
| `static` (기본) | **httpx** | 정적 HTML 사이트 |
| `headless` | **Playwright** (Chromium) | JS 렌더링 필요 사이트 (SPA 등) |
| `headless_with_iframe` | **Playwright** (Chromium) | 본문이 cross-origin iframe 안에 있는 경우 (예: 네이버 증권 종목토론) |

`domain` 테이블의 `render_mode` 컬럼으로 도메인별 설정. 미설정 시 `static`.

`headless_with_iframe` 동작: 모든 iframe HTML을 꺼내 외부 문서 `</body>` 직전에 `<div id="frame_{name}">` 으로 주입 → 일반 CSS 셀렉터로 iframe 내부에 접근 가능.

#### Extract 단계 — 제목·본문 추출

우선순위대로 시도:

1. **RuleEngine** — `domain.rules_json` 에 CSS/XPath 규칙이 있으면 먼저 시도
   - CSS: **selectolax** (C 기반 HTML 파서, 빠름)
   - XPath: **lxml**
   - 규칙 없거나 실패 시 LibraryChain 으로 폴백

2. **LibraryChain** — 범용 라이브러리 체인
   - **trafilatura** — 뉴스 본문 특화 추출기 (1순위)
   - **readability-lxml** — 범용 가독성 추출기 (폴백)

---

### 공통 인프라

| 역할 | 라이브러리 | 비고 |
|------|-----------|------|
| HTTP 클라이언트 | **httpx** | 동기, 리다이렉트 자동 추적, 공통 User-Agent 헤더 |
| DB ORM / 연결 | **SQLAlchemy Core** + **PyMySQL** | ORM 매핑 없이 Core(텍스트 쿼리)만 사용. 경량. |
| DB 마이그레이션 | **Alembic** | `migrations/versions/` 에 버전별 파일 관리 |
| SSH 터널 | **sshtunnel** + **paramiko** | RDS 접근 시 bastion 경유. `.env` 의 `SSH_*` 설정 |
| Rate Limiter | 자체 구현 | `domain.crawl_delay_ms` 우선, 없으면 전역 기본값. 메모리 내 host별 마지막 요청 시각 추적 |
| 로깅 | Python 표준 `logging` | `app.log` (INFO+) / `error.log` (WARNING+) |

---

### 왜 chromedriver 와 Playwright 를 함께 쓰나

두 라이브러리는 역할이 다르다.

```
Discovery (Google)       Extraction (headless 도메인)
─────────────────        ──────────────────────────
undetected-chromedriver  Playwright (Chromium)
+ Selenium               + sync API

목적: 봇 감지 우회         목적: iframe 주입 등 세밀한 제어
headless=False 필수       headless=True (봇 감지 불필요)
페이지 수십 개 탐색        단일 URL 렌더링 후 종료
```

Google 검색은 headless 브라우저를 즉시 차단하므로 `undetected-chromedriver` 가 필수다.  
반면 네이버 증권처럼 iframe이 복잡한 페이지는 Playwright의 `page.frames` API가 더 적합하다.

---

## 관련 문서

| 주제 | 문서 |
|------|------|
| 처음 실행 | [quickstart.md](quickstart.md) |
| 운영 명령어 / SQL | [ops-commands.md](ops-commands.md) |
| 도메인 규칙 설정 | [domain-rules-guide.md](domain-rules-guide.md) |
| 컨테이너 배포 | [deployment.md](deployment.md) |
| 전체 설계 명세 | [keyword-collector-design.md](keyword-collector-design.md) |
| 네이버·다음 발견 전략 (403 재시도 포함) | [decisions/naver-discovery-strategy.md](decisions/naver-discovery-strategy.md) |
| 네이버 증권 종목토론 발견 | [decisions/naver-stock-discovery.md](decisions/naver-stock-discovery.md) |
| Google 발견 전략 | [decisions/google-discovery.md](decisions/google-discovery.md) |
