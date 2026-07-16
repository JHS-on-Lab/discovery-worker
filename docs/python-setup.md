# Python 환경 설정 가이드

## pip 업그레이드

```bash
python -m pip install --upgrade pip
```

---

## 라이브러리 설치

### 일반 환경 (개인 PC / 외부 서버)

```bash
pip install -r requirements.txt
```

### 사내 네트워크 / 클라우드 환경 (SSL 인증서 오류 발생 시)

사내 프록시가 자체서명 인증서를 사용하는 경우 `--trusted-host` 옵션이 필요하다.

```bash
pip install -r requirements.txt \
  --trusted-host pypi.org \
  --trusted-host files.pythonhosted.org \
  --trusted-host pypi.python.org
```

> **증상:** `SSL: CERTIFICATE_VERIFY_FAILED` 또는 `certificate verify failed: self-signed certificate in certificate chain`

---

## Chrome / undetected-chromedriver 설치 (google_news, baidu_news 필수)

이 저장소는 Playwright를 쓰지 않는다(`requirements.txt`에 없음, 코드 어디서도 import하지
않음). `google_news`/`baidu_news` 어댑터는 봇 탐지를 우회하기 위해
`undetected-chromedriver` + `selenium`으로 실제 Chrome 브라우저를 headful/headless로
직접 띄운다(`app/adapters/google_news.py`, `app/adapters/baidu_news.py`).

- **Chrome 설치 필요**: `undetected_chromedriver`는 시스템에 설치된 Chrome/Chromium
  바이너리를 찾아 구동한다(`_detect_chrome_binary()`가 OS별 표준 설치 경로·레지스트리를
  탐색). Chrome이 없으면 두 어댑터는 동작하지 않는다.
- **드라이버 버전 자동 매칭**: `undetected-chromedriver`가 설치된 Chrome 메이저 버전에
  맞는 chromedriver를 자동으로 내려받으므로 별도 `chromedriver install` 단계는 없다.
  단, Chrome을 업그레이드하면 캐시된 드라이버와 버전이 어긋나 재시도가 필요할 수 있다.
- **Google 어댑터는 headless=False로 실행**(Google 봇 탐지 회피, `google_news.py` 상단
  주석 참고): 로컬 macOS/Windows에서는 실제 창이 뜬다. **Linux 서버(Xvfb 필요)**: 디스플레이가
  없으면 어댑터가 `Xvfb`를 자동 기동하므로(`_ensure_xvfb()`), Docker 이미지가 아닌 로컬 Linux
  환경에서 직접 돌릴 경우 `xvfb` 패키지가 설치돼 있어야 한다(`apt-get install -y xvfb` 등).
  Docker로 실행하면 `Dockerfile`이 `google-chrome-stable`/`xvfb`를 이미 포함하므로 신경 쓸
  필요 없다.

---

## 앱 실행 시 SSL 설정

사내 프록시 환경에서는 HTTP 요청에도 SSL 검증 오류가 발생한다.  
`.env.local` 에 아래 항목을 추가한다.

```
HTTP_VERIFY_SSL=false  # 사내 프록시 자체서명 인증서로 인한 SSL 검증 비활성화
```

외부 서버(Ubuntu 등) 에서는 설정하지 않거나 `true` 로 유지한다.
