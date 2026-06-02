# 네이버 · 다음 뉴스 발견 방식

## 현재 구현

### 네이버

**엔드포인트**
```
GET https://search.naver.com/search.naver
    ?where=news&query={keyword}&sort=1&pd=4&start={offset}
```

- `sort=1` = 최신순, `pd=4` = 1일 이내 (실측값, 공식 문서 없음)
- `start` 파라미터로 페이지네이션: 1 → 11 → 21 → ...
- 단순 HTTP GET, JS 실행 불필요
- 기사 링크 추출: 부모 클래스가 `sds-comps-base-layout` 인 `a[href]` + 차단 호스트 제외
  - 네이버 SDS(Smart Design System) 구조 클래스 — 빌드마다 해시가 바뀌는 `fender-ui_` 대신 사용
  - 0개 반환 시 `WARNING` 로그 출력

**기사 URL**: 언론사 직접 URL (예: `https://www.mk.co.kr/article/...`)

### 다음

**엔드포인트**
```
GET https://search.daum.net/search
    ?w=news&q={keyword}&sort=recency&period=d&p={page}
```

- `p` 파라미터로 페이지네이션: 1 → 2 → 3 → ...
- 기사 링크 추출: `a[href*="v.daum.net/v/"]` + `class=""` 조건

**기사 URL**: Daum 뷰어 URL (예: `http://v.daum.net/v/20260531003218841`)

---

## 안정성

| 항목 | 네이버 | 다음 |
|---|---|---|
| 셀렉터 | `sds-comps-base-layout` 부모 클래스 — 안정 | URL 패턴 기반 — 안정 |
| JS 렌더링 필요 | 불필요 | 불필요 |
| 차단 위험 | 낮음 | 낮음 |

**webdriver 전환 기준**: 정적 HTTP가 지속 실패하거나 JS 렌더링이 강제될 때. 현재는 해당 없음.

---

## 모니터링 쿼리

```sql
-- 최근 7일 수집량 추이 (급감 감지)
SELECT run_date, k.keyword, cl.portal_type, cl.urls_found
FROM collection_log cl
JOIN keyword k ON k.id = cl.keyword_id
WHERE cl.run_type = 'discovery'
  AND cl.run_date >= CURDATE() - INTERVAL 7 DAY
ORDER BY k.keyword, cl.portal_type, cl.run_date;

-- 오늘 수집량 0 (셀렉터 파손 의심)
SELECT k.keyword, cl.portal_type, cl.urls_found, cl.started_at
FROM collection_log cl
JOIN keyword k ON k.id = cl.keyword_id
WHERE cl.run_type = 'discovery'
  AND cl.run_date = CURDATE()
  AND cl.urls_found = 0;
```
