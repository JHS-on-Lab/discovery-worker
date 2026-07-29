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


def _child_type(proc: psutil.Process) -> str:
    """cmdline 의 --type= 인자로 Chrome 자식 프로세스 종류(renderer/gpu-process/utility/
    crashpad-handler/zygote 등)를 구분한다. --type 이 없으면(메인 브라우저 프로세스
    등) 프로세스 이름을 그대로 쓴다. zombie 상태는 커널이 이미 메모리를 회수해
    RSS 증가의 원인이 될 수 없으므로 태그로 따로 구분해둔다."""
    try:
        zombie = proc.status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        zombie = False
    suffix = ":zombie" if zombie else ""

    try:
        cmdline = proc.cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return f"unknown{suffix}"

    for arg in cmdline:
        if arg.startswith("--type="):
            return arg[len("--type="):] + suffix

    try:
        name = proc.name()
    except psutil.NoSuchProcess:
        name = "unknown"
    return f"{name}(browser){suffix}"


def log_memory_usage(worker_id: str) -> None:
    """현재 프로세스(self) + 자식 프로세스(Chrome 등) 전체의 RSS 를, 자식은 타입별
    (renderer/gpu-process/utility/crashpad-handler/...) 로 나눠 한 줄 로깅한다."""
    try:
        rss_self = _self.memory_info().rss
        children = _self.children(recursive=True)
    except psutil.NoSuchProcess:
        return

    rss_children = 0
    by_type: dict[str, list[int]] = {}  # type -> [count, rss_sum]
    for child in children:
        # oneshot() 은 status/name/memory_info 등을 한 번의 procfs 읽기로 캐싱해
        # 자식마다 여러 번 따로 읽는 것보다 저렴하다(cmdline() 은 별도 파일이라
        # 캐싱 대상 아님, 그래도 나머지 호출들엔 효과 있음).
        with child.oneshot():
            ctype = _child_type(child)
            try:
                rss = child.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                rss = 0  # zombie 등 — 이미 회수된 메모리, 0으로 집계
        rss_children += rss
        entry = by_type.setdefault(ctype, [0, 0])
        entry[0] += 1
        entry[1] += rss

    breakdown = " ".join(
        f"{t}={cnt}(rss_mb={rss / _MB:.1f})"
        for t, (cnt, rss) in sorted(by_type.items(), key=lambda kv: -kv[1][1])
    )

    _mem_logger.info(
        f"worker={worker_id} rss_self_mb={rss_self / _MB:.1f} "
        f"rss_children_mb={rss_children / _MB:.1f} children={len(children)} | {breakdown}"
    )
