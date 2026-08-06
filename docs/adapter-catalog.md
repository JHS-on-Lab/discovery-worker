# 어댑터 카탈로그 — 새 어댑터 개발 참고용

기존 어댑터(`app/adapters/`)가 어떤 방식으로 동작하는지 정리한 것. 새 소스를
추가할 때 어떤 패턴을 따를지 결정하는 데 참고한다.

## 1. 한눈에 비교

| 어댑터 | source_type | 수집 방식 | 베이스 클래스 | 커서 | 기간 필터 | 봇 차단 감지 |
|---|---|---|---|---|---|---|
| `naver_news.py` | `NAVER_NEWS` | 정적 HTTP (httpx) | `PaginatedAdapter` | `start` 오프셋 | `pd`(1주/1개월/오늘/1일) | 결과 0건 + "결과 없음" 마커 부재 |
| `naver_stock.py` | `NAVER_STOCK` | 정적 HTTP | `PaginatedAdapter` | 페이지 번호 | 없음 | 없음(결과 0건이면 그냥 종료) |
| `daum_news.py` | `DAUM_NEWS` | 정적 HTTP + 리다이렉트 해석 | `PaginatedAdapter` | 페이지 번호 | `period`(일/주/개월) | 결과 0건 + "결과 없음" 마커 부재 |
| `google_news.py` | `GOOGLE_NEWS` | Chrome(undetected-chromedriver), search/rss 이중 모드 | `ChromeLifecycleMixin` | 페이지 번호(search) / 없음(rss, 1회성) | `tbs=qdr:d`(search, 하드코딩) / `when:1d`+사후 필터(rss) | `/sorry/` URL, reCAPTCHA iframe, 텍스트 마커(en/ko) |
| `baidu_news.py` | `BAIDU_NEWS` | Chrome(undetected-chromedriver) | `ChromeLifecycleMixin` | `pn` 오프셋 | 없음(미발견) | `wappass.baidu.com` 리다이렉트, 페이지 타이틀 마커 |
| `duckduckgo_news.py` | `DUCKDUCKGO_NEWS` | 정적 HTTP(내부 JSON API) | `PaginatedAdapter` | `페이지:오프셋:vqd` 복합 문자열 | `df`(일/주/개월) | vqd 토큰 부재, JSON 파싱 실패 |
| `baomoi_news.py` | `BAOMOI_NEWS` | 정적 HTTP | `PaginatedAdapter` | 페이지 번호 | `<time datetime>` 파싱(1일) | 없음(미검증, "không tìm thấy" 부재 시 경고만) |
| `tinhte_forum.py` | `TINHTE_FORUM` | Chrome(순정 selenium), 검색창 UI 직접 타이핑 | `ChromeLifecycleMixin` | 페이지 번호(`.gsc-cursor-page` 클릭) | 없음(정렬만 최신순, URL 패턴(`/thread/...`)으로 노이즈 제거) | 검색창 요소 못 찾으면만 감지(API 레벨 차단 신호 없음) |

## 2. 수집 방식 두 갈래

### 2.1 정적 HTTP (naver_news, naver_stock, daum_news, duckduckgo_news, baomoi_news)

- `app/fetch/_client.py`의 `make_client()`(httpx 기반)로 직접 요청.
- `selectolax.parser.HTMLParser`로 파싱(daum/naver) 또는 JSON 파싱(duckduckgo).
- 브라우저 불필요 — 가볍고 빠르고 메모리 걱정 없음.
- **선택 기준**: 대상 사이트가 순수 HTTP 요청을 차단하지 않을 때만 가능. `baidu_news.py`의
  주석에 남아있듯, 실측(httpx/curl)으로 100% 캡차 리다이렉트되는 걸 확인하면 이 방식은
  포기해야 한다.

### 2.2 Chrome 기반 (google_news, baidu_news, tinhte_forum)

- `undetected_chromedriver` + `ChromeLifecycleMixin`(`_chrome_behavior.py`) 상속 — google/baidu.
- `_chrome_detect.py`(Chrome 바이너리 탐지, Xvfb 기동)와 `_profile_lock.py`(WORKER_ID별
  영구 프로필 flock)를 공용으로 사용.
- 행동 자연화: `jitter_sleep()`(고정 간격 대신 편차), `simulate_reading()`(스크롤 시뮬레이션),
  랜덤 `WINDOW_SIZES`, 영구 프로필 디렉터리.
- 메모리 절감 옵션(둘 다 적용): `--disable-features=BackForwardCache,IsolateOrigins,site-per-process`,
  이미지 로드 차단. `page_load_strategy=eager`는 google/tinhte만(baidu는 미적용).
- **선택 기준**: JS 실행이 필요하거나(google의 CBMi 리다이렉트처럼 클라이언트사이드 JS로만
  풀리는 경우) 순수 HTTP가 확실히 차단될 때만. Chrome은 메모리/속도 비용이 크므로
  최후의 수단으로 취급 — `docs/memory-oom-mitigation.md`에 이 비용을 줄이려 쌓은 조치들
  (URL별 탭 즉시 닫기, 광고 도메인 차단, stopLoading 등)이 정리돼 있다.

**tinhte_forum 는 다른 패턴** — API/페이지를 스크랩하는 게 아니라 실제 검색창에
타이핑하고 결과를 DOM에서 읽는다(tinhte.vn 검색이 사이트에 임베드된 Google Custom
Search Engine 위젯이라, 그 내부 API를 직접 재현하려 하면 정적 요청이든 브라우저
안에서의 스크립트 주입이든 차단되거나 브라우저 정책과 충돌한다 — 자세한 내용은
`tinhte_forum.py` 모듈 docstring 참고). 그래서:
  - `undetected_chromedriver` 대신 순정 `selenium.webdriver.Chrome()` 사용 — 사람처럼
    타이핑하는 방식이라 UC의 스텔스 패치가 결정적이지 않고, 순정 selenium이 이
    환경에서 더 안정적으로 동작한다.
  - 봇 차단 감지가 "검색창 요소 자체를 못 찾음" 하나뿐 — API를 직접 안 두드리니 API
    레벨 차단(`403`, reCAPTCHA 등) 신호가 이 어댑터에는 나타나지 않는다.
  - **새 소스가 "사이트 자체 검색이 아니라 제3자 위젯(구글 CSE 등)"인 경우**에 참고할
    만한 선례 — API를 역공학하기 전에 먼저 실제 UI에 사람처럼 타이핑하는 방식이
    되는지부터 검토해볼 가치가 있다.

## 3. 공용 인터페이스 (반드시 지켜야 하는 것)

### `app/ports.py` — `SourceAdapter` Protocol

```python
source_type: str
def discover(self, keyword: str, cursor: str | None) -> DiscoverResult: ...
```

모든 어댑터가 만족해야 하는 유일한 필수 계약. `cursor=None`이면 첫 페이지, 반환값의
`next_cursor`를 다음 호출에 그대로 넘겨받는다.

### `app/ports.py` — `SourceOptionsAware` Protocol (선택)

`apply_source_options(options: dict | None) -> None`. `t_keyword.source_options_json`
오버라이드가 필요한 어댑터만 구현(현재 `google_news`뿐). dispatcher가
`isinstance(adapter, SourceOptionsAware)`로 지원 여부를 확인한다. 옵션이 없을 때
반드시 내부 상태를 기본값으로 리셋해야 한다 — 어댑터 인스턴스가 여러 키워드를
연속 처리하므로, 리셋 안 하면 이전 키워드 설정이 새어 들어간다.

### `app/types.py`

- `DiscoverResult(urls, next_cursor, has_more, mode=None)` — `mode`는 `DiscoverMode`
  (search/rss, 현재 google 전용) 기본값 있어 다른 어댑터는 몰라도 됨.
- `BotBlockedError` — dispatcher가 잡아서 키워드별 재시도 스케줄링(`dispatcher.py`,
  5회·30분 간격)으로 처리. 결과가 0건이라고 무조건 던지면 안 되고, 실제 차단 신호가
  있을 때만(§8.2, §8.3 참고 — 정상 소진과 진짜 차단을 구분 못 하면 오탐 쌓임).

### `app/adapters/_base.py` — `PaginatedAdapter` + 정적 어댑터 공용 헬퍼

`period`/`max_pages`/`delay_ms`를 갖는 정적 HTTP 계열 어댑터의 공통 베이스.
`_exceeded(page_num)`(페이지 상한 체크), `_delay(is_first)`(첫 페이지 아니면 딜레이)를
제공. Chrome 기반 어댑터(`google_news`/`baidu_news`/`tinhte_forum`)는 이걸 상속하지 않고
`page_limit_exceeded()` 함수만 재사용한다(각자 `ChromeLifecycleMixin` 라이프사이클을 쓴다).

> **주의**: `PaginatedAdapter.__init__(period, max_pages, delay_ms)`는 위치 인자로
> 호출하는 곳이 3곳(naver_news/daum_news/duckduckgo_news) 있다. 매개변수 순서를
> 바꾸면 값이 조용히 뒤바뀌는 회귀가 생기니 바꾸려면 호출부 전체를 같이 고칠 것.

같은 파일의 `is_own_host(netloc, own_hosts)`(검색엔진 자체 도메인 결과 제외 —
naver_news/google_news 사용)와 `log_empty_or_blocked(logger, source, keyword,
page, is_genuine_empty, block_reason)`(빈 결과를 "진짜 빈 결과"와 "차단 의심"으로
구분해 로깅 — naver_news/daum_news/baomoi_news 사용)는 정적/Chrome 어댑터 전체가
공유하는 범용 헬퍼라 `PaginatedAdapter` 밖의 모듈 레벨 함수로 뒀다. `BotBlockedError`를
던질지는 소스마다 다르므로(baomoi 는 안 던지고 경고만 남김) 판단은 호출부 몫이다.

### `app/adapters/_chrome_behavior.py` — `ChromeLifecycleMixin`

Chrome 기반 어댑터(`google_news`/`baidu_news`/`tinhte_forum`) 공용 베이스.
`__init__(max_pages, delay_sec)`으로 `_max_pages`/`_delay_sec`/`_driver`/
`_user_data_dir`/`_profile_lock_file` 를 초기화하고, `_build_driver_or_release(build)`
로 드라이버 생성을 감싸 기동 실패 시 프로필 락을 반드시 풀어준다(안 풀면 같은
프로세스의 다음 재시도가 자기 자신의 flock 에 걸려 self-lockout 난다). `close()`/
`__del__()` 도 여기서 공용 구현. 서브클래스는 `super().__init__(max_pages, delay_sec)`
호출 후 자기만의 필드(google_news 의 `_search_blocked_until` 등)를 추가하면 된다.

### `app/adapters/__init__.py` — `make_adapter(source_type, max_pages=None)`

새 어댑터는 여기에 분기 추가해야 실제로 dispatcher/스크립트에서 생성 가능해진다.

## 4. 새 어댑터 만들 때 체크리스트

1. **수집 방식 결정**: 대상 사이트가 순수 HTTP를 차단하는지 먼저 실측(httpx/curl)으로
   확인 — 차단 확정이거나 JS 실행이 꼭 필요할 때만 Chrome行.
2. **`SourceType`에 새 값 추가**(`app/types.py`).
3. **베이스 클래스 선택**: 정적 HTTP면 `PaginatedAdapter` 상속, Chrome이면
   `ChromeLifecycleMixin` 상속 + `_chrome_detect`/`_profile_lock` 재사용.
4. **커서 형식 결정**: 오프셋 숫자만으로 충분한지, duckduckgo처럼 세션 토큰까지
   포함해야 하는지(`"페이지:오프셋:토큰"` 같은 복합 문자열).
5. **봇 차단 감지 기준 명확히**: "결과 0건"과 "진짜 차단"을 구분할 신호가 있는지
   확인(사이트별 "검색 결과 없음" 마커 유무). 없으면 baidu처럼 차단으로 취급 안 하고
   경고만 남기는 쪽을 고려(불필요한 백오프 낭비 방지).
6. **기간 필터 파라미터 확인**: 사이트가 지원하면 최근 N일로 제한(비공식 파라미터라도
   설정값으로 빼서 하드코딩 피할 것 — google의 `tbs=qdr:d`/`when:1d`처럼).
7. **리다이렉트/중간 URL 처리 필요 여부**: daum의 `cp.news.search.daum.net`처럼 발견
   단계에서 최종 목적지로 미리 풀어둬야 extraction-worker의 domain rule이 제대로
   적용되는 경우가 있는지 확인.
8. **`app/config.py`에 `<SOURCE>_MAX_PAGES` 등 설정값 추가**.
9. **`app/adapters/__init__.py`의 `make_adapter()`에 분기 추가**.
10. **`app/__main__.py`, `scripts/run_discovery.py`, `deploy/run.sh`의 `_SOURCES`/도움말
    문자열에 추가**.
11. **crawler-admin의 `SOURCE_TYPES` 목록**(`app/routes/keywords.py`, `app/routes/urls.py`,
    `app/routes/logs.py`)에도 추가해야 관리 화면에서 다뤄진다.
12. **`source_options_json` 오버라이드가 필요하면** `SourceOptionsAware` Protocol 구현 +
    `apply_source_options()`에서 리셋 로직 필수.
13. **실제 요청/파싱을 로컬에서 실측 검증** — 셀렉터가 실제 페이지 구조와 맞는지,
    봇 차단이 실제로 어떻게 나타나는지(리다이렉트 URL, 응답 코드, 페이지 마커)
    직접 확인 없이 추측만으로 만들면 나중에 운영 중 조용히 깨진다(baidu의 파싱
    셀렉터가 아직 "미검증"으로 남아있는 게 그 예).
