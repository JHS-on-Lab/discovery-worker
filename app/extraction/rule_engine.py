"""
도메인 전용 추출 규칙 엔진.

domain.rules_json 에 저장된 CSS/XPath 셀렉터로 제목·본문·저자·언론사·날짜를 추출한다.
규칙이 있으면 trafilatura/readability 보다 먼저 시도되고,
규칙이 없거나 실패하면 LibraryChain 으로 폴백한다.

rules_json 형식:
  {
    "title":        {"css": "h1.article-title"},
    "body":         {"css": "div.article-body p"},
    "author":       {"css": "span.byline"},
    "press":        {"xpath": "//meta[@property='og:site_name']/@content"},
    "published_at": {"css": "span.date", "date_format": "%Y.%m.%d %H:%M"},
    "min_body_len": 10
  }

지원 셀렉터 타입:
  "css"   — selectolax 로 처리. 여러 노드가 매칭되면 텍스트를 이어 붙인다.
  "xpath" — lxml 로 처리. 속성값(//@attr)과 텍스트(//tag) 모두 지원.

published_at 규칙:
  "date_format" — strptime 포맷 문자열. 미지정 시 날짜 파싱을 시도하지 않는다.
  파싱 실패 시 None 으로 폴백한다 (추출 전체를 실패시키지 않는다).
  타임존은 KST(UTC+9) 고정.

도메인 규칙은 TTL 캐시에 보관한다 (RULES_CACHE_TTL_SECONDS, 기본 60초).
재배포 없이 DB 에서 rules_json 을 수정하면 캐시 만료 후 자동 반영된다.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta

from app import config
from app.domain_logic.url_normalizer import normalize, url_hash
from app.types import Article, ErrorCode, ExtractionFailure

_KST = timezone(timedelta(hours=9))


class RuleEngine:
    """도메인별 CSS/XPath 규칙으로 본문을 추출한다."""

    def __init__(self) -> None:
        # host → (rules_dict, cached_at) 형태로 메모리 캐시
        self._cache: dict[str, tuple[dict, float]] = {}

    def get_rules(self, host: str, domain_row: dict | None) -> dict | None:
        """domain 행에서 rules_json 을 읽어 캐시에 보관한다. 규칙 없으면 None."""
        now = time.monotonic()
        cached = self._cache.get(host)
        if cached:
            rules, cached_at = cached
            if now - cached_at < config.RULES_CACHE_TTL_SECONDS:
                return rules or None  # 빈 dict {} 는 None 으로 취급

        # 캐시 미스 또는 만료 — DB 값으로 갱신
        rules: dict = {}
        if domain_row and domain_row.get("rules_enabled") and domain_row.get("rules_json"):
            raw = domain_row["rules_json"]
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = {}
            rules = raw or {}

        self._cache[host] = (rules, now)
        return rules or None

    def extract(
        self,
        url: str,
        html: str,
        host: str,
        rules: dict,
        portal_type: str = "",
        keyword: str = "",
    ) -> Article | ExtractionFailure:
        """rules_json 으로 HTML 에서 필드를 추출한다."""
        title  = _apply_rule(html, rules.get("title"))
        body   = _apply_rule(html, rules.get("body"))
        author = _apply_rule(html, rules.get("author")) or None
        press  = _apply_rule(html, rules.get("press"))  or None

        published_at_rule = rules.get("published_at")
        published_at = _parse_date(
            _apply_rule(html, published_at_rule),
            (published_at_rule or {}).get("date_format"),
        )

        if not title:
            return ExtractionFailure(
                url=url,
                error_code=ErrorCode.TITLE_EMPTY,
                error_msg="rule extracted empty title",
                is_permanent=True,
            )

        min_body = int(rules.get("min_body_len", 200))
        if not body or len(body) < min_body:
            return ExtractionFailure(
                url=url,
                error_code=ErrorCode.BODY_TOO_SHORT,
                error_msg=f"rule extracted body_len={len(body)} < {min_body}",
                is_permanent=False,
            )

        norm = normalize(url)
        return Article(
            url=norm,
            url_hash=url_hash(norm),
            portal_type=portal_type,
            keyword=keyword,
            title=title.strip(),
            body=body.strip(),
            published_at=published_at,
            author=author,
            press=press,
            collected_at=datetime.now(timezone.utc),
            extraction_method="rule:css" if "css" in str(rules) else "rule:xpath",
        )


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _apply_rule(html: str, rule: dict | None) -> str:
    """단일 필드 규칙을 HTML 에 적용해 텍스트를 반환한다. 실패 시 빈 문자열."""
    if not rule:
        return ""

    try:
        if "css" in rule:
            return _extract_css(html, rule["css"])
        if "xpath" in rule:
            return _extract_xpath(html, rule["xpath"])
    except Exception:
        pass

    return ""


def _parse_date(text: str, date_format: str | None) -> datetime | None:
    """텍스트를 KST datetime 으로 파싱한다. 실패하면 None."""
    if not text or not date_format:
        return None
    try:
        return datetime.strptime(text.strip(), date_format).replace(tzinfo=_KST)
    except ValueError:
        return None


def _extract_css(html: str, selector: str) -> str:
    from selectolax.parser import HTMLParser
    tree = HTMLParser(html)
    nodes = tree.css(selector)
    if not nodes:
        return ""
    # 여러 노드가 매칭되면 줄바꿈으로 이어 붙인다 (body 에서 <p> 여러 개 처리).
    return "\n".join(n.text(strip=True) for n in nodes if n.text(strip=True))


def _extract_xpath(html: str, expression: str) -> str:
    from lxml import etree
    tree = etree.HTML(html)
    if tree is None:
        return ""
    results = tree.xpath(expression)
    if not results:
        return ""
    # 속성값은 문자열, 노드는 텍스트로 변환
    texts = []
    for r in results:
        if isinstance(r, str):
            texts.append(r.strip())
        elif hasattr(r, "text_content"):
            texts.append(r.text_content().strip())
    return "\n".join(t for t in texts if t)
