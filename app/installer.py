"""
installer.py — Component detection and auto-installation.

Checks for and installs:
  1. Python 3.12 venv + pip
  2. OpenVINO packages (openvino, openvino-genai)
  3. GUI / proxy dependencies (customtkinter, fastapi, uvicorn, httpx, etc.)
  4. OVMS binary (ovms.exe) from GitHub releases

All install functions accept:
  on_log(line: str)          — called for each log line (thread-safe via .after)
  on_done(ok: bool, msg: str)— called on completion
"""

import os
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path
from typing import Callable

from app.config import cfg

LogCb  = Callable[[str], None]
DoneCb = Callable[[bool, str], None]

# Managed venv — always at this fixed location regardless of cfg.python_exe
import os as _os
_VENV_DIR = Path(_os.environ.get("LOCALAPPDATA") or _os.path.expanduser("~")) / "OVMS Manager" / "env"
_VENV_PY  = _VENV_DIR / "Scripts" / "python.exe"

# ── OVMS release ──────────────────────────────────────────────────────────
OVMS_VERSION  = "v2026.1"
OVMS_ZIP_URL  = (
    "https://github.com/openvinotoolkit/model_server/releases/download/"
    f"{OVMS_VERSION}/ovms_windows_2026.1.0_python_on.zip"
)

def _ovms_install_dir() -> Path:
    """Computed at call time so it always reflects the current cfg.ovms_exe."""
    return Path(cfg.ovms_exe).parent

# Python 3.x candidates — prefer 3.12 for OVMS compatibility, accept any 3.8+.
_PY3_CANDIDATES = [
    "py -3.12",    # prefer 3.12 via Windows py launcher
    "py -V:3.12",
    "python3.12",
    "py -3",       # any Python 3 via launcher
    "python3",
    "python",
]

# Required pip packages per group
_OPENVINO_PKGS    = ["openvino", "openvino-genai"]
_PROXY_PKGS       = ["fastapi", "uvicorn", "httpx"]
_GUI_PKGS         = ["customtkinter", "pystray", "pillow",
                     "huggingface_hub", "jinja2"]


# ── Detection helpers ─────────────────────────────────────────────────────

def check_ovms() -> bool:
    """True if ovms.exe exists at the configured path."""
    return Path(cfg.ovms_exe).is_file()


def check_venv() -> bool:
    """True if the managed venv exists at its fixed location."""
    return _VENV_PY.is_file()


_IMPORT_MAP = {
    "pillow":          "PIL",
    "huggingface_hub": "huggingface_hub",
    "pystray":         "pystray",
}

def _pip_check(pkg: str) -> bool:
    """True if *pkg* is importable inside the configured venv."""
    import_name = _IMPORT_MAP.get(pkg.lower(), pkg.replace("-", "_"))
    try:
        result = subprocess.run(
            [cfg.python_exe, "-c", f"import {import_name}"],
            capture_output=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.returncode == 0
    except Exception:
        return False


def check_openvino() -> bool:
    return check_venv() and _pip_check("openvino")


def check_proxy_deps() -> bool:
    return check_venv() and all(_pip_check(p) for p in _PROXY_PKGS)


def check_gui_deps() -> bool:
    return check_venv() and all(_pip_check(p) for p in _GUI_PKGS)


def all_ok() -> bool:
    return (check_ovms() and check_venv() and
            check_openvino() and check_proxy_deps() and check_gui_deps())


def get_status() -> dict[str, bool]:
    return {
        "OVMS binary":         check_ovms(),
        "Python 3.12 venv":    check_venv(),
        "OpenVINO packages":   check_openvino(),
        "Proxy dependencies":  check_proxy_deps(),
        "GUI dependencies":    check_gui_deps(),
    }


# ── Find Python 3.x ───────────────────────────────────────────────────────

def _find_python3() -> str | None:
    """Return a working Python 3.x (3.8+) command string, or None."""
    for candidate in _PY3_CANDIDATES:
        parts = candidate.split()
        try:
            r = subprocess.run(
                parts + ["--version"],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if r.returncode == 0 and "3." in (r.stdout + r.stderr):
                return candidate
        except Exception:
            continue
    return None


# ── Installers ────────────────────────────────────────────────────────────

def _run_bg(target, args=()):
    t = threading.Thread(target=target, args=args, daemon=True)
    t.start()
    return t


def install_venv(on_log: LogCb, on_done: DoneCb):
    def _worker():
        on_log("Looking for Python 3.x...")
        py = _find_python3()
        if not py:
            on_done(False,
                    "Python 3.x not found. Install it from python.org or via 'uv python install 3.12'.")
            return

        venv_path = _VENV_DIR
        on_log(f"Creating venv at {venv_path} using {py}...")
        try:
            r = subprocess.run(
                py.split() + ["-m", "venv", str(venv_path)],
                capture_output=True, text=True, timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if r.returncode != 0:
                on_done(False, f"venv creation failed:\n{r.stderr}")
                return
            # Point cfg to the new venv so subsequent pip installs use it
            cfg.set("python_exe", str(_VENV_PY))
            on_log("Upgrading pip...")
            subprocess.run(
                [str(_VENV_PY), "-m", "pip", "install", "--upgrade", "pip"],
                capture_output=True, timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            on_done(True, "Python venv ready.")
        except Exception as exc:
            on_done(False, str(exc))

    _run_bg(_worker)


def _pip_install(pkgs: list[str], on_log: LogCb, on_done: DoneCb, label: str):
    def _worker():
        on_log(f"Installing {label}: {' '.join(pkgs)}")
        try:
            proc = subprocess.Popen(
                [cfg.python_exe, "-m", "pip", "install"] + pkgs,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in proc.stdout:
                on_log(line.rstrip())
            proc.wait(timeout=300)
            if proc.returncode == 0:
                on_done(True, f"{label} installed successfully.")
            else:
                on_done(False, f"{label} installation failed (code {proc.returncode}).")
        except Exception as exc:
            on_done(False, str(exc))

    _run_bg(_worker)


def install_openvino(on_log: LogCb, on_done: DoneCb):
    _pip_install(_OPENVINO_PKGS, on_log, on_done, "OpenVINO")


def install_proxy_deps(on_log: LogCb, on_done: DoneCb):
    _pip_install(_PROXY_PKGS, on_log, on_done, "Proxy dependencies")


def install_gui_deps(on_log: LogCb, on_done: DoneCb):
    _pip_install(_GUI_PKGS, on_log, on_done, "GUI dependencies")


def install_all_pip(on_log: LogCb, on_done: DoneCb):
    """Install all pip packages in one shot."""
    all_pkgs = _OPENVINO_PKGS + _PROXY_PKGS + _GUI_PKGS
    _pip_install(all_pkgs, on_log, on_done, "All packages")


def install_ovms(on_log: LogCb, on_done: DoneCb):
    def _worker():
        import urllib.request

        install_dir = _ovms_install_dir()
        zip_path = install_dir.parent / "ovms_download.zip"
        install_dir.parent.mkdir(parents=True, exist_ok=True)

        on_log(f"Downloading OVMS {OVMS_VERSION}...")
        on_log(f"  URL: {OVMS_ZIP_URL}")
        on_log(f"  Install dir: {install_dir}")

        try:
            def _reporthook(block, block_size, total):
                if total > 0:
                    pct = min(100, block * block_size * 100 // total)
                    on_log(f"  Download: {pct}%")

            urllib.request.urlretrieve(OVMS_ZIP_URL, zip_path, _reporthook)
            on_log("Download complete. Extracting...")

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(install_dir.parent)

            zip_path.unlink(missing_ok=True)

            if not Path(cfg.ovms_exe).is_file():
                on_done(False,
                        f"Extraction done but ovms.exe not found at {cfg.ovms_exe}. "
                        "Check the OVMS path in Settings.")
                return

            on_done(True, f"OVMS installed at {install_dir}.")
        except Exception as exc:
            on_done(False, f"OVMS install failed: {exc}")

    _run_bg(_worker)


def install_everything(on_log: LogCb, on_done: DoneCb):
    """
    Run the full install sequence:
    venv → packages → OVMS (if missing).
    Steps are chained so each waits for the previous.
    """
    steps: list[tuple[str, bool]] = [
        ("venv",  check_venv()),
        ("pkgs",  check_openvino() and check_proxy_deps() and check_gui_deps()),
        ("ovms",  check_ovms()),
    ]
    pending = [s for s, done in steps if not done]

    if not pending:
        on_done(True, "Everything is already installed.")
        return

    def _chain(remaining: list[str]):
        if not remaining:
            on_done(True, "Installation complete.")
            return
        step = remaining[0]
        rest = remaining[1:]

        def _next(ok: bool, msg: str):
            on_log(f"{'✓' if ok else '✗'}  {msg}")
            if not ok:
                on_done(False, msg)
            else:
                _chain(rest)

        if step == "venv":
            install_venv(on_log, _next)
        elif step == "pkgs":
            install_all_pip(on_log, _next)
        elif step == "ovms":
            install_ovms(on_log, _next)

    _chain(pending)


# ── Uninstallers ──────────────────────────────────────────────────────────

def _pip_uninstall(pkgs: list[str], on_log: LogCb, on_done: DoneCb, label: str):
    def _worker():
        on_log(f"Removing {label}: {' '.join(pkgs)}")
        try:
            proc = subprocess.Popen(
                [cfg.python_exe, "-m", "pip", "uninstall", "-y"] + pkgs,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in proc.stdout:
                on_log(line.rstrip())
            proc.wait(timeout=120)
            if proc.returncode == 0:
                on_done(True, f"{label} removed.")
            else:
                on_done(False, f"{label} removal failed (code {proc.returncode}).")
        except Exception as exc:
            on_done(False, str(exc))
    _run_bg(_worker)


def uninstall_venv(on_log: LogCb, on_done: DoneCb):
    def _worker():
        venv_path = _VENV_DIR
        on_log(f"Removing Python venv at {venv_path}...")
        try:
            if venv_path.exists():
                shutil.rmtree(venv_path)
                # Reset python_exe to the (now absent) default managed path
                cfg.set("python_exe", str(_VENV_PY))
                on_done(True, "Python venv removed.")
            else:
                on_done(False, "Venv directory not found.")
        except Exception as exc:
            on_done(False, f"Failed to remove venv: {exc}")
    _run_bg(_worker)


def uninstall_openvino(on_log: LogCb, on_done: DoneCb):
    _pip_uninstall(_OPENVINO_PKGS, on_log, on_done, "OpenVINO")


def uninstall_proxy_deps(on_log: LogCb, on_done: DoneCb):
    _pip_uninstall(_PROXY_PKGS + _GUI_PKGS, on_log, on_done, "Dependencies")


def uninstall_ovms(on_log: LogCb, on_done: DoneCb):
    def _worker():
        install_dir = _ovms_install_dir()
        on_log(f"Removing OVMS at {install_dir}...")
        try:
            if install_dir.exists():
                shutil.rmtree(install_dir)
                on_done(True, "OVMS binary removed.")
            else:
                on_done(False, "OVMS directory not found.")
        except Exception as exc:
            on_done(False, f"Failed to remove OVMS: {exc}")
    _run_bg(_worker)
