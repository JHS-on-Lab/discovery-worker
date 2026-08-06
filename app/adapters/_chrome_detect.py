"""
Chrome 바이너리 탐지 + Xvfb 가상 디스플레이 설정.

google_news.py/baidu_news.py 가 undetected-chromedriver 를 띄우기 전에 공통으로
쓰는 헬퍼.
"""

from __future__ import annotations

import logging
import os
import sys
import time

_log = logging.getLogger(__name__)

_LINUX_CHROME_BINARIES = (
    "google-chrome", "google-chrome-stable", "google-chrome-unstable",
    "chromium-browser", "chromium",
)
_LINUX_CHROME_PATHS = (
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/snap/bin/chromium",
)
_MAC_CHROME_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
)


def detect_chrome_binary() -> str | None:
    """Chrome 실행 파일의 절대 경로를 반환한다. 못 찾으면 None."""
    import shutil

    if sys.platform == "win32":
        import winreg
        keys = [
            (winreg.HKEY_CURRENT_USER,  r"Software\Google\Chrome\BLBeacon", "version"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome", "DisplayVersion"),
        ]
        for hive, subkey, val in keys:
            try:
                with winreg.OpenKey(hive, subkey) as k:
                    path, _ = winreg.QueryValueEx(k, "InstallLocation")
                    candidate = os.path.join(path, "chrome.exe")
                    if os.path.isfile(candidate):
                        return candidate
            except Exception:
                continue
        return shutil.which("chrome") or shutil.which("chromium")

    if sys.platform == "darwin":
        for path in _MAC_CHROME_PATHS:
            if os.path.isfile(path):
                return path
        return shutil.which("chrome") or shutil.which("chromium")

    for binary in _LINUX_CHROME_BINARIES:
        path = shutil.which(binary)
        if path:
            return path
    for path in _LINUX_CHROME_PATHS:
        if os.path.isfile(path):
            return path
    return None


def detect_chrome_major() -> int | None:
    """설치된 Chrome 의 major 버전 반환. 감지 실패 시 None (uc 자동 감지에 위임)."""
    import re
    import subprocess

    binary = detect_chrome_binary()
    if binary is None:
        return None

    if sys.platform == "win32":
        # Windows: 레지스트리에서 버전 읽기
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon") as k:
                version, _ = winreg.QueryValueEx(k, "version")
                m = re.match(r"(\d+)", version)
                return int(m.group(1)) if m else None
        except Exception:
            pass

    try:
        out = subprocess.check_output(
            [binary, "--version"],
            stderr=subprocess.DEVNULL, text=True,
        )
        m = re.search(r"(\d+)\.\d+\.\d+", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def ensure_xvfb() -> None:
    """Linux 서버에 디스플레이가 없으면 Xvfb 가상 디스플레이를 시작한다.

    Xvfb 는 리눅스 전용 도구 — Windows/macOS 는 실제 디스플레이가 있어 불필요
    (게다가 macOS 엔 Xvfb 바이너리 자체가 없어 그대로 두면 FileNotFoundError)."""
    if sys.platform != "linux":
        return
    if os.environ.get("DISPLAY"):
        return
    import subprocess
    display = ":99"
    subprocess.Popen(
        ["Xvfb", display, "-screen", "0", "1280x720x24"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.environ["DISPLAY"] = display
    time.sleep(0.5)
    _log.info("Xvfb 가상 디스플레이 시작 (DISPLAY=:99)", extra={"component": "adapter"})
