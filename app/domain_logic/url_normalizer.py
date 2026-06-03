"""URL 정규화 + url_hash 생성 — 설계 문서 6절."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse

# utm_* / fbclid 등 추적 파라미터 제거 화이트리스트
_STRIP_PARAMS = re.compile(
    r"^(utm_source|utm_medium|utm_campaign|utm_term|utm_content"
    r"|fbclid|gclid|msclkid|ref|source)$",
    re.IGNORECASE,
)


def normalize(url: str) -> str:
    """
    URL 정규화:
    - 스킴: http → https
    - 호스트 소문자, www. 제거 (정책: 유지)
    - 추적 파라미터 제거
    - 끝 슬래시·기본 포트·프래그먼트 제거
    """
    parsed = urlparse(url.strip())

    scheme = "https"
    netloc = parsed.netloc.lower().rstrip(":")
    # 기본 포트 제거
    if netloc.endswith(":443") or netloc.endswith(":80"):
        netloc = netloc.rsplit(":", 1)[0]

    path = parsed.path.rstrip("/") or "/"

    # 추적 파라미터 제거
    qs = [(k, v) for k, v in parse_qsl(parsed.query) if not _STRIP_PARAMS.match(k)]
    query = urlencode(sorted(qs))

    return urlunparse((scheme, netloc, path, "", query, ""))


def url_hash(normalized_url: str) -> str:
    """sha256 hex (64자)."""
    return hashlib.sha256(normalized_url.encode()).hexdigest()
