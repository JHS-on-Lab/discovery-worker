# 빠른 시작 가이드

처음 코드를 받고 첫 수집까지 완료하는 순서를 설명한다.

---

## 사전 요건

| 항목 | 버전 |
|------|------|
| Python | 3.11 이상 |
| uv | 최신 (`pip install uv`) |
| RDS MySQL | 접근 가능한 상태 |
| SSH 키 | 터널 사용 시 `.pem` 파일 |

---

## 1단계 — 환경 설정

### 가상환경 생성 및 패키지 설치

```bash
cd news-crawler
uv venv
uv pip install -r requirements.txt
```

Playwright(headless 브라우저)가 필요하면:
```bash
playwright install chromium
```

### .env 파일 작성

환경별로 파일이 분리돼 있다. `APP_ENV` 환경변수로 선택한다.

| 환경 | 파일 | APP_ENV |
|------|------|---------|
| 로컬 Windows | `.env.local` | 미설정 (기본값 `local`) |
| Ubuntu 서버 | `.env.dev` | `dev` |

두 파일 모두 Git에 올라가지 않는다 (`.gitignore`의 `.env.*` 규칙).  
팀원에게 직접 받아서 프로젝트 루트에 복사한다.

**Ubuntu 서버에서 실행 시:**
```bash
export APP_ENV=dev
python -m news_crawler --role discovery --portal naver
```

또는 systemd/Docker 환경변수로 `APP_ENV=dev` 주입.

`.env.local` / `.env.dev` 파일이 없으면 `.env` 로 폴백된다.

---

## 2단계 — DB 연결 확인

```bash
python scripts/check_db.py
```

```
DB 연결 확인 중...
  MySQL 버전 : 8.4.x
  현재 DB   : news_crawler
연결 성공.
```

오류가 나면 `.env` 의 RDS 정보 또는 SSH 키 경로를 확인한다.

---

## 3단계 — DB 스키마 생성 (최초 1회)

```bash
python -m alembic upgrade head
```

```
Running upgrade  -> 5e62426e4d2f, initial_schema
Running upgrade 5e62426e4d2f -> ...
```

완료 후 테이블이 잘 만들어졌는지 확인:
```bash
python scripts/verify_schema.py
```

---

## 4단계 — 키워드 등록

수집할 검색어와 포털을 등록한다.

```bash
python scripts/add_keyword.py --keyword "삼성전자" --portal NAVER
python scripts/add_keyword.py --keyword "삼성전자" --portal DAUM
python scripts/add_keyword.py --keyword "삼성전자" --portal GOOGLE
```

등록 결과 확인:
```sql
SELECT id, keyword, portal_type, enabled, next_discover_at FROM keyword;
```

---

## 5단계 — 발견 워커 실행

키워드를 순환하며 뉴스 기사 URL을 수집한다.

```bash
# 한 번 실행하고 결과 확인 (자동 루프 X)
python scripts/run_discovery.py --keyword "삼성전자" --portal NAVER

# 자동 루프 (계속 실행)
python -m news_crawler --role discovery --portal naver
```

수집 결과 확인:
```sql
SELECT status, COUNT(*) FROM article_url GROUP BY status;
```

`discovered` 건수가 보이면 정상.

---

## 6단계 — 추출 워커 실행

발견된 URL에서 본문을 스크랩해 파일로 저장한다.

```bash
# N건만 처리하고 종료 (테스트용)
python scripts/run_extraction.py --limit 10

# 자동 루프 (계속 실행)
python -m news_crawler --role extraction
```

---

## 7단계 — 결과 확인

```bash
# 저장된 파일 목록
dir data\

# 샘플 1건 출력 (PowerShell) — worker-id 기본값은 worker-1
Get-Content data\2026-05-31\NAVER-worker-1.jsonl | Select-Object -First 1 | python -m json.tool
```

JSON 구조:
```json
{
  "url": "https://...",
  "title": "기사 제목",
  "body": "본문 전체...",
  "portal_type": "NAVER",
  "keyword": "삼성전자",
  "extraction_method": "trafilatura",
  "collected_at": "2026-05-31T12:00:00+00:00"
}
```

---

## 자주 쓰는 운영 명령어

상세한 SQL과 명령어는 [ops-commands.md](ops-commands.md) 참고.

```bash
# 실패한 URL 현황
python scripts/requeue_failed.py --show

# 특정 URL이 어느 도메인에서 잘 안 되는지 확인
# → SQL: SELECT host, last_error_code, COUNT(*) FROM article_url WHERE status != 'stored' GROUP BY host, last_error_code;
```

---

## 문제가 생겼을 때

| 증상 | 확인할 것 |
|------|-----------|
| DB 연결 실패 | `.env` RDS 정보, SSH 키 경로, EC2 상태 |
| 발견 URL 0건 | `preview_adapter.py` 로 어댑터 직접 테스트, 셀렉터 파손 가능 |
| 추출 PARSE_ERROR 반복 | JS 렌더링 필요 사이트. `add_domain_rule.py --render headless` 고려 |
| `extracting` 상태 URL 쌓임 | Reaper 가 5분 후 자동 회수. 급하면 `ops-commands.md` 수동 회수 SQL 실행 |
