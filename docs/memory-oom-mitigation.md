# 메모리 사용량 로깅 & OOM 완화 (2026-07-23)

서버에 배포한 뒤 OOM이 반복 발생해 원인 진단용 로깅과 완화 조치를 추가했다.
아래는 As-Is/To-Be 요약이다.

## 1. 메모리 사용량 로깅

| | As-Is | To-Be |
|---|---|---|
| 상태 | OOM이 나도 원인을 알 방법이 없었음 (일반 로그엔 메모리 정보 없음) | heartbeat 주기(기본 60초, `HEARTBEAT_INTERVAL_SECONDS`)마다 self + Chrome 자식 프로세스 RSS를 `{log_name}-mem.log`에 별도 기록 |
| 구현 | - | `app/memlog.py`(신규), `app/logging_setup.py`에 `"memlog"` 전용 로거 추가(`propagate=False`라 app.log/console엔 안 섞임), `app/scheduling/dispatcher.py`의 기존 heartbeat 스레드에서 호출 |
| 커밋 | - | `8eb7b24` |

**효과**: OOM 원인을 "감"이 아니라 실측 데이터로 추적 가능해짐. 실측 결과 `google_news` 워커가 순간적으로 자식 프로세스 15→50개, `rss_children_mb` 최대 4.6GB까지 튀는 버스트 패턴을 확인함(꾸준히 우상향하는 누수가 아니라 프로세스 개수 급증형).

extraction-worker에도 동일 구조로 적용됨(`app/memlog.py`, `run_extraction_loop`의 heartbeat 블록에서 호출, 커밋 `bf9d456`).

## 2. 컨테이너 메모리 제한 (`deploy/run.sh`)

| | As-Is | To-Be |
|---|---|---|
| 상태 | `docker run`에 `--memory` 제한 없음 — 워커 하나가 폭주하면 호스트 전체 OOM killer가 무관한 프로세스까지 임의로 죽일 위험 | 소스별 티어 적용 후 `--memory`/`--memory-swap`(스왑 비활성) 부여 |
| 티어 | - | `google_news`/`baidu_news`/`all` = `1.5g`, 나머지(`naver_news`/`daum_news`/`naver_stock`/`duckduckgo_news`) = `512m` |
| 오버라이드 | - | `MEM_LIMIT` 환경변수로 스크립트 수정 없이 값 조정 가능 (예: `MEM_LIMIT=3g ./deploy/run.sh google_news disc-google-1`) |

**효과**: 문제 컨테이너만 깔끔하게 OOM-kill되고 `--restart unless-stopped`로 재시작 — 다른 워커나 호스트 전체로 피해가 번지지 않음. 스왑을 꺼서 "조용히 느려지다 늦게 죽는" 대신 "한도 초과 즉시 kill"로 만들어, mem 로그의 마지막 기록과 재시작 시점이 정확히 대응되게 함.

> extraction-worker는 `render_mode`(headless 여부)가 `source_type`이 아니라 도메인별 설정이라 소스 필터로 안전하게 티어링할 수 없어 균일하게 `1.5g` 적용(커밋 `bf9d456`).

## 3. Chrome 메모리 절감 옵션 (`google_news.py` / `baidu_news.py`)

| | As-Is | To-Be |
|---|---|---|
| 상태 | BackForwardCache·Site Isolation 켜진 채 동작 — 검색결과 페이지 이동마다 렌더러 프로세스가 누적/급증 | Chrome 실행 옵션에 추가:<br>`--disable-features=BackForwardCache,IsolateOrigins,site-per-process`<br>`prefs: {"profile.managed_default_content_settings.images": 2}` (이미지 로드 끔) |
| 근거 | - | 검색결과 페이지에서 XPath로 링크 텍스트만 읽고 시각적 렌더링은 안 씀 → DOM/기능에 영향 없이 렌더러 프로세스 수와 이미지 캐시만 감소 |
| 커밋 | - | `de897b9` |

**효과**: 서버 실측 결과(2026-07-28 08:15~08:49, `disc-google-test`) 피크가 안 줄었음(renderer 최대 38개, `rss_children_mb` 4.9GB — 이전 관찰치 4.6GB와 비슷한 규모). mem 로그를 같은 시간대 discover/error 로그와 대조해보니 원인이 이 옵션과 무관했다 — 정상 `search` 페이지네이션 구간(08:15~08:18, 여러 키워드가 p1~p5까지 연속 로드)은 그 내내 renderer가 2로 완전히 평평했고, 급증은 전부 `rss` 폴백 모드의 CBMi URL 해석 구간에서만 발생함(§4 참고). 즉 이 옵션 자체는 정상 동작하고 있었고, 그냥 원인이 다른 곳에 있었던 것.

## 4. rss 폴백 모드 CBMi 해석 — 배치 재시작 (`google_news.py`) — **7번으로 대체됨**

| | As-Is | To-Be |
|---|---|---|
| 상태 | `_resolve_cbmi()`가 CBMi URL(최대 ~100건)을 하나의 Chrome 세션으로 전부 순차 탐색 — 외부 언론사 사이트(광고/트래커 iframe 많음)를 연달아 열면서 renderer 프로세스가 계속 누적 | `_CBMI_BATCH_SIZE`(20)개마다 Chrome을 껐다 다시 켬. 배치 중 hang이 나도 그 배치만 포기하고 다음 배치는 새 driver로 이어감(기존엔 hang 시 전체를 포기) — 데이터 유실이 오히려 줄어듦 |
| 근거 | - | mem 로그 스파이크 시각과 큰 CBMi 배치(37/100/101건) 처리 구간이 정확히 일치함을 확인(08:21~08:27, 08:27~08:39, 08:41~08:48) |
| 커밋 | - | `7b995a7` |

**효과**: mock driver + 실제 Chrome(배치 크기 축소해 강제 재현)으로 배치 분할·재시작 호출 횟수·hang 복구 경로 검증 완료.

**이후 경과(2026-07-29)**: 서버 재배포 전에 "URL 처리 후 그 페이지를 아예 닫아버리면 안 되나"라는 질문에서 출발해 7번(URL별 새 탭 열고 즉시 닫기)을 실측해보니 이 배치 방식보다 훨씬 효과적이었다 — `_CBMI_BATCH_SIZE`/배치 루프를 전부 제거하고 7번으로 교체했다. 이 섹션은 왜 배치 단위 접근을 먼저 시도했는지 기록으로 남겨둔다.

## 5. rss 폴백 모드 CBMi 해석 — `pageLoadStrategy=eager` (`google_news.py`)

| | As-Is | To-Be |
|---|---|---|
| 상태 | `driver.get(cbmi_url)`이 리다이렉트 완료 후 도착한 실제 언론사 페이지의 광고/트래커 iframe까지 전부 로드되길 기다림(page_load_strategy 기본값 `normal`) — 정작 쓰는 건 `current_url` 한 줄뿐, 본문은 안 읽음 | Chrome을 `page_load_strategy=eager`로 띄워 DOMContentLoaded 시점에 `driver.get()`이 바로 리턴하게 함. 리다이렉트가 그 이후에 끝나는 경우를 대비해 `_wait_for_cbmi_redirect()`로 `current_url`이 `news.google.com`을 벗어날 때까지 직접 폴링 |
| 근거 | - | 4번 배치 재시작은 누적된 걸 주기적으로 리셋하는 완화책이고, 이건 애초에 광고 페이지가 로드될 기회 자체를 줄이는 더 근본적인 조치 |
| 커밋 | - | `5cc152a` |

**주의**: `page_load_strategy`는 driver 세션 전체에 적용되는 설정이라 `_discover_search()`(정상 검색)에도 같이 걸림. 실측 결과 검색 결과 추출(10건, `has_more=True`)엔 영향 없음(서버렌더링 HTML이라 DOMContentLoaded 시점에 이미 링크 존재). CBMi 8건 실제 리다이렉트도 8/8 정상 해석 확인(로컬).

## 6. rss 폴백 모드 CBMi 해석 — 광고/트래커 도메인 차단 (`google_news.py`)

| | As-Is | To-Be |
|---|---|---|
| 상태 | `_resolve_cbmi()`가 실제 언론사 페이지를 방문할 때, 그 페이지의 광고/트래커 iframe(교차 출처)마다 renderer 프로세스가 추가로 생김 — 4·5번은 "생긴 걸 정리/대기 안 함"이었고, 이건 애초에 renderer 자체가 덜 생기게 하는 조치 | 주요 광고/트래커 도메인 38개(`_AD_TRACKER_DOMAINS`)를 `--host-resolver-rules`로 `0.0.0.0`에 매핑해 DNS 단계에서 차단 |
| 근거 | - | 별도 확장 파일 불필요 — Chrome 자체 내장 플래그라 Dockerfile/빌드 변경 없이 코드만으로 적용 가능. `google.com` 페이징 중엔 이 도메인들을 애초에 안 써서 부작용 없음 |
| 커밋 | - | `c9d710d` |

**효과**: 로컬 실측(2026-07-29) — 실제 뉴스 5건(viva100/조선비즈/한국경제/뉴스1/연합뉴스) 방문 시 renderer RSS 합계 기준 약 30~40% 감소 확인(사이트별 8~59% 편차, 사이트마다 광고 밀도가 달라 편차 큼). 정상 검색(10건 발견)과 CBMi 리다이렉트 해석(5/5 정상) 모두 회귀 없음 확인. 서버 mem 로그로 4·5번과 함께 종합 효과 확인 필요.

이후 실제로 서버 mem 로그에서 4~7번 적용 후에도 가끔 3~4GB까지 튀는 잔여 스파이크가 관찰됐고(§8 참고), 그 대응으로 아래 CDP 기반 조기 차단을 실제로 적용했다.

## 7. rss 폴백 모드 CBMi 해석 — 배치 재시작 대신 URL별 새 탭 열고 즉시 닫기 (`google_news.py`)

| | As-Is | To-Be |
|---|---|---|
| 상태 | 같은 탭에서 `driver.get()`으로 계속 이동만 함 — 이전 페이지의 renderer(광고 iframe 포함)가 Chrome 자체 유휴 프로세스 유지 정책 때문에 곧바로 정리되지 않고 쌓임(4번의 배치 재시작으로 20건마다만 리셋) | URL마다 새 탭을 열어 탐색 → `current_url` 확인 → **탭을 명시적으로 닫고** 원래 탭으로 복귀. `_CBMI_BATCH_SIZE`/배치 루프 전체 제거 |
| 근거 | - | "처리한 페이지를 아예 꺼버리면 안 되나"는 질문에서 출발 — 실측 결과 같은 탭 재사용 시 renderer가 11→24개로 계속 누적된 반면, 탭을 닫으면 방문마다 3~5개로 리셋됨을 확인 |
| 커밋 | - | `d749746` |

**효과**: 4번(배치 재시작)보다 근본적 — 20건 쌓일 때까지 기다리지 않고 **매 URL마다** 리셋되고, 브라우저 전체 재시작 오버헤드도 없어져 더 가볍다. 실제 CBMi 8건으로 검증: 8/8 정상 resolve, renderer 3→6으로 거의 안 늘어남. hang 나도 배치 전체가 아니라 그 URL 하나만 포기해 데이터 보존도 더 좋아짐(mock driver로 확인).

## 8. rss 폴백 모드 CBMi 해석 — 리다이렉트 감지 즉시 Page.stopLoading + 탭 즉시 닫기 (`google_news.py`)

4~7번 적용 후 서버 mem 로그(2026-07-29)를 분석해보니 대부분 renderer가 4~8개 수준으로 안정됐지만, 가끔 한 샘플만 3~4GB(renderer 16~28개)로 튀었다가 바로 다음 샘플에 회복되는 패턴이 남아있었다. `log.txt`/`error.txt`와 시각을 대조한 결과 hang과는 무관하게, 특정 키워드의 CBMi 해석 구간(예: 08:31:35~08:36:08 'JYP 엔터테인먼트' 38건) 안에서만 발생함을 확인 — 차단 목록(§6)에 없는 광고/트래커가 유독 많은 페이지 한 개가 그 순간 renderer를 몰아서 만든 것으로, 예전의 "누적" 버그와는 다른 성격이었다.

| | As-Is | To-Be |
|---|---|---|
| 상태 | `_wait_for_cbmi_redirect()`가 `current_url`이 news.google.com을 벗어나는 것만 확인하고 반환 — 목적지 페이지는 그 뒤로도 계속 로드됨(자기 JS로 광고 iframe 계속 생성 가능). 이후 `jitter_sleep()`으로 탭을 1.5초 더 열어둠 | URL이 바뀐 걸 감지하는 즉시 `Page.stopLoading()` 호출(poll_interval도 0.3→0.05초로 단축). `_resolve_cbmi()`에서도 지터 슬립을 탭 닫은 뒤로 옮겨, 탭을 최대한 빨리 닫음 |
| 근거 | - | `current_url` 판별 기준 자체는 그대로라(news.google.com을 벗어났는가) URL 유실 위험 없음 — 같은 시점에 같은 값을 잡고 그 이후 불필요한 로딩만 끊는 것. 도메인 목록에 없는 광고에도 구조적으로 대응(어떤 도메인인지 몰라도 로딩 자체를 끊음) |
| 커밋 | - | `6d5c71e` |

**효과**: 실측(2026-07-29) — 같은 5개 뉴스 사이트 재방문 시, stopLoading 적용 직후 측정하면 renderer 5~18(이전 탭 닫기만 적용 시 8~24 수준)까지 낮아짐. 단, stopLoading 이후에도 탭을 1.5초 열어두면(원래 지터 슬립 위치) 이미 실행 중이던 지연 스크립트가 계속 iframe을 만들어 효과가 상쇄됨을 확인 — 그래서 지터 슬립 재배치가 필수적이었다. 실제 CBMi 8건 재검증 — 8/8 정상 resolve, renderer 3→4(§7 단독 적용 시 3→6).

## 남은 작업

- 8번 적용 후 서버 mem 로그로 잔여 스파이크가 실제로 더 줄었는지 확인 (아직 실측 전 — 사용자가 직접 배포해 확인 예정)
- extraction-worker는 URL마다 새 탭을 열고 즉시 `close()`하는 구조라 상대적으로 안전할 것으로 추정되나 아직 실측 안 함 — 데이터 쌓이면 discovery-worker와 동일한 방식으로 점검
- 실측치가 쌓이는 대로 `MEM_LIMIT` 티어 값(현재는 관찰 전 임시값) 재조정
- rss 폴백 자체가 봇 차단 회피 수단인데 메모리 리스크의 진앙이라는 구조적 모순은 여전함 — 8번으로도 부족하면 리전/프로필 분리 등 추가 완화 검토
