"""
server.py — OVMS and proxy process management.

Responsibilities:
- Start / stop OVMS (ovms.exe) and the proxy (ovms-proxy.py) as subprocesses.
- Track whether each process is alive.
- Poll the OVMS REST health endpoint to confirm the server is actually ready.
- Expose simple status properties consumed by the GUI.
"""

import subprocess
import threading
import logging
import os
import httpx

from app.config import cfg

logger = logging.getLogger(__name__)

HEALTH_TIMEOUT = 5.0  # seconds per request


class ServerManager:
    """Manages the OVMS server and OpenAI-compatible proxy processes."""

    def __init__(self):
        self._ovms_proc:  subprocess.Popen | None = None
        self._proxy_proc: subprocess.Popen | None = None

        # Thread-safe state
        self._lock = threading.Lock()
        self._ovms_healthy  = False
        self._proxy_running = False

        # Background health-poll thread
        self._poll_thread  = threading.Thread(target=self._poll_loop, daemon=True)
        self._stop_polling = threading.Event()
        self._poll_thread.start()

    # ------------------------------------------------------------------
    # Public properties (read from any thread)
    # ------------------------------------------------------------------

    @property
    def ovms_running(self) -> bool:
        with self._lock:
            return self._ovms_healthy

    @property
    def proxy_running(self) -> bool:
        with self._lock:
            return self._proxy_running

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def start_stack(self) -> tuple[bool, str]:
        """Start OVMS then the proxy.  Returns (success, message)."""
        ok, msg = self._start_ovms()
        if not ok:
            return False, msg

        ok2, msg2 = self._start_proxy()
        if not ok2:
            # OVMS started but proxy failed – still partial success
            return False, f"OVMS started but proxy failed: {msg2}"

        return True, "OVMS and proxy started successfully."

    def stop_stack(self) -> tuple[bool, str]:
        """Stop the proxy first, then OVMS.  Returns (success, message)."""
        msgs = []
        self._stop_proc(self._proxy_proc, "Proxy")
        self._proxy_proc = None
        msgs.append("Proxy stopped.")

        self._stop_proc(self._ovms_proc, "OVMS")
        self._ovms_proc = None
        msgs.append("OVMS stopped.")

        with self._lock:
            self._ovms_healthy  = False
            self._proxy_running = False

        return True, " ".join(msgs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_ovms_env(self) -> dict:
        env = os.environ.copy()
        setupvars = cfg.setupvars
        if not os.path.isfile(setupvars):
            logger.warning("setupvars.bat not found at %s – skipping", setupvars)
            return env
        try:
            result = subprocess.run(
                ["cmd", "/c", f'"{setupvars}" && set'],
                capture_output=True, text=True, timeout=30,
            )
            for line in result.stdout.splitlines():
                if "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip()
        except Exception as exc:
            logger.warning("Could not source setupvars.bat: %s", exc)
        return env

    def _start_ovms(self) -> tuple[bool, str]:
        with self._lock:
            if self._ovms_proc and self._ovms_proc.poll() is None:
                return True, "OVMS already running."
            # Already healthy (started externally via start-ovms.bat)
            if self._ovms_healthy:
                return True, "OVMS already running (external process)."
        try:
            env = self._build_ovms_env()
            # Use a GUI-specific log to avoid colliding with an external OVMS process
            gui_log = cfg.ovms_log.replace("ovms-server.log", "ovms-gui.log") \
                      if "ovms-server.log" in cfg.ovms_log else cfg.ovms_log + ".gui"
            try:
                log_fh = open(gui_log, "a", encoding="utf-8")
            except PermissionError:
                import tempfile
                log_fh = open(tempfile.mktemp(suffix="-ovms.log"), "w", encoding="utf-8")
            cmd = [
                cfg.ovms_exe,
                "--config_path", str(cfg.config_json),
                "--port", "9000",
                "--rest_port", str(cfg.ovms_rest_port),
                "--log_level", "INFO",
            ]
            proc = subprocess.Popen(
                cmd, stdout=log_fh, stderr=log_fh, env=env,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            with self._lock:
                self._ovms_proc = proc
            logger.info("OVMS process started (pid=%d)", proc.pid)
            return True, f"OVMS started (pid={proc.pid})."
        except FileNotFoundError:
            msg = f"ovms.exe not found at {cfg.ovms_exe}"
            logger.error(msg)
            return False, msg
        except Exception as exc:
            logger.exception("Failed to start OVMS")
            return False, str(exc)

    def _start_proxy(self) -> tuple[bool, str]:
        with self._lock:
            if self._proxy_proc and self._proxy_proc.poll() is None:
                return True, "Proxy already running."
            # Already healthy (started externally)
            if self._proxy_running:
                return True, "Proxy already running (external process)."
        try:
            # Use a GUI-specific log to avoid colliding with an external proxy
            gui_proxy_log = cfg.proxy_log.replace(
                "ovms-proxy.log", "ovms-proxy-gui.log"
            ) if "ovms-proxy.log" in cfg.proxy_log else cfg.proxy_log + ".gui"
            try:
                log_fh = open(gui_proxy_log, "a", encoding="utf-8")
            except PermissionError:
                import tempfile
                log_fh = open(tempfile.mktemp(suffix="-proxy.log"), "w", encoding="utf-8")

            proc = subprocess.Popen(
                [cfg.python_exe, cfg.proxy_script],
                stdout=log_fh, stderr=log_fh,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            with self._lock:
                self._proxy_proc = proc
            logger.info("Proxy process started (pid=%d)", proc.pid)
            return True, f"Proxy started (pid={proc.pid})."
        except FileNotFoundError:
            msg = f"Proxy script not found at {cfg.proxy_script}"
            logger.error(msg)
            return False, msg
        except Exception as exc:
            logger.exception("Failed to start proxy")
            return False, str(exc)

    @staticmethod
    def _stop_proc(proc: subprocess.Popen | None, name: str):
        if proc is None:
            return
        if proc.poll() is not None:
            logger.info("%s already exited (code=%s)", name, proc.returncode)
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            logger.info("%s stopped.", name)
        except Exception as exc:
            logger.warning("Error stopping %s: %s", name, exc)

    # ------------------------------------------------------------------
    # Background health polling
    # ------------------------------------------------------------------

    def _poll_loop(self):
        """Runs in a daemon thread.  Polls OVMS health every 3 seconds."""
        while not self._stop_polling.is_set():
            self._check_ovms_health()
            self._check_proxy_alive()
            self._stop_polling.wait(timeout=3)

    def _check_ovms_health(self):
        healthy = False
        try:
            with httpx.Client(timeout=HEALTH_TIMEOUT) as client:
                resp = client.get(cfg.health_endpoint)
                healthy = resp.status_code in (200, 404)
        except Exception:
            healthy = False
        with self._lock:
            self._ovms_healthy = healthy

    def _check_proxy_alive(self):
        alive = False
        with self._lock:
            proc = self._proxy_proc
        if proc and proc.poll() is None:
            try:
                with httpx.Client(timeout=2.0) as client:
                    resp = client.get(f"http://localhost:{cfg.proxy_port}/health")
                    alive = resp.status_code < 500
            except Exception:
                alive = True
        with self._lock:
            self._proxy_running = alive

    def shutdown(self):
        """Call on application exit to clean up background thread."""
        self._stop_polling.set()
