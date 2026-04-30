"""
runner.py — Headless E2E test runner for OpenVINO Manager.

Usage:
    python tests/e2e/runner.py

Runs all 12 steps automatically. Prints pass/fail to terminal.
Exits 0 if all pass, 1 if any fail.
"""

import os
import sys
import time
import threading
from dataclasses import dataclass, field
from typing import Callable

# Force UTF-8 output on Windows so Unicode symbols print correctly
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ["OVMS_E2E_TEST"] = "1"

from app.test_harness import TestHarness, TestTimeout

# ANSI colours
_G = "\033[92m"
_R = "\033[91m"
_Y = "\033[93m"
_B = "\033[94m"
_D = "\033[2m"
_X = "\033[0m"


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
    if h.models.state("Phi-3.5-mini") not in ("Downloaded", "Active"):
        h.models.download("Phi-3.5-mini")
    h.models.wait_downloaded("Phi-3.5-mini", timeout=600)


def _cancel_download(h: TestHarness):
    h.tab("Models")
    if h.models.state("DeepSeek-R1-1.5B") in ("Downloaded", "Active"):
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
    assert h.chat.last_response(), "Expected partial response after stop"


def _settings_device(h: TestHarness):
    h.tab("Settings")
    original = h.settings.get_device() or "GPU"
    h.settings.set_device("CPU")
    assert h.settings.get_device() == "CPU", "Device not set to CPU"
    from app.config import cfg
    assert cfg.ovms_device == "CPU", f"Config not updated, got {cfg.ovms_device}"
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
# Headless runner
# ---------------------------------------------------------------------------

def _run(app, harness: TestHarness):
    results: dict[str, str] = {}
    total   = len(TESTS)
    passed  = 0
    failed  = 0
    skipped = 0

    print(f"\n{_B}OpenVINO Manager — E2E Tests{_X}  ({total} steps)\n")

    for step in TESTS:
        # Skip if dependency failed
        if any(results.get(dep) == "FAIL" for dep in step.depends_on):
            results[step.id] = "SKIP"
            skipped += 1
            print(f"  {_D}⊘  {step.label}  [skipped — dependency failed]{_X}")
            continue

        print(f"  {_Y}▶  {step.label}…{_X}", end="", flush=True)
        start = time.time()
        try:
            step.fn(harness)
            elapsed = time.time() - start
            results[step.id] = "PASS"
            passed += 1
            print(f"\r  {_G}✅ {step.label:<50}{_X}  {elapsed:.1f}s")
        except (TestTimeout, AssertionError, Exception) as exc:
            elapsed = time.time() - start
            results[step.id] = "FAIL"
            failed += 1
            print(f"\r  {_R}❌ {step.label:<50}{_X}  {elapsed:.1f}s")
            print(f"     {_R}{exc}{_X}")

    # Summary
    print()
    if failed == 0:
        print(f"{_G}All {passed} tests passed ✅{_X}\n")
    else:
        print(f"{_R}{failed} failed{_X} / {_G}{passed} passed{_X} / {_D}{skipped} skipped{_X}\n")

    # Quit app and return exit code
    app.after(0, app._quit)
    return 0 if failed == 0 else 1


def main():
    import tkinter.messagebox as _mb
    # Suppress all modal dialogs in headless mode:
    # - "Would you like to install missing components?" → No (runner handles installs)
    # - Any other yes/no dialogs → No by default
    _mb.askyesno   = lambda *a, **kw: False
    _mb.showinfo   = lambda *a, **kw: None
    _mb.showwarning = lambda *a, **kw: None
    _mb.showerror  = lambda *a, **kw: None

    from app.gui import App

    exit_code = [1]

    app = App()
    app.withdraw()   # hide window — headless mode
    harness: TestHarness = app._test_harness

    def _start():
        def _worker():
            code = _run(app, harness)
            exit_code[0] = code
        threading.Thread(target=_worker, daemon=True).start()

    app.after(500, _start)   # short delay so app fully initialises
    app.mainloop()

    sys.exit(exit_code[0])


if __name__ == "__main__":
    main()
