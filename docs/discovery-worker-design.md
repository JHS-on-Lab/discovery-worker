# discovery-worker — 설계 문서

> 이 문서는 구현 에이전트(Claude Code)가 읽고 개발에 착수하기 위한 설계 명세다.
> 결정 사항은 근거와 함께 기록했으며, 명세에서 벗어나야 할 경우 이 문서를 먼저 갱신한다.
>
> **프로젝트 범위**: 본문 추출은 `extraction-worker` 프로젝트가 담당하며, 이 프로젝트(`discovery-worker`)는 URL 발견(Discovery) 단계만 담당한다.

---

## 1. 개요

키워드 기반으로 여러 포털 소스를 탐색해, 발견된 콘텐츠의 **URL·제목·본문·메타데이터**를 수집·저장하는 서비스다. 뉴스 기사에 국한되지 않고, 포털에서 키워드로 탐색 가능한 **모든 종류의 웹 콘텐츠**를 수집 대상으로 한다. 단발 스크립트가 아니라 운영(operation)을 전제로 한다.

- **대상 소스**: 네이버(뉴스·증권 종목토론), 다음 뉴스, 구글 뉴스, 바이두 뉴스, 덕덕고 뉴스(베트남어), 바오머이 뉴스(베트남어), 띤뗴(Tinh tế, 베트남어 IT 커뮤니티) (`source_type`: `NAVER_NEWS`, `NAVER_STOCK`, `DAUM_NEWS`, `GOOGLE_NEWS`, `BAIDU_NEWS`, `DUCKDUCKGO_NEWS`, `BAOMOI_NEWS`, `TINHTE_FORUM`)
- **수집 단위**: 키워드. 키워드는 RDB에 저장되며 각 키워드는 `source_type`을 가진다.  
  포털 검색 소스는 검색어, 증권 종목토론은 종목코드 등이 키워드가 된다.
- **수집 대상의 핵심**: 본문 전문(full text). 이것이 빠지면 의미가 없다.
- **확장 방식**: 워커 컨테이너를 늘려 병렬 처리.

### 1.1 스크래핑 전용(API 미사용) 결정

본문 전문이 필수인데, 어떤 소스도 공식 API로 본문 전문을 제공하지 않는다(네이버 검색 API는 제목·요약·링크·날짜만, 다음/카카오는 콘텐츠 전용 검색 API 자체가 없음, 네이버 증권 종목토론·웨이보는 공개 API 미제공). 따라서 **모든 소스를 스크래핑으로 처리**한다. 발견(검색 결과 수집)도, 추출(본문 파싱)도 스크래핑이다. 그 결과 운영의 핵심 난제는 API 쿼터가 아니라 **안티봇 회피와 IP 관리**다.

---

## 2. 핵심 설계 원칙

1. **설정은 코드가 아니라 데이터로.** 추출 규칙, 도메인 정책, 수집 주기 등 운영 중 바뀌는 것들은 코드에 박지 않고 DB에 둔다. 재배포 없이 바꿀 수 있어야 한다.
2. **단계는 함수 호출이 아니라 영속 테이블로 분리한다.** 발견과 추출은 서로를 호출하지 않고, RDB의 작업 테이블(`crawl_url`)을 통해서만 소통한다. 이 테이블이 두 단계의 인터페이스다.
3. **경계는 포트(인터페이스)로 둔다.** 이 프로젝트의 경계는 `SourceAdapter`(소스)다. 예: 프록시 공급자를 단일 IP→로테이팅으로 교체해도 다른 코드는 손대지 않는다. (Sink(저장소)·Extractor(추출) 포트는 `extraction-worker` 프로젝트 소관 — 4.1 참고.)
4. **실패를 일급으로 다룬다.** 차단을 "막는다"가 아니라 "맞아도 우아하게 물러났다 다시 온다"로 설계한다.
5. **테이블은 과하게 분리하지 않는다.** 상태·실패·재시도는 별도 테이블이 아니라 작업 테이블의 컬럼으로 흡수한다.

---

## 3. 아키텍처 개요

```mermaid
flowchart LR
  KW[(keyword<br/>RDB)] --> DISP[Discovery dispatcher<br/>cron 트리거]
  DISP --> DA[Discovery adapters<br/>NAVER_NEWS / NAVER_STOCK / DAUM_NEWS / GOOGLE_NEWS / BAIDU_NEWS / DUCKDUCKGO_NEWS / BAOMOI_NEWS / TINHTE_FORUM]
  DA -->|INSERT ON CONFLICT DO NOTHING| AU[(crawl_url<br/>큐 + 상태)]
  AU --> EX[Extraction workers]
  EX --> SINK{{Sink 포트}}
  SINK --> FILE[FileSink .jsonl]
  SINK --> SOLR[SolrSink]
  DA -. uses .-> FET[Fetcher<br/>HTTP · headless · proxy · rate-limit]
  EX -. uses .-> FET
  DOM[(domain<br/>규칙 + 정책)] -. 핫리로드 .-> EX
  DOM -. 정책 .-> FET
```

### 3.1 2단계 파이프라인

- **발견(Discovery)**: 입력 `(keyword, source_type)` → 출력은 콘텐츠 URL을 `crawl_url`에 `status=discovered`로 적재. 소스별 어댑터가 검색·목록 페이지를 스크래핑한다. 본문은 건드리지 않는다.
- **추출(Extraction)**: `crawl_url`에서 작업을 점유 → 콘텐츠 페이지를 가져와 제목·본문·메타를 파싱 → 성공 시 Sink에 기록하고 `status=stored`.

두 단계를 분리하는 이유: ① 발견 실패와 추출 실패가 서로 다른 재시도 단위로 격리된다, ② 발견이 적재한 URL은 일부 추출이 실패해도 손실되지 않는다, ③ 수동 재스크랩이 별도 파이프라인 없이 상태 변경만으로 가능해진다.

---

## 4. 모듈 구조

패키지는 책임별로 나눈다(아래는 권장 구조이며 언어는 Python).

```
app/
  adapters/            # SourceAdapter 구현: naver_news.py, naver_stock.py, daum_news.py, google_news.py, baidu_news.py, duckduckgo_news.py, baomoi_news.py, tinhte_forum.py
                       # _process_kill.py(Chrome 프로세스 강제종료), _profile_lock.py(프로필 디렉터리 flock) 는
                       # google_news/baidu_news 가 공유하는 브라우저 자동화 헬퍼
  fetch/               # HTTP 클라이언트: _client.py (발견 어댑터 공용)
  repository/          # RDB 접근: keyword_repo.py, crawl_url_repo.py, collection_log_repo.py
  scheduling/          # discovery dispatcher, overlap lock
  worker/              # discovery worker 루프
  domain_logic/        # URL 정규화
  config.py            # 환경변수/설정파일 로딩
  types.py             # DiscoverResult 등 핵심 타입
  ports.py             # SourceAdapter 포트(Protocol)
# 본문 추출(extraction), Sink, reaper — extraction-worker 프로젝트에 위치
# 관리 UI/API — crawler-admin 프로젝트에 위치
```

### 4.1 핵심 포트(인터페이스)

이 프로젝트(`app/ports.py`)가 실제로 정의하는 포트는 `SourceAdapter` 하나뿐이다.

```python
class SourceAdapter(Protocol):
    source_type: str
    def discover(self, keyword: str, cursor: str | None) -> DiscoverResult:
        """검색·목록 결과를 긁어 콘텐츠 URL 목록과 다음 cursor를 반환. 본문은 다루지 않음."""
```

> `Fetcher`/`Extractor`/`Sink` 포트는 `extraction-worker`에서 정의한다. 발견 어댑터의 HTTP 클라이언트는 별도 포트 없이 `app/fetch/_client.py`를 직접 호출한다.

### 4.2 실행 모델 — 소스별 독립 실행

`--source` 인자로 처리할 소스를 지정한다. **`--role` 플래그는 없다** — 이 프로젝트는 발견(Discovery) 전용이다. 본문 추출은 `extraction-worker` 프로젝트가 별도로 담당한다.

- `--source` : `naver_news` | `naver_stock` | `daum_news` | `google_news` | `baidu_news` | `duckduckgo_news` | `baomoi_news` | `tinhte_forum` | `all` — **점유 쿼리의 `WHERE source_type` 필터값**. 기본값 없음(필수).

```bash
python -m app --source naver_news   # 네이버 발견자
python -m app --source daum_news    # 다음 발견자
python -m app --source all          # 전체 소스 발견자 (소규모 운영)
```

```yaml
# discovery-worker — 소스별 발견 워커
services:
  discover-naver_news: { image: discovery-worker:latest, command: ["--source","naver_news"] }
  discover-daum_news:  { image: discovery-worker:latest, command: ["--source","daum_news"] }
  discover-google:     { image: discovery-worker:latest, command: ["--source","google_news"] }

# extraction-worker — 별도 프로젝트에서 실행
# extract: { image: extraction-worker:latest, deploy: { replicas: 3 } }
```

**권장 형태**: 발견은 소스별로 분리(스크래핑 대상·차단 양상·렌더링 방식이 소스마다 다름). 확장 시 병목인 소스만 replicas를 늘린다. 소규모일 땐 `--source all` 하나로 시작해 트래픽이 커지면 소스별로 무중단 분리.

**전제**: 프로세스는 독립이지만 **MySQL과 `crawl_url` 큐는 공유**한다(데이터 평면은 하나). 소스별로 물리적으로 다른 DB를 쓰는 분리는 이 설계 범위 밖이다.

---

## 5. 데이터 모델

### 5.1 RDB 테이블 (현재 4개: keyword / crawl_url / domain / collection_log)

> 이 절은 최초 설계 당시 "3개로 통합" 구상으로 작성됐으나, 실제 구현에서는 실행 로그를
> 위한 `t_collection_log`가 4번째 테이블로 추가됐고(§8.1, §12.4에서 상시 사용),
> `crawl_url.collected_date`/`domain.excluded` 컬럼도 이후 추가됐다. 아래 ERD는 최신
> 마이그레이션 기준 실제 스키마를 반영한 것이다(스키마 사본: `docs/db/schema.sql`, 마이그레이션
> 원본은 `../crawlerdb-migrations`).

```mermaid
erDiagram
  KEYWORD ||--o{ CRAWL_URL : discovers
  DOMAIN  ||--o{ CRAWL_URL : "policy / rules"
  KEYWORD ||--o{ COLLECTION_LOG : "run history"
  KEYWORD {
    bigint id PK
    string keyword
    string source_type
    string display_name
    int interval_seconds
    timestamp next_discover_at
    int retry_pending
    bool enabled
    int priority
    string disabled_reason
  }
  CRAWL_URL {
    bigint id PK
    string url
    string url_hash UK
    string host
    bigint keyword_id FK
    string source_type
    string status
    date collected_date
    int attempt_count
    string last_error_code
    string last_error_msg
    timestamp next_retry_at
    timestamp claimed_at
    string claimed_by
    bool is_manual
    int priority
    string extraction_method
    timestamp created_at
    timestamp updated_at
  }
  DOMAIN {
    string host PK
    bool excluded
    json rules_json
    bool rules_enabled
    int rules_version
    int crawl_delay_ms
    string render_mode
    string proxy_tier
    timestamp cooldown_until
    int recent_fail_count
    float success_rate
    int avg_body_len
    timestamp updated_at
    string updated_by
  }
  COLLECTION_LOG {
    bigint id PK
    string run_type
    string source_type
    bigint keyword_id FK
    date run_date
    int urls_found
    int urls_inserted
    int urls_skipped
    int urls_attempted
    int urls_success
    int urls_failed
    string error_msg
  }
```

**`keyword`** — 작업 원천이자 스케줄 상태. `interval_seconds`는 플레이스홀더가 아니라
`claim_next()`(`app/repository/keyword_repo.py`)가 실제로 읽어 `next_discover_at = NOW() +
INTERVAL :interval_seconds SECOND`로 재스케줄하는 데 쓰인다 — 모든 키워드가 기본값
86400(24시간)이라 지금은 사실상 "하루 1회"로 보이지만, DB 값만 바꾸면 코드 변경 없이
키워드별 주기를 다르게 줄 수 있다.

**`crawl_url`** — 시스템의 심장. 작업 큐 + 상태 기계 + 실패 보관소 역할을 한 테이블이 모두 담당한다. "실패 URL을 따로 보관"하는 요구는 별도 테이블이 아니라 `status` 값으로 흡수된다.
- `url_hash`에 **UNIQUE 제약** (중복 방지의 관문 — 6절 참고).
- `status` enum: `discovered`, `extracting`, `stored`, `failed_transient`, `failed_permanent`, `dead`. (`stored`는 성공 종료. 나중에 Solr를 붙이면 의미상 "indexed"에 해당.)
- `collected_date`: 발견된 날짜(대시보드/통계 집계용, `ix_crawl_url_collected_date` 인덱스).
- 인덱스: `url_hash`(unique), `(status, next_retry_at, priority)`(점유 쿼리용), `host`, `keyword_id`, `collected_date`.

**`domain`** — 도메인별 **예외만** 담는 희소(sparse) 테이블. 추출 규칙 + 수집 정책 + 차단기 상태 + 건강 지표를 한 행에 모았다. **모든 도메인이 행을 갖지 않는다.** 규칙/정책 오버라이드가 필요한 도메인만 행이 있고 나머지는 전부 기본값으로 동작한다.
- `excluded`: 이 host를 발견 단계에서부터 완전히 차단(하드 스킵). `crawl_url_repo`가 발견
  결과에서 `excluded=1` host를 필터링한다.
- `render_mode`: `static` | `headless`.
- `success_rate`/`avg_body_len`: 드리프트 감지용(11.4절).

**`collection_log`** — 발견/추출 실행(run) 단위 결과 로그. `run_type`이 `discovery`면
`urls_found`/`urls_inserted`/`urls_skipped`, `extraction`이면 `urls_attempted`/`urls_success`/
`urls_failed`를 채운다(어느 쪽 컬럼을 쓰는지는 `run_type`에 따라 갈리며, 이 프로젝트는
`discovery` 런만 기록한다). crawler-admin 대시보드와 `/logs` 페이지가 이 테이블을 조회한다.

### 5.2 파일 출력 형식 (초기 Sink)

- **결과 데이터**: JSON Lines(`.jsonl`), append 친화적. Solr 스키마와 동일한 필드명을 사용한다.
- **파티셔닝**: `data/{YYYY-MM-DD}/{source_type}-{worker_id}.jsonl` — 날짜·소스별로 나눠 관리·재적재를 조각 단위로.
- **운영 로그**: 수집 진행·하트비트·에러는 콘텐츠 데이터와 섞지 않고 별도 로그로 분리한다. 정보 로그와 **전용 에러 로그**를 또 나눈다 — 상세는 12절.
- CollectedContent 저장 필드: `id`(crawl_id), `crawler_type`, `crawl_runtime_key`, `host`, `site`, `url`, `title`, `content`, `author`(배열), `tstamp`(UTC), `doc_version`(1), `keyword_id`(배열), `etc_exact1`("1").

---

## 6. 중복 방지 (다른 키워드라도 같은 URL)

중복 제거는 **Sink가 아니라 RDB에서** 한다. 파일은 유니크를 강제할 수 없으므로, `crawl_url.url_hash` UNIQUE 제약이 유일한 관문이다.

- 발견 단계에서 URL을 찾으면 어느 키워드에서 왔든 `INSERT ... ON DUPLICATE KEY UPDATE`(또는 `INSERT IGNORE`)로 `url_hash` UNIQUE 키 기준 중복을 흡수한다.
- 새로 들어가면 추출 대상이 되고, 이미 있으면(다른 키워드가 먼저 넣었거나 과거에 넣었거나) 조용히 무시된다.
- 결과: **하나의 콘텐츠는 한 번만 추출되고 Sink에 한 번만 기록된다.** Sink가 파일이든 Solr든 동일하게 동작한다.

**URL 정규화 필수.** 해시 전에 정규화하지 않으면 같은 콘텐츠가 다른 URL로 보여 중복 제거가 안 먹는다. 정규화 규칙:
- 추적 파라미터 제거(`utm_*`, `fbclid` 등 화이트리스트 기반),
- 스킴/호스트 통일(http→https, 호스트 소문자, `www.` 처리 정책),
- 끝 슬래시·기본 포트·프래그먼트(`#...`) 제거,
- (가능하면) 모바일/데스크톱 주소 통일.
정규화된 URL로 `url_hash`(예: sha256)를 만든다.

> "이 URL을 어떤 키워드들이 매칭했는지"까지 추적하려면 conflict 시 `keyword_id`를 JSON 배열에 덧붙이는 옵션을 둘 수 있다. 중복 방지 자체에는 불필요.

---

## 7. 스케줄링 (cron 트리거)

현재 요구: **하루 1회 수집**, cron 사용. 단, cron은 "무엇을 수집할지"를 박지 않고 **트리거(틱)로만** 쓴다.

- cron이 하루 1회 발견 디스패처를 깨운다.
- 디스패처는 DB에서 `enabled` 키워드를 (추출과 동일하게 낙관적 클레임 — `UPDATE ... WHERE status=... AND ...` 후 `rowcount` 확인으로) 점유해 발견을 돌린다.
- 이 구조 덕분에 나중에 "이 키워드만 3시간마다"가 필요해지면 cron을 더 자주(예: 매시) 돌리고 디스패처가 `next_discover_at <= now`인 것만 집어가게 바꾸면 끝이다. 스키마·구조 변경 없음.

**cron의 치명적 단점 대비 — 실행 겹침 방지.** 수집이 다음 cron 틱을 넘기면 두 실행이 부딪힌다. 시작 시 잠금(`flock` 또는 DB 실행 락 행)을 잡아 **이전 실행이 안 끝났으면 이번 틱은 건너뛴다.** (cron 호스트 다운으로 그날 실행이 누락되는 것은 하루 주기에서는 감수.)

---

## 8. 발견 전략 (소스별)

> **이 절의 전략값(기간 필터 단위·정렬·중단 조건)은 유동적이다** — 고객 요청에 따라 바뀔 수 있다(13.1). 따라서 모두 발견 어댑터 내부와 설정값으로 격리하고, 추출·저장·실패 처리는 이에 의존하지 않는다.

발견의 목표는 "검색 결과에서 새 콘텐츠 URL만 추려 큐에 넣기"다. 핵심 난제는 **어디까지 긁고 멈출 것인가**이며, 이는 소스가 제공하는 정렬·기간 필터 기능에 따라 갈린다.

### 8.1 정밀 경계는 코드가, 거친 경계는 필터가

각 소스의 기간 필터는 보통 띄엄띄엄한 단위(1일 / 1주 / 1개월)뿐이라 "지난 36시간" 같은 정확한 경계를 표현할 수 없다. 그래서 역할을 나눈다.

- **기간 필터 = 넉넉한 하한.** 누락이 안 생기게 한 단계 넉넉히 고른다(어제치가 확실히 포함되도록, 필요하면 "1일" 대신 "1주"). 과수집분은 아래 두 장치가 받아낸다.
- **정밀 경계 = `collection_log` 기반 컷오프.** 매 실행은 "마지막 성공 수집 시각 이후"를 목표로 하고, 약간의 안전 겹침을 둬서 그보다 조금 이전부터 가져온다. 마지막 성공 시각은 `collection_log`에서 `MAX(started_at) WHERE keyword_id=? AND error_msg IS NULL`로 조회한다. 실행이 하루·이틀 밀려도 컷오프 기준으로 따라잡으므로 "1일 필터가 없어서 생기는 누락"이 사라진다.
- **최종 방어 = `url_hash` 중복 제거.** 겹쳐 들어온 과거 글은 6절 메커니즘으로 조용히 버려진다.

### 8.2 정렬 신뢰 가능 여부로 중단 전략이 갈린다

**증분 중단**("이미 본 URL을 만나면 그 뒤는 다 오래된 것이니 멈춤")은 결과가 **최신순 정렬**일 때만 성립한다. 요즘 검색 소스는 기본이 정확도순이라 신·구 콘텐츠가 섞여 나올 수 있어, 정렬을 신뢰할 수 없으면 증분 중단은 새 콘텐츠를 놓치게 한다. 그래서 두 경로로 나눈다.

- **정렬 신뢰 가능(최신순 강제 가능)**: 기간 필터 + 최신순 + **증분 중단**(이미 본 url_hash 또는 컷오프보다 오래된 콘텐츠를 만나면 그 지점에서 페이징/스크롤 종료). 값싸게 끝난다.
- **정렬 신뢰 불가(정확도순뿐)**: 기간 필터로 **결과 집합을 한정**한 뒤, 정렬을 믿지 않고 그 유한 집합을 끝까지 훑으며 콘텐츠마다 날짜로 판정해 컷오프보다 새것만 담는다. 멈춤 기준은 "헌 콘텐츠를 만나서"가 아니라 "필터로 좁혀진 결과를 다 봤거나 페이지/스크롤 상한 도달". 집합이 작으니 끝까지 봐도 부담이 적다.

### 8.3 소스별 전략표

| 소스 | 기간 필터 | 최신순 정렬 | 중단 전략 | render_mode | 비고 |
|---|---|---|---|---|---|
| 네이버 | 1일·1주 | 가능 | 증분 중단(정렬 신뢰) | static 우선 | 검색 결과가 무한 스크롤 → 9.5 |
| 다음 | 1일·1주 | 가능 | 증분 중단(정렬 신뢰) | static 우선 | SHOW_DNS=0 쿠키로 전체 언론사 수집. 제휴사(v.daum.net/v/) + 비제휴사(cp.news.search.daum.net/p/) 두 URL 패턴 처리 |
| 구글 | 1일·1주(`tbs=qdr:d` 등) | **없음** | 집합 한정 + 날짜 판정 + 상한 | **headless** | 안티봇 가장 공격적, 보수적 속도 |
| 바이두 | 없음(분석 결과 미발견) | 불가(초점순만) | 증분 중단 | **비headless**(undetected-chromedriver) | 9.4, 실서버 캡차 검증 진행 중 |

기간 필터 파라미터(예: 구글 `tbs=qdr:d`)는 비공식이라 바뀔 수 있으므로 **코드에 하드코딩하지 말고 설정값으로** 둔다. 필터가 깨지거나 무시되어도 폭주하지 않도록, 필터는 최적화 수단으로만 쓰고 페이지/스크롤 상한과 컷오프 판정을 항상 보험으로 깔아둔다.

### 8.4 바이두 뉴스 (구현 완료, 실서버 검증 진행 중)

`app/adapters/baidu_news.py`. 분석 결과:
- 검색: `www.baidu.com/s?tn=news&cl=2&word=...`, 페이지네이션은 `pn` offset(0,10,20,...).
- 결과 링크: 대부분 `baijiahao.baidu.com`(바이두 자체 게시 플랫폼) — daum의 리다이렉트 wrapper와 달리 이 자체가 최종 콘텐츠라 리다이렉트 해석 없이 그대로 저장한다.
- 기간 필터: 확인 안 됨(초점순 정렬만 노출). 최신순 정렬도 불가능해 보임 — 네이버/다음형이 아니라 구글형(집합 한정)에 가깝다.
- **봇 차단**: 순수 HTTP 요청(httpx)은 실서버 IP에서도 100% `wappass.baidu.com` 캡차로 리다이렉트됨 — 확인됨. 순정 헤드리스 Chrome(자동화 흔적 은닉 없이)도 동일 IP에서 캡차에 걸림 — IP 평판 기반 차단으로 추정. google_news.py 와 동일한 undetected-chromedriver + 행동 자연화(영구 프로필, 지터, 스크롤 시뮬레이션) 적용해 실서버에서 통과 여부 확인 중.
- 파싱 셀렉터(`#content_left h3 a`)는 캡차를 통과한 실제 페이지로 아직 검증 못 함 — 미검증 상태.

### 8.5 무한 스크롤 처리 (네이버 등)

검색 결과가 페이지네이션이 아니라 무한 스크롤인 경우:

1. **내부 요청 직접 호출을 먼저 시도.** 무한 스크롤은 대개 뒤에서 "다음 N개" API(보통 JSON)를 호출한다. 브라우저 개발자도구 Network 탭에서 그 요청의 URL·파라미터(오프셋/start)·응답 형태를 확인해, 호출 가능하면 headless 없이 정적 HTTP로 페이지네이션처럼 다룬다. 가장 가볍고 차단 위험도 낮다. 가장 가볍고 차단 위험도 낮다.
2. **막히면 headless 스크롤로 폴백.** 토큰·서명·쿠키로 내부 요청이 거부되면 headless로 스크롤한다. 단 무작정 끝까지가 아니라 9.1~9.2의 중단 조건(기간 필터·컷오프·상한)을 그대로 적용한다. 스크롤 후에는 고정 sleep 대신 "새 항목이 나타날 때까지 대기"하고, 한 세션 내 중복은 url_hash가 최종적으로 잡는다.

### 8.6 구글 뉴스 — 봇 차단 감지 및 RSS 폴백 조건

`app/adapters/google_news.py`. `GOOGLE_DISCOVERY_MODE`에 따라 두 모드로 동작(README 참고):

- **`search`(기본)**: `google.com/search?tbm=nws`를 undetected-chromedriver로 스크랩. 페이지네이션 가능.
- **`rss`**: Google News RSS를 정적 HTTP로 가져온 뒤, RSS의 CBMi 리다이렉트 URL(최종 언론사 URL이 아니라 구글의 wrapper URL)을 Chrome으로 하나씩 열어 `current_url`을 읽어 실제 URL로 변환. CBMi는 순수 HTTP 리다이렉트가 아니라 news.google.com 안에서 클라이언트사이드 JS로 최종 URL을 알아내는 방식이라 Chrome이 필수.

**RSS 폴백이 자동으로 발동하는 조건**(설정으로 처음부터 `rss`를 강제하는 경우 제외): `search` 모드에서 결과가 0건일 때, 그게 진짜 봇 차단인지 단순히 결과가 소진된 정상 상황인지를 구분해야 한다(`tbs=qdr:d` 최근 1일 필터상 페이지 깊이가 늘수록 결과가 정상적으로 0건이 되는 경우가 흔함). 아래 신호 중 하나라도 있어야 "진짜 차단"으로 판정한다(`_is_bot_block_page()`):

- `driver.current_url`에 `/sorry/`가 포함
- reCAPTCHA iframe 존재(`iframe[src*='recaptcha']`) — 클래스명/URL 패턴이라 언어 무관하게 유효
- `driver.page_source`에 다음 문구 중 하나 포함: `unusual traffic`, `비정상적인 트래픽`, `g-recaptcha`, `detected unusual traffic from your computer network` — 이 문구들은 hl=en/ko 로케일에서만 유효하다(§8.7 리전 오버라이드로 다른 언어를 쓰면 못 잡을 수 있음, 위 reCAPTCHA iframe 체크가 언어 무관 보조 신호)

차단으로 판정되면 `_search_blocked_until = now + GOOGLE_BLOCK_COOLDOWN_SEC`(기본 3600초)를 세팅하고 `BotBlockedError`를 던진다. **이 상태는 어댑터 인스턴스 하나에 저장되고, 그 인스턴스는 워커 프로세스 수명 동안 모든 키워드가 공유한다** — 즉 키워드 하나가 차단당하면 그 순간부터 쿨다운이 끝날 때까지 이 워커가 처리하는 **모든** 키워드가 `rss` 모드로 넘어간다. 쿨다운이 지나면 다음 `discover()` 호출에서 자동으로 `search` 모드 복귀를 시도한다.

**키워드별 403/봇차단 재시도(`dispatcher.py`, 5회·30분 간격)와의 상호작용**: 이 둘은 서로 다른 걸 겨냥한 게 아니라 저장 범위가 다르다 — 어댑터의 `_search_blocked_until`은 이 프로세스 메모리에만 있고(로컬 최적화, "나는 당분간 계속 막힐 테니 rss로"), 키워드별 재시도는 DB에 영구 기록된다(워커 간 공유, "이 키워드는 어느 워커가 붙어도 당분간 쉬자"). 실제로는 재시도 간격(30분)이 쿨다운(1시간)보다 짧아서, 차단당한 키워드가 자기 재시도 차례가 와도 그때까지 워커는 여전히 `rss` 모드라 — 다시 `search`를 시도하는 게 아니라 `rss`로 조용히 처리된다(`_discover_rss()`는 차단 감지 자체가 없음). 그래서 이 키워드의 재시도 카운터는 쿨다운이 완전히 끝난 뒤 `search`가 재개되고 그 키워드가 실제로 다시 차단당해야만 올라간다 — 워커가 여러 개(`disc-google-1`, `disc-google-2` 등) 떠 있는 배포에선 재시도가 어느 워커에 걸리느냐에 따라 결과가 달라질 수 있다.

**운영상 주의**: `rss` 모드는 캡차 회피 수단이지만 그 자체로 메모리 리스크가 있다 — CBMi 해석은 구글 도메인이 아니라 광고/트래커가 많은 외부 언론사 사이트를 연달아 여러 개 열기 때문에, 정상 `search` 페이지네이션(구글 도메인 안에 계속 머묾)과 달리 Chrome renderer 프로세스가 급증할 수 있다. 완화 조치(eager 로드, 광고 도메인 차단, URL별 탭 즉시 닫기 등)는 `docs/memory-oom-mitigation.md` 참고.

### 8.7 구글 리전 오버라이드 (`t_keyword.source_options_json`)

키워드별로 구글 검색/RSS 요청의 언어·국가를 바꾸고 싶을 때 `t_keyword.source_options_json`에
`{"region": "..."}` 형태로 저장한다. `region` 값은 `도메인/?hl=언어코드&gl=국가코드&ceid=국가코드:언어코드`
형식의 문자열이다 — `apply_source_options()`가 dispatcher를 통해 키워드 처리 직전에
어댑터에 주입하고(`_parse_region()`), `search`/`rss` 두 모드 모두에 반영된다.

**주의할 점**:
- 도메인만 바꾸는 건 의미가 없다 — `hl`/`gl`(및 rss의 `ceid`)을 쿼리스트링에 직접
  명시해야 실제로 언어/지역이 바뀐다. `rss` 모드는 news.google.com 단일 도메인으로
  서빙되고 로케일이 전부 쿼리 파라미터로 결정되므로 도메인 부분 자체는 무시된다.
- 도메인은 검증된 패턴(`google.com` 고정)을 따르는 게 안전하다 — `google.co.jp` 같은
  ccTLD를 실제로 검증해본 적은 없다.
- 값을 비워두면(대부분의 키워드) 기본값(`hl=ko`, `gl=KR`, `ceid=KR:ko`, 도메인
  `www.google.com`)으로 리셋된다 — 같은 어댑터 인스턴스가 여러 키워드를 연속 처리하므로
  리셋을 안 하면 이전 키워드의 리전이 다음 키워드로 새어 들어간다.
- crawler-admin의 키워드 등록/수정 폼에서 `GOOGLE_NEWS` 선택 시 "리전 오버라이드"
  필드로 편집 가능(`{"region": ...}` 껍데기 없이 안쪽 문자열만 입력).

**예시** (`source_options_json` 컬럼에 저장되는 값 기준):

| 국가/언어 | 값 |
|---|---|
| 한국(기본값, 오버라이드 불필요) | `NULL` |
| 미국(영어) | `{"region": "google.com/?hl=en&gl=us&ceid=US:en"}` |
| 베트남(베트남어) — 실제 검증됨 | `{"region": "google.com/?hl=vi&gl=vn&ceid=VN:vi"}` |
| 일본(일본어) | `{"region": "google.com/?hl=ja&gl=jp&ceid=JP:ja"}` |
| 사우디아라비아(아랍어) | `{"region": "google.com/?hl=ar&gl=sa&ceid=SA:ar"}` |
| 영국(영어, 미국과 다른 국가) | `{"region": "google.com/?hl=en&gl=gb&ceid=GB:en"}` |
| 프랑스(프랑스어) | `{"region": "google.com/?hl=fr&gl=fr&ceid=FR:fr"}` |

패턴: `hl`=언어 코드(소문자), `gl`=국가 코드(소문자), `ceid`=국가코드(대문자):언어코드(소문자).
새 리전을 추가하는 데 소스코드 수정은 필요 없다 — 위 표처럼 값만 채워 넣으면 된다.

---

## 9. 추출 전략 (라이브러리 우선, 규칙 보정)

수집된 URL 의 HTML이 제각각이라 초반에는 라이브러리가 대부분을 처리하고, 규칙은 실패가 잦은 소수 도메인에만 쌓인다.

체인 순서:
1. **도메인에 활성 규칙이 있으면 규칙 우선.** 규칙을 등록했다는 건 라이브러리가 못 미더운 도메인이라는 뜻이므로 라이브러리를 먼저 돌리면 "틀린 본문"을 통과시킬 위험이 있다.
2. 규칙이 없는(처음 보는) 도메인은 **라이브러리 체인**: 1차 추출기 → 실패 시 2차 추출기.
3. 둘 다 실패하면 추출 실패로 분류(10절).

**성공/실패 판정 기준**(폴백 트리거): 본문 길이가 임계값(예: 200자) 미만이거나 제목이 비면 실패로 보고 다음 전략으로.

### 9.1 규칙 = 데이터 (재배포 없는 핫리로드)

규칙은 코드가 아니라 `domain.rules_json`에 선언적으로 둔다. `type`은 앱에 미리 구현된 고정 엔진(`css`/`xpath`/`regex`)만 가리킨다 — 임의 코드 실행이 아니다. 후처리(`exclude`/`parse` 등)도 화이트리스트로 제한.

```json
{
  "title":        { "type": "css", "expr": "h2.headline", "attr": "text" },
  "body":         { "type": "css", "expr": "#article-body", "attr": "text", "exclude": [".ad", ".reporter"] },
  "published_at": { "type": "css", "expr": "span.date", "attr": "data-time", "parse": "datetime" },
  "press":        { "type": "css", "expr": "img.logo", "attr": "alt" }
}
```

**핫리로드 메커니즘**: 워커가 규칙을 메모리에 캐시하되 짧은 TTL(예: 60초)을 둔다. TTL 경과 시 `domain`에서 다시 읽는다. 관리자가 규칙을 고치면 길어야 1분 안에 모든 워커가 새 규칙을 쓴다 — 배포·재시작 없음. (더 즉각적이어야 하면 전역 `rules_version` 카운터를 두고 버전 변동 시에만 리로드.)

---

## 10. 실패 전략 (핵심)

### 10.1 URL 상태 기계

```mermaid
stateDiagram-v2
  [*] --> discovered
  discovered --> extracting: claim (optimistic UPDATE + rowcount)
  extracting --> stored: 성공
  extracting --> failed_transient: 타임아웃 / 429 / 5xx / 차단
  extracting --> failed_permanent: 404 / 410 / paywall / 본문 불가
  failed_transient --> extracting: 백오프 후 재시도 (next_retry_at)
  failed_transient --> dead: 최대 시도 초과
  failed_permanent --> discovered: 수동 재투입
  dead --> discovered: 수동 재투입
  stored --> [*]
```

### 10.2 실패 분류

| 분류 | 예시 에러 | 처리 |
|---|---|---|
| 일시(transient) | 타임아웃, 연결 끊김, 429, 502/503/504, 차단 감지 | `attempt_count++`, `next_retry_at` = 지수 백오프 + 지터, 재점유 대기 |
| 영구(permanent) | 404, 410, 하드 403, paywall, 모든 전략으로도 본문 불가 | 자동 재시도 안 함. 검토/수동 재투입 대상 |
| dead | 일시 실패가 최대 시도 초과 | 자동 재시도에서 제외, 검토 목록에 노출 |

### 10.3 6겹 안전장치

1. **Fetcher 내부 네트워크 재시도** — 짧은 일시 오류(커넥션 블립)용, 소수 회.
2. **URL 상태 기계** — 분류 + 지수 백오프(+지터) `next_retry_at`.
3. **도메인 차단기** — 한 도메인에서 429가 연달면 `domain.cooldown_until`을 세워 그 도메인 전체를 잠시 쉰다(개별 URL 백오프와 별개).
4. **점유 회수기(reaper)** — `status=extracting`인데 `claimed_at`이 타임아웃을 넘긴 row(워커 크래시 추정)를 주기적으로 `discovered`로 되돌린다.
5. **dead-letter** — 최대 시도 초과 시 `dead`로 격리.
6. **수동 재투입** — 운영자 주도(10.4).

### 10.4 수동 재스크랩

큐가 상태 컬럼을 가진 테이블이므로 별도 수동 파이프라인이 필요 없다.
- 관리 UI에서 실패 URL을 필터(소스·도메인·에러·기간)로 골라 "재투입" → `status=discovered`, `next_retry_at=now`, 필요 시 `attempt_count=0`, `manual=true`.
- 평소 추출 워커가 동일한 점유 로직으로 집어간다.
- **규칙 핫리로드와의 시너지**: 특정 도메인 때문에 실패가 쌓였을 때, 관리 UI에서 그 도메인 규칙을 등록(즉시 반영)하고 실패 URL을 재투입하면 워커가 새 규칙으로 다시 긁는다.
- 재투입에 **우선순위 레인**(`priority`)을 주면 평소 백로그에 안 밀린다.
- 멱등성: 같은 URL을 다시 처리해도 Sink가 Solr면 `url_hash` 문서 id로 upsert되어 안전.

---

## 11. 페치 / 안티봇

### 11.1 공용 Fetcher와 IP 분리

모든 워커의 네트워크 요청은 공용 Fetcher를 통해서만 나간다. 안티봇 로직(프록시·레이트리밋·헤드리스 폴백)이 한 곳에만 산다.

**핵심: 출구 IP를 컨테이너 수에서 분리한다.** "컨테이너 1개당 IP 1개"로 묶지 말고, 모든 요청을 **공용 프록시 레이어**로 흘리고 IP 회전은 거기서 일어나게 한다. 컨테이너는 파싱 처리량을 위해 늘리고, IP 다양성은 프록시 풀이 책임진다. 프록시는 **공급자 교체 가능한 인터페이스**로 두고(단일 IP도 그 인터페이스의 한 구현), 공급자 결정은 나중에 해도 코드 재작업이 없게 한다. (현재 프록시 환경 미정 — 13.1 참고.)

### 11.2 예의(politeness) — 공짜이자 1차 방어

- 도메인별 요청 속도 제한(`domain.crawl_delay_ms`),
- 사람처럼 보이는 무작위 지연,
- 실제 브라우저 같은 User-Agent·헤더, 세션 재사용,
- **한 도메인 세션 동안은 IP·UA를 유지**(매 요청 무작정 바꾸면 그게 봇 신호). IP와 헤더는 한 묶음으로 회전.
- 429/403 수신 → 해당 도메인 백오프(10.3-3) 신호로 사용.

### 11.3 수집 방식 — 정적 우선, 헤드리스 폴백

기본은 정적 HTTP(빠르고 가벼움), 막히는 소스만 헤드리스(Playwright, 무겁지만 강함). 소스별 기본값은 `domain.render_mode`로 제어.
- 네이버·다음: 정적 우선.
- **바이두·구글: 헤드리스 가능성 높음.** 특히 **구글이 넷 중 안티봇이 가장 공격적**이다(캡차·차단이 빠름). 구글 도메인은 `render_mode=headless` + 긴 `crawl_delay_ms` + 보수적 속도로 시작할 것. 바이두는 중국 외 IP 차단 가능성이 있으므로 중국 프록시 필요 여부를 먼저 확인한다.

### 11.4 드리프트 감지 루프

글마다 `extraction_method`와 본문 길이를 기록하고, `domain`의 `success_rate`·`avg_body_len`을 갱신한다. 특정 도메인의 성공률/평균 본문 길이가 급락하면 알림 → "이 도메인 규칙을 손볼 때"라는 신호 → 관리 UI에서 규칙 수정 → 핫리로드로 자동 반영. 루프가 닫힌다.

---

## 12. 관측성 / 로깅

워커(발견자·추출자)가 멈추거나 죽었을 때 **왜 멈췄는지를 로그만 보고 알 수 있어야** 한다. 이를 위해 두 종류의 실패를 명확히 분리한다.

- **항목(item) 단위 실패** — 개별 URL/키워드의 실패는 DB(`crawl_url.status`·`last_error_*`)에 기록한다(10절). 한 항목이 실패해도 워커는 다음 항목으로 계속 간다.
- **프로세스(worker) 단위 멈춤** — 워커 루프나 프로세스 자체가 멈추거나 죽는 것은 DB가 아니라 **로그로 진단**한다. 이 절의 초점이다.

### 12.1 로그 스트림 분리

- `app.log` (정보 로그): 정상 동작·진행·하트비트. 시끄러워도 된다.
- **`error.log` (전용 에러 로그)**: WARNING/ERROR 이상만 쌓는다. **멈춤 원인을 한 곳에서** 본다 — 단순함이 목적이다. "왜 멈췄나"는 `error.log`의 마지막 줄만 보면 되도록 설계한다.
- (선택) 더 단순하게 보고 싶으면 컴포넌트별로 `discovery.error.log` / `extraction.error.log`로 나눠도 된다. 기본은 공용 `error.log` + 엔트리의 `component` 필드로 구분.
- 정보 로그와 에러 로그는 **같은 에러를 양쪽에 모두** 남겨도 된다(정보 로그엔 맥락 흐름, 에러 로그엔 진단). 핵심은 에러 로그가 에러만으로 자급자족하는 것.

### 12.2 에러 엔트리 포맷 (자급자족)

한 줄에 진단에 필요한 컨텍스트를 다 담아, 다른 로그와 교차 참조 없이 원인을 알 수 있게 한다.

```
{ts} {level} {component} worker={worker_id} phase={phase} keyword_id={id} url_id={id} host={host} code={error_code} {message}
<여러 줄 traceback 블록>
```

예:
```
2026-05-30T09:14:02Z ERROR extraction worker=ex-3 phase=fetch keyword_id=- url_id=42 host=news.example.com code=TIMEOUT httpx.ReadTimeout: read timed out
Traceback (most recent call last):
  ...
```

- `component`: `discovery` | `extraction` (그 외 `dispatcher`/`reaper` 등).
- `phase`: 어디서 터졌는지(`startup`/`claim`/`fetch`/`parse`/`sink`/`shutdown`).
- `worker_id`: **어느 워커가** 멈췄는지 즉시 식별.

### 12.3 멈춤(halt) 종류별 필수 로깅

워커 루프 최상단에 포괄 예외 처리를 두고, 아래 세 경우를 반드시 남긴 뒤 종료한다. **조용히 죽지 않게** 하는 것이 원칙이다.

1. **미처리 예외로 죽을 때** — traceback을 `error.log`에 남기고(레벨 ERROR, `phase=...` 포함) 죽는다.
2. **시작 실패**(DB 연결 불가, 설정 누락, 마이그레이션 미적용 등) — 원인을 `error.log`에 남기고(`phase=startup`) 비정상 종료 코드로 exit.
3. **정상/시그널 종료**(SIGTERM 등) — `phase=shutdown reason=signal`처럼 종료 사유를 남긴다.

→ 결과적으로 **`error.log`의 마지막 줄이 곧 그 워커가 멈춘 이유**가 된다.

항목 단위 실패와 프로세스 치명 오류를 레벨로 구분한다: 항목 실패는 분류(10.2) 후 DB 기록 + 정보 로그(WARNING 이하)로, 루프 자체를 끝내는 치명 오류만 ERROR + `error.log`로. 한 항목의 실패가 워커 전체를 죽이지 않도록 항목 처리는 `catch → 분류 → DB 기록 → 다음 항목`으로 감싼다.

### 12.4 생존 신호(하트비트)

각 워커는 주기적으로(예: `HEARTBEAT_INTERVAL_SECONDS`) 진행 카운터(처리/성공/실패 수, 마지막 항목)를 정보 로그에 남긴다. 워커가 "멈춘 듯" 보일 때, **정보 로그의 마지막 하트비트 + `error.log`의 마지막 에러**를 함께 보면 "언제까지 살아 있었고 무엇 때문에 멈췄나"가 드러난다. (DB 쪽에서는 `claimed_at`이 멈춘 row를 reaper가 회수하므로(10.3-4), 로그는 원인 진단, DB는 복구를 담당한다.)

**Docker HEALTHCHECK 파일(`/tmp/healthcheck`) 갱신은 별도 백그라운드 스레드가 담당한다** (`app/scheduling/dispatcher.py:_start_healthcheck_thread`). 메인 루프의 로그 하트비트(위 문단)와 달리, 이 파일 갱신은 한 키워드 처리가 얼마나 오래 걸리든 `HEARTBEAT_INTERVAL_SECONDS` 주기로 계속 갱신된다 — google RSS 폴백처럼 한 키워드 안에서 URL 수십~백 개를 순차 처리하느라 다음 키워드로 넘어가기까지 수 분 걸리는 경우에도, Docker가 이를 hang으로 오판해 컨테이너를 강제 재시작하지 않도록 하기 위함이다. google_news/baidu_news 어댑터에 이미 걸려있는 page-load 타임아웃 덕에 메인 스레드가 진짜로 무한정 멈추는 경우가 없어서, 이렇게 분리해도 실제 hang을 놓칠 위험은 낮다.

### 12.5 운영 편의

- **로그 로테이션**(크기 또는 일자 기준)으로 `error.log`가 무한정 커지지 않게 한다.
- 한 수집 사이클을 묶어 보려면 상관 ID(`run_id`/`cycle_id`)를 엔트리에 포함(선택).

---

## 13. 기술 스택 / 의존성 (권장)

- **언어**: Python.
- **정적 HTTP**: `httpx`.
- **헤드리스**: 구글 발견 어댑터만 `undetected-chromedriver`(+ Xvfb) 사용. 그 외 소스는 정적 HTTP만으로 충분.
- **RDB**: **MariaDB 10.5**(확정, 공유 RDS). MariaDB 10.5는 `FOR UPDATE ... SKIP LOCKED`(MySQL 8.0+/MariaDB 10.6+ 전용)를 지원하지 않으므로, row 점유는 락 없이 **`UPDATE ... WHERE id=:id AND status IN (...)` 후 `rowcount` 확인**(낙관적 클레임)으로 처리한다 — `rowcount=1`이면 이 워커가 점유 성공, `0`이면 다른 워커가 이미 가져간 것이므로 다음 후보로 넘어간다. 단일 row 클레임에 한해 SKIP LOCKED와 기능적으로 동치이며, 버전 제약과 무관하게 동작한다. 접근은 `SQLAlchemy`.
  - **문자셋**: 테이블·컬럼·커넥션을 모두 `utf8mb4`로 통일한다. 바이두 중문과 한국어를 함께 다루므로, 이게 누락되면 저장 단계에서 문자가 깨진다.
  - **중복 삽입 구문**: PostgreSQL의 `ON CONFLICT DO NOTHING`에 해당하는 MySQL 구문은 `INSERT ... ON DUPLICATE KEY UPDATE`(또는 `INSERT IGNORE`)다. `url_hash` UNIQUE 키 기준으로 중복을 흡수한다.
- **설정**: 환경변수·설정파일(DB 아님).

> 본문 추출 라이브러리 체인(`trafilatura` 등), 규칙 기반 파싱(`lxml`/`selectolax`), Sink(`pysolr` 등)는 `extraction-worker`의 스택 — 이 프로젝트는 본문을 다루지 않는다.

### 13.1 미결 사항

- **프록시/IP 공급자 미정.** 발견 어댑터의 프록시 설정(`PROXY_PROVIDER`)으로 추상화해두고, 단일 IP 구현으로 시작 가능. 결정 시 구현만 추가.
- **URL 수집 전략(발견)은 유동적.** 기간 필터 단위·정렬·중단 조건 등은 고객 요청에 따라 바뀔 수 있다(8절). 발견 어댑터와 설정값으로 격리되어 있어, 전략이 바뀌어도 추출·저장·실패 처리 등 나머지 구조는 영향받지 않는다. 전략 미확정 상태에서도 개발을 시작할 수 있다.
- **바이두 발견 전략 미확정** — 기간 필터/정렬 지원 여부, 해외 접속 차단 및 중국 프록시 필요 여부 분석 필요(8.4).

---

## 14. 설정 (실제 키 — `app/config.py` 기준)

- **RDS**: `RDS_HOST`, `RDS_PORT`, `RDS_USER`, `RDS_PASSWORD`, `RDS_DB`
- **SSH 터널**(로컬 개발용, `TUNNEL_ENABLED=true`일 때만): `TUNNEL_SSH_HOST`, `TUNNEL_SSH_PORT`, `TUNNEL_SSH_USER`, `TUNNEL_SSH_KEY_PATH`, `TUNNEL_LOCAL_PORT`
- **워커**: `WORKER_ID`(점유 식별)
- **Fetcher 공통**: `DEFAULT_CRAWL_DELAY_MS`, `DEFAULT_RENDER_MODE`, `PROXY_PROVIDER`, `HTTP_VERIFY_SSL`
- **소스별 옵션**: `GOOGLE_DISCOVERY_MODE`(search|rss), `DAUM_NEWS_ALL`
- **소스별 최대 페이지 수**: `NAVER_MAX_PAGES`, `DAUM_MAX_PAGES`, `GOOGLE_MAX_PAGES`, `BAIDU_MAX_PAGES`, `NAVER_STOCK_MAX_PAGES`, `DUCKDUCKGO_MAX_PAGES`, `BAOMOI_MAX_PAGES`, `TINHTE_MAX_PAGES`
- **재시도/재스케줄**: `DISCOVERY_403_RESCHEDULE_SEC`, `BOT_DETECT_RETRY_SEC`
- **로깅**: `LOG_DIR`, `LOG_LEVEL`, `LOG_ROTATION`(daily|size), `LOG_RETAIN_DAYS`, `LOG_BACKUP_COUNT`
- **하트비트**: `HEARTBEAT_INTERVAL_SECONDS`

> `SINK_TYPE`/`FILE_SINK_DIR`/`SOLR_*`/`RULES_CACHE_TTL_SECONDS`/`CLAIM_TIMEOUT_SECONDS`(reaper)/`MAX_ATTEMPTS`/`BACKOFF_*` 등은 extraction-worker 소관 설정이며 이 프로젝트의 `config.py`에는 존재하지 않는다.

---

## 15. 단계별 개발 가이드 (Claude Code용)

이 절은 Claude Code로 **한 번에 한 모듈씩** 개발하기 위한 가이드다. 모듈 경계가 뚜렷하게 유지되는 것이 최우선이다.

### 15.1 두 가지 원칙

1. **인터페이스를 먼저, 구현을 나중에.** 모듈이 뚜렷하다는 건 모듈 사이의 경계(포트)가 먼저 못 박혀 있다는 뜻이다. 각 단계는 "이 포트를 구현한다"로 정의하고, 다른 모듈은 포트 시그니처만 알면 되게 한다. 그래야 한 번에 한 모듈씩 시켜도 다른 모듈을 건드리지 않는다.
2. **각 단계는 독립적으로 검증 가능해야 한다.** 단계마다 "어떻게 동작을 확인하는가"를 함께 둔다. 다음 단계로 넘어가기 전에 그 단계의 검증(테스트·실행)을 먼저 통과시킨다.

### 15.2 단계

각 단계는 그 자체로 실행/검증 가능한 상태를 목표로 한다.

**0. 뼈대와 계약(contract).** 코드 살을 붙이기 전에 패키지 구조 + 포트 인터페이스(`SourceAdapter`) + 핵심 데이터 타입(`DiscoverResult`)을 시그니처만 정의(구현은 비움). 설정 로딩과 로깅 골격(정보 로그 / 전용 `error.log` 분리)도 여기서. **가장 중요한 단계** — 여기서 경계가 잘 그어지면 나머지는 빈칸 채우기가 된다.
→ 검증: import 통과 + 타입 체크 통과.

**1. 저장소 + 스키마.** MariaDB 10.5 테이블 마이그레이션, `utf8mb4`, URL 정규화 + `url_hash`, `INSERT ... ON DUPLICATE KEY UPDATE` 중복 삽입, 낙관적 클레임(`UPDATE ... WHERE ... AND status=...` + `rowcount` 확인) 점유 쿼리. 다른 모듈에 의존하지 않아 가장 먼저 살을 붙이기 좋다.
→ 검증: 단위 테스트 — 중복 삽입해도 한 row만 남는가, 점유 쿼리가 같은 row를 두 번 주지 않는가.

**2. Fetcher(정적).** `app/fetch/_client.py`(정적 HTTP) — 레이트리밋 + 프록시 인터페이스(단일 IP 구현) + 네트워크 재시도. 헤드리스(undetected-chromedriver)는 Chrome 기반 어댑터(§2.2) 전용으로 별도 관리하고, 그 외 소스는 정적 HTTP만 사용.
→ 검증: 저장한 샘플·안전한 테스트 URL로 응답 확인.

**3. 발견(한 소스부터).** 소스 하나만 — 검색 → URL 목록 → 큐 적재. 디스패처 + cron 트리거 + 실행 겹침 잠금. 한 소스로 끝까지 동작시킨 뒤 같은 인터페이스로 나머지 소스를 추가.
→ 검증: 키워드 하나로 발견 → 큐에 URL이 쌓이는가.

**4. 나머지 소스 어댑터.** 8절의 소스별 발견 전략과 `docs/adapter-catalog.md`를 참고해 하나씩 추가.
→ 검증: 새 어댑터도 `make_adapter()`로 생성 가능하고 기존 어댑터와 동일한 dispatcher 루프에서 동작하는가.

**5. 헤드리스 폴백.** Chrome 기반 어댑터(§2.2)의 Playwright/undetected-chromedriver 통합. 컨테이너 이미지에 브라우저 바이너리·폰트 포함 주의.

**6. 관리 UI/API.** 별도 프로젝트 `crawler-admin`(FastAPI + Jinja2)으로 구현. 규칙 편집·테스트(URL 대입 미리보기)·enable/version/rollback, 실패 재투입, run-now(`next_discover_at=now`), 드리프트 모니터링.

### 15.3 Claude Code 지시 팁

- **한 번에 한 단계만.** 예: "0단계만 해줘. 구현 말고 인터페이스와 타입만." 범위를 좁히면 길을 잃지 않는다.
- **단계마다 문서로 닻 내리기.** "설계 문서 N절을 읽고 시작" 으로 시작해 문서와 어긋나지 않게 한다.
- **검증 먼저 통과.** 다음 단계로 넘어가기 전에 그 단계의 테스트·실행을 통과시킨다.
- **경계 고정.** 0단계 포트 정의 후에는 "다른 모듈의 인터페이스는 바꾸지 말고 이 모듈만" 이라고 못 박는다.

---

## 16. 개발 착수 전 확인 사항

코드 작성 전에 실측·결정해두면 재작업을 줄일 수 있는 항목들.

- **검색 결과 로딩 방식 실측.** 각 소스의 검색 결과를 정적 요청으로 받아 콘텐츠 링크가 HTML에 다 들어있는지 확인한다. 무한 스크롤·"더보기"·동적 로딩이면 정적으로는 일부만 잡힌다. 이 실측이 발견 어댑터를 static으로 짤지 headless로 짤지를 가르며, 무한 스크롤이면 내부 요청 직접 호출 가능 여부(8.5)도 함께 확인한다.
- **발행일시 정규화 규칙.** 소스 검색 결과의 날짜와 콘텐츠 페이지의 날짜가 다를 수 있고, 타임존·상대표기("3시간 전")가 섞인다. 추출 시 발행일시를 어떤 기준으로 정규화할지 미리 정한다(8절 컷오프 판정의 정확도와 직결).
- **"본문"의 경계 기준.** 기자명·소속·사진 캡션·관련콘텐츠·구독 안내를 본문에 포함할지 제외할지 일관 기준을 정한다(규칙 작성과 라이브러리 보정의 기준이 됨).
- **테스트 픽스처 확보.** 개발 중 실제 소스를 반복 호출하면 그 단계에서 IP가 차단될 수 있다. 검색 결과·콘텐츠 페이지 HTML을 몇 개 저장해두고 파서를 그 위에서 개발하면 네트워크 없이 빠르게 반복하고 차단도 피한다(4단계 전제).
- **법적·정책 검토.** 포털·언론사 robots.txt와 이용약관, 수집 본문의 보관·활용 범위(사내 분석 vs 외부 노출)에 따라 리스크가 다르다. 기술 결정이 아니라 조직 차원의 합의가 필요한 부분.

---

## 17. 범위 밖 / 향후

- 원천 HTML 아카이브는 **보관하지 않는다.** (재파싱 보정은 재크롤로만 가능 — 감수하기로 결정.) 향후 필요 시 별도 객체 저장소를 Sink 옆에 추가.
- 키워드별 가변 주기(`interval_seconds`)는 컬럼만 두고 지금은 미사용(cron 하루 1회). 필요 시 7절 방식으로 전환.
- 별도 메시지 큐(Redis/RabbitMQ)는 도입하지 않음. RDB 낙관적 클레임(`UPDATE` + `rowcount` 확인)으로 시작하고, 병목이 확인되면 그때 승격.

---

## 18. 의도적으로 만들지 않은 것 (과분리 방지)

- URL↔키워드 다대다 연결 테이블 — `url_hash` 중복 제거 + 최초 발견 키워드만 기록으로 갈음.
- 별도 실패 URL 테이블 — `crawl_url.status`로 흡수.
- 워커 등록/하트비트 테이블 — `claimed_by`/`claimed_at` + reaper로 갈음.
- 별도 발견 작업(job)/스케줄 테이블 — `keyword` 행의 컬럼으로 흡수.
- 설정 테이블 — 환경변수·설정파일로.
