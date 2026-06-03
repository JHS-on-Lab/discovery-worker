# 도메인 규칙 가이드

`domain` 테이블은 언론사 도메인별 수집 정책을 저장한다.  
**행이 없는 도메인은 전역 기본값을 쓰므로, 특별히 설정이 필요한 도메인만 등록하면 된다.**

---

## 1. 설정 가능한 항목

| 컬럼 | 설명 | 기본값 |
|------|------|--------|
| `crawl_delay_ms` | 이 도메인에 요청 사이 최소 대기 시간 (ms) | `DEFAULT_CRAWL_DELAY_MS` (.env, 기본 1000ms) |
| `render_mode` | 본문 추출 방식 | `static` (정적 HTTP) |
| `cooldown_until` | 차단 해제 시각. 이 시각 전까지 요청 안 함 | NULL (차단 없음) |
| `rules_json` | 도메인 전용 CSS/XPath 추출 규칙 | NULL (라이브러리 자동 추출) |

---

## 2. 설정 명령어

```bash
# 현재 설정 조회
python scripts/add_domain_rule.py --host www.example.com --show

# crawl_delay 설정
python scripts/add_domain_rule.py --host www.example.com --delay 3000

# render_mode 변경
python scripts/add_domain_rule.py --host www.example.com --render headless

# 쿨다운 해제 (차단이 풀렸을 때)
python scripts/add_domain_rule.py --host www.example.com --cooldown-clear
```

---

## 3. 언제 설정하나

### crawl_delay_ms — 서버가 429를 반복할 때

```bash
# 기본(1초)에서 3초로 늘림
python scripts/add_domain_rule.py --host www.chosun.com --delay 3000
```

**판단 기준:**
- `article_url` 테이블에서 해당 호스트의 `last_error_code = 'FETCH_429'` 가 반복되면 딜레이를 늘린다.
- 반대로 수집이 원활하면 줄여도 된다.

```sql
-- 429 자주 나는 도메인 확인
SELECT host, COUNT(*) AS cnt
FROM article_url
WHERE last_error_code = 'FETCH_429'
GROUP BY host ORDER BY cnt DESC;
```

---

### render_mode = headless — 본문이 계속 비어 나올 때

정적 HTTP 로는 빈 HTML 만 오는 사이트 (JS 렌더링 필요)에 설정한다.

```bash
python scripts/add_domain_rule.py --host www.example.com --render headless
```

> **주의**: headless 모드는 Playwright 브라우저 설치 후 사용 가능하다.  
> 미설치 시 첫 headless 요청에서 오류가 발생한다: `playwright install chromium`

**headless 가 필요한 징후:**
- `last_error_code = 'PARSE_ERROR'` 또는 `BODY_TOO_SHORT'` 가 해당 도메인에서만 반복됨
- 브라우저로 직접 열면 본문이 보이는데 크롤러는 빈 결과를 반환함

```sql
-- PARSE_ERROR 많은 도메인 (headless 후보)
SELECT host, COUNT(*) AS cnt
FROM article_url
WHERE last_error_code IN ('PARSE_ERROR', 'BODY_TOO_SHORT')
GROUP BY host ORDER BY cnt DESC LIMIT 20;
```

---

### render_mode = headless_with_iframe — 본문이 iframe 안에 있을 때

페이지 자체는 JS 없이 로드되지만, **실제 본문이 다른 도메인의 iframe 안에 있는** 경우에 사용한다.  
대표 예: 네이버 증권 종목토론 (`finance.naver.com`) — 본문이 `m.stock.naver.com` iframe 안에 위치.

```bash
python scripts/add_domain_rule.py --host finance.naver.com --render headless_with_iframe
```

**동작 원리**

Playwright 로 페이지를 로드한 뒤, 로드된 모든 iframe 의 HTML 을 꺼내 외부 문서 `</body>` 직전에 주입한다.

```
원본 HTML                          주입 후 HTML
─────────────────────────────      ─────────────────────────────────────
<body>                             <body>
  <iframe name="contents"            <iframe name="contents" ...>
    src="m.stock.naver.com/...">     </iframe>
  </iframe>
</body>                             <!-- 주입된 부분 -->
                                     <div id="frame_contents">
                                       <div class="se-main-container">
                                         본문 내용...
                                       </div>
                                     </div>
                                   </body>
```

iframe 의 `name` 속성이 `contents` 이면 `<div id="frame_contents">` 로 감싸진다.  
이름이 없는 iframe 은 `frame_0`, `frame_1` 순서로 번호가 붙는다.

주입 후에는 일반 CSS 셀렉터로 iframe 안의 내용에 접근할 수 있다.  
`rules_json` 의 `body` 셀렉터를 `#frame_contents .se-main-container` 처럼 작성하면 된다.

**headless_with_iframe 이 필요한 징후:**
- 브라우저 개발자 도구에서 본문 영역을 찾으면 `<iframe>` 태그 안에 있음
- `headless` 만 써도 본문이 비어 나옴 (iframe 내부는 `page.content()` 에 포함되지 않음)

**설정 예 (네이버 증권 종목토론)**

```bash
python scripts/add_domain_rule.py \
  --host finance.naver.com \
  --render headless_with_iframe \
  --rules-json '{
    "title":        {"css": "div.title"},
    "body":         {"css": "#frame_contents .se-main-container"},
    "author":       {"css": "span.profile_name"},
    "published_at": {"css": "th.gray03", "date_format": "%Y.%m.%d %H:%M"},
    "min_body_len": 10
  }'
```

---

### cooldown — 수동 차단 해제

추출 워커가 429 또는 5xx 를 연속 감지하면 자동으로 `cooldown_until` 을 설정한다.  
쿨다운이 지나면 자동 해제되지만, 긴급하게 수동으로 해제할 때 사용한다.

```bash
python scripts/add_domain_rule.py --host www.example.com --cooldown-clear
```

---

## 4. 시스템이 자동으로 관리하는 항목 (직접 수정 불필요)

| 컬럼 | 의미 | 업데이트 시점 |
|------|------|--------------|
| `success_rate` | 최근 추출 성공률 (0~1, EMA 방식) | 추출할 때마다 자동 갱신 |
| `avg_body_len` | 평균 본문 길이 (EMA) | 추출할 때마다 자동 갱신 |
| `recent_fail_count` | 최근 연속 실패 횟수 | 추출할 때마다 자동 갱신 |
| `cooldown_until` | 차단 해제 시각 | 429 등 감지 시 자동 설정 |

이 값들은 운영 모니터링용으로, 직접 수정할 필요는 없다.

```sql
-- 문제 있는 도메인 한눈에 보기
SELECT host, success_rate, avg_body_len, recent_fail_count, cooldown_until
FROM domain
WHERE success_rate < 0.5 OR recent_fail_count >= 3
ORDER BY recent_fail_count DESC;
```

---

## 5. rules_json — 도메인 전용 추출 규칙

`rules_json` 을 설정하면 trafilatura/readability 보다 먼저 시도된다.  
규칙이 실패하면 자동으로 라이브러리 체인으로 폴백하므로 안전하다.

### 형식

```json
{
  "title":        {"css": "h1.article-title"},
  "body":         {"css": "div.article-body p"},
  "author":       {"css": "span.byline"},
  "press":        {"xpath": "//meta[@property='og:site_name']/@content"},
  "published_at": {"css": "span.date", "date_format": "%Y.%m.%d %H:%M"},
  "min_body_len": 10
}
```

| 키 | 설명 |
|----|------|
| `title` | 제목 셀렉터 |
| `body` | 본문 셀렉터. 여러 노드가 매칭되면 줄바꿈으로 이어 붙인다 |
| `author` | 작성자 셀렉터 (선택) |
| `press` | 언론사 셀렉터 (선택) |
| `published_at` | 날짜 셀렉터 + `date_format` (strptime 포맷). 파싱 실패 시 NULL 폴백. 타임존 KST 고정 |
| `min_body_len` | 최소 본문 길이 (기본 200자). 짧은 본문이 정상인 도메인에서 낮게 설정 |

셀렉터 타입:
- `css` — selectolax 로 처리
- `xpath` — lxml 로 처리. 속성값(`//@attr`)과 텍스트(`//tag`) 모두 지원

필드는 일부만 지정해도 된다. 없는 필드는 NULL 또는 라이브러리 폴백으로 처리된다.

### 등록 방법

`add_domain_rule.py --rules-json` 으로 등록한다. `rules_enabled = 1` 은 자동으로 설정된다.

```bash
python scripts/add_domain_rule.py --host www.chosun.com \
  --rules-json '{"title":{"css":"h1.article-tit"},"body":{"css":"div.article-body"}}'
```

SQL 로 직접 등록할 때:
```sql
INSERT INTO domain (host, rules_json, rules_enabled, updated_by)
VALUES (
  'www.chosun.com',
  '{"title": {"css": "h1.article-tit"}, "body": {"css": "div.article-body"}}',
  true,
  'manual'
)
ON DUPLICATE KEY UPDATE
  rules_json    = VALUES(rules_json),
  rules_enabled = true,
  updated_by    = 'manual';
```

규칙을 잠시 끄되 데이터는 보존하고 싶을 때:
```bash
python scripts/add_domain_rule.py --host www.chosun.com --rules-disable
```

### 규칙 캐시

규칙은 메모리에 캐시된다 (`RULES_CACHE_TTL_SECONDS`, 기본 60초).  
DB 에서 규칙을 수정하면 최대 60초 후 자동 반영된다. 재배포 불필요.

### 셀렉터 찾는 법

브라우저 개발자 도구(F12) → Elements 탭 → 본문 영역 우클릭 → "Copy selector" 로 CSS 셀렉터를 확인한다.

---

## 6. 전체 domain 현황 조회

```sql
SELECT
    host,
    crawl_delay_ms,
    render_mode,
    ROUND(success_rate * 100, 1)  AS success_pct,
    avg_body_len,
    recent_fail_count,
    cooldown_until,
    updated_at
FROM domain
ORDER BY recent_fail_count DESC, updated_at DESC;
```
