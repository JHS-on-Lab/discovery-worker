"""
Chrome 영구 프로필 디렉터리의 캐시성 하위 폴더를 정리하는 유지보수 스크립트.

지우는 대상은 app/adapters/_profile_cleanup.py 의 허용 목록(allow-list)뿐이다
— 쿠키/로컬스토리지/IndexedDB 등 "돌아오는 사용자" 신호는 절대 건드리지 않는다.

사용법:
  python scripts/clean_chrome_profiles.py

동작:
  GOOGLE_CHROME_PROFILE_DIR/BAIDU_CHROME_PROFILE_DIR/TINHTE_CHROME_PROFILE_DIR
  아래 워커별(WORKER_ID) 하위 디렉터리를 전부 훑는다. 각 디렉터리는 flock 을
  시도해(app/adapters/_profile_lock) 그 워커가 지금 실제로 Chrome 을 띄우고
  있으면(락 실패) 건드리지 않고 건너뛴다 — 운영 중인 프로필과의 경쟁을 피한다.
  건너뛴 디렉터리는 다음 실행 때 다시 시도하면 된다.

정기 실행하려면 호스트 crontab에 등록(예: 매일 새벽 4시):
  0 4 * * * cd /path/to/discovery-worker && .venv/bin/python scripts/clean_chrome_profiles.py >> logs/profile-cleanup.log 2>&1
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import config
from app.adapters import _profile_lock
from app.adapters._profile_cleanup import clean_cache_dirs

_PROFILE_BASE_DIRS = (
    config.GOOGLE_CHROME_PROFILE_DIR,
    config.BAIDU_CHROME_PROFILE_DIR,
    config.TINHTE_CHROME_PROFILE_DIR,
)


def main() -> None:
    total_freed = 0
    for base_dir in _PROFILE_BASE_DIRS:
        if not base_dir:
            continue
        base = Path(base_dir)
        if not base.is_dir():
            continue
        for worker_dir in sorted(base.iterdir()):
            if not worker_dir.is_dir():
                continue
            try:
                lock_file = _profile_lock.acquire(str(worker_dir), worker_dir.name)
            except _profile_lock.ProfileLockError:
                print(f"[건너뜀] {worker_dir} — 다른 프로세스가 사용 중")
                continue
            try:
                freed = clean_cache_dirs(str(worker_dir))
                total_freed += freed
                print(f"[정리 완료] {worker_dir} — {freed / 1024 / 1024:.1f} MB 회수")
            finally:
                _profile_lock.release(lock_file)

    print(f"\n총 회수: {total_freed / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
