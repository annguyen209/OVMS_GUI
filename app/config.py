"""
config.py — Persistent JSON-backed application settings.

All path/port constants previously scattered across modules are centralised here.
The singleton `cfg` is imported by other modules and read at call-time, so
changes made in the Settings tab take effect immediately without restart.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

import os as _os
import shutil as _shutil
import sys as _sys
import subprocess as _sp

_appdata = _os.environ.get("LOCALAPPDATA") or _os.path.expanduser("~")

# All app data lives under %LOCALAPPDATA%\OVMS Manager\ — no username hardcoded.
_base = Path(_appdata) / "OVMS Manager"

CONFIG_FILE = _base / "config.json"
CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)


def _detect_python() -> str:
    """
    Find the best available Python 3.x executable using standard system
    discovery — no hardcoded paths.

    Priority:
      1. System Python on PATH that has the required packages already
      2. Python found via the Windows 'py' launcher (py -3)
      3. Managed venv under the app base dir (created by Setup tab)
    """
    import shutil, subprocess, sys

    # When running as a PyInstaller bundle, sys.executable is the app exe —
    # don't use it; look for an external Python instead.
    if not getattr(sys, "frozen", False) and sys.executable:
        return sys.executable  # dev mode: use the current interpreter

    # Try shutil.which first (respects PATH, works on any OS)
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            try:
                r = subprocess.run(
                    [found, "--version"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if r.returncode == 0 and "3." in (r.stdout + r.stderr):
                    return found
            except Exception:
                pass

    # Windows py launcher — handles side-by-side installs cleanly
    py = shutil.which("py")
    if py:
        try:
            r = subprocess.run(
                [py, "-3", "--version"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if r.returncode == 0:
                # Resolve to the actual interpreter path
                r2 = subprocess.run(
                    [py, "-3", "-c", "import sys; print(sys.executable)"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if r2.returncode == 0:
                    return r2.stdout.strip()
        except Exception:
            pass

    # Fall back to the managed venv (user installs via Setup tab)
    return str(_base / "env" / "Scripts" / "python.exe")


def _detect_ovms() -> str:
    """
    Find ovms.exe — checks in priority order:
      1. App-managed path (%LOCALAPPDATA%\OVMS Manager\ovms\)
      2. ovms.exe on system PATH  (user added it globally)
    Falls back to the managed path so Setup tab can install it there.
    """
    managed = _base / "ovms" / "ovms.exe"
    if managed.is_file():
        return str(managed)

    import shutil as _sh
    found = _sh.which("ovms") or _sh.which("ovms.exe")
    if found:
        return found

    return str(managed)  # fallback — Setup tab will install here


DEFAULTS: dict = {
    "models_dir":     str(_base / "models"),
    "ovms_exe":       _detect_ovms(),
    "ovms_workspace": str(_base / "workspace"),
    "setupvars":      str(Path(_detect_ovms()).parent / "setupvars.bat"),
    "python_exe":     _detect_python(),
    "proxy_script":   str(_base / "ovms-proxy.py"),
    "ovms_log":       str(_base / "logs" / "ovms-server.log"),
    "proxy_log":      str(_base / "logs" / "ovms-proxy.log"),
    "ovms_rest_port": 8000,
    "proxy_port":     8001,
    "auto_start_stack": False,
    "ovms_device":      "GPU",
}


class AppConfig:
    """Thin wrapper around a JSON config file with typed property accessors."""

    def __init__(self):
        self._data: dict = dict(DEFAULTS)
        self._load()
        self._heal_paths()

    def _heal_paths(self):
        """
        Re-detect python_exe if the saved path no longer works, and reset
        ovms_exe to the default managed location if the saved path is missing.
        Keeps the config valid without requiring the user to open Settings.
        """
        changed = False

        # Re-detect Python if the saved exe doesn't exist
        saved_py = self._data.get("python_exe", "")
        if not Path(saved_py).is_file():
            detected = _detect_python()
            if detected != saved_py:
                logger.info("python_exe '%s' not found — updated to '%s'", saved_py, detected)
                self._data["python_exe"] = detected
                changed = True

        # Re-detect OVMS if the saved path no longer exists
        saved_ovms = self._data.get("ovms_exe", "")
        if not Path(saved_ovms).is_file():
            detected_ovms = _detect_ovms()
            if detected_ovms != saved_ovms:
                logger.info("ovms_exe '%s' not found — updated to '%s'", saved_ovms, detected_ovms)
                self._data["ovms_exe"] = detected_ovms
                self._data["setupvars"] = str(Path(detected_ovms).parent / "setupvars.bat")
                changed = True

        if changed:
            self.save()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        if CONFIG_FILE.is_file():
            try:
                with CONFIG_FILE.open(encoding="utf-8") as fh:
                    saved = json.load(fh)
                self._data.update(saved)
                logger.debug("Config loaded from %s", CONFIG_FILE)
            except Exception as exc:
                logger.warning("Could not load config: %s — using defaults", exc)

    def save(self):
        try:
            with CONFIG_FILE.open("w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
            logger.info("Config saved to %s", CONFIG_FILE)
        except Exception as exc:
            logger.error("Could not save config: %s", exc)

    # ------------------------------------------------------------------
    # Generic get / set
    # ------------------------------------------------------------------

    def get(self, key: str, fallback=None):
        return self._data.get(key, DEFAULTS.get(key, fallback))

    def set(self, key: str, value):
        self._data[key] = value
        self.save()

    def update(self, mapping: dict):
        self._data.update(mapping)
        self.save()

    # ------------------------------------------------------------------
    # Typed properties (read-only convenience accessors)
    # ------------------------------------------------------------------

    @property
    def models_dir(self) -> Path:
        return Path(self._data["models_dir"])

    @property
    def ovms_exe(self) -> str:
        return self._data["ovms_exe"]

    @property
    def ovms_workspace(self) -> Path:
        return Path(self._data["ovms_workspace"])

    @property
    def config_json(self) -> Path:
        return self.ovms_workspace / "config.json"

    @property
    def graph_pbtxt(self) -> Path:
        return self.ovms_workspace / "graph.pbtxt"

    @property
    def setupvars(self) -> str:
        return self._data["setupvars"]

    @property
    def python_exe(self) -> str:
        return self._data["python_exe"]

    @property
    def proxy_script(self) -> str:
        return self._data["proxy_script"]

    @property
    def ovms_log(self) -> str:
        return self._data["ovms_log"]

    @property
    def proxy_log(self) -> str:
        return self._data["proxy_log"]

    @property
    def ovms_rest_port(self) -> int:
        return int(self._data["ovms_rest_port"])

    @property
    def proxy_port(self) -> int:
        return int(self._data["proxy_port"])

    @property
    def ovms_device(self) -> str:
        return self._data.get("ovms_device", "GPU")

    @property
    def ovms_gui_log(self) -> str:
        """Path of the log file the GUI-launched OVMS process writes to."""
        log = self.ovms_log
        if "ovms-server.log" in log:
            return log.replace("ovms-server.log", "ovms-gui.log")
        return log + ".gui"

    @property
    def health_endpoint(self) -> str:
        return f"http://localhost:{self.ovms_rest_port}/v3/models"


# Module-level singleton — import this everywhere
cfg = AppConfig()
