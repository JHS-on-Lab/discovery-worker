"""
Chrome 프로필 디렉터리 잠금 — flock 기반.

WORKER_ID 가 실수로 중복되면(같은 이름의 컨테이너 두 개, docker-compose 설정 실수,
run.sh 를 거치지 않은 수동 실행 등) 같은 user_data_dir 로 Chrome 을 동시에 띄우게
된다. 이 경우 증상이 "driver.get() 이 응답 없이 멈춘다"로만 나타나서, 예전에
고쳤던 page-load 무한대기 버그와 겉보기엔 구분이 안 돼 원인 파악이 오래 걸린다.

PID 를 텍스트 파일에 적어 비교하는 방식(이전 구현)은:
  - "확인 → 기록" 두 단계 사이에 두 프로세스가 동시에 통과할 수 있는 TOCTOU race가 있고,
  - 죽은 프로세스의 PID 가 다른 무관한 프로세스에 재사용되면 오탐/누락 가능성이 있다.

대신 커널이 원자적으로 보장하는 flock(LOCK_EX | LOCK_NB) 을 쓴다:
  - 잠금 시도 자체가 원자적이라 race window 가 없다 — 두 프로세스가 동시에 시도해도
    반드시 하나만 성공한다.
  - 프로세스가 어떻게 죽든(정상 종료, 크래시, SIGKILL, OOM-kill) 커널이 그 프로세스의
    파일 디스크립터를 정리하는 즉시 락도 자동으로 풀린다 — "죽은 프로세스의 stale
    lock" 이라는 개념 자체가 없어진다. 어떤 경로로 실행되든(run.sh, 수동 실행,
    docker-compose 등) 실제로 충돌이 있으면 반드시 한쪽만 통과한다.

이 보장은 로컬 디스크(같은 호스트) 기준이다. 여러 서버가 같은 프로필 디렉터리를
NFS 등으로 공유 마운트하는 구성이라면 NFS 구현체/버전에 따라 flock 신뢰도가 달라질
수 있다(이 프로젝트의 run.sh 는 호스트 로컬 경로를 쓰므로 해당 없음).

fcntl 은 POSIX 전용이라 Windows(로컬 개발 환경)에서는 잠금을 건너뛴다 — 프로덕션은
Linux 컨테이너에서만 돈다.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import IO

_log = logging.getLogger(__name__)

_LOCK_FILENAME = ".worker.lock"


class ProfileLockError(RuntimeError):
    """다른 살아있는 프로세스가 이미 이 프로필 디렉터리를 사용 중일 때."""


def acquire(profile_dir: str, worker_id: str) -> IO | None:
    """profile_dir 에 배타적 락을 건다.

    이미 다른 프로세스가 쥐고 있으면 즉시 ProfileLockError. 반환된 파일 객체를
    어댑터가 살아있는 동안 계속 들고 있어야 락이 유지된다 — release() 로 명시적으로
    닫거나, 프로세스가 어떻게 죽든 커널이 자동으로 풀어준다.

    Windows 에서는 fcntl 이 없어 잠금을 건너뛰고 None 을 반환한다(로컬 개발 전용,
    프로덕션은 Linux 컨테이너).
    """
    if sys.platform == "win32":
        return None

    import fcntl

    lock_path = Path(profile_dir) / _LOCK_FILENAME
    f = open(lock_path, "w")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise ProfileLockError(
            f"Chrome 프로필 디렉터리가 이미 다른 프로세스에서 사용 중입니다: "
            f"{profile_dir} (WORKER_ID='{worker_id}'). "
            f"동일한 WORKER_ID로 여러 프로세스/컨테이너가 동시에 떠 있지 않은지 확인하세요."
        ) from None

    f.write(f"pid={_current_pid()}\n")
    f.flush()
    return f


def release(lock_file: IO | None) -> None:
    if lock_file is None:
        return
    if sys.platform != "win32":
        import fcntl
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
    try:
        lock_file.close()
    except OSError:
        pass


def _current_pid() -> int:
    import os
    return os.getpid()
