"""
로깅 골격 — 설계 문서 12절.

스트림 분리:
  app.log   — 정상 동작·진행·하트비트 (INFO 이상)
  error.log — WARNING 이상만. "왜 멈췄나"를 한 곳에서 본다.

에러 엔트리 포맷:
  {ts} {level} {component} worker={id} phase={phase} keyword_id={id} url_id={id} host={host} code={code} {msg}
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

from news_crawler import config

_initialized = False


def setup(component: str, worker_id: str | None = None) -> logging.Logger:
    """
    로깅을 초기화하고 component 전용 Logger를 반환한다.
    프로세스당 한 번만 실제 초기화하고 이후 호출은 Logger만 반환한다.
    """
    global _initialized

    log_dir = Path(config.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    if not _initialized:
        _configure_root(log_dir)
        _initialized = True

    logger = logging.getLogger(component)
    if worker_id:
        logger = logging.LoggerAdapter(logger, {"worker_id": worker_id, "component": component})  # type: ignore[assignment]
    return logger


# ---------------------------------------------------------------------------
# 내부 구현
# ---------------------------------------------------------------------------

class _ContextFilter(logging.Filter):
    """필드가 없을 때 기본값을 채워준다."""

    _DEFAULTS = {
        "worker_id":  "-",
        "component":  "app",
        "phase":      "-",
        "keyword_id": "-",
        "url_id":     "-",
        "host":       "-",
        "error_code": "-",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        for key, val in self._DEFAULTS.items():
            if not hasattr(record, key):
                setattr(record, key, val)
        return True


_APP_FMT = (
    "%(asctime)s %(levelname)-5s [%(component)s] "
    "worker=%(worker_id)s phase=%(phase)s keyword_id=%(keyword_id)s url_id=%(url_id)s host=%(host)s "
    "%(message)s"
)

_ERROR_FMT = (
    "%(asctime)s %(levelname)-5s [%(component)s] "
    "worker=%(worker_id)s phase=%(phase)s keyword_id=%(keyword_id)s url_id=%(url_id)s host=%(host)s "
    "code=%(error_code)s %(message)s"
)

_DATE_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _make_rotating_handler(path: Path, level: int) -> logging.Handler:
    rotation = config.LOG_ROTATION
    if rotation == "daily":
        handler: logging.Handler = logging.handlers.TimedRotatingFileHandler(
            path, when="midnight", backupCount=30, encoding="utf-8", utc=True
        )
    else:
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=100 * 1024 * 1024, backupCount=10, encoding="utf-8"
        )
    handler.setLevel(level)
    return handler


def _configure_root(log_dir: Path) -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))

    # 외부 라이브러리 내부 로그 억제 — app.log 노이즈 방지
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("undetected_chromedriver").setLevel(logging.WARNING)

    ctx = _ContextFilter()

    # app.log — INFO 이상
    app_handler = _make_rotating_handler(log_dir / "app.log", logging.INFO)
    app_handler.addFilter(ctx)
    app_handler.setFormatter(logging.Formatter(_APP_FMT, datefmt=_DATE_FMT))
    root.addHandler(app_handler)

    # error.log — WARNING 이상
    err_handler = _make_rotating_handler(log_dir / "error.log", logging.WARNING)
    err_handler.addFilter(ctx)
    err_handler.setFormatter(logging.Formatter(_ERROR_FMT, datefmt=_DATE_FMT))
    root.addHandler(err_handler)

    # 콘솔 — 개발 편의용 (LOG_LEVEL 이상)
    console = logging.StreamHandler()
    console.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
    console.addFilter(ctx)
    console.setFormatter(logging.Formatter(_APP_FMT, datefmt=_DATE_FMT))
    root.addHandler(console)
