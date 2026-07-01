"""
crawler-admin 화면이 비어 보이지 않도록 더미 데이터를 적재하는 스크립트.

적재 대상:
  - t_keyword      : 키워드 관리 화면
  - t_domain       : 도메인 규칙 화면
  - t_crawl_url    : 대시보드 상태 카드 + URL 목록 화면
  - t_collection_log : 대시보드 수집통계 + 로그 화면

실행:
  python scripts/seed_dummy_data.py           # 전체 적재
  python scripts/seed_dummy_data.py --dry-run # 실행 없이 적재 계획만 출력
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app import config
from app.repository.db import db_context

KST = timezone(timedelta(hours=9))


# ────────────────────────────────────────────────────────────────────────────
# helpers
# ────────────────────────────────────────────────────────────────────────────

def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:64]

def _kst_now(offset_hours: float = 0) -> datetime:
    return datetime.now(KST) + timedelta(hours=offset_hours)

def _kst_days_ago(days: int, hour: int = 9, minute: int = 0) -> datetime:
    d = datetime.now(KST) - timedelta(days=days)
    return d.replace(hour=hour, minute=minute, second=0, microsecond=0)


# ────────────────────────────────────────────────────────────────────────────
# 1. t_keyword
# ────────────────────────────────────────────────────────────────────────────

_KEYWORDS: list[tuple[str, str, str | None, int, int]] = [
    # (keyword, source_type, display_name, priority, interval_seconds)

    # NAVER_NEWS
    ("삼성전자",        "NAVER_NEWS", None, 5, 86400),
    ("LG에너지솔루션",  "NAVER_NEWS", None, 5, 86400),
    ("현대자동차",      "NAVER_NEWS", None, 4, 86400),
    ("전기차 화재",     "NAVER_NEWS", None, 4, 86400),
    ("배터리",          "NAVER_NEWS", None, 3, 86400),
    ("반도체",          "NAVER_NEWS", None, 3, 86400),
    ("ESG",             "NAVER_NEWS", None, 2, 86400),
    ("공급망",          "NAVER_NEWS", None, 2, 86400),
    ("랜섬웨어",        "NAVER_NEWS", None, 1, 86400),
    ("산업재해",        "NAVER_NEWS", None, 1, 86400),
    ("리콜",            "NAVER_NEWS", None, 1, 86400),
    ("유상증자",        "NAVER_NEWS", None, 0, 86400),
    ("물적분할",        "NAVER_NEWS", None, 0, 86400),
    ("수출통제",        "NAVER_NEWS", None, 0, 86400),
    ("희토류",          "NAVER_NEWS", None, 0, 86400),
    ("탄소중립",        "NAVER_NEWS", None, 0, 86400),
    ("HYBE",            "NAVER_NEWS", None, 0, 86400),
    ("특허소송",        "NAVER_NEWS", None, 0, 86400),
    ("해킹",            "NAVER_NEWS", None, 0, 86400),
    ("홍해 물류",       "NAVER_NEWS", None, 0, 86400),

    # DAUM_NEWS
    ("삼성전자",        "DAUM_NEWS", None, 5, 86400),
    ("현대자동차",      "DAUM_NEWS", None, 4, 86400),
    ("전기차 화재",     "DAUM_NEWS", None, 4, 86400),
    ("배터리",          "DAUM_NEWS", None, 3, 86400),
    ("반도체",          "DAUM_NEWS", None, 3, 86400),
    ("ESG",             "DAUM_NEWS", None, 2, 86400),
    ("랜섬웨어",        "DAUM_NEWS", None, 1, 86400),
    ("산업재해",        "DAUM_NEWS", None, 1, 86400),
    ("리콜",            "DAUM_NEWS", None, 0, 86400),
    ("공급망",          "DAUM_NEWS", None, 0, 86400),

    # GOOGLE_NEWS
    ("Samsung Electronics",  "GOOGLE_NEWS", None, 3, 86400),
    ("LG Energy Solution",   "GOOGLE_NEWS", None, 3, 86400),
    ("electric vehicle fire","GOOGLE_NEWS", None, 2, 86400),
    ("battery recall",       "GOOGLE_NEWS", None, 2, 86400),
    ("supply chain",         "GOOGLE_NEWS", None, 1, 86400),

    # NAVER_STOCK
    ("005930", "NAVER_STOCK", "삼성전자",    5, 86400),
    ("066570", "NAVER_STOCK", "LG전자",      4, 86400),
    ("051910", "NAVER_STOCK", "LG화학",      4, 86400),
    ("005380", "NAVER_STOCK", "현대자동차",  3, 86400),
    ("373220", "NAVER_STOCK", "LG에너지솔루션", 3, 86400),
    ("000270", "NAVER_STOCK", "기아",        2, 86400),
    ("035420", "NAVER_STOCK", "NAVER",       2, 86400),
    ("035720", "NAVER_STOCK", "카카오",      2, 86400),
    ("006400", "NAVER_STOCK", "삼성SDI",     1, 86400),
    ("207940", "NAVER_STOCK", "삼성바이오로직스", 1, 86400),
]


def _seed_keywords(conn, dry_run: bool) -> tuple[int, int]:
    inserted = skipped = 0
    for kw, source_type, display_name, priority, interval in _KEYWORDS:
        if dry_run:
            print(f"  [keyword] {source_type:<14} {kw}")
            continue
        r = conn.execute(text("""
            INSERT INTO t_keyword
                (keyword, source_type, display_name, enabled, priority, interval_seconds)
            VALUES (:kw, :st, :dn, 1, :prio, :interval)
            ON DUPLICATE KEY UPDATE id = id
        """), {"kw": kw, "st": source_type, "dn": display_name,
               "prio": priority, "interval": interval})
        if r.rowcount == 1:
            inserted += 1
        else:
            skipped += 1
    return inserted, skipped


# ────────────────────────────────────────────────────────────────────────────
# 2. t_domain
# ────────────────────────────────────────────────────────────────────────────

_DOMAINS: list[dict] = [
    # 규칙 활성
    {"host": "n.news.naver.com",    "render_mode": "static",   "crawl_delay_ms": 500,
     "rules_enabled": True,  "success_rate": 0.95, "recent_fail_count": 0,
     "rules_json": {"title": {"css": "h2.media_end_head_headline"},
                    "body":  {"css": "div#newsct_article"}, "min_body_len": 100}},
    {"host": "v.daum.net",          "render_mode": "static",   "crawl_delay_ms": 500,
     "rules_enabled": True,  "success_rate": 0.92, "recent_fail_count": 1,
     "rules_json": {"title": {"css": "h3.tit_view"},
                    "body":  {"css": "div.article_view"}, "min_body_len": 100}},
    {"host": "www.mk.co.kr",        "render_mode": "static",   "crawl_delay_ms": 1000,
     "rules_enabled": True,  "success_rate": 0.88, "recent_fail_count": 2,
     "rules_json": {"title": {"css": "h1.news_ttl"},
                    "body":  {"css": "div.news_cnt_detail_wrap"}, "min_body_len": 100}},
    {"host": "www.nocutnews.co.kr", "render_mode": "static",   "crawl_delay_ms": 1000,
     "rules_enabled": True,  "success_rate": 0.90, "recent_fail_count": 0,
     "rules_json": {"title": {"css": "h1.title"},
                    "body":  {"css": "div.article_body"}, "min_body_len": 100}},
    {"host": "biz.chosun.com",      "render_mode": "headless", "crawl_delay_ms": 1500,
     "rules_enabled": True,  "success_rate": 0.85, "recent_fail_count": 3,
     "rules_json": {"headless_wait_for": "section.article-body",
                    "title": {"css": "h1.article-header__headline"},
                    "body":  {"css": "section.article-body"}, "min_body_len": 100}},
    {"host": "news.jtbc.co.kr",     "render_mode": "headless", "crawl_delay_ms": 2000,
     "rules_enabled": True,  "success_rate": 0.78, "recent_fail_count": 5,
     "rules_json": {"headless_wait_for": "div#ijam_content",
                    "title": {"xpath": "//meta[@property='og:title']/@content"},
                    "body":  {"css": "div#ijam_content"}, "min_body_len": 100}},
    {"host": "finance.naver.com",   "render_mode": "static",   "crawl_delay_ms": 500,
     "rules_enabled": True,  "success_rate": 0.97, "recent_fail_count": 0,
     "rules_json": {"json_api": {"url_template": "https://m.stock.naver.com/front-api/discussion/detail?id={nid}",
                                  "url_param": "nid", "title": "result.title",
                                  "body_html": "result.contentHtml"}, "min_body_len": 5}},

    # 규칙 비활성 (rules_json 있지만 enabled=False)
    {"host": "www.nytimes.com",     "render_mode": "static",   "crawl_delay_ms": 1000,
     "rules_enabled": False, "success_rate": 0.05, "recent_fail_count": 12,
     "rules_json": None},
    {"host": "www.thebell.co.kr",   "render_mode": "headless", "crawl_delay_ms": 2000,
     "rules_enabled": False, "success_rate": 0.60, "recent_fail_count": 4,
     "rules_json": {"headless_wait_for": "div#article_main p",
                    "title": {"xpath": "//meta[@property='og:title']/@content"},
                    "body":  {"css": "div#article_main"}, "min_body_len": 100}},

    # 규칙 없음 (rules_json NULL — 라이브러리 기본 추출)
    {"host": "www.hankyung.com",    "render_mode": "static",   "crawl_delay_ms": 1000,
     "rules_enabled": True,  "success_rate": 0.82, "recent_fail_count": 1, "rules_json": None},
    {"host": "www.yonhapnews.co.kr","render_mode": "static",   "crawl_delay_ms": 800,
     "rules_enabled": True,  "success_rate": 0.93, "recent_fail_count": 0, "rules_json": None},
    {"host": "www.edaily.co.kr",    "render_mode": "static",   "crawl_delay_ms": 1000,
     "rules_enabled": True,  "success_rate": 0.80, "recent_fail_count": 2, "rules_json": None},
    {"host": "www.sedaily.com",     "render_mode": "static",   "crawl_delay_ms": 1000,
     "rules_enabled": True,  "success_rate": 0.75, "recent_fail_count": 6, "rules_json": None},
    {"host": "www.yna.co.kr",       "render_mode": "static",   "crawl_delay_ms": 800,
     "rules_enabled": True,  "success_rate": 0.91, "recent_fail_count": 0, "rules_json": None},
    # 쿨다운 중인 도메인
    {"host": "www.chosun.com",      "render_mode": "static",   "crawl_delay_ms": 1000,
     "rules_enabled": True,  "success_rate": 0.55, "recent_fail_count": 8,
     "cooldown_until": _kst_now(offset_hours=3), "rules_json": None},
    {"host": "biz.sbs.co.kr",       "render_mode": "static",   "crawl_delay_ms": 1500,
     "rules_enabled": True,  "success_rate": 0.62, "recent_fail_count": 5,
     "cooldown_until": _kst_now(offset_hours=1), "rules_json": None},
]


def _seed_domains(conn, dry_run: bool) -> tuple[int, int]:
    inserted = updated = 0
    for d in _DOMAINS:
        if dry_run:
            print(f"  [domain] {d['host']} render={d['render_mode']} rules={'Y' if d.get('rules_json') else 'N'}")
            continue
        r = conn.execute(text("""
            INSERT INTO t_domain
                (host, rules_json, rules_enabled, rules_version,
                 render_mode, crawl_delay_ms, updated_by,
                 success_rate, recent_fail_count, cooldown_until)
            VALUES
                (:host, :rules_json, :rules_enabled, 1,
                 :render_mode, :crawl_delay_ms, 'seed',
                 :success_rate, :recent_fail_count, :cooldown_until)
            ON DUPLICATE KEY UPDATE
                rules_json        = VALUES(rules_json),
                rules_enabled     = VALUES(rules_enabled),
                render_mode       = VALUES(render_mode),
                crawl_delay_ms    = VALUES(crawl_delay_ms),
                success_rate      = VALUES(success_rate),
                recent_fail_count = VALUES(recent_fail_count),
                cooldown_until    = VALUES(cooldown_until),
                updated_by        = 'seed'
        """), {
            "host":            d["host"],
            "rules_json":      json.dumps(d["rules_json"], ensure_ascii=False) if d.get("rules_json") else None,
            "rules_enabled":   d.get("rules_enabled", True),
            "render_mode":     d.get("render_mode"),
            "crawl_delay_ms":  d.get("crawl_delay_ms"),
            "success_rate":    d.get("success_rate"),
            "recent_fail_count": d.get("recent_fail_count", 0),
            "cooldown_until":  d.get("cooldown_until"),
        })
        if r.rowcount == 1:
            inserted += 1
        else:
            updated += 1
    return inserted, updated


# ────────────────────────────────────────────────────────────────────────────
# 3. t_crawl_url
# ────────────────────────────────────────────────────────────────────────────

_HOSTS = [
    "n.news.naver.com", "v.daum.net", "www.mk.co.kr", "www.nocutnews.co.kr",
    "biz.chosun.com", "news.jtbc.co.kr", "www.hankyung.com",
    "www.yonhapnews.co.kr", "www.edaily.co.kr", "www.sedaily.com",
    "www.yna.co.kr", "finance.naver.com", "www.chosun.com", "biz.sbs.co.kr",
]

_SOURCES = ["NAVER_NEWS", "NAVER_NEWS", "NAVER_NEWS",  # 비중 높게
            "DAUM_NEWS", "DAUM_NEWS",
            "GOOGLE_NEWS", "NAVER_STOCK"]

_ARTICLES = [
    ("삼성전자-3분기-실적-발표",       "n.news.naver.com"),
    ("LG에너지솔루션-배터리-리콜",     "n.news.naver.com"),
    ("현대차-전기차-화재-원인",         "n.news.naver.com"),
    ("반도체-수출규제-영향-분석",       "www.mk.co.kr"),
    ("ESG-경영-중소기업-확산",          "www.mk.co.kr"),
    ("공급망-재편-가속화",              "biz.chosun.com"),
    ("홍해-물류-차질-지속",             "www.hankyung.com"),
    ("랜섬웨어-공격-국내-기업",         "www.nocutnews.co.kr"),
    ("산업재해-안전-대책",              "www.yonhapnews.co.kr"),
    ("특허소송-판결-결과",              "www.edaily.co.kr"),
    ("탄소중립-2030-로드맵",            "www.yna.co.kr"),
    ("물적분할-주주-반발",              "biz.sbs.co.kr"),
    ("HYBE-민희진-경영권-분쟁",         "n.news.naver.com"),
    ("희토류-중국-수출-통제",           "www.mk.co.kr"),
    ("삼성SDI-배터리-화재",             "news.jtbc.co.kr"),
    ("삼성전자-HBM-납품",               "www.sedaily.com"),
    ("LG전자-2분기-실적",               "v.daum.net"),
    ("카카오-규제-이슈",                "v.daum.net"),
    ("현대차-기아-전기차-판매",         "www.hankyung.com"),
    ("SK하이닉스-AI-반도체",            "www.edaily.co.kr"),
]

_ERROR_CODES = ["FETCH_TIMEOUT", "FETCH_429", "FETCH_403", "BODY_TOO_SHORT", "PARSE_ERROR", "FETCH_5XX"]
_ERROR_MSGS  = [
    "httpx.ReadTimeout: read timed out",
    "HTTP 429 Too Many Requests",
    "HTTP 403 Forbidden",
    "extracted body length 12 < min 100",
    "lxml.etree.XMLSyntaxError: invalid element name",
    "HTTP 503 Service Unavailable",
]


def _make_crawl_urls(keyword_id_map: dict) -> list[dict]:
    """각 상태별로 더미 URL 목록 생성."""
    rows = []
    counter = [0]

    def _make(status: str, source_type: str, host: str, slug: str,
              attempt: int = 0, error_code: str | None = None,
              error_msg: str | None = None, extraction_method: str | None = None,
              days_ago: int = 0) -> dict:
        counter[0] += 1
        url = f"https://{host}/article/{counter[0]:05d}/{slug}"
        kw_ids = [v for k, v in keyword_id_map.items() if k[1] == source_type]
        keyword_id = random.choice(kw_ids) if kw_ids else None
        created = _kst_days_ago(days_ago, hour=random.randint(6, 22))
        collected = (date.today() - timedelta(days=days_ago)) if status == "stored" else None
        return {
            "url":              url,
            "url_hash":         _url_hash(url),
            "host":             host,
            "keyword_id":       keyword_id,
            "source_type":      source_type,
            "status":           status,
            "attempt_count":    attempt,
            "last_error_code":  error_code,
            "last_error_msg":   error_msg,
            "extraction_method": extraction_method,
            "priority":         random.choice([0, 0, 0, 1, 2]),
            "is_manual":        0,
            "collected_date":   collected,
            "created_at":       created,
            "updated_at":       created + timedelta(minutes=random.randint(1, 30)),
        }

    # discovered — 아직 처리 대기 중
    for i in range(30):
        src  = random.choice(_SOURCES)
        host = random.choice(_HOSTS)
        slug, _ = random.choice(_ARTICLES)
        rows.append(_make("discovered", src, host, f"{slug}-{i}", days_ago=random.randint(0, 2)))

    # extracting — 현재 처리 중 (소수)
    for i in range(4):
        src  = random.choice(_SOURCES)
        host = random.choice(_HOSTS)
        slug, _ = random.choice(_ARTICLES)
        rows.append(_make("extracting", src, host, f"{slug}-ext-{i}", attempt=1, days_ago=0))

    # stored — 성공
    methods = ["trafilatura", "trafilatura", "readability", "rule:css"]
    for i in range(120):
        slug, host = random.choice(_ARTICLES)
        src = random.choice(_SOURCES)
        rows.append(_make("stored", src, host, f"{slug}-ok-{i}",
                          attempt=random.randint(1, 3),
                          extraction_method=random.choice(methods),
                          days_ago=random.randint(0, 7)))

    # failed_transient — 일시 실패
    for i in range(25):
        src  = random.choice(_SOURCES)
        host = random.choice(_HOSTS)
        slug, _ = random.choice(_ARTICLES)
        ec, em = random.choice(list(zip(_ERROR_CODES, _ERROR_MSGS)))
        rows.append(_make("failed_transient", src, host, f"{slug}-ft-{i}",
                          attempt=random.randint(1, 4),
                          error_code=ec, error_msg=em,
                          days_ago=random.randint(0, 3)))

    # failed_permanent — 영구 실패
    for i in range(12):
        src  = random.choice(_SOURCES)
        host = random.choice(_HOSTS)
        slug, _ = random.choice(_ARTICLES)
        ec, em = random.choice([
            ("FETCH_403",    "HTTP 403 Forbidden — paywall detected"),
            ("BODY_TOO_SHORT","extracted body length 8 < min 100"),
            ("PAYWALL",      "paywall marker detected in body"),
        ])
        rows.append(_make("failed_permanent", src, host, f"{slug}-fp-{i}",
                          attempt=random.randint(3, 5),
                          error_code=ec, error_msg=em,
                          days_ago=random.randint(0, 7)))

    # dead — 재시도 횟수 초과
    for i in range(6):
        src  = random.choice(_SOURCES)
        host = random.choice(_HOSTS)
        slug, _ = random.choice(_ARTICLES)
        ec, em = random.choice(list(zip(_ERROR_CODES, _ERROR_MSGS)))
        rows.append(_make("dead", src, host, f"{slug}-dead-{i}",
                          attempt=5, error_code=ec, error_msg=em,
                          days_ago=random.randint(2, 7)))

    return rows


def _seed_crawl_urls(conn, dry_run: bool) -> tuple[int, int]:
    # 기존 키워드 ID 조회
    kw_rows = conn.execute(text("SELECT id, keyword, source_type FROM t_keyword")).mappings().all()
    keyword_id_map = {(r["keyword"], r["source_type"]): r["id"] for r in kw_rows}

    rows = _make_crawl_urls(keyword_id_map)

    if dry_run:
        from collections import Counter
        counts = Counter(r["status"] for r in rows)
        for status, cnt in sorted(counts.items()):
            print(f"  [crawl_url] {status:<20} {cnt:>3}건")
        return len(rows), 0

    inserted = skipped = 0
    for r in rows:
        try:
            conn.execute(text("""
                INSERT INTO t_crawl_url
                    (url, url_hash, host, keyword_id, source_type,
                     status, attempt_count, last_error_code, last_error_msg,
                     extraction_method, priority, is_manual,
                     collected_date, created_at, updated_at)
                VALUES
                    (:url, :url_hash, :host, :keyword_id, :source_type,
                     :status, :attempt_count, :last_error_code, :last_error_msg,
                     :extraction_method, :priority, :is_manual,
                     :collected_date, :created_at, :updated_at)
                ON DUPLICATE KEY UPDATE url_hash = url_hash
            """), r)
            inserted += 1
        except Exception:
            skipped += 1
    return inserted, skipped


# ────────────────────────────────────────────────────────────────────────────
# 4. t_collection_log
# ────────────────────────────────────────────────────────────────────────────

def _make_collection_logs() -> list[dict]:
    logs = []

    disc_sources = ["NAVER_NEWS", "DAUM_NEWS", "GOOGLE_NEWS", "NAVER_STOCK"]
    ext_sources  = ["NAVER_NEWS", "DAUM_NEWS", "GOOGLE_NEWS", "NAVER_STOCK"]

    for days_ago in range(7, -1, -1):  # 7일 전 ~ 오늘
        run_date = (date.today() - timedelta(days=days_ago)).isoformat()

        # discovery — 소스별 1건씩, 각 소스 여러 키워드
        for src in disc_sources:
            n_keywords = random.randint(8, 25)
            for _ in range(n_keywords):
                found    = random.randint(20, 120)
                inserted = int(found * random.uniform(0.3, 0.9))
                started  = _kst_days_ago(days_ago, hour=random.randint(2, 8),
                                         minute=random.randint(0, 59))
                logs.append({
                    "run_type":      "discovery",
                    "run_date":      run_date,
                    "keyword_id":    None,
                    "source_type":   src,
                    "worker_id":     f"disc-{src.lower()[:5]}-1",
                    "started_at":    started,
                    "duration_ms":   random.randint(3000, 25000),
                    "urls_found":    found,
                    "urls_inserted": inserted,
                    "urls_skipped":  found - inserted,
                    "urls_attempted": None,
                    "urls_success":  None,
                    "urls_failed":   None,
                    "error_msg":     None,
                })

        # extraction — 소스별 배치 로그 (하트비트 단위이지만 하루 몇 건으로 대표)
        for src in ext_sources:
            n_batches = random.randint(3, 8)
            for _ in range(n_batches):
                attempted = random.randint(30, 120)
                success   = int(attempted * random.uniform(0.75, 0.97))
                failed    = attempted - success
                started   = _kst_days_ago(days_ago, hour=random.randint(2, 22),
                                          minute=random.randint(0, 59))
                logs.append({
                    "run_type":      "extraction",
                    "run_date":      run_date,
                    "keyword_id":    None,
                    "source_type":   src,
                    "worker_id":     "extr-1",
                    "started_at":    started,
                    "duration_ms":   random.randint(30000, 180000),
                    "urls_found":    None,
                    "urls_inserted": None,
                    "urls_skipped":  None,
                    "urls_attempted": attempted,
                    "urls_success":  success,
                    "urls_failed":   failed,
                    "error_msg":     None,
                })

    return logs


def _seed_collection_logs(conn, dry_run: bool) -> int:
    logs = _make_collection_logs()

    if dry_run:
        from collections import Counter
        counts = Counter((r["run_type"], r["source_type"]) for r in logs)
        for (rt, src), cnt in sorted(counts.items()):
            print(f"  [collection_log] {rt:<12} {src:<15} {cnt:>3}건")
        return len(logs)

    conn.execute(text("""
        INSERT INTO t_collection_log
            (run_type, run_date, keyword_id, source_type, worker_id,
             started_at, duration_ms,
             urls_found, urls_inserted, urls_skipped,
             urls_attempted, urls_success, urls_failed, error_msg)
        VALUES
            (:run_type, :run_date, :keyword_id, :source_type, :worker_id,
             :started_at, :duration_ms,
             :urls_found, :urls_inserted, :urls_skipped,
             :urls_attempted, :urls_success, :urls_failed, :error_msg)
    """), logs)
    return len(logs)


# ────────────────────────────────────────────────────────────────────────────
# main
# ────────────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="crawler-admin 더미 데이터 적재")
    p.add_argument("--dry-run", action="store_true", help="DB에 쓰지 않고 계획만 출력")
    args = p.parse_args()

    if not args.dry_run:
        config.validate()

    print("=== crawler-admin 더미 데이터 적재 ===\n")

    with db_context() as engine:
        with engine.begin() as conn:

            # 1. 키워드
            print(f"[1/4] t_keyword — {len(_KEYWORDS)}개")
            if args.dry_run:
                _seed_keywords(conn, dry_run=True)
            else:
                ins, skp = _seed_keywords(conn, dry_run=False)
                print(f"      신규 {ins}건 / 중복 스킵 {skp}건")

            # 2. 도메인
            print(f"\n[2/4] t_domain — {len(_DOMAINS)}개")
            if args.dry_run:
                _seed_domains(conn, dry_run=True)
            else:
                ins, upd = _seed_domains(conn, dry_run=False)
                print(f"      INSERT {ins}건 / UPDATE {upd}건")

            # 3. crawl_url
            print(f"\n[3/4] t_crawl_url")
            if args.dry_run:
                total, _ = _seed_crawl_urls(conn, dry_run=True)
                print(f"      총 {total}건 예정")
            else:
                ins, skp = _seed_crawl_urls(conn, dry_run=False)
                print(f"      INSERT {ins}건 / 중복 스킵 {skp}건")

            # 4. collection_log
            print(f"\n[4/4] t_collection_log (최근 8일)")
            if args.dry_run:
                total = _seed_collection_logs(conn, dry_run=True)
                print(f"      총 {total}건 예정")
            else:
                total = _seed_collection_logs(conn, dry_run=False)
                print(f"      INSERT {total}건")

    print("\n완료.")


if __name__ == "__main__":
    main()
