"""
Tinh tế(tinhte.vn, 베트남 IT/가전 커뮤니티) 발견 어댑터.

tinhte.vn 화면의 검색창은 자체 검색이 아니라 사이트에 임베드된 Google Custom
Search Engine(GCSE) 무료 위젯이다(검색창 마크업이 `<div class="gcse-search">`).
이 어댑터는 그 검색엔진의 내부 API를 직접 재현하지 않고, 실제 사람처럼 검색창에
타이핑하고 결과를 DOM에서 읽는다 — GCSE 검색 API는 정적 HTTP로 두드리면 반복
요청 시 차단되고, TLS 지문을 위장해도 마찬가지로 차단되며, 브라우저 페이지
컨텍스트 안에서 `<script>` 태그로 직접 불러와도 응답의 `Content-Disposition:
attachment` 헤더 때문에 브라우저가 스크립트 실행 대신 파일 다운로드로 처리해버려
근본적으로 재현이 안 된다. 위젯이 알아서 렌더링하는 결과를 그대로 읽으면 이
문제들을 전부 우회한다.

확인된 DOM 구조:
  - 검색창: `input.gsc-input`.
  - 결과: 최상위 문서에 바로 렌더링된다(iframe 전환 불필요). 결과 링크는
    `a.gs-title`의 href 속성에 tinhte.vn URL이 그대로 들어있다(트래킹 URL
    파싱 불필요).
  - 페이지네이션: `.gsc-cursor-page` 요소들이 페이지 번호(1~10)로 나열되고
    클릭하면 그 페이지로 이동한다("다음" 화살표 버튼이 아니라 번호 클릭 방식).
  - 정렬: 기본값은 관련도순(Relevance). `.gsc-selected-option-container` 클릭
    → 드롭다운(`.gsc-option-menu-item`)에서 "Date" 클릭하면 최신순으로 바뀐다.
    검색 키워드 제출 직후 이 클릭을 자동으로 수행해 항상 최신순으로 받는다.

undetected-chromedriver 대신 순정 selenium을 쓴다 — API를 직접 흉내내는 게
아니라 사람처럼 타이핑하는 방식이라 UC의 스텔스 패치(webdriver 플래그 은닉
등)가 결정적으로 필요하지 않고, 순정 selenium이 이 환경에서 더 안정적으로
동작한다.

이름에 관해 — `TINHTE_NEWS`가 아니라 `TINHTE_FORUM`인 이유: tinhte.vn은 뉴스
매체가 아니라 XenForo 기반 커뮤니티 포럼이고, 이 어댑터가 모으는 건 "뉴스"가
아니라 검색어에 걸리는 모든 게시판의 스레드다(스마트폰 뉴스뿐 아니라 잡담,
DIY, 리뷰, 차량, 사진/음악, 광고 게시글까지 카테고리 무관). `NAVER_STOCK`이
`_NEWS`가 아니라 콘텐츠 실체(종목토론)를 반영한 접미사를 쓰는 것과 같은 이유다.

**검색 결과 노이즈 — 관리자 확인 후 결정 예정**: tinhte.vn 모든 페이지에 공통
으로 뜨는 사이드바("인기글" 등)가 있어서, 검색어와 무관한 글이라도 그 사이드바에
실려있으면 결과에 섞여 나온다. 검색 결과 제목(`a.gs-title` 텍스트)에 키워드가
실제로 포함된 것만 남기는 필터로 이 노이즈를 거의 다 걸러낼 수 있는데(브랜드명
대신 제품 라인명만 쓴 제목은 놓칠 수 있다는 트레이드오프 있음), 적용 여부를
관리자 확인 후 결정하기로 하고 코드에서는 빼뒀다(`_extract_result_urls` 는
지금 `/thread/` URL 패턴 필터만 적용하고, `keyword` 인자는 이 필터를 다시 넣을
때 바로 쓸 수 있도록 시그니처에 남겨둠). 즉 지금 이 어댑터가 반환하는 URL에는
노이즈가 상당수 섞여 있을 수 있다. 스니펫(`.gs-snippet`, 제목 밑 요약)까지 검사
대상에 포함하는 건 적합하지 않다 — 스니펫은 사이드바보다 더 심하게 오염돼
있어서(구글이 사이드바 "인기글" 목록이나 사이트 푸터 메뉴 텍스트까지 스니펫으로
뽑아옴), 필터 의미가 없어질 정도로 매치율이 치솟는다.

미검증/제약:
  - 최근 1일 컷오프 불가: 결과 DOM에 발행일 정보가 없다(baomoi의 <time
    datetime> 같은 게 없음). 컷오프 없이 t_crawl_url.url_hash dedup 에 맡긴다.
  - 봇 차단 신호(구글 CSE API를 직접 두드릴 때 나오는 `403 Sorry`)는 이 방식
    에선 나타나지 않는 것으로 보이나(사람과 동일 경로라), 장시간 대량 수집 시
    나타날 수도 있어 지켜봐야 한다 — 지금 코드엔 이 상황에 대한 별도 감지/처리가
    없음(검색창을 못 찾는 경우만 BotBlockedError 로 처리).
  - 제목 필터를 켤 경우 실수확량이 낮아진다(키워드당 페이지를 여러 장 넘겨야
    유의미한 글이 소수만 나오는 수준) — 페이지 이동/대기 비용 대비 수율이 낮은
    편이라는 걸 감안해야 한다.
"""

from __future__ import annotations

import logging
import random
import re
import sys
import time
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from app import config
from app.adapters._base import page_limit_exceeded
from app.adapters._chrome_behavior import (
    ChromeLifecycleMixin, PROFILE_DISK_USAGE_ARGS, WINDOW_SIZES, jitter_sleep, simulate_reading,
)
from app.adapters._chrome_detect import ensure_xvfb, require_chrome_binary
from app.adapters._profile_lock import acquire_profile_dir
from app.types import BotBlockedError, DiscoverResult, SourceType

_log = logging.getLogger(__name__)

_HOME_URL = "https://tinhte.vn/"

_SEARCH_INPUT_SELECTOR = "input.gsc-input"
_RESULT_LINK_SELECTOR  = "a.gs-title"
_PAGE_BUTTON_SELECTOR  = ".gsc-cursor-page"
_SORT_TOGGLE_SELECTOR  = ".gsc-selected-option-container"
_SORT_OPTION_SELECTOR  = ".gsc-option-menu-item"
_SORT_DATE_LABEL       = "date"  # GCSE 위젯 UI 문구(영문 고정, hl 과 무관)

# 검색 결과엔 실제 글(/thread/{제목}.{숫자id}/) 외에 태그 페이지(/samsunggalaxy/,
# breadcrumb "Tag")나 홈페이지(/)같은 노이즈가 섞여 나온다. 진짜 글 URL은 예외
# 없이 이 패턴을 따르므로 경로 자체로 걸러낸다.
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
        super().__init__(max_pages or config.TINHTE_MAX_PAGES, delay_sec)

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
            chrome_binary = require_chrome_binary()

            opts = ChromeOptions()
            opts.binary_location = chrome_binary
            # tinhte.vn은 광고/트래커 iframe이 많이 붙어있어 "normal" 전략(load
            # 이벤트, 모든 하위 리소스 완료까지 대기)으로는 driver.get() 이 오래
            # 걸려 타임아웃날 수 있다. google_news.py와 동일하게 DOMContentLoaded
            # 시점까지만 기다리는 eager로 바꾼다 — 검색창/결과는 서버 렌더링/위젯 JS가
            # DOM에 반영되는 시점이라 eager로도 문제없다.
            opts.page_load_strategy = "eager"
            opts.add_argument("--lang=vi-VN,vi")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            opts.add_argument(f"--window-size={random.choice(WINDOW_SIZES)}")
            for arg in PROFILE_DISK_USAGE_ARGS:
                opts.add_argument(arg)
            if sys.platform == "win32":
                opts.add_argument("--window-position=-32000,-32000")

            user_data_dir = None
            if config.TINHTE_CHROME_PROFILE_DIR:
                # 워커마다 독립된 프로필 디렉터리 — 매 실행마다 새 세션이 아니라
                # 쿠키·로컬스토리지가 누적된 "돌아오는 사용자"처럼 보이게 한다.
                user_data_dir, self._profile_lock_file = acquire_profile_dir(
                    config.TINHTE_CHROME_PROFILE_DIR, config.WORKER_ID
                )
                opts.add_argument(f"--user-data-dir={user_data_dir}")

            self._user_data_dir = user_data_dir

            def _build():
                driver = webdriver.Chrome(options=opts)
                driver.set_page_load_timeout(config.TINHTE_PAGE_LOAD_TIMEOUT_SEC)
                # google_news.py/baidu_news.py 와 동일한 이유로 모든 webdriver 명령에
                # 동일한 상한을 강제한다(set_page_load_timeout 은 탐색 명령에만 적용).
                driver.command_executor.client_config.timeout = config.TINHTE_PAGE_LOAD_TIMEOUT_SEC
                driver.get(_HOME_URL)
                time.sleep(_INITIAL_LOAD_WAIT_SEC)  # GCSE 위젯 JS 초기화 대기
                return driver

            self._build_driver_or_release(_build)
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
    문구라 hl(언어) 설정과 무관하게 항상 영어로 뜬다.

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

    `keyword` 는 지금 필터링엔 안 쓰지만(모듈 docstring "검색 결과 노이즈 —
    관리자 확인 후 결정 예정" 참고), 향후 제목/카테고리 기반 필터를 다시 넣을
    때 바로 쓸 수 있도록 시그니처에 남겨둔다."""
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
