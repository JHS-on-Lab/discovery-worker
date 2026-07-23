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

**효과**: 재배포 후 mem 로그로 피크값(이전 관찰치 최대 4.6GB)이 줄었는지 확인 필요 — 아직 서버 실측 전.

## 남은 작업

- Chrome 옵션 변경 후 mem 로그로 실제 효과(피크 감소폭) 확인
- extraction-worker는 URL마다 새 탭을 열고 즉시 `close()`하는 구조라 상대적으로 안전할 것으로 추정되나 아직 실측 안 함 — 데이터 쌓이면 discovery-worker와 동일한 방식으로 점검
- 실측치가 쌓이는 대로 `MEM_LIMIT` 티어 값(현재는 관찰 전 임시값) 재조정
