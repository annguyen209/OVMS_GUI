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

# Config file lives next to the project root
CONFIG_FILE = Path(__file__).parent.parent / "ovms-gui-config.json"

DEFAULTS: dict = {
    "models_dir":    r"C:\Users\annguyen209\models",
    "ovms_exe":      r"C:\Users\annguyen209\ovms\ovms.exe",
    "ovms_workspace": r"C:\Users\annguyen209\ovms-workspace",
    "setupvars":     r"C:\Users\annguyen209\ovms\setupvars.bat",
    "python_exe":    r"C:\Users\annguyen209\openvino-env\Scripts\python.exe",
    "proxy_script":  r"C:\Users\annguyen209\ovms-proxy.py",
    "ovms_log":      r"C:\Users\annguyen209\ovms-server.log",
    "proxy_log":     r"C:\Users\annguyen209\ovms-proxy.log",
    "ovms_rest_port": 8000,
    "proxy_port":    8001,
}


class AppConfig:
    """Thin wrapper around a JSON config file with typed property accessors."""

    def __init__(self):
        self._data: dict = dict(DEFAULTS)
        self._load()

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
    def health_endpoint(self) -> str:
        return f"http://localhost:{self.ovms_rest_port}/v3/models"


# Module-level singleton — import this everywhere
cfg = AppConfig()
