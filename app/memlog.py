"""
메모리 사용량 스냅샷 로깅.

heartbeat 스레드(scheduling/dispatcher.py: _start_healthcheck_thread)와 같은
주기로 호출한다. 소스 구분 없이 항상 로깅한다 — google_news/baidu_news 처럼
Chrome 을 띄우는 소스는 rss_children_mb 가 점점 쌓이고, naver_news 처럼 안 쓰는
소스는 계속 0 근처에 머무는 게 정상이다. 후자를 대조군으로 남겨둬야 OOM 이
정말 Chrome 자식 프로세스 누수 때문인지, 아니면 파이썬 프로세스 자체(캐시,
커넥션 풀 등) 문제인지 로그만으로 구분할 수 있다.

출력은 logging_setup.py 가 구성한 "memlog" 로거(→ {log_name}-mem.log)로 간다.
"""

from __future__ import annotations

import logging

import psutil

_mem_logger = logging.getLogger("memlog")
_self = psutil.Process()

_MB = 1024 * 1024


def log_memory_usage(worker_id: str) -> None:
    """현재 프로세스(self) + 자식 프로세스(Chrome 등) 전체의 RSS 를 한 줄 로깅한다."""
    try:
        rss_self = _self.memory_info().rss
        children = _self.children(recursive=True)
    except psutil.NoSuchProcess:
        return

    rss_children = 0
    for child in children:
        try:
            rss_children += child.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    _mem_logger.info(
        f"worker={worker_id} rss_self_mb={rss_self / _MB:.1f} "
        f"rss_children_mb={rss_children / _MB:.1f} children={len(children)}"
    )
