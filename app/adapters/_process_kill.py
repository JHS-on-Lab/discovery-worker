"""
Chrome/chromedriver 프로세스 강제 종료 헬퍼.

undetected_chromedriver.Chrome.quit() 은 브라우저 프로세스(browser_pid)에
SIGTERM 만 보내고 실제로 죽었는지 확인하지 않는다 — os.kill() 은 신호를
커널에 전달만 하고 즉시 리턴하며, 대상이 응답 안 해도 예외를 던지지 않는다.

이 정리를 호출하는 시점은 하필 driver.get() 이 멈춰서 타임아웃난 직후,
즉 브라우저가 SIGTERM 에 가장 응답 못 할 가능성이 높은 상태다. 그 결과
정리 안 된 프로세스(+renderer/GPU/network/crashpad 자식들)가 컨테이너
수명 동안 계속 쌓일 수 있다 (google_news/baidu_news 어댑터에서 관찰된
좀비 프로세스 증가의 원인).

이 헬퍼는 SIGTERM → 짧은 대기 → 생존 시 SIGKILL 로 확실히 종료시키고,
자식 프로세스까지 재귀적으로 정리한다.
"""

from __future__ import annotations

import logging

import psutil

_log = logging.getLogger(__name__)

# PID 재사용 레이스 컨디션 방지용 — 대상이 chrome 계열 프로세스인지 이름으로 한 번 확인한다.
_CHROME_NAME_MARKERS = ("chrome",)


def kill_process_tree(pid: int | None, timeout: float = 5.0) -> None:
    """pid 와 그 자식 프로세스 전체를 SIGTERM → (timeout 초 후) SIGKILL 로 종료한다.

    pid 가 None 이거나 이미 종료된 프로세스면 조용히 무시한다. 대상 프로세스 이름이
    chrome 계열이 아니면(PID 재사용으로 무관한 프로세스가 됐을 가능성) 건드리지 않는다.
    """
    if pid is None:
        return

    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return

    if not _looks_like_chrome(parent):
        return

    procs = [parent]
    try:
        procs += parent.children(recursive=True)
    except psutil.NoSuchProcess:
        pass

    for proc in procs:
        try:
            proc.terminate()
        except psutil.NoSuchProcess:
            pass

    _, alive = psutil.wait_procs(procs, timeout=timeout)

    for proc in alive:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            pass

    if alive:
        _log.warning(
            f"chrome process tree did not exit gracefully on SIGTERM, "
            f"force-killed {len(alive)} process(es) (root pid={pid})",
            extra={"component": "adapter"},
        )


def _looks_like_chrome(proc: psutil.Process) -> bool:
    try:
        name = (proc.name() or "").lower()
    except psutil.NoSuchProcess:
        return False
    return any(marker in name for marker in _CHROME_NAME_MARKERS)
