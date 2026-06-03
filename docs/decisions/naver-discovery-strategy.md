# 네이버 · 다음 뉴스 발견 전략

## 네이버 기본 동작

**엔드포인트**
```
GET https://search.naver.com/search.naver
    ?where=news&query={keyword}&sort=1&pd=4&start={offset}
```

| 파라미터 | 값 | 의미 |
|---|---|---|
| `sort` | `1` | 최신순 |
| `pd` | `4` | 1일 이내 (실측값, 공식 문서 없음) |
| `start` | `1 → 11 → 21 → ...` | 페이지네이션 오프셋 |

- 단순 HTTP GET, JS 실행 불필요 (`render_mode=static`)
- 셀렉터: 부모 클래스가 `sds-comps-base-layout` 인 `a[href]` — 빌드마다 해시가 바뀌는 `fender-ui_` 대신 사용
- 반환: 언론사 직접 URL (예: `https://www.mk.co.kr/article/...`)

**페이지 수 설정** (`.env`)
```
NAVER_MAX_PAGES=50   # 키워드당 최대 50페이지 = 최대 500건
```

---

---

## 다음 기본 동작

**엔드포인트**
```
GET https://search.daum.net/search
    ?w=news&q={keyword}&sort=recency&period=d&p={page}
```

| 파라미터 | 값 | 의미 |
|---|---|---|
| `period` | `d` | 1일 이내 (`w`=1주, `m`=1개월) |
| `p` | `1 → 2 → 3 → ...` | 페이지 번호 |

- 단순 HTTP GET, JS 실행 불필요
- 셀렉터: `a[href*="v.daum.net/v/"]` + `class=""` 조건 (썸네일 제외)
- 반환: Daum 뷰어 URL (예: `https://v.daum.net/v/20260603003218841`)
- 다음은 403 레이트리밋 이슈 없음 — 재시도 전략 불필요

**페이지 수 설정** (`.env`)
```
DAUM_MAX_PAGES=10   # 키워드당 최대 10페이지 = 최대 100건
```

---

## 공통 — 페이지네이션 재개 (last_cursor)

`keyword.last_cursor` 컬럼에 마지막으로 시도한 cursor 를 저장한다.

```
1회차
  page 1 (cursor=None)   → 성공, cursor = "start=11"
  page 2 (cursor="start=11") → 403 발생
    → keyword.last_cursor = "start=11"  저장

재시도 (30분 뒤)
  claim_next() 가 last_cursor="start=11" 반환
  page 2 (cursor="start=11") → 성공  ← page 1 재요청 없음
  page 3, 4, ... → 성공
  완료 → keyword.last_cursor = NULL  리셋
```

- page 1 실패 시: `last_cursor=NULL` → 재시도도 page 1부터
- 성공 완료 시: `last_cursor=NULL` → 다음 24h 수집은 항상 page 1부터
- 중복 기사: `url_hash` UNIQUE 로 DB 레벨에서 조용히 무시

---

## 403 실패 전략 (네이버 전용)

### 원인

네이버는 **IP 전체 차단이 아닌 쿼리별 레이트리밋**을 적용한다.
같은 키워드를 연속 여러 페이지 요청 시 403 발생. 다른 키워드 요청은 정상인 경우가 많다.

```
keyword A: page 1 성공 → page 2 403
keyword B: page 1 성공  ← 다른 쿼리라서 OK
```

### 재시도 흐름

```
403 발생 (_run_one 내부에서 처리)
  ↓
keyword.last_cursor = 실패한 cursor 저장
collection_log 에 error_msg = "HTTPStatusError: 403..." 기록

오늘 403 횟수 조회 (collection_log COUNT)
  ├─ count < 5  → keyword.next_discover_at = NOW() + DISCOVERY_403_RESCHEDULE_SEC
  │               WARNING: "403 '{keyword}' cursor={cursor} N/5 retry=HH:MMKST"
  │               60초 대기 후 다음 키워드 처리 (IP 레벨 냉각)
  └─ count >= 5 → 포기, next_discover_at 는 claim_next 시 설정한 +24h 유지
                  WARNING: "403 '{keyword}' cursor={cursor} gave_up=5 next=24h"
```

재시도 유예 시간: `.env` 의 `DISCOVERY_403_RESCHEDULE_SEC` (기본 1800초 = 30분).

### 재시도 횟수 근거

메모리가 아닌 `collection_log` 에서 집계하므로 **워커 재시작에도 카운트가 유지**된다.

```sql
SELECT COUNT(*)
FROM collection_log
WHERE keyword_id = :kid
  AND error_msg LIKE '%403%'
  AND run_date = CURDATE()   -- UTC 기준
```

로그에 표시되는 회차는 `count+1` (현재 시도 번호):

1회차 시도: rows=0 → 로그 `1/5`, reschedule  
2회차 시도: rows=1 → 로그 `2/5`, reschedule  
…  
5회차 시도: rows=4 → 로그 `5/5`, reschedule  
6회차 시도: rows=5, 5 >= 5 → 포기

### 200 + 빈 HTML

403 대신 200으로 차단 페이지를 반환하는 경우.

```
GET → 200, 하지만 sds-comps-base-layout 셀렉터에 매칭 없음 → urls=[]
  ↓
WARNING [adapter] naver_news 0 urls keyword='...' page=N
collection_log: urls_found=0, error_msg=NULL (정상 처리)
```

에러로 간주하지 않음. 0건 수집은 그날 뉴스가 없는 정상 케이스도 있음.

---

### 0건 WARNING 사후처리 — 봇 감지 vs 셀렉터 파손

`error.log` 에서 아래 패턴이 반복될 때의 진단·조치 절차.

```
WARNING [adapter] naver_news 0 urls keyword='...' page=N — bot detection or sds-comps-base-layout change
```

**주의**: 크롤러는 멈추지 않는다. 해당 키워드가 조용히 0건으로 기록될 뿐이므로  
방치하면 수집 누락이 무기한 지속된다.

---

#### Step 1 — 케이스 구분

| 관찰 패턴 | 우선 의심 원인 |
|---|---|
| page=1 에서 0건 (여러 키워드 동시) | **셀렉터 파손** — 클래스명 일괄 변경 |
| page=1 에서 0건 (일부 키워드만) | 봇 감지 or 해당 키워드 뉴스 없음 |
| page=5 이상에서 0건 | 봇 감지 (연속 요청 차단) |

미리보기 스크립트로 실제 URL 반환 여부 확인:

```bash
# DB 저장 없이 셀렉터 동작만 확인
.venv\Scripts\python.exe scripts\preview_adapter.py --keyword "삼성전자" --portal naver_news

# 0건이면 HTML 덤프 후 브라우저로 열어 구조 확인
python - <<'EOF'
import httpx
r = httpx.get(
    "https://search.naver.com/search.naver",
    params={"where": "news", "query": "삼성전자", "sort": "1", "pd": "4", "start": "1"},
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    follow_redirects=True,
)
open("naver_debug.html", "w", encoding="utf-8").write(r.text)
print(r.status_code, len(r.text))
EOF
```

`naver_debug.html` 을 브라우저에서 열어 기사 링크 요소의 부모 클래스를 DevTools 로 확인한다.

---

#### Case A — 봇 감지

증상: `preview_adapter.py` 를 수동 실행하면 URL 이 정상 반환되지만  
워커가 연속 요청 중에 0건이 발생하는 경우.

**조치 1 — delay 상향 (즉시 적용)**

`.env.local` 또는 `.env.dev` 수정 후 워커 재시작:

```bash
# 기본값 800ms → 1500~2000ms 로 상향
NAVER_CRAWL_DELAY_MS=1500
```

**조치 2 — max_pages 축소**

연속 페이지가 많을수록 감지율 상승. 임시로 줄여서 완화:

```bash
NAVER_MAX_PAGES=10   # 기본 50 → 10으로 임시 축소
```

안정화 확인 후 단계적으로 복원한다.

**조치 3 — headless 전환 (조치 1·2 로 해결 안 될 때)**

Playwright 는 쿠키·세션을 유지해 봇 감지 우회 가능성이 높다.  
단, 리소스 비용이 크므로 최후 수단으로 사용.

현재 NaverNewsAdapter 는 `render_mode=static` 고정이므로  
헤드리스 전환은 코드 수정 또는 별도 어댑터 분기가 필요하다 (미구현).

```sql
-- headless 전환 후 domain 테이블에 기록 (미래 참조용)
INSERT INTO domain (host, render_mode, crawl_delay_ms)
VALUES ('search.naver.com', 'headless', 2000)
ON DUPLICATE KEY UPDATE render_mode='headless', crawl_delay_ms=2000;
```

---

#### Case B — sds-comps-base-layout 셀렉터 파손

증상: `preview_adapter.py` 수동 실행에서도 0건이고,  
`naver_debug.html` 에서 `sds-comps-base-layout` 클래스를 찾을 수 없는 경우.

**진단: 새 클래스명 찾기**

`naver_debug.html` 을 열고 DevTools 에서 기사 제목 링크 요소의 부모 `<div>` 클래스 확인.

또는 Python 으로 후보 추출:

```python
from selectolax.parser import HTMLParser

html = open("naver_debug.html", encoding="utf-8").read()
tree = HTMLParser(html)

# 기사 링크 후보 찾기 (href 가 언론사 직링크인 a 태그)
for a in tree.css("a[href^='http']"):
    href = a.attributes.get("href", "")
    parent_class = (a.parent.attributes.get("class") or "") if a.parent else ""
    if "mk.co.kr" in href or "chosun.com" in href or "yna.co.kr" in href:
        print(repr(parent_class), href[:80])
```

**조치: naver_news.py `_parse_urls` 셀렉터 교체**

[`app/adapters/naver_news.py`의 `_parse_urls`](../../app/adapters/naver_news.py) 함수에서 조건 수정:

```python
# 기존 (파손된 경우)
if "sds-comps-base-layout" not in (parent.attributes.get("class") or ""):

# 새 클래스명으로 교체
if "새로_확인된_클래스명" not in (parent.attributes.get("class") or ""):
```

파일 상단 docstring의 `셀렉터 전략` 설명도 함께 업데이트한다.

**검증**

```bash
# 수정 후 preview_adapter 로 URL 반환 확인
.venv\Scripts\python.exe scripts\preview_adapter.py --keyword "삼성전자" --portal naver_news

# URL 이 정상 반환되면 워커 재시작 (hot-reload 없음 — 코드 변경이므로)
```

---

#### 0건 누락 기간 복구

봇 감지 또는 셀렉터 파손으로 수집이 누락된 기간이 있으면  
`pd` 파라미터를 변경해 과거 기간을 재수집한다:

```bash
# pd=1 : 1주 이내 (누락 기간이 7일 이내일 때)
.venv\Scripts\python.exe scripts\run_discovery.py --keyword "블랙핑크" --portal naver_news --period 1 --pages 50

# pd=2 : 1개월 이내
.venv\Scripts\python.exe scripts\run_discovery.py --keyword "블랙핑크" --portal naver_news --period 2 --pages 50
```

중복 URL 은 `url_hash` UNIQUE 제약으로 자동 무시된다.

---

## Idle 주기

처리할 due 키워드가 없으면 **60초마다** DB 를 재확인한다.
30분 reschedule 된 키워드는 최대 30분 1초 이내에 재수집이 시작된다.

```python
_IDLE_SLEEP_SEC = 60   # dispatcher.py
```

---

## 실행

```bash
# 워커 (무한 루프, 전 키워드 순환)
.venv\Scripts\python.exe -m app --role discovery --portal naver_news

# 단일 키워드 수동 실행
.venv\Scripts\python.exe scripts\run_discovery.py --keyword "삼성전자" --portal naver_news --pages 10
```

---

## 모니터링

```sql
-- 오늘 403 에러 현황
SELECT k.keyword, cl.urls_found, cl.error_msg, cl.started_at
FROM collection_log cl
JOIN keyword k ON k.id = cl.keyword_id
WHERE cl.run_type = 'discovery'
  AND cl.run_date = CURDATE()
  AND cl.error_msg IS NOT NULL
ORDER BY cl.started_at DESC;

-- 403 재시도 대기 중인 키워드 (next_discover_at 이 30분 이내)
SELECT keyword, display_name, next_discover_at, last_cursor
FROM keyword
WHERE portal_type = 'naver_news'
  AND next_discover_at BETWEEN NOW() AND NOW() + INTERVAL 30 MINUTE;

-- 오늘 포털별 수집 성공률
SELECT
    portal_type,
    COUNT(*)                           AS total_runs,
    SUM(error_msg IS NOT NULL)         AS failed_runs,
    ROUND(AVG(urls_found), 1)          AS avg_urls_found
FROM collection_log
WHERE run_type = 'discovery' AND run_date = CURDATE()
GROUP BY portal_type;
```
