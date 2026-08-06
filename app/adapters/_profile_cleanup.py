"""Chrome 영구 프로필의 캐시성 하위 폴더만 정리한다.

쿠키/로컬스토리지/IndexedDB/Service Worker 등 "돌아오는 사용자"로 보이게
만드는 실제 사이트 상태는 절대 지우지 않는다 — 아래 허용 목록(allow-list)에
명시된 경로만 지운다. 목록에 없는 폴더는 Chrome이 새 버전에서 새로 만들어도
기본적으로 보존된다(허용 목록 방식 — 캐시인지 확인 안 된 폴더는 그냥
남겨두는 쪽으로 안전하게 실패한다).

허용 목록에 담긴 두 종류:
  - `Default/Cache`, `Default/Code Cache`, `Default/GPUCache` 등 — 순수
    브라우저 디스크 캐시. 원격 사이트는 이 데이터를 볼 수 없고, 지워도
    다음 방문 때 다시 받아질 뿐이라 "새 사용자"로 보이지 않는다.
  - `component_crx_cache`, `optimization_guide_model_store`,
    `Safe Browsing` 등 — Chrome 컴포넌트 업데이터가 받는 전역 참조 데이터.
    특정 사이트 방문 이력과 무관하다.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

_log = logging.getLogger(__name__)

_SAFE_TO_DELETE = (
    # 프로필 루트 — Chrome 컴포넌트 업데이터 / 전역 참조 데이터
    "component_crx_cache",
    "optimization_guide_model_store",
    "WasmTtsEngine",
    "Safe Browsing",
    "ActorSafetyLists",
    "CertificateRevocation",
    "PKIMetadata",
    "Crowd Deny",
    "SafetyTips",
    "Subresource Filter",
    "segmentation_platform",
    "OptimizationHints",
    "ZxcvbnData",
    "MEIPreload",
    "TrustTokenKeyCommitments",
    "GraphiteDawnCache",
    # Default/ 하위 — 순수 브라우저 디스크 캐시(사이트 상태 아님)
    "Default/Cache",
    "Default/Code Cache",
    "Default/GPUCache",
    "Default/DawnWebGPUCache",
    "Default/DawnGraphiteCache",
)


def clean_cache_dirs(user_data_dir: str) -> int:
    """user_data_dir 아래 허용 목록에 있는 캐시성 폴더만 지운다.
    반환값은 회수한 바이트 수(추정)."""
    freed = 0
    root = Path(user_data_dir)
    for rel in _SAFE_TO_DELETE:
        target = root / rel
        if not target.exists():
            continue
        try:
            freed += _dir_size(target)
            shutil.rmtree(target)
        except OSError as exc:
            _log.warning(
                f"프로필 캐시 정리 실패 target={target} err={exc}",
                extra={"component": "adapter"},
            )
    return freed


def _dir_size(path: Path) -> int:
    total = 0
    for f in path.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total
