# Commit Log

이 저장소에 커밋될 때마다 커밋ID·날짜·메시지·수정된 파일 목록을 기록한다.
최신 항목이 맨 위로 오도록 앞에 추가한다.

> 주의: 커밋 자신의 해시는 그 커밋 내용(트리)을 해시한 결과라서, 같은 커밋 안에
> 자기 자신의 해시를 담을 수 없다(자기 참조 불가). 그래서 이 파일은 매 커밋을
> "즉시" 기록하는 게 아니라, **다음 커밋을 만들 때 직전 커밋의 항목을 함께
> 기록**하는 방식으로 갱신한다 — 커밋 수를 늘리지 않으면서 정확한 해시를 남기기
> 위한 절충이다. 따라서 가장 최근 커밋 하나는 그다음 커밋이 생기기 전까지 이
> 목록에 아직 나타나지 않을 수 있다.

---

## 5cc152a — 2026-07-29
perf: pageLoadStrategy=eager + current_url 폴링으로 CBMi 해석 시 불필요한 페이지 로드 대기 제거

- app/adapters/google_news.py
- docs/commit-log.md

## 7b995a7 — 2026-07-29
fix: rss 모드 CBMi URL 해석을 배치로 나눠 Chrome 을 주기적으로 재시작

- app/adapters/google_news.py
- docs/commit-log.md

## 2a6f1bc — 2026-07-29
fix: 더미 키워드 대신 실제 뉴스 키워드 여러 개로 renderer 급증 재현 시도

- docs/commit-log.md
- scripts/check_chrome_isolation.py

## 761e5d6 — 2026-07-29
fix: 검색 1건짜리 재현 테스트를 연속 페이지네이션으로 확장

- docs/commit-log.md
- scripts/check_chrome_isolation.py

## 7f2efa4 — 2026-07-29
fix: 진단 스크립트의 WORKER_ID 오버라이드가 실제로 안 먹히던 문제 수정

- docs/commit-log.md
- scripts/check_chrome_isolation.py

## 1278906 — 2026-07-29
feat: Site Isolation/BackForwardCache 플래그 실제 적용 여부 진단 스크립트 추가

- .gitignore
- docs/commit-log.md
- scripts/check_chrome_isolation.py

## e8811da — 2026-07-28
feat: t_keyword.source_options_json 의 region 오버라이드를 google_news 어댑터에 연결

- app/adapters/google_news.py
- app/repository/keyword_repo.py
- app/scheduling/dispatcher.py
- docs/commit-log.md

## 8a48e55 — 2026-07-28
fix: .gitignore 의 chrome_profile/ 패턴이 실제 기본 경로와 안 맞던 문제 수정

- .gitignore
- docs/commit-log.md

## feef7dd — 2026-07-28
fix: macOS 에서 Chrome 바이너리 탐지 실패하는 문제 수정

- app/adapters/baidu_news.py
- app/adapters/google_news.py
- docs/commit-log.md

## 73068bb — 2026-07-28
fix: macOS 로컬 개발 환경에서 Xvfb 기동 시도로 크래시하는 문제 수정

- app/adapters/baidu_news.py
- app/adapters/google_news.py
- docs/commit-log.md

## 892b4dc — 2026-07-28
feat: mem 로그에 Chrome 자식 프로세스 타입별(renderer/gpu/utility/crashpad 등) breakdown 추가

- app/memlog.py
- docs/commit-log.md

## bea91d0 — 2026-07-23
docs: 메모리 로깅/OOM 완화 작업 As-Is·To-Be 정리 문서 추가

- docs/commit-log.md
- docs/memory-oom-mitigation.md

## de897b9 — 2026-07-23
perf: google/baidu Chrome 메모리 절감 옵션 추가 (BFCache/Site Isolation 끄기, 이미지 끄기)

- app/adapters/baidu_news.py
- app/adapters/google_news.py
- docs/commit-log.md

## 8eb7b24 — 2026-07-23
feat: heartbeat 주기 메모리 사용량 로깅 + 소스별 컨테이너 메모리 제한

- app/logging_setup.py
- app/memlog.py
- app/scheduling/dispatcher.py
- deploy/run.sh
- docs/commit-log.md

## d1b94f5 — 2026-07-17
docs: 커밋 로그 트래킹 파일 추가 (docs/commit-log.md)

- docs/commit-log.md

## 6130a48 — 2026-07-16
docs: add README, fix baidu_news gaps and stale Playwright references

- .env
- .gitignore
- README.md
- deploy/run.sh
- docs/db/schema.sql
- docs/discovery-worker-design.md
- docs/ops-commands.md
- docs/python-setup.md
