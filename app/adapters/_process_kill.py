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

그런데 이 방식도 놓치는 좀비가 있다: Chrome은 crash reporting용
chrome_crashpad 핸들러 등 일부 헬퍼 프로세스를 브라우저 프로세스에서
의도적으로 detach(더블포크)시켜, 브라우저가 죽어도 크래시 리포트를 남길
수 있게 한다. 그 결과 이 헬퍼들은 kill_process_tree() 가 추적하는
browser_pid 의 자손 트리에서 이미 벗어나(형제 관계가 되어) 컨테이너의
PID 1(이 파이썬 프로세스)에 바로 reparent 된다 — kill_process_tree() 는
특정 browser_pid 트리만 훑으므로 이런 detach 프로세스는 애초에 순회
대상이 아니라서 SIGTERM/SIGKILL 도, reap 도 못 받는다(실측: PPID 가 전부
이 파이썬 프로세스인 chrome_crashpad/chrome 좀비가 세션마다 누적).

reap_zombie_children() 은 특정 PID를 추적하지 않고 "내 자식 중 이미 끝난
프로세스는 누구든 다 거둔다"는 표준 subreaper 패턴으로 이 detach 케이스까지
포괄한다. 어댑터별 정리 로직과 무관하게 디스패처의 heartbeat 주기에서
호출한다.
"""

from __future__ import annotations

import logging
import os

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


def reap_zombie_children() -> int:
    """이미 종료됐지만 부모가 아직 wait() 하지 않은 자식 프로세스를 전부 거둔다.

    특정 PID를 추적하는 kill_process_tree() 와 달리, "내 자식 중 끝난 놈은
    누구든 다 거둔다"는 표준 subreaper 패턴이다. Chrome 이 detach 시키는
    chrome_crashpad 등 kill_process_tree() 의 추적 대상에서 벗어난 프로세스도
    이 파이썬 프로세스의 자식인 이상 여기서 걸린다.

    os.waitpid(-1, WNOHANG) 은 이미 종료된(zombie) 자식만 즉시 거두고,
    아직 살아있는 자식엔 영향을 주지 않는다 — 실행 중인 프로세스를
    실수로 건드릴 위험이 없다. Windows 에는 없는 API 이므로 그 경우
    아무 것도 하지 않는다.
    반환: 이번 호출에서 reap 한 프로세스 수.
    """
    reaped = 0
    if not hasattr(os, "waitpid"):
        return reaped
    while True:
        try:
            pid, _status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break  # 대기 중인 자식이 하나도 없음
        if pid == 0:
            break  # 아직 안 끝난 자식은 있지만, 끝난 애는 더 없음
        reaped += 1
    return reaped
