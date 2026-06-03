# Google 발견 방식

## 현재 구현

`UCGoogleAdapter` — `GOOGLE_DISCOVERY_MODE` 환경변수로 수집 방식을 선택한다.

### search 모드 (기본)

`google.com/search?q={keyword}&tbm=nws` 를 Chrome으로 스크랩.

- 언론사 직접 URL 반환, 리다이렉트 불필요
- `&start=N` 페이지네이션으로 100개 한도 없음

### rss 모드 (봇 차단 시 대안)

Google News RSS 피드를 HTTP로 가져온 뒤, CBMi 리다이렉트 URL을 Chrome으로 변환.

- RSS는 HTTP로 빠르게 가져오고 (최대 ~100건), Chrome은 URL 변환에만 사용
- 페이지네이션 없음 (단일 호출)
- search 모드가 봇 감지로 막혔을 때 `.env`에서 전환

```bash
GOOGLE_DISCOVERY_MODE=search   # 기본
GOOGLE_DISCOVERY_MODE=rss      # 봇 차단 시
```

**headless 모드 불가**: headless(구형·신형 모두) 는 Google Bot 감지에 걸린다. `headless=False` 로 실제 브라우저를 구동한다.

| 환경 | 처리 방식 |
|------|-----------|
| Windows 로컬 | `--window-position=-32000,-32000` 으로 창을 화면 밖으로 이동 |
| Linux Docker | `xvfb-run` 가상 디스플레이 (`deployment.md` 참고) |

---

## max_pages 선정 기준 (search 모드)

페이지당 10건, `delay_sec=1.5` 기준.

| max_pages | 최대 수집 | 소요 시간(최소) | 권장 상황 |
|-----------|-----------|----------------|-----------|
| 3 | 30건 | ~5초 | 소규모 키워드, 수집 주기가 짧을 때 |
| **5 (기본)** | **50건** | **~8초** | **일반적인 인기 키워드** |
| 10 | 100건 | ~15초 | 전수 수집이 필요할 때 |

**5페이지 이상은 권장하지 않는 이유**
- `tbs=qdr:d`(1일) 기준으로 핵심 콘텐츠는 1~3페이지에 집중됨
- 4페이지 이후는 중복·관련성 낮은 콘텐츠 비율 증가
- 페이지 수가 많을수록 Bot 감지 리스크 상승
- 더 많이 필요하면 `GOOGLE_DISCOVERY_MODE=rss` 전환이 효율적 (~100건, 단일 호출)

---

## RSS 방식을 버린 이유

Google News RSS(`news.google.com/rss/search`)는 기사 URL이 `CBMi...` 형태의 Google 내부 리다이렉트 URL이다. 실제 언론사 URL로 해소하는 방법을 모두 시도했으나 실패했다.

| 시도 | 결과 |
|------|------|
| HTTP HEAD/GET + follow_redirects | `302 → Google News SPA(200)` 에서 끊김 |
| Playwright headless | Google Bot 감지 → 400 Bad Request |
| CBMi base64 디코딩 | protobuf 구조라 단순 디코딩 불가 |

