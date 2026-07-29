# 메모리 사용량 로깅 & OOM 완화 (현재 상태)

`google_news`/`baidu_news`(undetected-chromedriver 기반) 어댑터는 Chrome을 직접
띄우기 때문에 워커 중 메모리 리스크가 가장 크다. 아래는 현재 적용돼 있는 진단·완화
장치를 상태 기준으로 정리한 것이다.

## 1. 진단: 메모리 사용량 로깅

heartbeat 주기(기본 60초, `HEARTBEAT_INTERVAL_SECONDS`)마다 워커 자신 + Chrome 자식
프로세스의 RSS를 타입별(renderer/gpu-process/utility/zygote/crashpad 등)로 나눠
`{log_name}-mem.log`에 기록한다(`app/memlog.py`, `app/logging_setup.py`의
`"memlog"` 전용 로거, `propagate=False`라 app.log/console엔 안 섞임).
`app/scheduling/dispatcher.py`의 heartbeat 스레드에서 호출된다.
extraction-worker에도 동일 구조가 적용돼 있다.

## 2. 컨테이너 메모리 제한 (`deploy/run.sh`)

소스별 티어로 `--memory`/`--memory-swap`(스왑 비활성)을 부여한다:
`google_news`/`baidu_news`/`all` = `1.5g`, 나머지 = `512m`.
`MEM_LIMIT` 환경변수로 스크립트 수정 없이 오버라이드 가능
(예: `MEM_LIMIT=3g ./deploy/run.sh google_news disc-google-1`).
스왑을 꺼서 초과 시 즉시 kill되게 해 mem 로그 마지막 기록과 재시작 시점이
정확히 대응되도록 한다. extraction-worker는 소스 필터로 안전하게 티어링할
근거(`render_mode`가 도메인별 설정이라 source_type과 무관)가 없어 균일하게
`1.5g` 적용돼 있다.

## 3. Chrome 실행 옵션 (`google_news.py` / `baidu_news.py`)

두 어댑터 모두 다음 Chrome 옵션으로 띄운다:
- `--disable-features=BackForwardCache,IsolateOrigins,site-per-process` — 뒤로가기 캐시와 출처별 프로세스 격리를 꺼서 불필요한 렌더러 프로세스를 줄인다. 검색 결과 페이지는 XPath로 링크 텍스트만 읽고 시각적 렌더링을 안 쓰므로 기능 영향은 없다.
- `prefs: {"profile.managed_default_content_settings.images": 2}` — 이미지 로드 차단.
- `page_load_strategy = "eager"` — DOMContentLoaded 시점에 `driver.get()`이 리턴하게 해, 페이지 하위 리소스(광고 등) 로드 완료를 기다리지 않는다.

## 4. RSS 폴백 모드(CBMi 해석)의 메모리 관리

`google_news.py`의 `rss` 모드(`_resolve_cbmi()`)는 구글 도메인이 아니라 광고/트래커가
많은 실제 언론사 사이트를 여러 개 열어야 해서, 정상 `search` 페이지네이션(구글 도메인
안에서만 페이징)보다 메모리 리스크가 훨씬 크다. 아래 세 가지가 함께 적용돼 있다:

- **URL마다 새 탭을 열고 확인 즉시 닫음**: 같은 탭을 재사용하며 이동만 하면 Chrome이
  이전 페이지의 renderer 프로세스를 곧바로 정리하지 않고 쌓아두는 반면, 탭을 명시적으로
  닫으면 방문마다 거의 베이스라인으로 리셋된다. 브라우저 전체 재시작 없이 URL 단위로
  누적을 막는다.
- **광고/트래커 도메인 차단**: 주요 도메인 목록(`_AD_TRACKER_DOMAINS`)을
  `--host-resolver-rules`로 `0.0.0.0`에 매핑해 DNS 단계에서 차단 — 별도 확장 파일 없이
  코드만으로 적용되며 Dockerfile/빌드 변경이 필요 없다.
- **리다이렉트 감지 즉시 `Page.stopLoading()`**: `current_url`이 news.google.com을
  벗어나는 순간(`_wait_for_cbmi_redirect()`, poll_interval 0.05초) 그 페이지의 나머지
  로딩을 강제로 끊는다. URL 판별 기준 자체는 그대로라 URL 유실 위험은 없다 — 이후
  탐지 회피용 지터 슬립도 탭을 닫은 뒤로 배치해, stopLoading 이후 탭을 계속 열어두며
  지연 스크립트가 iframe을 더 만드는 걸 막는다.

이 세 가지는 서로 다른 각도에서 같은 문제(외부 페이지의 광고 iframe이 renderer
프로세스를 늘리는 것)를 줄인다 — 탭 닫기는 "생긴 걸 확실히 치움", 도메인 차단과
stopLoading은 "애초에 덜 생기게 함"이다.

## 알려진 한계

- 도메인 차단 목록에 없는 광고/트래커(지역 네트워크, 특정 퍼블리셔 자체 광고 등)가
  유독 많은 개별 페이지를 방문하면 그 순간 renderer가 일시적으로 튀었다가 다음 방문에서
  바로 회복되는 패턴이 남아있다 — 페이지 하나가 원인인 단발성 스파이크이며, 누적되며
  계속 커지는 문제는 아니다.
- extraction-worker는 URL마다 새 탭을 열고 즉시 닫는 구조라 상대적으로 안전할 것으로
  추정되나 실측 확인은 안 돼 있다.
- `MEM_LIMIT` 티어 값은 실측 기반 재조정이 필요할 수 있다.
- rss 폴백 자체가 봇 차단 회피 수단인데 메모리 리스크의 진앙이라는 구조적 긴장은
  여전하다 — 위 조치로도 부족하면 리전/프로필 분리 등을 검토한다.
