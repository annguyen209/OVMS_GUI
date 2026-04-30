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
from pathlib import Path
import httpx

from app.config import cfg

logger = logging.getLogger(__name__)

HEALTH_TIMEOUT = 5.0  # seconds per request


class ServerManager:
    """Manages the OVMS server and OpenAI-compatible proxy processes."""

    def __init__(self):
        self._ovms_proc:  subprocess.Popen | None = None
        self._proxy_proc: subprocess.Popen | None = None
        self._ovms_log_fh  = None
        self._proxy_log_fh = None

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
        msgs = []
        self._stop_proc(self._proxy_proc, "Proxy")
        self._proxy_proc = None
        if self._proxy_log_fh:
            try:
                self._proxy_log_fh.close()
            except Exception:
                pass
            self._proxy_log_fh = None
        msgs.append("Proxy stopped.")

        self._stop_proc(self._ovms_proc, "OVMS")
        self._ovms_proc = None
        if self._ovms_log_fh:
            try:
                self._ovms_log_fh.close()
            except Exception:
                pass
            self._ovms_log_fh = None
        msgs.append("OVMS stopped.")

        with self._lock:
            self._ovms_healthy  = False
            self._proxy_running = False

        return True, " ".join(msgs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_ovms_env(self) -> dict:
        import sys as _sys
        # Normalise all keys to uppercase — Windows env vars are case-insensitive
        # but Python dicts are not.  os.environ may store "Path" not "PATH", which
        # would make every subsequent env.get("PATH") return "".
        env = {k.upper(): v for k, v in os.environ.items()}

        # Source setupvars.bat to pick up OpenVINO paths and PYTHONHOME.
        setupvars = cfg.setupvars
        if not os.path.isfile(setupvars):
            logger.warning("setupvars.bat not found at %s – skipping", setupvars)
        else:
            try:
                result = subprocess.run(
                    ["cmd", "/c", f'"{setupvars}" && set'],
                    capture_output=True, text=True, timeout=30,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                for line in result.stdout.splitlines():
                    if "=" in line:
                        key, _, value = line.partition("=")
                        env[key.strip().upper()] = value.strip()
            except Exception as exc:
                logger.warning("Could not source setupvars.bat: %s", exc)

        # Set PYTHONHOME and PYTHONPATH explicitly for OVMS's embedded Python.
        # OVMS ships Python in <ovms>\python\; the stdlib .pyc files live in
        # <ovms>\python\python312\ (not Lib\ which only has site-packages).
        # PYTHONHOME sets sys.prefix; PYTHONPATH ensures the stdlib subdir is
        # on sys.path regardless of which python312.dll gets loaded.
        ovms_python_dir = Path(cfg.ovms_exe).parent / "python"
        ovms_stdlib_dir = ovms_python_dir / "python312"
        if ovms_python_dir.is_dir():
            env["PYTHONHOME"] = str(ovms_python_dir)
        if ovms_stdlib_dir.is_dir():
            env["PYTHONPATH"] = str(ovms_stdlib_dir)

        for _key in ("TCL_LIBRARY", "TK_LIBRARY"):
            env.pop(_key, None)

        # Guarantee OVMS directories are on PATH — mirrors what setupvars.bat does:
        #   PATH = OVMS_DIR ; PYTHONHOME ; PYTHONHOME\Scripts ; original PATH
        # We do this explicitly so that parsing setupvars.bat stdout is not the
        # single point of failure.
        ovms_dir        = str(Path(cfg.ovms_exe).parent)
        python_dir      = str(ovms_python_dir)
        python_scripts  = str(ovms_python_dir / "Scripts")
        prepend = os.pathsep.join(
            d for d in [ovms_dir, python_dir, python_scripts]
            if d and Path(d).exists()
        )
        current_path = env.get("PATH", "")
        env["PATH"] = prepend + os.pathsep + current_path
        logger.info("OVMS PATH prepend: %s", prepend)

        # Strip PyInstaller bundle dirs from PATH so OVMS loads its own DLLs.
        if getattr(_sys, "frozen", False):
            bundle_root = os.path.dirname(_sys.executable)
            internal_dir = os.path.join(bundle_root, "_internal")
            sep = os.pathsep
            drop = {bundle_root.lower(), internal_dir.lower()}
            parts = [p for p in env.get("PATH", "").split(sep)
                     if p.lower() not in drop]
            env["PATH"] = sep.join(parts)

        logger.info("OVMS env: PYTHONHOME=%s", env.get("PYTHONHOME", "(not set)"))

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
            # Ensure log and workspace directories exist
            Path(cfg.ovms_log).parent.mkdir(parents=True, exist_ok=True)
            cfg.ovms_workspace.mkdir(parents=True, exist_ok=True)
            # Create a minimal config.json if none exists so OVMS can start
            if not cfg.config_json.is_file():
                import json as _json
                cfg.config_json.write_text(
                    _json.dumps({"model_config_list": [], "mediapipe_config_list": []}, indent=2),
                    encoding="utf-8",
                )
                logger.info("Created empty config.json — activate a model to load one")
            gui_log = cfg.ovms_gui_log
            try:
                log_fh = open(gui_log, "a", encoding="utf-8")
            except PermissionError:
                import tempfile
                tf = tempfile.NamedTemporaryFile(
                    delete=False, suffix="-ovms.log", mode="a", encoding="utf-8")
                log_fh = tf
            cmd = [
                cfg.ovms_exe,
                "--config_path", str(cfg.config_json),
                "--port", "9000",
                "--rest_port", str(cfg.ovms_rest_port),
                "--log_level", "INFO",
            ]
            self._ovms_log_fh = log_fh
            proc = subprocess.Popen(
                cmd, stdout=log_fh, stderr=log_fh, env=env,
                creationflags=subprocess.CREATE_NO_WINDOW,
                cwd=str(Path(cfg.ovms_exe).parent),
            )
            with self._lock:
                self._ovms_proc = proc
            logger.info("OVMS process started (pid=%d)", proc.pid)
            # Watch for early exit and write the exit code to the log
            threading.Thread(
                target=self._watch_ovms_exit,
                args=(proc, gui_log),
                daemon=True,
            ).start()
            return True, f"OVMS started (pid={proc.pid})."
        except FileNotFoundError:
            msg = f"ovms.exe not found at {cfg.ovms_exe}"
            logger.error(msg)
            return False, msg
        except Exception as exc:
            logger.exception("Failed to start OVMS")
            return False, str(exc)

    def _watch_ovms_exit(self, proc: subprocess.Popen, log_path: str):
        """Write a diagnostic line to the log if OVMS exits within 10 seconds."""
        try:
            proc.wait(timeout=10)
            code = proc.returncode
            hex_code = f"0x{code & 0xFFFFFFFF:08X}" if code < 0 else hex(code)
            msg = f"\n[OpenVINO Manager] OVMS process exited early (code {code} / {hex_code}).\n"
            if code in (0xC0000135, -1073741515):
                msg += "[OpenVINO Manager] 0xC0000135 = DLL not found. Possible fix: install Visual C++ Redistributable (vc_redist.x64.exe) or ensure setupvars.bat ran correctly.\n"
            try:
                with open(log_path, "a", encoding="utf-8") as fh:
                    fh.write(msg)
            except Exception:
                pass
        except subprocess.TimeoutExpired:
            pass  # still running after 10 s — normal

    def _start_proxy(self) -> tuple[bool, str]:
        with self._lock:
            if self._proxy_proc and self._proxy_proc.poll() is None:
                return True, "Proxy already running."
            # Already healthy (started externally)
            if self._proxy_running:
                return True, "Proxy already running (external process)."
        try:
            Path(cfg.proxy_log).parent.mkdir(parents=True, exist_ok=True)
            # Deploy proxy script from bundle if it doesn't exist at the config path
            proxy_path = Path(cfg.proxy_script)
            if not proxy_path.is_file():
                import sys as _sys
                bundle_proxy = Path(getattr(_sys, "_MEIPASS", Path(__file__).parent.parent)) / "ovms-proxy.py"
                if bundle_proxy.is_file():
                    proxy_path.parent.mkdir(parents=True, exist_ok=True)
                    import shutil as _sh
                    _sh.copy2(bundle_proxy, proxy_path)
                    logger.info("Deployed proxy script to %s", proxy_path)
            gui_proxy_log = cfg.proxy_log.replace(
                "ovms-proxy.log", "ovms-proxy-gui.log"
            ) if "ovms-proxy.log" in cfg.proxy_log else cfg.proxy_log + ".gui"
            try:
                log_fh = open(gui_proxy_log, "a", encoding="utf-8")
            except PermissionError:
                import tempfile
                tf = tempfile.NamedTemporaryFile(
                    delete=False, suffix="-proxy.log", mode="a", encoding="utf-8")
                log_fh = tf

            self._proxy_log_fh = log_fh
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
        """
        Detect proxy regardless of whether it was started by the GUI or
        externally (e.g. start-ovms.bat). Always do a network check on
        the proxy port so external processes are visible.
        """
        alive = False

        # 1. Check our managed process first (fast path)
        with self._lock:
            proc = self._proxy_proc
        if proc and proc.poll() is not None:
            # Our process exited — clear the reference
            with self._lock:
                self._proxy_proc = None
            proc = None

        # 2. Network check — covers both managed and external processes
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(
                    f"http://localhost:{cfg.proxy_port}/v3/models"
                )
                alive = resp.status_code in (200, 404)
        except Exception:
            alive = False

        with self._lock:
            self._proxy_running = alive

    def shutdown(self):
        self._stop_polling.set()
        for fh in (self._ovms_log_fh, self._proxy_log_fh):
            if fh:
                try:
                    fh.close()
                except Exception:
                    pass
