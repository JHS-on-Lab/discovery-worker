"""
구글 뉴스 발견 어댑터.

GOOGLE_DISCOVERY_MODE 환경변수로 수집 방식을 선택한다.

  search (기본): google.com/search?tbm=nws 스크랩
    - 언론사 직접 URL 반환, 페이지네이션 가능
    - undetected-chromedriver 필요

  rss: Google News RSS + Chrome CBMi URL 변환
    - RSS 최대 ~100건을 HTTP로 가져온 뒤 Chrome으로 실제 URL 변환
    - 봇 감지로 search 모드가 막혔을 때 대안
    - 동일 Chrome 드라이버 재사용, 페이지네이션 없음

GOOGLE_DISCOVERY_MODE=search(기본)일 때, 실제 봇 차단(캡차/챌린지 페이지, 단순
결과 소진과 구분됨)이 감지되면 GOOGLE_BLOCK_COOLDOWN_SEC 동안 이 어댑터
인스턴스(워커 프로세스 수명 동안 키워드 간 공유)가 자동으로 rss 모드로
전환되고, 쿨다운이 지나면 자동으로 search 모드로 복귀를 시도한다.

headless 모드는 Google Bot 감지에 걸리므로 headless=False 로 실행.
  Windows: 창을 화면 밖으로 이동
  Linux:   Xvfb 가상 디스플레이 사용 (deployment.md 참고)

행동 자연화(behavioral naturalization) — IP 로테이션 없이 탐지 신호를 줄이기 위한 조치:
  - 영구 Chrome 프로필(GOOGLE_CHROME_PROFILE_DIR, WORKER_ID별 분리): 매 실행마다
    빈 세션이 아니라 쿠키·로컬스토리지가 누적된 상태로 접속.
  - 요청 간격에 랜덤 지터(jitter_sleep, app.adapters._chrome_behavior) — 고정 간격은
    그 자체로 자동화 신호. 페이지 번호와 무관하게 매 요청 전 적용해 키워드 전환
    시에도 딜레이 없이 바로 이어지지 않게 한다.
  - 결과 페이지 로드 후 스크롤 시뮬레이션(simulate_reading) 후 DOM 파싱.
  - Chrome 창 크기를 무작위 해상도 중에서 선택 — 워커 전체가 동일 해상도면 지문이 됨.
"""

from __future__ import annotations

import logging
import random
import sys
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode
from xml.etree import ElementTree as ET

from app import config
from app.adapters import _profile_lock
from app.adapters._base import page_limit_exceeded
from app.adapters._chrome_behavior import ChromeLifecycleMixin, WINDOW_SIZES, jitter_sleep, simulate_reading
from app.adapters._chrome_detect import detect_chrome_binary, detect_chrome_major, ensure_xvfb
from app.types import BotBlockedError, DiscoverMode, DiscoverResult, SourceType

_log = logging.getLogger(__name__)

_RSS_URL    = "https://news.google.com/rss/search"

# rss 모드 기간 제한. search 모드의 tbs=qdr:d 와 동일하게 "최근 1일"로 맞춘다.
# 쿼리에 when:{N}d 를 안 넣으면 구글이 관련도 기준으로 최대 ~100건을 추려 반환하는데,
# 그 후보군에 최대 3~4일치 기사가 다 섞여 경쟁하다 보니 관련도가 낮은 실제 최근(1일
# 이내) 기사가 top 100 에서 밀려날 수 있다(2026-07-31 실측 — when: 없이 요청하면
# 최대 80시간 전 기사까지 섞여 들어옴, when:1d 를 넣으면 후보군 자체가 1일 이내로
# 좁혀져 가장 오래된 항목이 7.7시간 전으로 확 줄어듦). when:{N}d 로 후보군 자체를
# 좁혀 이 문제를 줄인다 — _parse_rss() 의 pubDate 사후 필터링은 pubDate 파싱 실패 시
# fail-open 하는 안전장치로 그대로 남겨둔다(이중 방어, 서로 대체 관계 아님).
_RSS_CUTOFF_DAYS = 1

_GOOGLE_HOSTS = {
    "google.com", "www.google.com", "news.google.com",
    "googleapis.com", "gstatic.com", "google.co.kr",
}

_DEFAULT_MAX_PAGES = 5
_DEFAULT_DELAY_SEC = 1.5

# rss 폴백(_resolve_cbmi)이 실제 언론사 페이지를 방문할 때, 그 페이지의 광고/트래커
# iframe(교차 출처)이 Chrome renderer 프로세스를 계속 늘려 메모리가 급증했다
# (2026-07-28 mem 로그 실측). 이 도메인들을 호스트 리졸버 단에서 막으면 그 iframe
# 자체가 탐색을 못 해 renderer 가 안 생긴다 — 실측(2026-07-29, 뉴스 5건)으로
# renderer RSS 합계 약 39% 감소 확인(사이트별 8~59% 편차). google.com 페이징
# 중엔 이 도메인들을 애초에 안 써서 부작용 없음.
_AD_TRACKER_DOMAINS = (
    "doubleclick.net", "googlesyndication.com", "googletagmanager.com", "googletagservices.com",
    "google-analytics.com", "adservice.google.com", "adnxs.com", "criteo.com", "taboola.com",
    "outbrain.com", "amazon-adsystem.com", "connect.facebook.net", "scorecardresearch.com",
    "moatads.com", "media.net", "pubmatic.com", "rubiconproject.com", "casalemedia.com",
    "contextweb.com", "openx.net", "smartadserver.com", "adform.net", "bidswitch.net",
    "rlcdn.com", "agkn.com", "mathtag.com", "adsrvr.org", "tapad.com", "krxd.net",
    "demdex.net", "admixer.net", "adotmob.com", "yieldmo.com", "adsafeprotected.com",
    "gumgum.com", "smilewanted.com", "adcolony.com", "innovid.com", "flashtalking.com",
)


def _host_resolver_rules(domains: tuple[str, ...]) -> str:
    """도메인 목록을 --host-resolver-rules 인자값으로 변환 — 각 도메인과
    서브도메인(*.domain)을 전부 0.0.0.0(블랙홀)으로 매핑한다."""
    rules = []
    for d in domains:
        rules.append(f"MAP {d} 0.0.0.0")
        rules.append(f"MAP *.{d} 0.0.0.0")
    return ", ".join(rules)


def _wait_for_cbmi_redirect(driver, timeout: float = 10.0, poll_interval: float = 0.05) -> str:
    """CBMi 리다이렉트가 news.google.com 을 벗어날 때까지 current_url 을 폴링한다.

    page_load_strategy=eager 라 driver.get() 은 news.google.com 셸의 DOM 준비
    시점에 이미 리턴할 수 있고, 실제 리다이렉트(클라이언트사이드 JS)는 그 이후에
    끝날 수 있다 — 그래서 get() 리턴을 신뢰하지 않고 URL 이 실제로 바뀔 때까지
    직접 기다린다. timeout 안에 안 바뀌면 마지막 상태(대개 여전히 news.google.com)
    그대로 반환 — 호출부에서 unresolved 로 처리된다.

    URL 이 바뀐 걸 확인하는 즉시 Page.stopLoading() 으로 그 페이지의 나머지 로딩을
    끊는다 — current_url 은 탐색이 커밋되는 시점에 갱신되는데, 이는 목적지 페이지가
    자기 JS(광고/트래커 iframe 포함)를 실행하기 이전이므로, 빨리 감지해서(poll_interval
    단축) 끊을수록 그 페이지가 만드는 cross-origin iframe(=renderer 프로세스) 수가
    줄어든다 — 도메인 차단 목록에 없는 광고 네트워크가 있는 페이지에도 효과가 있다
    (2026-07-29, 목록 기반 차단만으로 못 잡는 롱테일 대응). "news.google.com 을
    벗어났는가"라는 URL 판별 기준 자체는 그대로라 기존 대비 URL 유실 위험은 없다 —
    같은 시점에 잡는 값을 그대로 반환하고, 거기 이후의 불필요한 로딩만 끊는 것뿐이다.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = driver.current_url
        if "news.google.com" not in urlparse(current).netloc:
            try:
                driver.execute_cdp_cmd("Page.stopLoading", {})
            except Exception:
                pass  # stopLoading 실패해도 URL 은 이미 확보됐으니 무시하고 진행
            return current
        time.sleep(poll_interval)
    return driver.current_url


def _parse_region(region: str) -> tuple[str, dict[str, str]]:
    """t_keyword.source_options_json 의 region 값을 (host, extra_params) 로 분해한다.

    'google.com' → ('google.com', {})
    'google.com/?gl=us' → ('google.com', {'gl': 'us'})

    scheme 없이 저장돼 있으므로 urlparse 가 host 를 path 로 오인하지 않도록 붙여서 파싱한다.
    """
    parsed = urlparse(region if "://" in region else f"https://{region}")
    extra = {k: v[0] for k, v in parse_qs(parsed.query).items() if v}
    return parsed.netloc, extra


class UCGoogleNewsAdapter(ChromeLifecycleMixin):
    """
    GOOGLE_DISCOVERY_MODE 에 따라 search / rss 방식으로 동작하는 Google 뉴스 어댑터.
    두 모드 모두 undetected-chromedriver 를 사용한다.
    """

    source_type: str = SourceType.GOOGLE_NEWS

    def __init__(
        self,
        max_pages: int | None = None,
        delay_sec: float = _DEFAULT_DELAY_SEC,
    ) -> None:
        self._max_pages = max_pages or config.GOOGLE_MAX_PAGES
        self._delay_sec = delay_sec
        self._driver = None
        self._user_data_dir: str | None = None  # close() 에서 PID 재사용 방지 확인에 사용
        self._profile_lock_file = None  # WORKER_ID 중복 감지용 flock 파일 핸들
        self._search_blocked_until: datetime | None = None  # 봇 차단 감지 시 rss 폴백 만료 시각
        self._region_host: str | None = None  # source_options_json.region 오버라이드 (없으면 기본 도메인)
        self._region_extra_params: dict[str, str] = {}  # 위 region 의 쿼리스트링(gl= 등) — 기본 hl/gl 을 덮어씀

    def apply_source_options(self, options: dict | None) -> None:
        """dispatcher 가 키워드 처리 직전에 호출하는 훅. t_keyword.source_options_json 을 받아
        region 오버라이드를 적용한다. region 이 없으면(대부분의 키워드) 기본값으로 리셋한다 —
        같은 어댑터 인스턴스가 여러 키워드를 연속 처리하므로, 리셋을 안 하면 이전 키워드의
        region 이 다음 키워드로 새어 들어간다."""
        region = (options or {}).get("region")
        if not region:
            self._region_host = None
            self._region_extra_params = {}
            return
        self._region_host, self._region_extra_params = _parse_region(region)

    def _ensure_driver(self):
        if self._driver is None:
            import undetected_chromedriver as uc

            ensure_xvfb()

            chrome_binary = detect_chrome_binary()
            if chrome_binary is None:
                raise RuntimeError(
                    "Chrome 바이너리를 찾을 수 없습니다. "
                    "google-chrome 또는 chromium 을 설치하세요."
                )

            opts = uc.ChromeOptions()
            opts.binary_location = chrome_binary
            # DOMContentLoaded 시점에 driver.get() 이 바로 리턴 — 이미지/광고iframe 같은
            # 하위 리소스 로드 완료를 안 기다린다. 검색 결과 페이지는 서버렌더링 HTML이라
            # 링크 추출(XPath)엔 영향 없고, rss 모드에서 CBMi 리다이렉트 후 도착하는 실제
            # 언론사 페이지의 광고/트래커 iframe 로딩을 기다리지 않게 돼 renderer 프로세스
            # 급증을 줄인다(_resolve_cbmi 참고). 리다이렉트가 DOMContentLoaded 이후에
            # 완료되는 경우를 대비해 _wait_for_cbmi_redirect() 로 current_url 을 폴링한다.
            opts.page_load_strategy = "eager"
            opts.add_argument("--lang=ko-KR,ko")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-software-rasterizer")
            opts.add_argument(f"--window-size={random.choice(WINDOW_SIZES)}")
            # 메모리 절감. 검색결과 페이지에서 XPath로 링크 텍스트만 읽고 이미지/시각적
            # 렌더링 결과는 안 쓰므로 기능상 리스크 없음(mem 로그에서 관찰된 children
            # 프로세스 급증(15→50)이 BackForwardCache/Site Isolation과 상관관계).
            #   - BackForwardCache: 뒤로가기 없이 앞으로만 이동하므로 순수 낭비
            #   - IsolateOrigins/site-per-process: 교차 출처 iframe(광고 등)마다 별도
            #     프로세스를 만드는 보안 격리 기능. DOM/렌더링 결과 자체는 안 바뀜.
            opts.add_argument("--disable-features=BackForwardCache,IsolateOrigins,site-per-process")
            opts.add_argument(f"--host-resolver-rules={_host_resolver_rules(_AD_TRACKER_DOMAINS)}")
            opts.add_experimental_option("prefs", {
                "profile.managed_default_content_settings.images": 2,
            })
            if sys.platform == "win32":
                opts.add_argument("--window-position=-32000,-32000")

            user_data_dir = None
            if config.GOOGLE_CHROME_PROFILE_DIR:
                # 워커마다 독립된 프로필 디렉터리 — 매 실행마다 새 세션이 아니라
                # 쿠키·로컬스토리지가 누적된 "돌아오는 사용자"처럼 보이게 한다.
                # WORKER_ID 로 분리해 동시에 여러 워커가 같은 프로필을 잠그는 것을 방지.
                profile_dir = Path(config.GOOGLE_CHROME_PROFILE_DIR) / (config.WORKER_ID or "default")
                profile_dir.mkdir(parents=True, exist_ok=True)
                user_data_dir = str(profile_dir.resolve())
                # WORKER_ID 가 실수로 중복되면 위 분리만으로는 못 막는다 — flock 으로
                # 실제 배타적 잠금을 걸어, 이미 다른 프로세스가 쓰고 있으면 애매한
                # hang 대신 여기서 바로 명확하게 실패한다.
                self._profile_lock_file = _profile_lock.acquire(user_data_dir, config.WORKER_ID)

            self._user_data_dir = user_data_dir

            try:
                self._driver = uc.Chrome(
                    options=opts,
                    headless=False,
                    use_subprocess=True,
                    version_main=detect_chrome_major(),
                    user_data_dir=user_data_dir,
                )
                self._driver.set_page_load_timeout(config.GOOGLE_PAGE_LOAD_TIMEOUT_SEC)
                # set_page_load_timeout 은 "탐색(navigation)" 명령에만 적용된다. chromedriver
                # 자체가 응답 불능이 되면(브라우저 크래시/좀비 프로세스 등) current_url 읽기
                # 같은 다른 명령들은 이 상한의 영향을 받지 않고 HTTP 클라이언트의 기본
                # 소켓 타임아웃(환경에 따라 매우 길거나 없을 수 있음)에 그대로 노출된다.
                # 모든 webdriver 명령에 동일한 상한을 명시적으로 강제한다.
                self._driver.command_executor.client_config.timeout = config.GOOGLE_PAGE_LOAD_TIMEOUT_SEC
            except Exception:
                # 락을 잡은 뒤 Chrome 기동 자체가 실패하면, 락을 안 풀고 그대로 두면
                # 같은 프로세스의 다음 재시도(_ensure_driver 재호출)가 자기 자신의
                # flock 에 걸려 self-lockout 난다(flock 은 파일이 아니라 open file
                # description 단위라 같은 프로세스라도 다시 열면 막힌다). 반드시 풀어준다.
                _profile_lock.release(self._profile_lock_file)
                self._profile_lock_file = None
                raise
        return self._driver

    def discover(self, keyword: str, cursor: str | None) -> DiscoverResult:
        mode = config.GOOGLE_DISCOVERY_MODE.lower()
        if mode == "rss":
            return self._discover_rss(keyword, cursor)

        if self._search_blocked_until is not None:
            if datetime.now(timezone.utc) < self._search_blocked_until:
                # 최근 봇 차단 감지 — 쿨다운 동안 rss 로 임시 폴백
                return self._discover_rss(keyword, cursor)
            # 쿨다운 만료 — search 모드로 자동 복귀
            _log.info(
                "google search 모드 쿨다운 만료 — search 재시도",
                extra={"component": "adapter"},
            )
            self._search_blocked_until = None

        return self._discover_search(keyword, cursor)

    # ------------------------------------------------------------------
    # search 모드
    # ------------------------------------------------------------------

    def _discover_search(self, keyword: str, cursor: str | None) -> DiscoverResult:
        page = int(cursor) if cursor else 1

        if page_limit_exceeded(page, self._max_pages):
            return DiscoverResult(urls=[], next_cursor=None, has_more=False, mode=DiscoverMode.SEARCH)

        # 페이지 번호와 무관하게 매 요청 전 지터 — page==1(새 키워드 시작)에서도
        # 적용해야 이전 키워드 처리 직후 딜레이 없이 바로 이어지는 걸 막는다.
        jitter_sleep(self._delay_sec)

        query = {
            "q":     keyword,
            "tbm":   "nws",
            "start": (page - 1) * 10,
            "tbs":   "qdr:d",
            "hl":    "ko",
            "gl":    "KR",
        }
        # source_options_json.region 오버라이드 — 있으면 hl/gl 등 기본값을 덮어쓴다.
        query.update(self._region_extra_params)
        params = urlencode(query)
        host = self._region_host or "www.google.com"

        driver = self._ensure_driver()
        try:
            driver.get(f"https://{host}/search?{params}")
        except Exception as exc:
            # TimeoutException/WebDriverException 뿐 아니라, chromedriver 커맨드
            # 채널 자체가 죽으면 urllib3.exceptions.ReadTimeoutError 등이 selenium을
            # 거치지 않고 그대로 올라온다 — 넓게 잡아 이 driver 를 무조건 폐기한다.
            # 이 driver 는 이후에도 계속 멈춰있을 수 있으므로 폐기하고, 다음 호출에서
            # _ensure_driver() 가 새 인스턴스를 띄우게 한다.
            _log.warning(
                f"google page load hung keyword='{keyword}' page={page} — resetting driver ({exc})",
                extra={"component": "adapter"},
            )
            self.close()
            raise

        jitter_sleep(self._delay_sec)
        simulate_reading(driver)

        urls = _extract_search_urls(driver)

        if not urls:
            if _is_bot_block_page(driver):
                self._search_blocked_until = (
                    datetime.now(timezone.utc) + timedelta(seconds=config.GOOGLE_BLOCK_COOLDOWN_SEC)
                )
                _log.warning(
                    f"google blocked keyword='{keyword}' page={page} — bot detection, "
                    f"rss 로 {config.GOOGLE_BLOCK_COOLDOWN_SEC}s 동안 폴백",
                    extra={"component": "adapter"},
                )
                raise BotBlockedError(f"google_news keyword='{keyword}' page={page}")

            # 캡차/차단 신호 없이 결과만 없는 경우 — tbs=qdr:d(최근 1일) 필터상
            # 해당 페이지 깊이까지 결과가 실제로 소진된 정상적인 상황. 차단이 아니므로
            # 여기서 조용히 페이지네이션을 끝낸다 (봇 차단 백오프를 소비하지 않음).
            _log.debug(
                f"google no more results keyword='{keyword}' page={page}",
                extra={"component": "adapter"},
            )
            return DiscoverResult(urls=[], next_cursor=None, has_more=False, mode=DiscoverMode.SEARCH)

        has_more = len(urls) >= 8 and page < self._max_pages
        next_cursor = str(page + 1) if has_more else None

        return DiscoverResult(urls=urls, next_cursor=next_cursor, has_more=has_more, mode=DiscoverMode.SEARCH)

    # ------------------------------------------------------------------
    # rss 모드
    # ------------------------------------------------------------------

    def _discover_rss(self, keyword: str, cursor: str | None) -> DiscoverResult:
        """RSS 피드 수집 후 Chrome으로 CBMi URL → 실제 언론사 URL 변환."""
        if cursor is not None:
            return DiscoverResult(urls=[], next_cursor=None, has_more=False, mode=DiscoverMode.RSS)

        from app.fetch._client import make_client

        params = {"q": f"{keyword} when:{_RSS_CUTOFF_DAYS}d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
        # source_options_json.region 오버라이드 — search 모드와 동일하게 hl/gl/ceid 등
        # 기본값을 덮어쓴다. RSS 는 news.google.com 단일 도메인으로 로케일이 전부 쿼리
        # 파라미터로 결정되므로(도메인 자체를 바꾸는 _region_host 는 search 전용이라
        # 여기선 적용 대상이 아님), region 문자열에 hl/gl/ceid 를 직접 넣어야 실제로
        # 반영된다(예: "news.google.com/?hl=vi&gl=vn&ceid=VN:vi" — 도메인 부분은 무시됨).
        params.update(self._region_extra_params)
        with make_client() as client:
            resp = client.get(_RSS_URL, params=params)
            resp.raise_for_status()

        cbmi_urls = _parse_rss(resp.content, cutoff_days=_RSS_CUTOFF_DAYS)
        _log.info(f"rss mode: {len(cbmi_urls)} cbmi urls, resolving via Chrome")

        urls = self._resolve_cbmi(cbmi_urls)
        _log.info(f"rss mode: resolved {len(urls)}/{len(cbmi_urls)}")

        return DiscoverResult(urls=urls, next_cursor=None, has_more=False, mode=DiscoverMode.RSS)

    def _resolve_cbmi(self, cbmi_urls: list[str]) -> list[str]:
        """Chrome으로 CBMi URL 탐색 → 최종 언론사 URL 수집.

        CBMi 링크는 news.google.com 안에서 클라이언트사이드 JS 로 최종 언론사
        URL 을 알아내는 방식이라(순수 HTTP 는 302 하나만 타고 news.google.com
        SPA 셸로 떨어짐 — httpx 로 직접 확인함, 2026-07-29) Chrome 이 필수다.

        URL 마다 새 탭을 열어 탐색하고, 확인 즉시 그 탭을 닫는다. 같은 탭에서
        driver.get() 으로 계속 이동만 하면 이전 페이지의 renderer(광고/트래커
        iframe 포함)가 Chrome 자체 유휴 프로세스 유지 정책 때문에 곧바로
        정리되지 않고 그대로 쌓이는 반면(2026-07-29 실측 — 같은 탭 재사용 시
        renderer 11→24개로 계속 누적), 탭을 명시적으로 닫으면 매 방문마다
        거의 베이스라인으로 리셋된다(같은 조건에서 방문마다 3~5개로 복귀).
        그래서 배치 단위 브라우저 재시작 없이도 renderer 누적을 막을 수 있다.

        탭을 열거나 닫는 도중 hang 이 나면(chromedriver 커맨드 채널 자체가
        죽었을 가능성) 그 URL 만 포기하고 driver 전체를 폐기 — 다음 URL 은
        _ensure_driver() 가 새로 띄운 드라이버로 이어서 진행한다.
        """
        resolved: list[str] = []
        total = len(cbmi_urls)

        for i, url in enumerate(cbmi_urls, start=1):
            driver = self._ensure_driver()
            try:
                main_handle = driver.current_window_handle
                driver.switch_to.new_window("tab")
                driver.get(url)
                final = _wait_for_cbmi_redirect(driver)
                if "google.com" not in urlparse(final).netloc:
                    resolved.append(final)
                else:
                    _log.warning(
                        f"cbmi unresolved: {url[:80]}",
                        extra={"component": "adapter"},
                    )
                # URL 확보 즉시 탭을 닫는다 — _wait_for_cbmi_redirect() 의
                # Page.stopLoading() 이후에도 그대로 열어두면 이미 실행 중인
                # setTimeout/지연 스크립트가 계속 광고 iframe 을 만들 수 있어
                # (2026-07-29 실측 — 탭을 안 닫고 1.5초 두면 renderer 11→21,
                # 닫으면 5~18 수준으로 확인), stopLoading 의 이득이 죽기 전에
                # 닫아버린다. 탐지 회피용 간격은 탭을 닫은 뒤(=다음 탐색 전)로
                # 옮겨 페이지의 하위 리소스 로드를 기다리는 데 쓰이지 않게 한다.
                driver.close()
                driver.switch_to.window(main_handle)
                jitter_sleep(self._delay_sec)
            except Exception as exc:
                _log.warning(
                    f"cbmi navigate hung at {i}/{total} — resetting driver, "
                    f"이 URL 포기하고 다음 URL로 진행 (url={url[:60]} err={exc})",
                    extra={"component": "adapter"},
                )
                self.close()

            if i % 5 == 0 or i == total:
                _log.debug(
                    f"cbmi progress {i}/{total} — resolved {len(resolved)}",
                    extra={"component": "adapter"},
                )

        return resolved



_BLOCK_PAGE_MARKERS = (
    "unusual traffic",                          # "Our systems have detected unusual traffic ..."
    "비정상적인 트래픽",                          # 위 문구의 한국어(hl=ko) 버전
    "g-recaptcha",
    "detected unusual traffic from your computer network",
)


def _is_bot_block_page(driver) -> bool:
    """결과 0건이 실제 구글 봇 차단(캡차/챌린지 페이지)인지 확인한다.

    tbs=qdr:d(최근 1일) 필터 특성상 페이지 깊이가 늘수록 결과가 정상적으로
    소진돼 URL이 0개가 되는 경우가 흔하다. 이걸 전부 BotBlockedError로
    처리하면 오탐이 쌓여 불필요한 백오프·키워드 포기가 발생하므로,
    실제 차단 신호(리다이렉트 /sorry/, reCAPTCHA 요소, 캡차 문구)가 있을 때만 True.

    _BLOCK_PAGE_MARKERS 의 문구 두 개(영어/한국어)는 그 로케일(hl=en/ko)에서만
    유효하다 — source_options_json.region 으로 다른 언어(아랍어/베트남어 등)를
    쓰면 문구가 달라 안 걸릴 수 있다. reCAPTCHA iframe 존재 여부는 클래스명/URL
    패턴이라 언어와 무관하게 항상 유효한 신호라 별도로 확인한다(완벽한 커버리지를
    보장하진 않음 — 실제 비-en/ko 차단 페이지 샘플로 검증한 적은 없다).
    """
    from selenium.webdriver.common.by import By

    try:
        if "/sorry/" in (driver.current_url or ""):
            return True
        if driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']"):
            return True
        page_source = (driver.page_source or "").lower()
    except Exception:
        return False
    return any(marker.lower() in page_source for marker in _BLOCK_PAGE_MARKERS)


def _extract_search_urls(driver) -> list[str]:
    """Google 뉴스 검색 결과에서 언론사 직접 URL 추출."""
    from selenium.webdriver.common.by import By

    urls = []
    seen: set[str] = set()

    elements = driver.find_elements(
        By.XPATH, "//a[.//h3 or .//div[@role='heading']]"
    )

    for el in elements:
        href = el.get_attribute("href") or ""
        if not href.startswith("http"):
            continue

        if "google.com/url" in href:
            qs = parse_qs(urlparse(href).query)
            href = qs.get("q", [""])[0] or href

        if not href.startswith("http"):
            continue

        parsed = urlparse(href)
        if any(g in parsed.netloc.lower() for g in _GOOGLE_HOSTS):
            continue
        if not parsed.path or parsed.path == "/":
            continue

        if href not in seen:
            seen.add(href)
            urls.append(href)

    return urls


def _parse_rss(content: bytes, cutoff_days: int) -> list[str]:
    """RSS XML 파싱 → CBMi URL 목록. pubDate 기준 cutoff_days 이내만 포함."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
    root = ET.fromstring(content)
    channel = root.find("channel")
    if channel is None:
        return []

    urls: list[str] = []
    for item in channel.findall("item"):
        link   = item.findtext("link", "").strip()
        pubdate = item.findtext("pubDate", "").strip()
        if not link:
            continue
        if pubdate:
            try:
                if parsedate_to_datetime(pubdate) < cutoff:
                    continue
            except Exception:
                pass
        urls.append(link)
    return urls
