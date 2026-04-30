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
        self.label   = label
        self.elapsed = elapsed


# ---------------------------------------------------------------------------
# Base class with thread-safe helpers (shared by all harnesses)
# ---------------------------------------------------------------------------

class _HarnessBase:
    def __init__(self, app):
        self._app = app

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
        done   = threading.Event()
        start  = time.time()
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


# ---------------------------------------------------------------------------
# Top-level harness
# ---------------------------------------------------------------------------

class TestHarness(_HarnessBase):
    def __init__(self, app):
        super().__init__(app)
        self.setup     = SetupHarness(app)
        self.models    = ModelsHarness(app)
        self.dashboard = DashboardHarness(app)
        self.chat      = ChatHarness(app)
        self.settings  = SettingsHarness(app)

    def tab(self, name: str) -> "TestHarness":
        self._invoke(lambda: self._app._tabs.set(name))
        return self


# ---------------------------------------------------------------------------
# Per-tab harnesses — all inherit _invoke / wait from _HarnessBase
# ---------------------------------------------------------------------------

class SetupHarness(_HarnessBase):

    @property
    def _tab(self):
        return self._app._setup_tab

    def install_all(self) -> None:
        self._invoke(lambda: self._tab._install_all_btn.invoke())

    def wait_all_ok(self, timeout: float = 120) -> None:
        self.wait(
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
            self._invoke(row._uninstall)
        finally:
            _mb.askyesno = orig

    def install(self, component_name: str) -> None:
        row = self._find_row(component_name)
        self._invoke(row._btn.invoke)

    def status(self, component_name: str) -> str:
        return self._find_row(component_name)._status_lbl.cget("text")


class ModelsHarness(_HarnessBase):

    @property
    def _tab(self):
        return self._app._models_tab

    def _find_row(self, display_name: str):
        for row in self._tab._rows:
            if display_name.lower() in row._model.display_name.lower():
                return row
        raise ValueError(f"Model row not found: {display_name!r}")

    def download(self, display_name: str) -> None:
        self._invoke(self._find_row(display_name)._btn.invoke)

    def cancel(self, display_name: str) -> None:
        self._invoke(self._find_row(display_name)._cancel_download)

    def activate(self, display_name: str) -> None:
        self._invoke(self._find_row(display_name)._btn.invoke)

    def state(self, display_name: str) -> str:
        return self._find_row(display_name)._status_lbl.cget("text")

    def wait_downloaded(self, display_name: str, timeout: float = 600) -> None:
        self.wait(
            lambda: self.state(display_name) == "Downloaded",
            timeout=timeout, poll_ms=2000, label=f"{display_name} downloaded",
        )

    def wait_active(self, display_name: str, timeout: float = 90) -> None:
        self.wait(
            lambda: self.state(display_name) == "Active",
            timeout=timeout, poll_ms=1000, label=f"{display_name} active",
        )


class DashboardHarness(_HarnessBase):

    def start_stack(self) -> None:
        self._invoke(self._app._dashboard._action_btn.invoke)

    def stop_stack(self) -> None:
        self._invoke(self._app._dashboard._action_btn.invoke)

    def wait_running(self, timeout: float = 60) -> None:
        self.wait(
            lambda: self._app._server.ovms_running and self._app._server.proxy_running,
            timeout=timeout, poll_ms=1000, label="stack running",
        )

    def wait_stopped(self, timeout: float = 30) -> None:
        self.wait(
            lambda: not self._app._server.ovms_running and not self._app._server.proxy_running,
            timeout=timeout, poll_ms=500, label="stack stopped",
        )

    def ovms_status(self) -> str:
        return "Running" if self._app._server.ovms_running else "Stopped"

    def proxy_status(self) -> str:
        return "Running" if self._app._server.proxy_running else "Stopped"


class ChatHarness(_HarnessBase):

    @property
    def _tab(self):
        return self._app._chat_tab

    def set_model(self, name: str) -> None:
        self._invoke(lambda: self._tab._model_combo.set(name))

    def send(self, text: str) -> None:
        def _do():
            self._tab._input.delete("1.0", "end")
            self._tab._input.insert("1.0", text)
            self._tab._send()
        self._invoke(_do)

    def wait_response(self, timeout: float = 120) -> None:
        self.wait(
            lambda: not self._tab._streaming,
            timeout=timeout, poll_ms=500, label="chat response",
        )

    def stop(self) -> None:
        self._invoke(self._tab._stop_streaming)

    def last_response(self) -> str:
        for bubble in reversed(self._tab._bubbles):
            if bubble._role == "assistant":
                return bubble.get_text()
        return ""

    def clear(self) -> None:
        self._invoke(self._tab._clear)


class SettingsHarness(_HarnessBase):

    @property
    def _tab(self):
        return self._app._settings_tab

    def set_device(self, device: str) -> None:
        from app.config import cfg
        def _do():
            self._tab._device_menu.set(device)
            cfg.set("ovms_device", device)
        self._invoke(_do)

    def get_device(self) -> str:
        return self._tab._device_menu.get()

    def save(self) -> None:
        self._invoke(self._tab._save)
