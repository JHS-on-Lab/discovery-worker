"""
Tinh tế(tinhte.vn, 베트남 IT/가전 커뮤니티) 발견 어댑터.

tinhte.vn 화면의 검색창은 자체 검색이 아니라 사이트에 임베드된 **Google Custom
Search Engine(GCSE) 무료 위젯**이다(검색창 마크업이 `<div class="gcse-search">`).
이 어댑터는 실제 사람처럼 그 검색창에 타이핑하고 결과를 DOM에서 읽어온다.

이 방식에 이르기까지 시도했다가 버린 것들(2026-08-03~04 조사):
  - 정적 HTTP(httpx)로 GCSE 내부 검색 엔드포인트(cse.google.com/cse/element/v1)를
    두 단계(cse.js 로 cse_token 발급 → 검색)로 직접 흉내 — 검색 엔드포인트만
    반복 요청 시 `403 + <title>Sorry...</title>` 차단.
  - curl_cffi(Chrome TLS/JA3 지문 위장)로도 동일하게 차단 — 즉 TLS 핑거프린팅
    문제가 아니었음.
  - undetected-chromedriver로 브라우저를 띄우고 그 페이지 컨텍스트 안에서
    `<script>` 태그로 검색 URL을 직접 불러오는 방식(JSONP 흉내) — 응답에
    `Content-Disposition: attachment`가 붙어있어 최신 Chrome이 스크립트 실행이
    아니라 파일 다운로드로 처리해버려 무한 대기(차단이 아니라 브라우저 정책 문제).
  → 결론: API를 흉내내지 말고 실제 검색창에 타이핑 → 결과는 검색엔진 API를 직접
    두드리는 게 아니라 위젯이 알아서 렌더링하므로 이 문제들을 전부 우회한다.

실측 확인된 DOM 구조(2026-08-04, 사용자 환경에서 실제 검색 후 확인):
  - 검색창: `input.gsc-input` (placeholder="Tìm sản phẩm công nghệ, cộng đồng, bạn bè...")
  - 결과: 최상위 문서에 바로 렌더링됨(iframe 전환 불필요) — 우려와 달리 오버레이가
    top-level DOM 안에 뜬다. 결과 링크는 `a.gs-title`의 href 속성에 tinhte.vn
    URL이 그대로 들어있다(트래킹 URL 파싱 불필요).
  - 페이지네이션: `.gsc-cursor-page` 요소들이 페이지 번호(1~10)로 나열되고
    클릭하면 그 페이지로 이동한다("다음" 화살표 버튼이 아니라 번호 클릭 방식).
  - 정렬: 검색 직후 기본값은 관련도순(Relevance). `.gsc-selected-option-container`
    클릭 → 드롭다운(`.gsc-option-menu-item`)에서 "Date" 클릭하면 최신순으로 바뀜
    (실측: 관련도순/날짜순 상위 결과가 확실히 달라짐 확인). 검색 키워드 제출
    직후 이 클릭을 자동으로 수행해 항상 최신순으로 받는다.

undetected-chromedriver 대신 순정 selenium을 쓰는 이유: 이 환경에서
undetected-chromedriver + Chrome 151 조합이 세션 생성 직후 창이 닫히는 문제가
반복 발생(실측, 수 회 연속 실패)했고, 순정 selenium은 매번 안정적으로 동작했다.
이제는 API를 직접 흉내내는 게 아니라 사람처럼 타이핑하는 방식이라, UC의 스텔스
패치(webdriver 플래그 은닉 등)가 결정적으로 필요하지도 않다.

검증 완료(2026-08-04, 실제 브라우저로 'samsung' 키워드 3페이지 연속 실행):
  - 1~3페이지 전부 10건씩, 서로 다른 실제 tinhte.vn 글 URL 정상 추출.
  - `.gsc-cursor-page` 번호 클릭으로 페이지 이동 정상 동작.
  - `has_more` 가 max_pages(3)에서 정확히 False 로 멈춤.

**검색 결과 노이즈 문제 — 관리자 확인 후 결정 예정** (2026-08-04, samsung/iphone/xe
3개 키워드로 실측, 현재 미적용 상태):
  - tinhte.vn 모든 페이지에 공통으로 뜨는 사이드바("인기글" 등)가 있어서, 완전히
    무관한 키워드로 검색해도 그 사이드바에 지금 우연히 실린 글이 결과에 섞여
    나온다. 3개 키워드 검색에서 노이즈 비율이 80~90%에 달했고, 노이즈로 뜨는
    제목 목록이 키워드와 무관하게 거의 동일하게 겹쳤다(사이드바 콘텐츠라는 증거).
  - **검증됨, 아직 미적용**: 검색 결과 제목(`a.gs-title` 텍스트)에 키워드가 실제로
    포함된 것만 남기는 필터를 만들어 실측까지 마쳤고 노이즈를 거의 다 걸러내는 걸
    확인했으나(브랜드명 대신 제품 라인명만 쓴 제목은 놓칠 수 있다는 트레이드오프
    있음), **관리자 확인 후 적용 여부를 결정하기로 하고 코드에서는 뺐다**
    (`_extract_result_urls` 는 지금 `/thread/` URL 패턴 필터만 적용, keyword
    인자는 향후 이 필터를 다시 넣을 때 바로 쓰도록 시그니처에만 남겨둠). 즉
    **지금 이 어댑터가 반환하는 URL에는 노이즈가 80~90% 섞여 있을 수 있다** —
    관리자 확인 후 이 필터를 켤지, 아니면 다른 기준으로 갈지 결정 필요.
  - **시도했다가 기각**(제목 필터와 별개로, 켜든 안 켜든 이 안 자체는 폐기):
    스니펫(`.gs-snippet`, 제목 밑 요약)까지 같이 검사하는 안. 스니펫은 사이드바
    보다 더 심하게 오염돼 있어서(구글이 스니펫으로 사이드바 "인기글" 목록이나
    사이트 푸터 메뉴 텍스트까지 뽑아옴), 스니펫 포함 시 매치율이 96~100%로
    치솟아 필터 의미가 없어졌다.

이름에 관해 — `TINHTE_NEWS`가 아니라 `TINHTE_FORUM`인 이유: tinhte.vn은 뉴스
매체가 아니라 XenForo 기반 커뮤니티 포럼이고, 이 어댑터가 모으는 건 "뉴스"가
아니라 검색어에 걸리는 **모든 게시판의 스레드**다(스마트폰 뉴스뿐 아니라 잡담,
DIY, 리뷰, 차량, 사진/음악, 광고 게시글까지 카테고리 무관). `NAVER_STOCK`이
`_NEWS`가 아니라 콘텐츠 실체(종목토론)를 반영한 접미사를 쓰는 것과 같은 이유로
`_FORUM`을 택함(2026-08-04, TINHTE_NEWS 에서 개명).

미검증/제약:
  - **최근 1일 컷오프 불가**: 결과 DOM에 발행일 정보가 없다(baomoi의 <time
    datetime> 같은 게 없음). 컷오프 없이 t_crawl_url.url_hash dedup 에 맡긴다.
  - 봇 차단 신호(구글 CSE API를 직접 두드릴 때 나오는 `403 Sorry`)는 이 방식
    에선 아예 안 나오는 것으로 보이나(사람과 동일 경로라), 장시간 대량 수집 시
    나타날 수도 있어 지켜봐야 한다 — 지금 코드엔 이 상황에 대한 별도 감지/처리가
    없음(검색창을 못 찾는 경우만 BotBlockedError 로 처리).
  - 제목 필터를 켤 경우 실수확량이 낮아진다(키워드당 페이지를 여러 장 넘겨야
    유의미한 글이 몇 건 나오는 수준, 실측 페이지당 1~2건꼴) — 페이지 이동/대기
    비용 대비 수율이 낮은 편이라는 걸 감안해야 한다. (지금은 필터를 껐으니
    페이지당 최대 10건까지 그대로 나오지만, 위 "검색 결과 노이즈 문제"에
    적었듯 그중 80~90%가 노이즈일 수 있다.)
"""

from __future__ import annotations

import logging
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from app import config
from app.adapters import _profile_lock
from app.adapters._base import page_limit_exceeded
from app.adapters._chrome_behavior import ChromeLifecycleMixin, WINDOW_SIZES, jitter_sleep, simulate_reading
from app.adapters._chrome_detect import detect_chrome_binary, ensure_xvfb
from app.types import BotBlockedError, DiscoverResult, SourceType

_log = logging.getLogger(__name__)

_HOME_URL = "https://tinhte.vn/"

_SEARCH_INPUT_SELECTOR = "input.gsc-input"
_RESULT_LINK_SELECTOR  = "a.gs-title"
_PAGE_BUTTON_SELECTOR  = ".gsc-cursor-page"
_SORT_TOGGLE_SELECTOR  = ".gsc-selected-option-container"
_SORT_OPTION_SELECTOR  = ".gsc-option-menu-item"
_SORT_DATE_LABEL       = "date"  # GCSE 위젯 UI 문구(영문 고정, hl 과 무관 — 실측 확인)

# 검색 결과엔 실제 글(/thread/{제목}.{숫자id}/) 외에 태그 페이지(/samsunggalaxy/,
# breadcrumb "Tag")나 홈페이지(/)같은 노이즈가 섞여 나온다(실측, 2026-08-04 —
# 사용자가 직접 결과 화면에서 확인). 지금까지 확인된 진짜 글 URL은 예외 없이
# 이 패턴이라 경로 자체로 걸러낸다.
_THREAD_PATH_RE = re.compile(r"^/thread/[^/]+\.\d+/?$")

_DEFAULT_DELAY_SEC        = 1.5
_INITIAL_LOAD_WAIT_SEC    = 4.0
_SEARCH_RENDER_WAIT_SEC   = 4.0
_SEARCH_BOX_TIMEOUT_SEC   = 10.0
_SEARCH_BOX_POLL_SEC      = 0.3


class TinhteForumAdapter(ChromeLifecycleMixin):
    source_type: str = SourceType.TINHTE_FORUM

    def __init__(
        self,
        max_pages: int | None = None,
        delay_sec: float = _DEFAULT_DELAY_SEC,
    ) -> None:
        self._max_pages = max_pages or config.TINHTE_MAX_PAGES
        self._delay_sec = delay_sec
        self._driver = None
        self._user_data_dir: str | None = None  # close() 에서 PID 재사용 방지 확인에 사용
        self._profile_lock_file = None  # WORKER_ID 중복 감지용 flock 파일 핸들

    def discover(self, keyword: str, cursor: str | None) -> DiscoverResult:
        page = int(cursor) if cursor else 1

        if page_limit_exceeded(page, self._max_pages):
            return DiscoverResult(urls=[], next_cursor=None, has_more=False)

        jitter_sleep(self._delay_sec)
        driver = self._ensure_driver()

        if page == 1:
            if not self._submit_search(driver, keyword):
                raise BotBlockedError(f"tinhte_forum keyword='{keyword}' — 검색창을 못 찾음(구조 변경 또는 차단)")
        else:
            if not self._go_to_page(driver, page):
                # 그 페이지 번호 버튼이 없음 — 결과가 그만큼 없다는 뜻(정상 종료)
                return DiscoverResult(urls=[], next_cursor=None, has_more=False)

        time.sleep(_SEARCH_RENDER_WAIT_SEC)
        simulate_reading(driver)

        urls = _extract_result_urls(driver, keyword)
        # has_more 는 필터 통과 개수(urls)가 아니라 다음 페이지 버튼 존재 여부로 판단한다 —
        # 한 페이지에 우연히 제목 매치가 0건이어도(노이즈만 있어도) 뒤 페이지엔 있을 수 있다.
        has_more = page < self._max_pages and _page_button_exists(driver, page + 1)
        next_cursor = str(page + 1) if has_more else None

        return DiscoverResult(urls=urls, next_cursor=next_cursor, has_more=has_more)

    def _ensure_driver(self):
        if self._driver is None:
            ensure_xvfb()

            chrome_binary = detect_chrome_binary()
            if chrome_binary is None:
                raise RuntimeError(
                    "Chrome 바이너리를 찾을 수 없습니다. "
                    "google-chrome 또는 chromium 을 설치하세요."
                )

            opts = ChromeOptions()
            opts.binary_location = chrome_binary
            # tinhte.vn은 광고/트래커 iframe이 수십 개 붙어있어(실측 55개) "normal"
            # 전략(load 이벤트, 모든 하위 리소스 완료까지 대기)로는 driver.get() 이
            # 30초 넘게 걸려 타임아웃난다(실측). google_news.py와 동일하게 DOMContentLoaded
            # 시점까지만 기다리는 eager로 바꾼다 — 검색창/결과는 서버 렌더링/위젯 JS가
            # DOM에 반영되는 시점이라 eager로도 문제없다.
            opts.page_load_strategy = "eager"
            opts.add_argument("--lang=vi-VN,vi")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            opts.add_argument(f"--window-size={random.choice(WINDOW_SIZES)}")
            if sys.platform == "win32":
                opts.add_argument("--window-position=-32000,-32000")

            user_data_dir = None
            if config.TINHTE_CHROME_PROFILE_DIR:
                # 워커마다 독립된 프로필 디렉터리 — 매 실행마다 새 세션이 아니라
                # 쿠키·로컬스토리지가 누적된 "돌아오는 사용자"처럼 보이게 한다.
                profile_dir = Path(config.TINHTE_CHROME_PROFILE_DIR) / (config.WORKER_ID or "default")
                profile_dir.mkdir(parents=True, exist_ok=True)
                user_data_dir = str(profile_dir.resolve())
                opts.add_argument(f"--user-data-dir={user_data_dir}")
                self._profile_lock_file = _profile_lock.acquire(user_data_dir, config.WORKER_ID)

            self._user_data_dir = user_data_dir

            try:
                self._driver = webdriver.Chrome(options=opts)
                self._driver.set_page_load_timeout(config.TINHTE_PAGE_LOAD_TIMEOUT_SEC)
                self._driver.get(_HOME_URL)
                time.sleep(_INITIAL_LOAD_WAIT_SEC)  # GCSE 위젯 JS 초기화 대기
            except Exception:
                _profile_lock.release(self._profile_lock_file)
                self._profile_lock_file = None
                raise
        return self._driver

    def _submit_search(self, driver, keyword: str) -> bool:
        """검색창을 찾아 키워드를 입력하고 엔터로 제출한다. 검색창을 못 찾으면 False."""
        deadline = time.monotonic() + _SEARCH_BOX_TIMEOUT_SEC
        inp = None
        while time.monotonic() < deadline:
            elements = driver.find_elements(By.CSS_SELECTOR, _SEARCH_INPUT_SELECTOR)
            if elements:
                inp = elements[0]
                break
            time.sleep(_SEARCH_BOX_POLL_SEC)
        if inp is None:
            return False

        inp.click()
        inp.clear()
        inp.send_keys(keyword)
        jitter_sleep(0.6, spread=0.5)
        inp.send_keys(Keys.RETURN)
        time.sleep(_SEARCH_RENDER_WAIT_SEC)

        _sort_by_date(driver)
        return True

    def _go_to_page(self, driver, page: int) -> bool:
        """`.gsc-cursor-page` 버튼(1~10페이지 번호) 중 page번째를 클릭한다.
        해당 페이지 버튼 자체가 없으면(결과가 그만큼 없음) False."""
        buttons = driver.find_elements(By.CSS_SELECTOR, _PAGE_BUTTON_SELECTOR)
        if page > len(buttons):
            return False
        buttons[page - 1].click()
        return True


def _sort_by_date(driver) -> None:
    """정렬 드롭다운("정렬 기준")을 열어 "Date" 옵션을 선택한다 — 기본값인
    관련도순(Relevance) 대신 최신순으로 결과를 받기 위함. 옵션 라벨("Relevance"/
    "Date")은 tinhte.vn 이 위젯 설정(orderByOptions)에 직접 박아넣은 고정 영문
    문구라 hl(언어) 설정과 무관하게 항상 영어로 뜬다(실측 확인).

    드롭다운 자체가 없거나(구조 변경) "Date" 항목을 못 찾으면 조용히 넘어간다 —
    정렬 실패가 발견 자체를 막을 정도는 아니라고 판단(관련도순으로라도 결과는
    나옴), BotBlockedError 로 단정하지 않는다."""
    try:
        driver.find_element(By.CSS_SELECTOR, _SORT_TOGGLE_SELECTOR).click()
        jitter_sleep(0.5, spread=0.5)
        for item in driver.find_elements(By.CSS_SELECTOR, _SORT_OPTION_SELECTOR):
            if item.text.strip().lower() == _SORT_DATE_LABEL:
                item.click()
                time.sleep(_SEARCH_RENDER_WAIT_SEC)  # 정렬 변경 후 결과 재렌더링 대기
                return
        _log.warning("tinhte_forum: 정렬 드롭다운에 'Date' 옵션을 못 찾음 — 관련도순 그대로 진행",
                     extra={"component": "adapter"})
    except Exception as exc:
        _log.warning(f"tinhte_forum: 날짜순 정렬 전환 실패, 관련도순 그대로 진행 ({exc})",
                     extra={"component": "adapter"})


def _extract_result_urls(driver, keyword: str) -> list[str]:
    """`a.gs-title` 링크의 href 를 순서대로, 중복 없이 추출한다.
    태그 페이지/홈페이지 등 `/thread/{제목}.{id}/` 패턴이 아닌 건 제외한다.

    `keyword` 는 지금 필터링엔 안 쓰지만(§관리자 확인 후 결정 예정, 모듈
    docstring "검색 결과 노이즈 문제와 필터링" 참고), 향후 제목/카테고리 기반
    필터를 다시 넣을 때 바로 쓸 수 있도록 시그니처에 남겨둔다."""
    seen: set[str] = set()
    urls: list[str] = []
    for el in driver.find_elements(By.CSS_SELECTOR, _RESULT_LINK_SELECTOR):
        href = el.get_attribute("href") or ""
        if not href or href in seen:
            continue
        if not _THREAD_PATH_RE.match(urlparse(href).path):
            continue
        seen.add(href)
        urls.append(href)
    return urls


def _page_button_exists(driver, page: int) -> bool:
    buttons = driver.find_elements(By.CSS_SELECTOR, _PAGE_BUTTON_SELECTOR)
    return page <= len(buttons)
