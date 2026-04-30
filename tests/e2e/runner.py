"""
runner.py — E2E test runner for OpenVINO Manager.

Usage:
    set OVMS_E2E_TEST=1 && python tests/e2e/runner.py   (Windows)
    OVMS_E2E_TEST=1 python tests/e2e/runner.py           (Unix)
"""

import os
import sys
import time
import threading
from dataclasses import dataclass, field
from typing import Callable

# Ensure project root is on path
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ["OVMS_E2E_TEST"] = "1"

from tests.e2e.panel import (
    TestPanel, PENDING, RUNNING, PASSED, FAILED, SKIPPED,
)
from app.test_harness import TestHarness, TestTimeout


# ---------------------------------------------------------------------------
# Step dataclass
# ---------------------------------------------------------------------------

@dataclass
class Step:
    id:         str
    label:      str
    fn:         Callable
    depends_on: list = field(default_factory=list)
    timeout:    int  = 60
    desc:       str  = ""


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------

def _fresh_state(h: TestHarness):
    h.tab("Dashboard")
    assert h.dashboard.ovms_status() == "Stopped", \
        f"Expected OVMS Stopped on launch, got {h.dashboard.ovms_status()}"
    assert h.dashboard.proxy_status() == "Stopped", \
        f"Expected Proxy Stopped on launch, got {h.dashboard.proxy_status()}"


def _install_all(h: TestHarness):
    h.tab("Setup")
    h.setup.install_all()
    h.setup.wait_all_ok(timeout=300)


def _remove_venv(h: TestHarness):
    h.tab("Setup")
    h.setup.remove("Python 3.x venv")
    h.wait(
        lambda: "Not found" in h.setup.status("Python 3.x venv"),
        timeout=30, label="venv removed",
    )


def _reinstall_venv(h: TestHarness):
    h.tab("Setup")
    h.setup.install("Python 3.x venv")
    h.wait(
        lambda: "Installed" in h.setup.status("Python 3.x venv"),
        timeout=120, label="venv reinstalled",
    )


def _download_model(h: TestHarness):
    h.tab("Models")
    state = h.models.state("Phi-3.5-mini")
    if state not in ("Downloaded", "Active"):
        h.models.download("Phi-3.5-mini")
    h.models.wait_downloaded("Phi-3.5-mini", timeout=600)


def _cancel_download(h: TestHarness):
    h.tab("Models")
    state = h.models.state("DeepSeek-R1-1.5B")
    if state in ("Downloaded", "Active"):
        return  # already downloaded — skip cancel test
    h.models.download("DeepSeek-R1-1.5B")
    h.wait(
        lambda: "Downloading" in h.models.state("DeepSeek-R1-1.5B"),
        timeout=30, label="DeepSeek download started",
    )
    time.sleep(3)
    h.models.cancel("DeepSeek-R1-1.5B")
    h.wait(
        lambda: "Downloading" not in h.models.state("DeepSeek-R1-1.5B"),
        timeout=30, label="DeepSeek download cancelled",
    )


def _activate_model(h: TestHarness):
    h.tab("Models")
    if h.models.state("Phi-3.5-mini") != "Active":
        h.models.activate("Phi-3.5-mini")
    h.models.wait_active("Phi-3.5-mini", timeout=90)


def _verify_stack(h: TestHarness):
    h.tab("Dashboard")
    if h.dashboard.ovms_status() == "Stopped":
        h.dashboard.start_stack()
    h.dashboard.wait_running(timeout=60)
    assert h.dashboard.ovms_status()  == "Running", "OVMS not Running"
    assert h.dashboard.proxy_status() == "Running", "Proxy not Running"


def _chat_send(h: TestHarness):
    h.tab("Chat")
    h.chat.clear()
    h.chat.send("Reply with exactly: hello")
    h.chat.wait_response(timeout=120)
    resp = h.chat.last_response()
    assert resp and not resp.startswith("[Error"), \
        f"Expected non-empty response, got: {resp[:80]!r}"


def _chat_stop(h: TestHarness):
    h.tab("Chat")
    h.chat.clear()
    h.chat.send("Write a very long essay about the history of computing, at least 2000 words")
    h.wait(lambda: h._app._chat_tab._streaming, timeout=15, label="streaming started")
    time.sleep(2)
    h.chat.stop()
    h.wait(lambda: not h._app._chat_tab._streaming, timeout=15, label="streaming stopped")
    resp = h.chat.last_response()
    assert resp, "Expected partial response content after stop"


def _settings_device(h: TestHarness):
    h.tab("Settings")
    original = h.settings.get_device() or "GPU"
    h.settings.set_device("CPU")
    assert h.settings.get_device() == "CPU", "Device not set to CPU"
    from app.config import cfg
    assert cfg.ovms_device == "CPU", f"Config not updated to CPU, got {cfg.ovms_device}"
    h.settings.set_device(original)
    assert h.settings.get_device() == original


def _stop_stack(h: TestHarness):
    h.tab("Dashboard")
    if h.dashboard.ovms_status() == "Running" or h.dashboard.proxy_status() == "Running":
        h.dashboard.stop_stack()
    h.dashboard.wait_stopped(timeout=30)
    assert h.dashboard.ovms_status()  == "Stopped", "OVMS still running"
    assert h.dashboard.proxy_status() == "Stopped", "Proxy still running"


# ---------------------------------------------------------------------------
# Test registry
# ---------------------------------------------------------------------------

TESTS: list[Step] = [
    Step("fresh_state",     "Fresh state check",                  _fresh_state,     timeout=10),
    Step("install_all",     "Install All components",              _install_all,     timeout=300),
    Step("remove_venv",     "Remove Python venv",                  _remove_venv,     depends_on=["install_all"], timeout=30),
    Step("reinstall_venv",  "Reinstall Python venv",               _reinstall_venv,  depends_on=["remove_venv"], timeout=120),
    Step("download_model",  "Download Phi-3.5-mini (~2 GB)",       _download_model,  depends_on=["install_all"], timeout=600),
    Step("cancel_download", "Cancel download (DeepSeek-R1-1.5B)",  _cancel_download, depends_on=["install_all"], timeout=60),
    Step("activate_model",  "Activate Phi-3.5-mini",               _activate_model,  depends_on=["download_model"], timeout=90),
    Step("verify_stack",    "Dashboard: verify stack running",     _verify_stack,    depends_on=["activate_model"], timeout=60),
    Step("chat_send",       "Chat: send message",                  _chat_send,       depends_on=["verify_stack"], timeout=120),
    Step("chat_stop",       "Chat: stop streaming",                _chat_stop,       depends_on=["verify_stack"], timeout=30),
    Step("settings_device", "Settings: change device",             _settings_device, timeout=10),
    Step("stop_stack",      "Stop stack",                          _stop_stack,      depends_on=["verify_stack"], timeout=30),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class Runner:
    def __init__(self, app, panel: TestPanel, harness: TestHarness):
        self._app     = app
        self._panel   = panel
        self._harness = harness
        self._results: dict[str, str] = {}
        self._stopped = False
        self._done    = 0

    def start(self):
        self._results = {}
        self._stopped = False
        self._done    = 0
        threading.Thread(target=self._run_all, daemon=True, name="e2e-runner").start()

    def stop(self):
        self._stopped = True

    def _run_all(self):
        for step in TESTS:
            if self._stopped:
                break
            self._run_step(step)

        passed  = sum(1 for v in self._results.values() if v == PASSED)
        failed  = sum(1 for v in self._results.values() if v == FAILED)
        skipped = sum(1 for v in self._results.values() if v == SKIPPED)
        self._app.after(0, lambda: self._panel.finish(passed, failed, skipped))

    def _run_step(self, step: Step):
        # Skip if any dependency failed
        if any(self._results.get(dep) == FAILED for dep in step.depends_on):
            self._results[step.id] = SKIPPED
            self._app.after(0, lambda s=step: self._panel.mark(s.id, SKIPPED))
            self._done += 1
            self._refresh_counters()
            return

        self._app.after(0, lambda s=step: self._panel.mark(s.id, RUNNING))
        start = time.time()

        try:
            step.fn(self._harness)
            elapsed = time.time() - start
            self._results[step.id] = PASSED
            self._app.after(0, lambda s=step, e=elapsed:
                            self._panel.mark(s.id, PASSED, elapsed=e))
        except (TestTimeout, AssertionError, Exception) as exc:
            elapsed = time.time() - start
            self._results[step.id] = FAILED
            err = str(exc)
            self._app.after(0, lambda s=step, e=elapsed, er=err:
                            self._panel.mark(s.id, FAILED, elapsed=e, error=er))

        self._done += 1
        self._refresh_counters()

    def _refresh_counters(self):
        passed  = sum(1 for v in self._results.values() if v == PASSED)
        failed  = sum(1 for v in self._results.values() if v == FAILED)
        done    = self._done
        total   = len(TESTS)
        self._app.after(0, lambda: self._panel.update_counters(done, total, passed, failed))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    from app.gui import App
    app = App()

    harness: TestHarness = app._test_harness
    panel   = TestPanel(app, TESTS)
    runner  = Runner(app, panel, harness)

    panel.set_callbacks(on_run=runner.start, on_stop=runner.stop)
    app.mainloop()


if __name__ == "__main__":
    main()
