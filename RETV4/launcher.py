# launcher.py
from __future__ import annotations

import os
import sys
import socket
import time
import webbrowser
import subprocess
from pathlib import Path
from typing import Optional


# -----------------------------------------------------------------------------
# Resolve runtime base directory.
# Supports PyInstaller via sys._MEIPASS.
# -----------------------------------------------------------------------------
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)).resolve()

# Entry file: prefer RET_ENTRY; fallback to login.py / Home.py
ENTRY_NAME = (os.environ.get("RET_ENTRY", "login.py") or "login.py").strip()
CANDIDATES = [ENTRY_NAME, "login.py", "Home.py", "home.py"]


def find_entry_file(base: Path) -> Path:
    """Find the Streamlit entry file under base directory."""
    # Direct candidates
    for name in CANDIDATES:
        p = base / name
        if p.exists():
            return p

    # Last resort: search recursively
    for name in ("login.py", "Home.py", "home.py"):
        found = list(base.rglob(name))
        if found:
            return found[0]

    raise RuntimeError(f"Cannot find entry file (tried: {', '.join(CANDIDATES)}) under {base}")


ENTRY_FILE = find_entry_file(BASE)


# -----------------------------------------------------------------------------
# Networking helpers
# -----------------------------------------------------------------------------
def port_is_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """Return True if TCP port accepts a connection."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_port(host: str, port: int, timeout: float = 30.0) -> bool:
    """Wait until host:port is reachable."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_is_open(host, port, timeout=0.5):
            return True
        time.sleep(0.25)
    return False


def pick_free_port(host: str = "127.0.0.1") -> int:
    """Ask OS for an available ephemeral port and return it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def open_browser(url: str) -> None:
    """Open browser best-effort."""
    try:
        webbrowser.open(url)
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Process helpers
# -----------------------------------------------------------------------------
def build_streamlit_cmd(entry_file: Path, port: int) -> list[str]:
    """
    Build command to start streamlit using the same Python interpreter
    that launched this script (works in venv and PyInstaller embedded python).
    """
    return [
        sys.executable, "-m", "streamlit", "run", str(entry_file),
        "--server.headless", "true",
        "--server.port", str(port),
        "--server.fileWatcherType", "none",
        "--browser.gatherUsageStats", "false",
    ]


def popen_streamlit(cmd: list[str]) -> subprocess.Popen:
    """
    Start Streamlit:
      - Hide console window on Windows
      - Start as a new process group so we can terminate child processes too
    """
    creationflags = 0
    startupinfo = None

    if os.name == "nt":
        # Hide console window on Windows
        creationflags |= subprocess.CREATE_NO_WINDOW
        # New process group for easier termination
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        return subprocess.Popen(
            cmd,
            creationflags=creationflags,
            startupinfo=startupinfo,
            cwd=str(BASE),
        )

    # POSIX: start new process group for killpg termination
    return subprocess.Popen(
        cmd,
        cwd=str(BASE),
        start_new_session=True,  # new process group
    )


def terminate_process_tree(proc: subprocess.Popen, timeout: float = 5.0) -> None:
    """Terminate Streamlit process (and its children if possible)."""
    if proc.poll() is not None:
        return

    try:
        if os.name == "nt":
            # On Windows, best-effort terminate the process
            proc.terminate()
        else:
            # On POSIX, terminate the whole process group
            import signal
            os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        pass

    # Wait briefly, then force kill if needed
    try:
        proc.wait(timeout=timeout)
        return
    except Exception:
        pass

    try:
        if os.name == "nt":
            proc.kill()
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main() -> None:
    # Ensure we run in BASE so relative asset paths work
    os.chdir(str(BASE))

    # Allow user to configure port:
    # - If RET_PORT=0, we auto pick a free port.
    # - If specified port is busy, we also fall back to a free port.
    env_port = os.environ.get("RET_PORT", "8501").strip()
    try:
        requested_port = int(env_port)
    except Exception:
        requested_port = 8501

    if requested_port <= 0:
        port = pick_free_port()
    else:
        port = requested_port
        # If already open, we assume streamlit is already running there
        if port_is_open("127.0.0.1", port) or port_is_open("localhost", port):
            url = f"http://localhost:{port}"
            open_browser(url)
            return

        # If port is bound by something else but not accepting yet, try fallback:
        # (rare, but can happen)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
        except OSError:
            port = pick_free_port()

    url = f"http://localhost:{port}"

    # Build and launch Streamlit
    cmd = build_streamlit_cmd(ENTRY_FILE, port)
    proc = popen_streamlit(cmd)

    # Wait until server is reachable, then open browser
    if wait_for_port("127.0.0.1", port, timeout=30.0) or wait_for_port("localhost", port, timeout=30.0):
        open_browser(url)
    else:
        # Streamlit failed to start; terminate process
        terminate_process_tree(proc)
        return

    # Block until Streamlit exits; terminate cleanly on Ctrl+C
    try:
        proc.wait()
    except KeyboardInterrupt:
        terminate_process_tree(proc)


if __name__ == "__main__":
    main()
# -----------------------------------------------------------------------------