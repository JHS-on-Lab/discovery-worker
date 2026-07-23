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
