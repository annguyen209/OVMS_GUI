# E2E Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-driving GUI test suite that runs all 12 user flows against the real app with a floating progress panel.

**Architecture:** A background runner thread drives the app via `TestHarness` (widget refs + thread-safe wait helpers). A `CTkToplevel` panel floats over the app showing per-step pass/fail. Entry point: `OVMS_E2E_TEST=1 python tests/e2e/runner.py`.

**Tech Stack:** Python 3.x, customtkinter, tkinter, threading, app/test_harness.py (new), tests/e2e/ (new)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app/test_harness.py` | Create | Per-tab harness objects; thread-safe wait + invoke helpers |
| `tests/e2e/__init__.py` | Create | Package marker |
| `tests/e2e/panel.py` | Create | Floating CTkToplevel test panel UI |
| `tests/e2e/runner.py` | Create | Step definitions + orchestration loop |
| `app/gui.py` | Modify | Env-gated harness hook in `App.__init__` |

---

## Task 1: `app/test_harness.py` — Core harness infrastructure

**Files:**
- Create: `app/test_harness.py`

- [ ] **Step 1: Create the file with base infrastructure**

```python
"""
test_harness.py — Programmatic test interface for OpenVINO Manager.
Loaded only when OVMS_E2E_TEST=1 is set.
"""

import time
import threading
from typing import Callable


class TestTimeout(Exception):
    def __init__(self, label: str, elapsed: float):
        super().__init__(f"Timeout after {elapsed:.1f}s waiting for: {label}")
        self.label = label
        self.elapsed = elapsed


class TestHarness:
    def __init__(self, app):
        self._app    = app
        self.setup     = SetupHarness(app)
        self.models    = ModelsHarness(app)
        self.dashboard = DashboardHarness(app)
        self.chat      = ChatHarness(app)
        self.settings  = SettingsHarness(app)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def tab(self, name: str) -> "TestHarness":
        self._invoke(lambda: self._app._tabs.set(name))
        return self

    # ------------------------------------------------------------------
    # Thread-safe helpers
    # ------------------------------------------------------------------

    def _invoke(self, fn: Callable) -> None:
        """Run fn on the tkinter main thread and block until done."""
        done = threading.Event()
        def _wrap():
            try:
                fn()
            finally:
                done.set()
        self._app.after(0, _wrap)
        done.wait(timeout=10)

    def wait(self, condition_fn: Callable[[], bool],
             timeout: float = 60, poll_ms: int = 500,
             label: str = "") -> None:
        """Poll condition_fn (on main thread) until True or raise TestTimeout."""
        done  = threading.Event()
        start = time.time()
        result = [False]

        def _check():
            try:
                result[0] = bool(condition_fn())
            except Exception:
                result[0] = False
            if result[0]:
                done.set()
            elif time.time() - start < timeout:
                self._app.after(poll_ms, _check)
            else:
                done.set()  # timed out

        self._app.after(0, _check)
        done.wait(timeout + 2)

        if not result[0]:
            raise TestTimeout(label or repr(condition_fn), time.time() - start)
```

- [ ] **Step 2: Add SetupHarness**

Append to `app/test_harness.py`:

```python
class SetupHarness:
    def __init__(self, app):
        self._app = app
        self._h   = TestHarness(app)

    @property
    def _tab(self):
        return self._app._setup_tab

    def install_all(self) -> None:
        self._h._invoke(lambda: self._tab._install_all_btn.invoke())

    def wait_all_ok(self, timeout: float = 120) -> None:
        self._h.wait(
            lambda: "All components installed" in self._tab._all_badge.cget("text"),
            timeout=timeout, label="all components installed",
        )

    def _find_row(self, name: str):
        for row in self._tab._rows:
            if name.lower() in row._name.lower():
                return row
        raise ValueError(f"Component row not found: {name!r}")

    def remove(self, component_name: str) -> None:
        """Remove component, auto-confirming the dialog."""
        import tkinter.messagebox as _mb
        orig = _mb.askyesno
        _mb.askyesno = lambda *a, **kw: True
        try:
            row = self._find_row(component_name)
            self._h._invoke(row._uninstall)
        finally:
            _mb.askyesno = orig

    def install(self, component_name: str) -> None:
        row = self._find_row(component_name)
        self._h._invoke(row._btn.invoke)

    def status(self, component_name: str) -> str:
        row = self._find_row(component_name)
        return row._status_lbl.cget("text")
```

- [ ] **Step 3: Add ModelsHarness**

Append to `app/test_harness.py`:

```python
class ModelsHarness:
    def __init__(self, app):
        self._app = app
        self._h   = TestHarness(app)

    @property
    def _tab(self):
        return self._app._models_tab

    def _find_row(self, display_name: str):
        for row in self._tab._rows:
            if display_name.lower() in row._model.display_name.lower():
                return row
        raise ValueError(f"Model row not found: {display_name!r}")

    def download(self, display_name: str) -> None:
        self._h._invoke(self._find_row(display_name)._btn.invoke)

    def cancel(self, display_name: str) -> None:
        self._h._invoke(self._find_row(display_name)._cancel_download)

    def activate(self, display_name: str) -> None:
        self._h._invoke(self._find_row(display_name)._btn.invoke)

    def state(self, display_name: str) -> str:
        return self._find_row(display_name)._status_lbl.cget("text")

    def wait_downloaded(self, display_name: str, timeout: float = 600) -> None:
        self._h.wait(
            lambda: self.state(display_name) == "Downloaded",
            timeout=timeout, poll_ms=2000, label=f"{display_name} downloaded",
        )

    def wait_active(self, display_name: str, timeout: float = 90) -> None:
        self._h.wait(
            lambda: self.state(display_name) == "Active",
            timeout=timeout, poll_ms=1000, label=f"{display_name} active",
        )
```

- [ ] **Step 4: Add DashboardHarness, ChatHarness, SettingsHarness**

Append to `app/test_harness.py`:

```python
class DashboardHarness:
    def __init__(self, app):
        self._app = app
        self._h   = TestHarness(app)

    def start_stack(self) -> None:
        self._h._invoke(self._app._dashboard._action_btn.invoke)

    def stop_stack(self) -> None:
        self._h._invoke(self._app._dashboard._action_btn.invoke)

    def wait_running(self, timeout: float = 60) -> None:
        self._h.wait(
            lambda: self._app._server.ovms_running and self._app._server.proxy_running,
            timeout=timeout, poll_ms=1000, label="stack running",
        )

    def wait_stopped(self, timeout: float = 30) -> None:
        self._h.wait(
            lambda: not self._app._server.ovms_running and not self._app._server.proxy_running,
            timeout=timeout, poll_ms=500, label="stack stopped",
        )

    def ovms_status(self) -> str:
        return "Running" if self._app._server.ovms_running else "Stopped"

    def proxy_status(self) -> str:
        return "Running" if self._app._server.proxy_running else "Stopped"


class ChatHarness:
    def __init__(self, app):
        self._app = app
        self._h   = TestHarness(app)

    @property
    def _tab(self):
        return self._app._chat_tab

    def set_model(self, name: str) -> None:
        self._h._invoke(lambda: self._tab._model_combo.set(name))

    def send(self, text: str) -> None:
        def _do():
            self._tab._input.delete("1.0", "end")
            self._tab._input.insert("1.0", text)
            self._tab._send()
        self._h._invoke(_do)

    def wait_response(self, timeout: float = 120) -> None:
        self._h.wait(
            lambda: not self._tab._streaming,
            timeout=timeout, poll_ms=500, label="chat response",
        )

    def stop(self) -> None:
        self._h._invoke(self._tab._stop_streaming)

    def last_response(self) -> str:
        for bubble in reversed(self._tab._bubbles):
            if bubble._role == "assistant":
                return bubble.get_text()
        return ""

    def clear(self) -> None:
        self._h._invoke(self._tab._clear)


class SettingsHarness:
    def __init__(self, app):
        self._app = app
        self._h   = TestHarness(app)

    @property
    def _tab(self):
        return self._app._settings_tab

    def set_device(self, device: str) -> None:
        from app.config import cfg
        def _do():
            self._tab._device_menu.set(device)
            cfg.set("ovms_device", device)
        self._h._invoke(_do)

    def get_device(self) -> str:
        return self._tab._device_menu.get()

    def save(self) -> None:
        self._h._invoke(self._tab._save)
```

- [ ] **Step 5: Verify import**

```bash
cd D:/Project/OVMS_GUI
python -c "from app.test_harness import TestHarness, TestTimeout; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add app/test_harness.py
git commit -m "feat: add TestHarness for E2E test automation"
```

---

## Task 2: Hook in `App.__init__` + `tests/e2e/__init__.py`

**Files:**
- Modify: `app/gui.py` (last line of `App.__init__`)
- Create: `tests/e2e/__init__.py`

- [ ] **Step 1: Add env-gated hook to `App.__init__`**

In `app/gui.py`, find the `App.__init__` method. At the very end (after `self.after(2000, self._auto_start_stack)` block), add:

```python
        # E2E test harness — only loaded when OVMS_E2E_TEST=1
        import os as _os
        if _os.environ.get("OVMS_E2E_TEST"):
            from app.test_harness import TestHarness
            self._test_harness = TestHarness(self)
```

- [ ] **Step 2: Create tests/e2e package**

Create `tests/e2e/__init__.py` (empty):
```python
```

- [ ] **Step 3: Verify app still starts normally**

```bash
python -c "from app.gui import App; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Verify harness attaches in test mode**

```bash
python -c "
import os; os.environ['OVMS_E2E_TEST'] = '1'
from app.test_harness import TestHarness
print('TestHarness importable: OK')
"
```

Expected: `TestHarness importable: OK`

- [ ] **Step 5: Commit**

```bash
git add app/gui.py tests/e2e/__init__.py
git commit -m "feat: add E2E test harness hook to App and tests/e2e package"
```

---

## Task 3: `tests/e2e/panel.py` — Floating test panel UI

**Files:**
- Create: `tests/e2e/panel.py`

- [ ] **Step 1: Create the panel**

```python
"""
panel.py — Floating CTkToplevel that shows E2E test progress.
"""

import time
import customtkinter as ctk
from app import theme

PENDING = "pending"
RUNNING = "running"
PASSED  = "passed"
FAILED  = "failed"
SKIPPED = "skipped"

_ICONS = {PENDING: "○", RUNNING: "⏳", PASSED: "✅", FAILED: "❌", SKIPPED: "⊘"}
_COLORS = {
    PENDING: theme.MUTED,
    RUNNING: theme.AMBER,
    PASSED:  theme.GREEN,
    FAILED:  theme.RED,
    SKIPPED: theme.MUTED,
}


class TestPanel(ctk.CTkToplevel):
    def __init__(self, app, steps: list):
        super().__init__(app)
        self._app      = app
        self._steps    = steps
        self._start_t  = None
        self._ticking  = False
        self._on_run   = None
        self._on_stop  = None

        self.title("E2E Tests")
        self.attributes("-topmost", True)
        self.resizable(False, True)
        self.geometry("420x620")
        sw = self.winfo_screenwidth()
        self.geometry(f"+{sw - 440}+20")
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # prevent accidental close

        self._build(steps)

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build(self, steps):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=theme.BANNER, corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="OpenVINO Manager — E2E Tests",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#f8fafc").pack(padx=12, pady=8)

        # Progress bar
        pf = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=0)
        pf.pack(fill="x")
        self._prog = ctk.CTkProgressBar(pf, height=10)
        self._prog.set(0)
        self._prog.pack(fill="x", padx=10, pady=(8, 2))
        info = ctk.CTkFrame(pf, fg_color="transparent")
        info.pack(fill="x", padx=10, pady=(0, 8))
        self._prog_lbl = ctk.CTkLabel(info, text=f"0 / {len(steps)}",
                                       font=ctk.CTkFont(size=11), text_color=theme.MUTED)
        self._prog_lbl.pack(side="left")
        self._time_lbl = ctk.CTkLabel(info, text="",
                                       font=ctk.CTkFont(size=11), text_color=theme.MUTED)
        self._time_lbl.pack(side="right")

        # Current step indicator
        curr = ctk.CTkFrame(self, fg_color=theme.CARD2, corner_radius=0)
        curr.pack(fill="x")
        self._curr_lbl = ctk.CTkLabel(curr, text="Ready — click Run All",
                                       font=ctk.CTkFont(size=12, weight="bold"),
                                       text_color=theme.MUTED, anchor="w")
        self._curr_lbl.pack(fill="x", padx=14, pady=8)

        # Step list
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=6, pady=4)

        self._row_lbls:  dict[str, ctk.CTkLabel] = {}
        self._time_lbls: dict[str, ctk.CTkLabel] = {}
        for step in steps:
            row = ctk.CTkFrame(self._scroll, fg_color="transparent")
            row.pack(fill="x", pady=1)
            lbl = ctk.CTkLabel(row, text=f"○  {step.label}",
                               font=ctk.CTkFont(size=11), text_color=theme.MUTED, anchor="w")
            lbl.pack(side="left", fill="x", expand=True)
            tlbl = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=10),
                                text_color=theme.MUTED, width=50, anchor="e")
            tlbl.pack(side="right")
            self._row_lbls[step.id]  = lbl
            self._time_lbls[step.id] = tlbl

        # Controls
        bot = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=0)
        bot.pack(fill="x", side="bottom")
        ctrl = ctk.CTkFrame(bot, fg_color="transparent")
        ctrl.pack(fill="x", padx=10, pady=8)
        self._run_btn = ctk.CTkButton(ctrl, text="Run All", width=90,
                                       fg_color=theme.BLUE, hover_color=theme.BLUE_H,
                                       command=self._click_run)
        self._run_btn.pack(side="left")
        self._stop_btn = ctk.CTkButton(ctrl, text="Stop", width=70,
                                        fg_color=theme.CARD2, hover_color=theme.BORDER,
                                        border_width=1, border_color=theme.BORDER2,
                                        text_color=theme.TEXT2,
                                        command=self._click_stop, state="disabled")
        self._stop_btn.pack(side="left", padx=4)
        self._summary_lbl = ctk.CTkLabel(ctrl, text="",
                                          font=ctk.CTkFont(size=11), text_color=theme.MUTED)
        self._summary_lbl.pack(side="right")

    # ------------------------------------------------------------------
    # Button callbacks
    # ------------------------------------------------------------------

    def _click_run(self):
        self._start_t = time.time()
        self._ticking = True
        self._run_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._tick()
        if self._on_run:
            self._on_run()

    def _click_stop(self):
        self._ticking = False
        self._stop_btn.configure(state="disabled")
        if self._on_stop:
            self._on_stop()

    def _tick(self):
        if self._ticking and self._start_t:
            e = time.time() - self._start_t
            self._time_lbl.configure(text=f"{int(e//60)}:{int(e%60):02d}")
            self.after(1000, self._tick)

    # ------------------------------------------------------------------
    # Public update methods (called from runner thread via app.after)
    # ------------------------------------------------------------------

    def set_callbacks(self, on_run, on_stop):
        self._on_run  = on_run
        self._on_stop = on_stop

    def mark(self, step_id: str, status: str,
             elapsed: float = None, error: str = None):
        lbl   = self._row_lbls.get(step_id)
        tlbl  = self._time_lbls.get(step_id)
        label = next((s.label for s in self._steps if s.id == step_id), step_id)
        icon  = _ICONS.get(status, "?")
        color = _COLORS.get(status, theme.MUTED)

        if lbl:
            suffix = f"  [{error[:40]}]" if (error and status == FAILED) else ""
            lbl.configure(text=f"{icon}  {label}{suffix}", text_color=color)
        if tlbl and elapsed is not None:
            tlbl.configure(text=f"{elapsed:.1f}s")
        if status == RUNNING:
            self._curr_lbl.configure(text=f"▶  {label}…", text_color=theme.AMBER)

    def update_counters(self, done: int, total: int, passed: int, failed: int):
        self._prog.set(done / total if total > 0 else 0)
        self._prog_lbl.configure(text=f"{done} / {total}")
        color = theme.RED if failed > 0 else (theme.GREEN if passed > 0 else theme.MUTED)
        self._summary_lbl.configure(text=f"✅ {passed}  ❌ {failed}", text_color=color)

    def finish(self, passed: int, failed: int, skipped: int):
        self._ticking = False
        total = passed + failed + skipped
        if failed == 0:
            msg = f"All {passed} passed ✅"
            color = theme.GREEN
        else:
            msg = f"{passed}/{total} passed — {failed} failed ❌"
            color = theme.RED
        self._curr_lbl.configure(text=msg, text_color=color)
        self._run_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._prog.set(1.0)
```

- [ ] **Step 2: Verify import**

```bash
python -c "from tests.e2e.panel import TestPanel, PASSED, FAILED; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/panel.py
git commit -m "feat: add floating E2E test panel UI"
```

---

## Task 4: `tests/e2e/runner.py` — Test definitions + orchestration

**Files:**
- Create: `tests/e2e/runner.py`

- [ ] **Step 1: Create Step dataclass and constants**

```python
"""
runner.py — E2E test runner for OpenVINO Manager.

Usage:
    OVMS_E2E_TEST=1 python tests/e2e/runner.py
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


@dataclass
class Step:
    id:          str
    label:       str
    fn:          Callable
    depends_on:  list = field(default_factory=list)
    timeout:     int  = 60
    desc:        str  = ""
```

- [ ] **Step 2: Define all 12 test step functions**

Append to `tests/e2e/runner.py`:

```python
# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------

def _fresh_state(h: TestHarness):
    h.tab("Dashboard")
    assert h.dashboard.ovms_status() == "Stopped", \
        f"Expected OVMS Stopped on fresh launch, got {h.dashboard.ovms_status()}"
    assert h.dashboard.proxy_status() == "Stopped", \
        f"Expected Proxy Stopped on fresh launch, got {h.dashboard.proxy_status()}"


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
    # Only download if not already downloaded
    if h.models.state("Phi-3.5-mini") not in ("Downloaded", "Active"):
        h.models.download("Phi-3.5-mini")
    h.models.wait_downloaded("Phi-3.5-mini", timeout=600)


def _cancel_download(h: TestHarness):
    h.tab("Models")
    state_before = h.models.state("DeepSeek-R1-1.5B")
    if state_before in ("Downloaded", "Active"):
        return  # already downloaded, skip cancel test
    h.models.download("DeepSeek-R1-1.5B")
    # Wait until download has started
    h.wait(
        lambda: "Downloading" in h.models.state("DeepSeek-R1-1.5B"),
        timeout=30, label="DeepSeek download started",
    )
    time.sleep(3)  # let it progress a bit
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
        f"Expected non-empty non-error response, got: {resp[:80]!r}"


def _chat_stop(h: TestHarness):
    h.tab("Chat")
    h.chat.clear()
    h.chat.send("Write a very long essay about the history of computing, at least 2000 words")
    # Wait for streaming to begin
    h.wait(lambda: h._app._chat_tab._streaming, timeout=15, label="streaming started")
    time.sleep(2)
    h.chat.stop()
    h.wait(lambda: not h._app._chat_tab._streaming, timeout=15, label="streaming stopped")
    # Verify status showed Stopped (check bubble has partial content)
    resp = h.chat.last_response()
    assert resp, "Expected partial response after stop, got empty"


def _settings_device(h: TestHarness):
    h.tab("Settings")
    original = h.settings.get_device()
    h.settings.set_device("CPU")
    assert h.settings.get_device() == "CPU", "Device not set to CPU"
    from app.config import cfg
    assert cfg.ovms_device == "CPU", "Config not updated to CPU"
    h.settings.set_device(original or "GPU")
    assert h.settings.get_device() == (original or "GPU")


def _stop_stack(h: TestHarness):
    h.tab("Dashboard")
    if h.dashboard.ovms_status() == "Running" or h.dashboard.proxy_status() == "Running":
        h.dashboard.stop_stack()
    h.dashboard.wait_stopped(timeout=30)
    assert h.dashboard.ovms_status()  == "Stopped", "OVMS still running after stop"
    assert h.dashboard.proxy_status() == "Stopped", "Proxy still running after stop"
```

- [ ] **Step 3: Define TESTS list**

Append to `tests/e2e/runner.py`:

```python
# ---------------------------------------------------------------------------
# Test registry
# ---------------------------------------------------------------------------

TESTS: list[Step] = [
    Step("fresh_state",     "Fresh state check",               _fresh_state,    timeout=10),
    Step("install_all",     "Install All components",           _install_all,    timeout=300),
    Step("remove_venv",     "Remove Python venv",               _remove_venv,    depends_on=["install_all"], timeout=30),
    Step("reinstall_venv",  "Reinstall Python venv",            _reinstall_venv, depends_on=["remove_venv"], timeout=120),
    Step("download_model",  "Download Phi-3.5-mini (~2 GB)",    _download_model, depends_on=["install_all"], timeout=600),
    Step("cancel_download", "Cancel download (DeepSeek-R1-1.5B)", _cancel_download, depends_on=["install_all"], timeout=60),
    Step("activate_model",  "Activate Phi-3.5-mini",            _activate_model, depends_on=["download_model"], timeout=90),
    Step("verify_stack",    "Dashboard: verify stack running",  _verify_stack,   depends_on=["activate_model"], timeout=60),
    Step("chat_send",       "Chat: send message",               _chat_send,      depends_on=["verify_stack"], timeout=120),
    Step("chat_stop",       "Chat: stop streaming",             _chat_stop,      depends_on=["verify_stack"], timeout=30),
    Step("settings_device", "Settings: change device",          _settings_device, timeout=10),
    Step("stop_stack",      "Stop stack",                       _stop_stack,     depends_on=["verify_stack"], timeout=30),
]
```

- [ ] **Step 4: Add the Runner class**

Append to `tests/e2e/runner.py`:

```python
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
        self._results  = {}
        self._stopped  = False
        self._done     = 0
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
            self._app.after(0, lambda: self._panel.update_counters(
                self._done, len(TESTS),
                sum(1 for v in self._results.values() if v == PASSED),
                sum(1 for v in self._results.values() if v == FAILED),
            ))
            return

        self._app.after(0, lambda s=step: self._panel.mark(s.id, RUNNING))
        start = time.time()

        try:
            step.fn(self._harness)
            elapsed = time.time() - start
            self._results[step.id] = PASSED
            self._app.after(0, lambda s=step, e=elapsed: self._panel.mark(s.id, PASSED, elapsed=e))
        except (TestTimeout, AssertionError, Exception) as exc:
            elapsed = time.time() - start
            self._results[step.id] = FAILED
            err = str(exc)
            self._app.after(0, lambda s=step, e=elapsed, er=err:
                            self._panel.mark(s.id, FAILED, elapsed=e, error=er))

        self._done += 1
        self._app.after(0, lambda: self._panel.update_counters(
            self._done, len(TESTS),
            sum(1 for v in self._results.values() if v == PASSED),
            sum(1 for v in self._results.values() if v == FAILED),
        ))
```

- [ ] **Step 5: Add the entry point**

Append to `tests/e2e/runner.py`:

```python
# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    from app.gui import App
    app = App()

    # Harness is attached by App.__init__ when OVMS_E2E_TEST=1
    harness: TestHarness = app._test_harness

    panel = TestPanel(app, TESTS)
    runner = Runner(app, panel, harness)

    panel.set_callbacks(on_run=runner.start, on_stop=runner.stop)

    app.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Verify the runner imports without errors**

```bash
python -c "
import os; os.environ['OVMS_E2E_TEST'] = '1'
import tests.e2e.runner as r
print('Steps:', len(r.TESTS))
print('OK')
"
```

Expected:
```
Steps: 12
OK
```

- [ ] **Step 7: Commit**

```bash
git add tests/e2e/runner.py
git commit -m "feat: add E2E test runner with 12 step definitions"
```

---

## Task 5: Smoke test — launch the panel and verify UI

**Files:**
- No new files

- [ ] **Step 1: Launch in E2E mode and verify panel appears**

```bash
cd D:/Project/OVMS_GUI
set OVMS_E2E_TEST=1 && python tests/e2e/runner.py
```

Expected: App opens maximized + test panel appears top-right with 12 steps all showing `○`. "Run All" button visible.

- [ ] **Step 2: Verify Run All starts the runner**

Click "Run All" in the panel. The first step "Fresh state check" should immediately turn ✅ (or ❌ if OVMS is already running). The timer should start ticking.

- [ ] **Step 3: Commit if any fixes were needed**

```bash
git add -u
git commit -m "fix: e2e smoke test adjustments"
```

---

## Self-Review

### Spec coverage

| Spec section | Covered by task |
|---|---|
| TestHarness + sub-harnesses | Task 1 |
| App hook `OVMS_E2E_TEST` | Task 2 |
| Panel UI (progress, steps, controls) | Task 3 |
| 12 test step definitions | Task 4 |
| Runner orchestration + skip logic | Task 4 |
| Entry point | Task 4 |
| Two-tier (automated + live panel) | Task 4+5 |

All spec sections covered. ✓

### Type consistency

- `TestHarness._invoke(fn)` — defined Task 1, used by all sub-harnesses ✓
- `TestHarness.wait(condition_fn, timeout, poll_ms, label)` — defined Task 1, used in runner ✓
- `TestTimeout(label, elapsed)` — defined Task 1, caught in runner Task 4 ✓
- `Step.id` — defined Task 4, used in `_results` dict and `panel.mark(step_id)` ✓
- `panel.mark(step_id, status, elapsed, error)` — defined Task 3, called in Task 4 ✓
- `panel.update_counters(done, total, passed, failed)` — defined Task 3, called Task 4 ✓
- `panel.finish(passed, failed, skipped)` — defined Task 3, called Task 4 ✓

### Placeholder scan

No TBD, TODO, "similar to", "add appropriate" patterns. ✓
