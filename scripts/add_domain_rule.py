"""
도메인 정책 설정 — crawl_delay_ms / render_mode / rules_json / cooldown 관리.

실행:
  python scripts/add_domain_rule.py --host www.example.com --delay 2000
  python scripts/add_domain_rule.py --host www.example.com --render headless
  python scripts/add_domain_rule.py --host www.example.com --render headless_with_iframe
  python scripts/add_domain_rule.py --host finance.naver.com --render headless_with_iframe \\
      --rules-json '{"title":{"css":"em.title"},"body":{"css":"#frame_contents [class*=\\'content\\']"}}'
  python scripts/add_domain_rule.py --host www.example.com --cooldown-clear
  python scripts/add_domain_rule.py --host www.example.com --show
"""

import sys
import argparse
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.repository.db import db_context


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host",           required=True, help="대상 도메인 (예: www.example.com)")
    p.add_argument("--delay",          type=int,       help="crawl_delay_ms 설정 (ms)")
    p.add_argument("--render",         choices=["static", "headless", "headless_with_iframe"],
                                                       help="render_mode 설정")
    p.add_argument("--rules-json",     help="rules_json JSON 문자열 (자동으로 rules_enabled=1 설정)")
    p.add_argument("--rules-disable",  action="store_true", help="rules_enabled=0 으로 설정")
    p.add_argument("--cooldown-clear", action="store_true", help="cooldown_until 초기화")
    p.add_argument("--show",           action="store_true", help="현재 설정 조회")
    args = p.parse_args()

    host = args.host.lower()
    updates: dict = {}

    if args.delay is not None:
        updates["crawl_delay_ms"] = args.delay
    if args.render:
        updates["render_mode"] = args.render
    if args.rules_json:
        try:
            parsed = json.loads(args.rules_json)
        except json.JSONDecodeError as e:
            print(f"rules-json 파싱 오류: {e}")
            sys.exit(1)
        updates["rules_json"]    = json.dumps(parsed, ensure_ascii=False)
        updates["rules_enabled"] = 1
    if args.rules_disable:
        updates["rules_enabled"] = 0
    if args.cooldown_clear:
        updates["cooldown_until"] = None

    with db_context() as engine:
        if args.show or not updates:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT * FROM domain WHERE host = :host"),
                    {"host": host},
                ).fetchone()
            if row:
                d = dict(row._mapping)
                print(f"host           : {d['host']}")
                print(f"crawl_delay_ms : {d['crawl_delay_ms']}")
                print(f"render_mode    : {d['render_mode']}")
                print(f"cooldown_until : {d['cooldown_until']}")
                print(f"success_rate   : {d['success_rate']}")
                print(f"rules_enabled  : {d['rules_enabled']}")
            else:
                print(f"'{host}' 에 대한 domain 설정 없음 (전역 기본값 사용)")
            return

        set_parts = ", ".join(f"{k} = :{k}" for k in updates)
        updates["host"] = host

        with engine.begin() as conn:
            # 행이 없으면 INSERT, 있으면 UPDATE
            conn.execute(
                text(f"""
                    INSERT INTO domain (host, updated_at)
                    VALUES (:host, NOW())
                    ON DUPLICATE KEY UPDATE updated_at = NOW()
                """),
                {"host": host},
            )
            conn.execute(
                text(f"UPDATE domain SET {set_parts}, updated_by = 'manual', updated_at = NOW() WHERE host = :host"),
                updates,
            )

        print(f"[{host}] 설정 완료:")
        for k, v in updates.items():
            if k != "host":
                print(f"  {k} = {v}")


if __name__ == "__main__":
    main()
