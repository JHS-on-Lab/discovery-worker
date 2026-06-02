# keyword 통계 → collection_log 이전

## 결정 요약

`keyword` 테이블에 있던 `last_discovery_url_count`, `last_discovery_duration_ms` 컬럼을 제거하고,
런 단위 통계를 `collection_log` 테이블에 저장한다.

## 이유

`keyword` 테이블에 두면 마지막 실행 결과만 남는다.

- 어제 50건 → 오늘 5건이 된 원인을 알 수 없음
- 실패 시 컬럼이 갱신되지 않아 성공/실패 구분 불가
- 포털별·날짜별 추이 조회 불가능

## 현재 구조

| 테이블 | 저장 내용 |
|--------|-----------|
| `keyword` | `last_discovered_at` — 마지막 성공 시각만 보존 |
| `collection_log` | 런마다 1행: `urls_found`, `urls_inserted`, `urls_skipped`, `duration_ms`, `error_msg` |
