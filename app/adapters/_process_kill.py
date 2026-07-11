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


def kill_process_tree(
    pid: int | None,
    timeout: float = 5.0,
    expected_user_data_dir: str | None = None,
) -> None:
    """pid 와 그 자식 프로세스 전체를 SIGTERM → (timeout 초 후) SIGKILL 로 종료한다.

    pid 가 None 이거나 이미 종료된 프로세스면 조용히 무시한다.

    PID 재사용 레이스 컨디션 방지: 이름이 chrome 계열인지만 보면, 같은 호스트에서
    여러 Chrome 기반 워커가 동시에 뜬 상태일 때 원래 pid가 이미 죽고 그 번호가
    "다른 워커의 정상 Chrome"으로 재사용됐을 가능성을 걸러내지 못한다.
    expected_user_data_dir 를 넘기면(영구 프로필 사용 시) cmdline 의
    --user-data-dir 인자가 정확히 그 경로를 가리키는지까지 확인해 훨씬 정밀하게
    판별한다. 넘기지 않으면(임시 프로필 등, 경로를 특정할 수 없는 경우) 이름 확인만
    수행한다 — 완벽하진 않지만 아무것도 안 하는 것보단 낫다.
    """
    if pid is None:
        return

    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return

    if not _looks_like_chrome(parent, expected_user_data_dir):
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


def _looks_like_chrome(proc: psutil.Process, expected_user_data_dir: str | None) -> bool:
    try:
        name = (proc.name() or "").lower()
    except psutil.NoSuchProcess:
        return False
    if not any(marker in name for marker in _CHROME_NAME_MARKERS):
        return False

    if expected_user_data_dir is None:
        return True

    try:
        cmdline = proc.cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        # cmdline 을 못 읽으면 이름 확인만으로 판단(플랫폼/권한 제약) — 완전 무시하지 않는다.
        return True
    return any(expected_user_data_dir in arg for arg in cmdline)
