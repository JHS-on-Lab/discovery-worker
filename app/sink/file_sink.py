"""
FileSink — Article 을 JSONL 파일에 기록.

파티셔닝: {FILE_SINK_DIR}/{YYYY-MM-DD}/{portal_type}-{worker_id}.jsonl
worker-id 별로 파일을 분리해 여러 extractor 가 동시에 써도 충돌하지 않는다.
"""

from __future__ import annotations

import dataclasses
import json
import os
from datetime import timezone
from pathlib import Path

from app import config
from app.types import Article


class FileSink:
    def __init__(self, base_dir: str | None = None) -> None:
        self._base = Path(base_dir or config.FILE_SINK_DIR)

    def write(self, article: Article) -> None:
        date_str = article.collected_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
        out_dir = self._base / date_str
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{article.portal_type}-{config.WORKER_ID}.jsonl"

        row = dataclasses.asdict(article)
        # datetime → ISO 문자열
        if row.get("published_at") is not None:
            row["published_at"] = row["published_at"].isoformat()
        row["collected_at"] = row["collected_at"].isoformat()

        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
