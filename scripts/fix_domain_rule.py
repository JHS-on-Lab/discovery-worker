"""
도메인 규칙 조회 · 진단 · 업데이트 스크립트.

사용법:
  # 호스트의 현재 규칙 조회만
  python scripts/fix_domain_rule.py --host www.thepowernews.co.kr

  # URL로 현재 규칙 진단 (왜 실패하는지 필드별 분석)
  python scripts/fix_domain_rule.py --url "https://www.thepowernews.co.kr/view.php?ud=..."

  # 새 규칙 테스트
  python scripts/fix_domain_rule.py --url "..." --rule '{"title":{"css":"div.gmv1d"},"body":{"css":"div.gmv2c_con01"},"min_body_len":100}'

  # 새 규칙 테스트 + DB 저장
  python scripts/fix_domain_rule.py --url "..." --rule '...' --save
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.repository.db import db_context
from app.repository.domain_repo import DomainRepo
from app.fetch._client import make_client


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="도메인 규칙 조회·진단·업데이트")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--url",  help="진단할 기사 URL (host 자동 추출)")
    g.add_argument("--host", help="호스트 직접 지정 (규칙 조회만, 진단 없음)")
    p.add_argument("--rule", default=None, help="새 rules_json (JSON 문자열). 미지정 시 현재 규칙만 진단")
    p.add_argument("--save", action="store_true", help="테스트 성공 시 DB 에 바로 저장 (미지정 시 확인 후 저장)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# HTML 페치
# ---------------------------------------------------------------------------

def _fetch(url: str) -> str:
    print(f"Fetching {url} ...")
    with make_client() as client:
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()
    print(f"  → {resp.status_code}  {len(resp.text):,} bytes\n")
    return resp.text


# ---------------------------------------------------------------------------
# 규칙 필드별 진단
# ---------------------------------------------------------------------------

def _diagnose_rule(html: str, rules: dict) -> bool:
    """rules 를 필드별로 적용해 결과를 출력한다. 추출 성공 여부를 반환."""
    from selectolax.parser import HTMLParser
    from lxml import etree

    def _css(selector: str) -> list[str]:
        nodes = HTMLParser(html).css(selector)
        return [n.text(strip=True) for n in nodes if n.text(strip=True)]

    def _xpath(expr: str) -> list[str]:
        tree = etree.HTML(html)
        if tree is None:
            return []
        results = tree.xpath(expr)
        if isinstance(results, str):
            return [results.strip()] if results.strip() else []
        out = []
        for r in results:
            if isinstance(r, str) and r.strip():
                out.append(r.strip())
            elif hasattr(r, "text_content") and r.text_content().strip():
                out.append(r.text_content().strip())
        return out

    def _apply(rule: dict | None, label: str) -> str:
        if not rule:
            print(f"  {label:<14}: (규칙 없음)")
            return ""
        if "css" in rule:
            hits = _css(rule["css"])
            if hits:
                preview = hits[0][:120].replace("\n", " ")
                total = sum(len(h) for h in hits)
                print(f"  {label:<14}: [CSS OK] {len(hits)}개 노드 / 총 {total}자  »  {preview!r}")
                return "\n".join(hits)
            else:
                print(f"  {label:<14}: [CSS MISS] selector='{rule['css']}' → 매칭 없음")
                return ""
        if "xpath" in rule:
            hits = _xpath(rule["xpath"])
            if hits:
                preview = hits[0][:120].replace("\n", " ")
                total = sum(len(h) for h in hits)
                print(f"  {label:<14}: [XPATH OK] {len(hits)}개 결과 / 총 {total}자  »  {preview!r}")
                return "\n".join(hits)
            else:
                print(f"  {label:<14}: [XPATH MISS] expr='{rule['xpath']}' → 매칭 없음")
                return ""
        print(f"  {label:<14}: (css/xpath 키 없음)")
        return ""

    print("--- 필드별 적용 결과 ---")
    title  = _apply(rules.get("title"),        "title")
    body   = _apply(rules.get("body"),          "body")
    _apply(rules.get("author"),                 "author")
    _apply(rules.get("published_at"),           "published_at")

    min_body = int(rules.get("min_body_len", 200))
    print()

    ok = True
    if not title:
        print("  [실패] title 빈값")
        ok = False
    if not body:
        print("  [실패] body 빈값")
        ok = False
    elif len(body) < min_body:
        print(f"  [실패] body_len={len(body)} < min_body_len={min_body}")
        ok = False

    if ok:
        print(f"  [성공] title={len(title)}자  body={len(body)}자")

    return ok


# ---------------------------------------------------------------------------
# DB 저장
# ---------------------------------------------------------------------------

_UPSERT_SQL = text("""
    INSERT INTO t_domain
        (host, rules_json, rules_enabled, rules_version, updated_by)
    VALUES
        (:host, :rules_json, 1, 1, 'fix_domain_rule')
    ON DUPLICATE KEY UPDATE
        rules_json        = VALUES(rules_json),
        rules_enabled     = 1,
        rules_version     = rules_version + 1,
        updated_by        = VALUES(updated_by),
        cooldown_until    = NULL,
        recent_fail_count = 0
""")


def _save_rule(engine, host: str, rules: dict) -> None:
    with engine.begin() as conn:
        conn.execute(_UPSERT_SQL, {
            "host":       host,
            "rules_json": json.dumps(rules, ensure_ascii=False),
        })
    print(f"\n저장 완료: {host}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def _print_domain_row(domain: dict | None) -> dict | None:
    """현재 DB 규칙을 출력하고 rules dict 를 반환한다."""
    print("=== 현재 DB 규칙 ===")
    if domain is None:
        print("  (등록된 행 없음)\n")
        return None

    for field in ("rules_enabled", "render_mode", "crawl_delay_ms", "cooldown_until",
                  "recent_fail_count", "success_rate", "avg_body_len"):
        val = domain.get(field)
        if val is not None:
            print(f"  {field:<20}: {val}")

    raw = domain.get("rules_json")
    if raw:
        rules = raw if isinstance(raw, dict) else json.loads(raw)
        print(f"  rules_json          :\n{json.dumps(rules, ensure_ascii=False, indent=4)}")
    else:
        print("  rules_json          : (없음)")
        rules = None
    print()
    return rules


def main() -> None:
    args = _parse_args()

    # ── --host 모드: 규칙 조회만 (URL 또는 호스트명 모두 수용) ─────────────
    if args.host:
        host = urlparse(args.host).netloc or args.host
        print(f"host : {host}\n")
        with db_context() as engine:
            domain = DomainRepo(engine).get(host)
        _print_domain_row(domain)
        return

    # ── --url 모드: 진단 + 선택적 업데이트 ─────────────────────────────────
    host = urlparse(args.url).netloc
    print(f"host : {host}\n")

    html = _fetch(args.url)

    with db_context() as engine:
        domain = DomainRepo(engine).get(host)
        current_rules = _print_domain_row(domain)

        # ── 현재 규칙 진단 ──────────────────────────────────────────────────
        if current_rules:
            label = "현재 규칙 진단" if domain.get("rules_enabled") else \
                    "현재 규칙 진단 (rules_enabled=False — 실제 추출에서는 무시됨)"
            print(f"=== {label} ===")
            _diagnose_rule(html, current_rules)
            print()

        # ── 새 규칙 테스트 ──────────────────────────────────────────────────
        if not args.rule:
            return

        print("=== 새 규칙 테스트 ===")
        try:
            new_rules = json.loads(args.rule)
        except json.JSONDecodeError as e:
            print(f"--rule JSON 파싱 실패: {e}")
            sys.exit(1)

        print(json.dumps(new_rules, ensure_ascii=False, indent=2))
        print()

        ok = _diagnose_rule(html, new_rules)

        if not ok:
            print("\n새 규칙도 추출 실패 — DB 저장 안 함")
            sys.exit(1)

        # ── 저장 ────────────────────────────────────────────────────────────
        if args.save:
            _save_rule(engine, host, new_rules)
        else:
            ans = input("\nDB에 저장할까요? [y/N] ").strip().lower()
            if ans == "y":
                _save_rule(engine, host, new_rules)
            else:
                print("저장 취소")


if __name__ == "__main__":
    main()
