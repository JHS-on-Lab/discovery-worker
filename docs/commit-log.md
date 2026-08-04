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

## 79064c5 — 2026-08-04
chore: docker run --user 를 1001:1001 로 고정

- deploy/run.sh
- docs/commit-log.md

## bfc35fb — 2026-07-31
chore: BAOMOI_MAX_PAGES 를 .env에 명시적으로 추가

- .env
- docs/commit-log.md

## 39695e8 — 2026-07-31
feat: baomoi.com(Báo Mới, 베트남 뉴스 애그리게이터) 발견 어댑터 추가

- app/__main__.py
- app/adapters/__init__.py
- app/adapters/baomoi_news.py
- app/config.py
- app/types.py
- deploy/run.sh
- docs/commit-log.md
- scripts/run_discovery.py

## 9047a67 — 2026-07-31
docs: 새 어댑터 개발 참고용 카탈로그 추가 (docs/adapter-catalog.md)

- README.md
- docs/adapter-catalog.md
- docs/commit-log.md

## 285ed36 — 2026-07-31
docs: 구글 리전 오버라이드(source_options_json) 예시와 사용법 문서화

- docs/commit-log.md
- docs/discovery-worker-design.md

## 050c42a — 2026-07-31
perf: 봇 차단 감지에 reCAPTCHA iframe 구조 체크 추가 (언어 무관 신호 보강)

- app/adapters/google_news.py
- docs/commit-log.md

## cc449ce — 2026-07-31
fix: rss 폴백 모드가 t_keyword.source_options_json 의 region 오버라이드를 무시하던 문제 수정

- app/adapters/google_news.py
- docs/commit-log.md

## 0d90845 — 2026-07-31
perf: rss 모드 쿼리에 when:1d 추가 — 서버 단계에서 최근 1일로 후보군 제한

- app/adapters/google_news.py
- docs/commit-log.md

## 492800f — 2026-07-29
docs: duckduckgo_news 재활성화 — "운영상 비활성" 표기 제거

- README.md
- docs/commit-log.md
- docs/discovery-worker-design.md
- docs/ops-commands.md

## 4563bf1 — 2026-07-29
docs: memory-oom-mitigation.md 를 이력 나열 대신 현재 상태 기준으로 재정리

- docs/commit-log.md
- docs/discovery-worker-design.md
- docs/memory-oom-mitigation.md

## dba7b82 — 2026-07-29
docs: stopLoading + 탭 즉시 닫기(8번) 문서화, 실측 기반 잔여 스파이크 원인 기록

- docs/commit-log.md
- docs/memory-oom-mitigation.md

## 6d5c71e — 2026-07-29
perf: CBMi 리다이렉트 감지 즉시 Page.stopLoading + 탭 즉시 닫기로 광고 iframe 차단 강화

- app/adapters/google_news.py
- docs/commit-log.md

## ec4741c — 2026-07-29
docs: 배치 재시작 → URL별 탭 열고 닫기 교체 반영 (7번 섹션 추가)

- docs/commit-log.md
- docs/discovery-worker-design.md
- docs/memory-oom-mitigation.md

## d749746 — 2026-07-29
perf: rss 모드 CBMi 해석을 배치 재시작 대신 URL별 새 탭 열고 즉시 닫기로 변경

- app/adapters/google_news.py
- docs/commit-log.md

## d042617 — 2026-07-29
docs: 광고/트래커 도메인 차단(6번) 및 재시도/폴백 상호작용 문서화

- docs/commit-log.md
- docs/discovery-worker-design.md
- docs/memory-oom-mitigation.md

## c9d710d — 2026-07-29
perf: rss 폴백 시 광고/트래커 도메인을 host-resolver-rules 로 차단

- app/adapters/google_news.py
- docs/commit-log.md

## b9b70d3 — 2026-07-29
refactor: 전체 코드베이스 품질 리뷰(reuse/simplification/efficiency/altitude) 적용

- app/adapters/__init__.py
- app/adapters/_base.py
- app/adapters/_chrome_behavior.py
- app/adapters/baidu_news.py
- app/adapters/google_news.py
- app/config.py
- app/repository/collection_log_repo.py
- app/repository/crawl_url_repo.py
- app/repository/db.py
- app/scheduling/dispatcher.py
- docs/commit-log.md
- scripts/healthcheck.py
- scripts/run_discovery.py
- scripts/verify_schema.py

## 76efeec — 2026-07-29
refactor: 오늘 세션 diff에 대한 품질 리뷰(reuse/simplification/efficiency/altitude) 적용

- app/adapters/_chrome_detect.py
- app/adapters/baidu_news.py
- app/adapters/google_news.py
- app/memlog.py
- app/ports.py
- app/repository/crawl_url_repo.py
- app/scheduling/dispatcher.py
- app/types.py
- docs/commit-log.md
- scripts/check_chrome_isolation.py

## 4e122a9 — 2026-07-29
fix: bulk_insert_discovered() 의 inserted/skipped 카운트가 rowcount 에 의존해 부정확하던 문제 수정

- app/repository/crawl_url_repo.py
- docs/commit-log.md

## 0073cf8 — 2026-07-29
feat: t_crawl_url.discovery_mode 로 google_news search/rss 발견 모드 영구 기록

- app/adapters/google_news.py
- app/repository/crawl_url_repo.py
- app/scheduling/dispatcher.py
- app/types.py
- docs/commit-log.md

## 7d0b10e — 2026-07-29
docs: 구글 RSS 폴백 봇 차단 감지 조건 문서화 + 메모리 완화 조치 4·5번 기록

- docs/commit-log.md
- docs/discovery-worker-design.md
- docs/memory-oom-mitigation.md

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
