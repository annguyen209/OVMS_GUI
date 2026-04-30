# OVMS GUI Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all known bugs, add shared theme module, add markdown rendering with stop button in Chat, add device selector for OVMS inference, and improve model activation feedback across the UI.

**Architecture:** Foundation-first order — create `app/theme.py` and migrate all files to it, then fix bugs, then add new features (chat improvements, device selector, activation feedback). Each task is independently committable and leaves the app in a working state.

**Tech Stack:** Python 3.12, customtkinter 5.2+, tkinter (stdlib), threading (stdlib), httpx, pytest

---

## File Map

| File | Action | Reason |
|------|--------|--------|
| `app/theme.py` | **Create** | Shared palette constants |
| `app/log_viewer.py` | Modify | Replace local color constants with `theme.*` |
| `app/about.py` | Modify | Replace local color constants with `theme.*` |
| `app/guide.py` | Modify | Replace local color constants with `theme.*` |
| `app/setup_tab.py` | Modify | Theme import + remove duplicate method + fix global status |
| `app/gui.py` | Modify | Theme import + `import time` + device dropdown + activation feedback |
| `app/server.py` | Modify | Store and close log file handles |
| `app/config.py` | Modify | Add `ovms_device` key and property |
| `app/models.py` | Modify | Parameterise `device` in `GRAPH_TEMPLATE` |
| `app/chat.py` | Modify | Theme + `tk.Text` markdown rendering + stop button |
| `tests/__init__.py` | **Create** | pytest package marker |
| `tests/test_theme.py` | **Create** | Verify all palette constants |
| `tests/test_config.py` | **Create** | Verify `ovms_device` default |
| `tests/test_models.py` | **Create** | Verify GRAPH_TEMPLATE device param |
| `tests/test_markdown.py` | **Create** | Unit-test `_apply_markdown` helper |

---

## Task 1: Bootstrap pytest

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Install pytest into the dev environment**

```bash
pip install pytest
```

Expected output: `Successfully installed pytest-...`

- [ ] **Step 2: Create the tests package**

Create `tests/__init__.py` (empty file):
```python
```

- [ ] **Step 3: Write a smoke test**

Create `tests/test_smoke.py`:
```python
def test_app_package_importable():
    import app
```

- [ ] **Step 4: Run to confirm pytest works**

```bash
cd D:/Project/OVMS_GUI
python -m pytest tests/test_smoke.py -v
```

Expected:
```
tests/test_smoke.py::test_app_package_importable PASSED
1 passed in 0.XXs
```

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "chore: bootstrap pytest"
```

---

## Task 2: Create `app/theme.py`

**Files:**
- Create: `app/theme.py`
- Create: `tests/test_theme.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_theme.py`:
```python
import re
import pytest
from app import theme

_HEX = re.compile(r'^#[0-9a-fA-F]{6}$')

_EXPECTED = [
    "BG", "CARD", "CARD2", "BORDER", "BORDER2",
    "TEXT", "TEXT2", "MUTED",
    "BLUE", "BLUE_H", "GREEN", "RED", "AMBER",
    "BANNER", "FOOTER", "GRAY",
    "CODE_BG", "CODE_FG",
    "USER_BG", "ASSIST_BG", "SYSTEM_BG", "CHAT_BG",
]

@pytest.mark.parametrize("name", _EXPECTED)
def test_constant_exists_and_is_hex(name):
    value = getattr(theme, name)
    assert _HEX.match(value), f"{name}={value!r} is not a valid hex color"
```

- [ ] **Step 2: Run to confirm it fails**

```bash
python -m pytest tests/test_theme.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.theme'`

- [ ] **Step 3: Create `app/theme.py`**

```python
BG      = "#f3f4f6"
CARD    = "#ffffff"
CARD2   = "#f9fafb"
BORDER  = "#e5e7eb"
BORDER2 = "#d1d5db"
TEXT    = "#111827"
TEXT2   = "#374151"
MUTED   = "#6b7280"
BLUE    = "#0078d4"
BLUE_H  = "#106ebe"
GREEN   = "#107c10"
RED     = "#a4262c"
AMBER   = "#c55000"
BANNER  = "#1b1f23"
FOOTER  = "#1b1f23"
GRAY    = "#64748b"
CODE_BG = "#1e293b"
CODE_FG = "#e2e8f0"
USER_BG    = "#eff6ff"
ASSIST_BG  = "#ffffff"
SYSTEM_BG  = "#f9fafb"
CHAT_BG    = "#f3f4f6"
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_theme.py -v
```

Expected: `23 passed`

- [ ] **Step 5: Commit**

```bash
git add app/theme.py tests/test_theme.py
git commit -m "feat: add shared theme palette module"
```

---

## Task 3: Migrate `log_viewer.py`, `about.py`, `guide.py` to theme

**Files:**
- Modify: `app/log_viewer.py`
- Modify: `app/about.py`
- Modify: `app/guide.py`

These three files only use theme constants — no logic changes.

- [ ] **Step 1: Update `app/log_viewer.py`**

Replace the local constants block (lines 19–21):
```python
_CARD2   = "#f9fafb"   # secondary surfaces (gray-50)
_TEXT2   = "#374151"   # secondary text (gray-700)
_BORDER  = "#e5e7eb"   # borders (gray-200)
```
With:
```python
from app import theme
```

Then replace all references in the file:
- `_CARD2` → `theme.CARD2`
- `_TEXT2` → `theme.TEXT2`
- `_BORDER` → `theme.BORDER`

Affected lines in `_build_ui`:
```python
        self._textbox = ctk.CTkTextbox(
            self,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled",
            fg_color=theme.CARD2,
            text_color=theme.TEXT2,
            border_width=1,
            border_color=theme.BORDER,
        )
```

- [ ] **Step 2: Update `app/about.py`**

Remove the entire local constants block (lines 15–28):
```python
_BG      = "#f3f4f6"
_CARD    = "#ffffff"
...
_BANNER  = "#1b1f23"
```
Add at the top (after existing imports):
```python
from app import theme
```

Replace all `_NAME` references with `theme.NAME` throughout the file. Full replacement map:
- `_BG` → `theme.BG`
- `_CARD` → `theme.CARD`
- `_CARD2` → `theme.CARD2`
- `_BORDER` → `theme.BORDER`
- `_BORDER2` → `theme.BORDER2`
- `_TEXT` → `theme.TEXT`
- `_TEXT2` → `theme.TEXT2`
- `_MUTED` → `theme.MUTED`
- `_GREEN` → `theme.GREEN`
- `_BLUE` → `theme.BLUE`
- `_BLUE_H` → `theme.BLUE_H`
- `_RED` → `theme.RED`
- `_AMBER` → `theme.AMBER`
- `_BANNER` → `theme.BANNER`

- [ ] **Step 3: Update `app/guide.py`**

Remove the entire local constants block (lines 18–34):
```python
_BG      = "#f3f4f6"
...
_TAG_GREEN = "#dcfce7"
```
Add:
```python
from app import theme
```

Replace all references. Additional constants in guide.py:
- `_TAG_BLUE` → `"#dbeafe"` (keep inline — it is guide-specific and not in theme)
- `_TAG_GREEN` → `"#dcfce7"` (keep inline — guide-specific)

So in `_Tag.__init__`:
```python
    _COLORS = {
        "blue":  ("#dbeafe", theme.BLUE),
        "green": ("#dcfce7", theme.GREEN),
    }
```

All other `_NAME` → `theme.NAME` as per about.py map. `_CODE_BG` → `theme.CODE_BG`, `_CODE_FG` → `theme.CODE_FG`.

- [ ] **Step 4: Verify the app starts without errors**

```bash
python main.py
```

Expected: app window opens, Guide and About tabs display correctly. Close the app.

- [ ] **Step 5: Commit**

```bash
git add app/log_viewer.py app/about.py app/guide.py
git commit -m "refactor: migrate log_viewer, about, guide to shared theme"
```

---

## Task 4: Migrate `app/setup_tab.py` to theme + fix bugs

**Files:**
- Modify: `app/setup_tab.py`

Three changes in one file: theme migration + remove duplicate method + fix global status label.

- [ ] **Step 1: Replace local constants with theme import**

Remove the block at lines 14–29:
```python
_BG      = "#f3f4f6"
_CARD    = "#ffffff"
...
_CODE_FG = "#e2e8f0"
```
Add after existing imports:
```python
from app import theme
```

Replace all `_NAME` → `theme.NAME` throughout. The `_CODE_BG` / `_CODE_FG` constants map to `theme.CODE_BG` / `theme.CODE_FG`.

- [ ] **Step 2: Remove the duplicate `_refresh_aggregate` method**

The method appears twice. Lines 381–383 are the first (identical) definition. Delete them:

```python
    def _refresh_aggregate(self):
        """Run aggregate all_ok() check in background, update badge."""
        threading.Thread(target=self._aggregate_bg, daemon=True).start()
```

Keep only the second definition that immediately follows (the one that stays is the one before `_aggregate_bg`).

- [ ] **Step 3: Fix global status in `_apply_aggregate`**

Find `_apply_aggregate` and update both branches:

```python
    def _apply_aggregate(self, ok: bool):
        if ok:
            self._all_badge.configure(text="All components installed",
                                      fg_color="#f0fdf4", text_color=theme.GREEN)
            self._install_all_btn.configure(state="disabled",
                                            text="All installed",
                                            fg_color=theme.CARD2,
                                            border_width=1,
                                            border_color=theme.BORDER2,
                                            text_color=theme.MUTED)
            self._global_status.configure(text="All components ready.",
                                          text_color=theme.GREEN)
            if self._on_all_ok:
                self._on_all_ok()
        else:
            self._global_status.configure(text="Some components missing.",
                                          text_color=theme.AMBER)
            if self._on_missing:
                self._on_missing()
            self._all_badge.configure(
                text="Some components missing — click Install to set up",
                fg_color="#fff7ed", text_color=theme.AMBER,
            )
```

- [ ] **Step 4: Verify the app starts and Setup tab works**

```bash
python main.py
```

Open Setup tab. Confirm status indicator updates correctly (green "All components ready." or amber). Close.

- [ ] **Step 5: Commit**

```bash
git add app/setup_tab.py
git commit -m "refactor: migrate setup_tab to theme; fix duplicate method and global status"
```

---

## Task 5: Migrate `app/gui.py` to theme + fix `import time`

**Files:**
- Modify: `app/gui.py`

- [ ] **Step 1: Replace local constants with theme import**

Remove the palette block at lines 34–51:
```python
_BG      = "#f3f4f6"   # page background (gray-100)
...
_GRAY    = "#64748b"   # slate-500 (Download button)
```
Add after existing imports (keep `import time` — we are adding it here):
```python
import time
from app import theme
```

Replace all `_NAME` → `theme.NAME` throughout the entire file. The `_GRAY` constant maps to `theme.GRAY`. `_BANNER` → `theme.BANNER`. `_FOOTER` → `theme.FOOTER`.

- [ ] **Step 2: Remove inline `import time` from `ModelRow._activate`**

Find in `_activate` the worker lambda body:
```python
                self._server.stop_stack()
                import time; time.sleep(1)
                ok2, msg2 = self._server.start_stack()
```
Replace with:
```python
                self._server.stop_stack()
                time.sleep(1)
                ok2, msg2 = self._server.start_stack()
```

(The `import time` at the top of the file added in Step 1 covers this.)

- [ ] **Step 3: Verify the app starts and all tabs render**

```bash
python main.py
```

Confirm Dashboard, Models, Settings tabs display with correct colors. Close.

- [ ] **Step 4: Commit**

```bash
git add app/gui.py
git commit -m "refactor: migrate gui to theme; move import time to module level"
```

---

## Task 6: Fix log file handles in `app/server.py`

**Files:**
- Modify: `app/server.py`

- [ ] **Step 1: Add handle fields to `__init__`**

In `ServerManager.__init__`, after the process fields:
```python
        self._ovms_proc:  subprocess.Popen | None = None
        self._proxy_proc: subprocess.Popen | None = None
```
Add:
```python
        self._ovms_log_fh  = None
        self._proxy_log_fh = None
```

- [ ] **Step 2: Store handle in `_start_ovms`**

In `_start_ovms`, find the line:
```python
            proc = subprocess.Popen(
```
Directly before it, change the `log_fh` assignment to also store on `self`:
```python
            self._ovms_log_fh = log_fh
            proc = subprocess.Popen(
                cmd, stdout=log_fh, stderr=log_fh, env=env,
                creationflags=subprocess.CREATE_NO_WINDOW,
                cwd=str(Path(cfg.ovms_exe).parent),
            )
```

- [ ] **Step 3: Store handle in `_start_proxy`**

In `_start_proxy`, similarly before `proc = subprocess.Popen(...)`:
```python
            self._proxy_log_fh = log_fh
            proc = subprocess.Popen(
                [cfg.python_exe, cfg.proxy_script],
                stdout=log_fh, stderr=log_fh,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
```

- [ ] **Step 4: Close handles in `stop_stack`**

In `stop_stack`, after stopping each process, close its handle. The full updated method:

```python
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
```

- [ ] **Step 5: Close handles in `shutdown`**

```python
    def shutdown(self):
        self._stop_polling.set()
        for fh in (self._ovms_log_fh, self._proxy_log_fh):
            if fh:
                try:
                    fh.close()
                except Exception:
                    pass
```

- [ ] **Step 6: Verify start/stop cycle works**

```bash
python main.py
```

Start the stack (Dashboard → Start Stack), wait for green status, then Stop Stack. Confirm no errors in console. Close app.

- [ ] **Step 7: Commit**

```bash
git add app/server.py
git commit -m "fix: store and close OVMS/proxy log file handles on stop"
```

---

## Task 7: Add `ovms_device` to `app/config.py` + test

**Files:**
- Modify: `app/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:
```python
from app.config import AppConfig


def test_ovms_device_default():
    cfg = AppConfig.__new__(AppConfig)
    cfg._data = {}
    assert cfg.ovms_device == "GPU"


def test_ovms_device_reads_from_data():
    cfg = AppConfig.__new__(AppConfig)
    cfg._data = {"ovms_device": "CPU"}
    assert cfg.ovms_device == "CPU"


def test_ovms_device_valid_choices():
    cfg = AppConfig.__new__(AppConfig)
    for device in ("GPU", "CPU", "NPU", "AUTO"):
        cfg._data = {"ovms_device": device}
        assert cfg.ovms_device == device
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_config.py -v
```

Expected: `AttributeError: 'AppConfig' object has no attribute 'ovms_device'`

- [ ] **Step 3: Add key to `DEFAULTS` and property to `AppConfig`**

In `DEFAULTS` dict (after `"auto_start_stack": False`):
```python
    "ovms_device":      "GPU",
```

After the `proxy_port` property in `AppConfig`:
```python
    @property
    def ovms_device(self) -> str:
        return self._data.get("ovms_device", "GPU")
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_config.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat: add ovms_device config key with GPU default"
```

---

## Task 8: Parameterise device in `GRAPH_TEMPLATE` + test

**Files:**
- Modify: `app/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:
```python
from app.models import GRAPH_TEMPLATE, activate_model, ModelInfo
from unittest.mock import patch, MagicMock
from pathlib import Path


def test_graph_template_accepts_device():
    result = GRAPH_TEMPLATE.format(model_path="/some/path", device="CPU")
    assert 'device: "CPU"' in result


def test_graph_template_gpu_default_usable():
    result = GRAPH_TEMPLATE.format(model_path="/models/qwen", device="GPU")
    assert 'device: "GPU"' in result
    assert 'models_path: "/models/qwen"' in result


def test_graph_template_npu():
    result = GRAPH_TEMPLATE.format(model_path="/m", device="NPU")
    assert 'device: "NPU"' in result
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_models.py -v
```

Expected: `KeyError: 'device'` (template has no `{device}` placeholder yet)

- [ ] **Step 3: Update `GRAPH_TEMPLATE` in `app/models.py`**

Find the line:
```python
      device: "GPU"
```
Replace with:
```python
      device: "{device}"
```

- [ ] **Step 4: Update `activate_model` to pass device**

Find in `activate_model`:
```python
    graph_content = GRAPH_TEMPLATE.format(model_path=model_path_str)
```
Replace with:
```python
    graph_content = GRAPH_TEMPLATE.format(
        model_path=model_path_str,
        device=cfg.ovms_device,
    )
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
python -m pytest tests/test_models.py -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add app/models.py tests/test_models.py
git commit -m "feat: parameterise OVMS inference device in graph.pbtxt template"
```

---

## Task 9: Add device dropdown to `SettingsTab` in `app/gui.py`

**Files:**
- Modify: `app/gui.py`

- [ ] **Step 1: Locate the insertion point in `SettingsTab._build_ui`**

The scrollable frame is created with:
```python
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        scroll.columnconfigure(1, weight=1)
```

The device row goes inside `scroll`, after the last field row (the port fields). At the end of the `for row_idx, (key, label, kind) in enumerate(self._FIELDS):` loop, add a device section.

- [ ] **Step 2: Add device row inside the scrollable frame**

After the `for` loop that builds path/port fields, before the `# Windows startup section` comment, add:

```python
        # ---- Inference device ----
        device_row_idx = len(self._FIELDS) + 1

        ctk.CTkFrame(scroll, height=1, fg_color=theme.BORDER).grid(
            row=device_row_idx - 1, column=0, columnspan=3,
            sticky="ew", padx=8, pady=(8, 4),
        )

        ctk.CTkLabel(
            scroll,
            text="Inference Device",
            font=ctk.CTkFont(size=12),
            text_color=theme.TEXT2,
            anchor="w",
            width=200,
        ).grid(row=device_row_idx, column=0, sticky="w", padx=(8, 12), pady=6)

        self._device_menu = ctk.CTkOptionMenu(
            scroll,
            values=["GPU", "CPU", "NPU", "AUTO"],
            font=ctk.CTkFont(size=12),
            fg_color=theme.CARD2,
            button_color=theme.BORDER2,
            button_hover_color=theme.BORDER,
            text_color=theme.TEXT,
            dropdown_fg_color=theme.CARD,
            dropdown_hover_color=theme.CARD2,
            dropdown_text_color=theme.TEXT,
            command=lambda v: cfg.set("ovms_device", v),
        )
        self._device_menu.set(cfg.ovms_device)
        self._device_menu.grid(row=device_row_idx, column=1, sticky="w", padx=(0, 8), pady=6)

        ctk.CTkLabel(
            scroll,
            text="Takes effect the next time you activate a model.",
            font=ctk.CTkFont(size=11),
            text_color=theme.MUTED,
            anchor="w",
        ).grid(row=device_row_idx + 1, column=0, columnspan=2,
               sticky="w", padx=(8, 8), pady=(0, 8))
```

- [ ] **Step 3: Verify device dropdown appears and saves**

```bash
python main.py
```

Open Settings tab. Scroll to the bottom of the fields section. Confirm a device dropdown labelled "Inference Device" appears with options GPU / CPU / NPU / AUTO. Change selection to CPU, close app. Re-open app, open Settings — confirm CPU is still selected.

- [ ] **Step 4: Commit**

```bash
git add app/gui.py
git commit -m "feat: add inference device dropdown to Settings tab"
```

---

## Task 10: Markdown rendering in `MessageBubble` (`app/chat.py`)

**Files:**
- Modify: `app/chat.py`
- Create: `tests/test_markdown.py`

The `_apply_markdown` helper is a pure function — fully unit-testable. The widget swap is manual-test only.

- [ ] **Step 1: Write failing tests for `_apply_markdown`**

Create `tests/test_markdown.py`:

```python
import tkinter as tk
import pytest

# Guard: skip entire module if no display (CI without $DISPLAY)
pytestmark = pytest.mark.skipif(
    __import__("sys").platform == "win32" and not __import__("os").environ.get("DISPLAY", True),
    reason="no display"
)


@pytest.fixture
def text_widget():
    root = tk.Tk()
    root.withdraw()
    widget = tk.Text(root)
    # Configure the tags that _apply_markdown expects
    widget.tag_configure("bold",        font=("Segoe UI", 12, "bold"))
    widget.tag_configure("italic",      font=("Segoe UI", 12, "italic"))
    widget.tag_configure("code_inline", font=("Consolas", 12),
                         background="#f1f5f9")
    widget.tag_configure("code_block",  font=("Consolas", 12),
                         background="#1e293b", foreground="#e2e8f0")
    widget.tag_configure("heading",     font=("Segoe UI", 14, "bold"))
    yield widget
    root.destroy()


def _get_text(widget):
    return widget.get("1.0", "end-1c")


def _tags_at(widget, index):
    return widget.tag_names(index)


def test_plain_text(text_widget):
    from app.chat import _apply_markdown
    _apply_markdown(text_widget, "Hello world")
    assert _get_text(text_widget) == "Hello world"


def test_bold(text_widget):
    from app.chat import _apply_markdown
    _apply_markdown(text_widget, "Say **hello** now")
    content = _get_text(text_widget)
    assert content == "Say hello now"
    assert "bold" in _tags_at(text_widget, "1.5")


def test_inline_code(text_widget):
    from app.chat import _apply_markdown
    _apply_markdown(text_widget, "Use `print()` here")
    content = _get_text(text_widget)
    assert content == "Use print() here"
    assert "code_inline" in _tags_at(text_widget, "1.5")


def test_heading(text_widget):
    from app.chat import _apply_markdown
    _apply_markdown(text_widget, "## My Title\nBody text")
    content = _get_text(text_widget)
    assert "My Title" in content
    assert "heading" in _tags_at(text_widget, "1.0")


def test_code_block(text_widget):
    from app.chat import _apply_markdown
    _apply_markdown(text_widget, "Look:\n```\nprint('hi')\n```\nDone")
    content = _get_text(text_widget)
    assert "print('hi')" in content
    assert "Done" in content
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_markdown.py -v
```

Expected: `ImportError: cannot import name '_apply_markdown' from 'app.chat'`

- [ ] **Step 3: Add `_apply_markdown` to `app/chat.py`**

Add this function after the `_strip_markdown` function (which we will delete later — keep it for now):

```python
import re as _re


def _apply_markdown(widget: "tk.Text", text: str) -> None:
    """
    Clear *widget* and re-insert *text* with markdown formatting tags applied.

    Expected tags already configured on the widget:
      bold, italic, code_inline, code_block, heading
    """
    widget.configure(state="normal")
    widget.delete("1.0", "end")

    # Split on fenced code blocks first so inline patterns don't match inside them
    parts = _re.split(r"```(?:[a-zA-Z]*\n?)?(.*?)```", text, flags=_re.DOTALL)

    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            # Fenced code block content
            widget.insert("end", part.strip(), "code_block")
            widget.insert("end", "\n")
        else:
            lines = part.split("\n")
            for line_no, line in enumerate(lines):
                if line_no > 0:
                    widget.insert("end", "\n")
                _insert_inline(widget, line)

    widget.configure(state="disabled")
    _auto_height(widget)


def _insert_inline(widget: "tk.Text", line: str) -> None:
    """Insert one line with inline markdown tags (bold, italic, code, heading)."""
    # Heading
    m = _re.match(r"^(#{1,3})\s+(.+)$", line)
    if m:
        widget.insert("end", m.group(2), "heading")
        return

    # Inline tokens: code > bold > italic (order matters — longer patterns first)
    pattern = _re.compile(
        r"`([^`]+)`"           # inline code
        r"|\*\*\*(.+?)\*\*\*"  # bold-italic (consume before bold)
        r"|\*\*(.+?)\*\*"      # bold
        r"|___(.+?)___"        # bold (underscore)
        r"|\*(.+?)\*"          # italic
        r"|__(.+?)__"          # bold (double underscore)
        r"|_([^_]+)_"          # italic (underscore)
    )
    pos = 0
    for match in pattern.finditer(line):
        if match.start() > pos:
            widget.insert("end", line[pos:match.start()])
        g = match.groups()
        if g[0] is not None:
            widget.insert("end", g[0], "code_inline")
        elif g[1] is not None:
            widget.insert("end", g[1], ("bold", "italic"))
        elif g[2] is not None:
            widget.insert("end", g[2], "bold")
        elif g[3] is not None:
            widget.insert("end", g[3], "bold")
        elif g[4] is not None:
            widget.insert("end", g[4], "italic")
        elif g[5] is not None:
            widget.insert("end", g[5], "bold")
        elif g[6] is not None:
            widget.insert("end", g[6], "italic")
        pos = match.end()
    if pos < len(line):
        widget.insert("end", line[pos:])


def _auto_height(widget: "tk.Text") -> None:
    """Resize the tk.Text to fit its content (no scrollbar needed)."""
    lines = int(widget.index("end-1c").split(".")[0])
    widget.configure(height=max(1, lines))
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_markdown.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Replace `CTkLabel` content area in `MessageBubble` with `tk.Text`**

Find `MessageBubble.__init__` in `app/chat.py`. Remove these lines in the content section:

```python
        # Content
        self._text_var = tk.StringVar(value=content)
        self._label = ctk.CTkLabel(
            self,
            textvariable=self._text_var,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=theme.TEXT,
            anchor="w",
            justify="left",
            wraplength=700,
        )
        self._label.pack(anchor="w", padx=14, pady=(0, 10), fill="x")
```

Replace with:

```python
        # Content — tk.Text for markdown rendering
        self._textbox = tk.Text(
            self,
            font=("Segoe UI", 13),
            bg=self._BG_COLORS.get(role, theme.ASSIST_BG),
            fg=theme.TEXT,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            wrap="word",
            state="disabled",
            cursor="arrow",
            padx=14,
            pady=4,
            height=1,
        )
        self._textbox.pack(fill="x", padx=0, pady=(0, 10))

        # Configure markdown tags
        self._textbox.tag_configure("bold",
            font=("Segoe UI", 13, "bold"))
        self._textbox.tag_configure("italic",
            font=("Segoe UI", 13, "italic"))
        self._textbox.tag_configure("code_inline",
            font=("Consolas", 12), background="#f1f5f9")
        self._textbox.tag_configure("code_block",
            font=("Consolas", 12),
            background=theme.CODE_BG, foreground=theme.CODE_FG)
        self._textbox.tag_configure("heading",
            font=("Segoe UI", 15, "bold"))

        if content:
            _apply_markdown(self._textbox, content)
```

- [ ] **Step 6: Update `MessageBubble` methods to use `_textbox`**

Replace `_copy`:
```python
    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.get_text())
        self._copy_lbl.configure(text="Copied")
        self.after(2000, lambda: self._copy_lbl.configure(text=""))
```

Replace `append`:
```python
    def append(self, text: str):
        self._textbox.configure(state="normal")
        self._textbox.insert("end", text)
        self._textbox.configure(state="disabled")
        _auto_height(self._textbox)
```

Replace `get_text`:
```python
    def get_text(self) -> str:
        return self._textbox.get("1.0", "end-1c")
```

Replace `set_wrap`:
```python
    def set_wrap(self, pixel_width: int):
        chars = max(40, (pixel_width - 120) // 8)
        self._textbox.configure(width=chars)
```

- [ ] **Step 7: Update `ChatTab._finish` — call `_apply_markdown` instead of `_strip_markdown`**

Find in `_finish`:
```python
        if self._active_bubble:
            raw     = self._active_bubble.get_text()
            cleaned = _strip_markdown(raw)
            # Update bubble display with clean text
            if cleaned != raw:
                self._active_bubble._text_var.set(cleaned)
            # Only append to history if tools didn't already sync it
            if not self._messages or self._messages[-1].get("role") != "assistant":
                self._messages.append({"role": "assistant", "content": cleaned})
```

Replace with:
```python
        if self._active_bubble:
            raw = self._active_bubble.get_text()
            # Re-render with markdown formatting
            _apply_markdown(self._active_bubble._textbox, raw)
            # Only append to history if tools didn't already sync it
            if not self._messages or self._messages[-1].get("role") != "assistant":
                self._messages.append({"role": "assistant", "content": raw})
```

- [ ] **Step 8: Remove `_strip_markdown` function**

Delete the entire `_strip_markdown` function (lines 48–73 in the original file). It is no longer called anywhere.

- [ ] **Step 9: Run markdown tests again to confirm nothing broke**

```bash
python -m pytest tests/test_markdown.py tests/test_theme.py -v
```

Expected: all pass.

- [ ] **Step 10: Manual verification**

```bash
python main.py
```

Open Chat tab. Send a message like: `"write hello world in Python"`. Confirm:
- Text streams in as raw characters
- On completion, `**bold**` renders bold, `` `code` `` has gray background, code blocks use dark background
- Copy button copies the raw text correctly

- [ ] **Step 11: Commit**

```bash
git add app/chat.py tests/test_markdown.py
git commit -m "feat: replace CTkLabel with tk.Text markdown rendering in MessageBubble"
```

---

## Task 11: Add Stop button to `ChatTab` (`app/chat.py`)

**Files:**
- Modify: `app/chat.py`
- Modify: `app/chat.py` (stream_chat signature)

- [ ] **Step 1: Add `_stop_event` to `ChatTab.__init__`**

In `ChatTab.__init__`, after `self._ime_composing = False`:
```python
        self._stop_event = threading.Event()
```

- [ ] **Step 2: Add `stop_event` parameter to `stream_chat`**

Change the function signature from:
```python
def stream_chat(
    messages: list[dict],
    model: str,
    on_chunk: Callable[[str], None],
    on_done: Callable[[], None],
    on_error: Callable[[str], None],
    max_tokens: int = 2048,
    use_tools: bool = False,
    on_tool_call: Callable[[str, str], None] | None = None,
    on_messages_update: Callable[[list[dict]], None] | None = None,
):
```
To:
```python
def stream_chat(
    messages: list[dict],
    model: str,
    on_chunk: Callable[[str], None],
    on_done: Callable[[], None],
    on_error: Callable[[str], None],
    max_tokens: int = 2048,
    use_tools: bool = False,
    on_tool_call: Callable[[str, str], None] | None = None,
    on_messages_update: Callable[[list[dict]], None] | None = None,
    stop_event: "threading.Event | None" = None,
):
```

- [ ] **Step 3: Add stop checks inside `_worker` — tool loop**

In the `if use_tools:` agentic loop, at the top of the `for _ in range(5):` body:
```python
                for _ in range(5):
                    if stop_event and stop_event.is_set():
                        if on_messages_update:
                            on_messages_update(msgs)
                        on_done()
                        return
                    # ... rest of the loop unchanged
```

- [ ] **Step 4: Add stop check inside `_worker` — SSE loop**

In the plain streaming `for line in resp.iter_lines():` loop, add check at the top:
```python
                    for line in resp.iter_lines():
                        if stop_event and stop_event.is_set():
                            break
                        if not line.startswith("data: "):
                            continue
                        # ... rest unchanged
```
After the loop ends (the `on_done()` call outside the `with` block), this already fires — no change needed there.

- [ ] **Step 5: Wire stop_event in `_send` and `_retry`**

In `_send`, clear the event before streaming and pass it:
```python
        self._stop_event.clear()
        stream_chat(
            messages=self._messages,
            model=self._current_model(),
            on_chunk=self._on_chunk,
            on_done=self._on_done,
            on_error=self._on_error,
            use_tools=use_tools,
            on_tool_call=self._on_tool_call,
            on_messages_update=self._on_messages_update,
            stop_event=self._stop_event,
        )
```

In `_retry`, same addition:
```python
        self._stop_event.clear()
        stream_chat(
            messages=self._messages,
            model=self._current_model(),
            on_chunk=self._on_chunk,
            on_done=self._on_done,
            on_error=self._on_error,
            use_tools=self._tools_var.get(),
            on_tool_call=self._on_tool_call,
            on_messages_update=self._on_messages_update,
            stop_event=self._stop_event,
        )
```

- [ ] **Step 6: Change Send button to Stop during streaming**

In `_send`, replace:
```python
        self._send_btn.configure(state="disabled", text="...")
```
With:
```python
        self._send_btn.configure(
            text="Stop", fg_color=theme.RED, hover_color="#8c1c22",
            state="normal", command=self._stop_streaming,
        )
```

In `_retry`, same replacement.

- [ ] **Step 7: Add `_stop_streaming` method**

```python
    def _stop_streaming(self):
        self._stop_event.set()
        self._send_btn.configure(state="disabled", text="Stopping...")
```

- [ ] **Step 8: Restore Send button state in `_finish` and `_show_error`**

In `_finish`, replace:
```python
        self._send_btn.configure(state="normal", text="Send")
```
With:
```python
        self._send_btn.configure(
            state="normal", text="Send",
            fg_color=theme.BLUE, hover_color=theme.BLUE_H,
            command=self._send,
        )
        if self._stop_event.is_set():
            self._status.configure(text="Stopped.", text_color=theme.MUTED)
            self.after(2000, lambda: self._status.configure(text=""))
```

In `_show_error`, replace:
```python
        self._send_btn.configure(state="normal", text="Send")
```
With:
```python
        self._send_btn.configure(
            state="normal", text="Send",
            fg_color=theme.BLUE, hover_color=theme.BLUE_H,
            command=self._send,
        )
```

- [ ] **Step 9: Manual verification**

```bash
python main.py
```

Open Chat tab. Send a message. While streaming, confirm the button shows "Stop" in red. Click Stop — confirm streaming halts, partial response stays in the bubble, status shows "Stopped." briefly, button returns to "Send".

- [ ] **Step 10: Commit**

```bash
git add app/chat.py
git commit -m "feat: add stop button to cancel streaming in Chat tab"
```

---

## Task 12: Add `DashboardTab.notify_status` and wire activation feedback

**Files:**
- Modify: `app/gui.py`

This task adds `notify_status` to `DashboardTab`, threads the callback through `ModelsTab` and `ModelRow`, and adds richer activation button states.

- [ ] **Step 1: Add `notify_status` to `DashboardTab`**

At the end of `DashboardTab` class, after `on_destroy`:
```python
    def notify_status(self, text: str, color: str = ""):
        self._status_msg.configure(
            text=text,
            text_color=color or theme.MUTED,
        )
```

- [ ] **Step 2: Pass `dashboard_notify_cb` to `ModelsTab`**

In `App._build_ui`, change the `ModelsTab` construction:
```python
        self._models_tab = ModelsTab(
            self._tabs.tab("Models"),
            server=self._server,
            dashboard_notify_cb=self._dashboard.notify_status,
        )
```

- [ ] **Step 3: Accept and store `dashboard_notify_cb` in `ModelsTab`**

Change `ModelsTab.__init__`:
```python
    def __init__(self, master, server: ServerManager,
                 dashboard_notify_cb=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._server = server
        self._dashboard_notify = dashboard_notify_cb or (lambda *a: None)
        self._rows: list[ModelRow] = []
        self._build_ui()
        self._schedule_refresh()
```

- [ ] **Step 4: Pass `dashboard_notify_cb` to each `ModelRow`**

In `ModelsTab._build_ui`, change the `ModelRow` construction inside the loop:
```python
            row = ModelRow(
                self._scroll,
                model=model,
                server=self._server,
                notify_cb=self._notify,
                dashboard_notify_cb=self._dashboard_notify,
            )
```

Also in `ModelsTab._add_custom_model`:
```python
        row = ModelRow(
            self._scroll,
            model=model,
            server=self._server,
            notify_cb=self._notify,
            dashboard_notify_cb=self._dashboard_notify,
        )
```

- [ ] **Step 5: Accept and use `dashboard_notify_cb` in `ModelRow`**

Change `ModelRow.__init__`:
```python
    def __init__(self, master, model: ModelInfo, server: ServerManager,
                 notify_cb, dashboard_notify_cb=None, **kwargs):
        ...
        self._notify            = notify_cb
        self._dashboard_notify  = dashboard_notify_cb or (lambda *a: None)
```

- [ ] **Step 6: Add richer activation states + dashboard notifications in `_activate`**

Replace the `_activate` method entirely:
```python
    def _activate(self):
        self._btn.configure(state="disabled", text="Applying model…",
                            fg_color=theme.AMBER, text_color="#ffffff")
        self._notify(f"Activating {self._model.display_name}…", theme.AMBER)

        def _worker():
            ok, msg = activate_model(self._model)
            if ok and (self._server.ovms_running or self._server.proxy_running):
                self.after(0, lambda: self._btn.configure(text="Stopping stack…"))
                self.after(0, lambda: self._dashboard_notify(
                    "Restarting stack for new model…", theme.AMBER))
                self._server.stop_stack()
                time.sleep(1)
                self.after(0, lambda: self._btn.configure(text="Starting stack…"))
                ok2, msg2 = self._server.start_stack()
                self.after(0, lambda: self._dashboard_notify("", theme.MUTED))
                if not ok2:
                    msg += f" (restart warning: {msg2})"

            self.after(0, lambda: self._on_activate_done(ok, msg))

        threading.Thread(target=_worker, daemon=True).start()
```

- [ ] **Step 7: Manual verification**

```bash
python main.py
```

1. Start the stack (Dashboard → Start Stack, wait for green).
2. Go to Models tab, click Activate on a downloaded model.
3. Confirm button cycles through "Applying model…" → "Stopping stack…" → "Starting stack…".
4. Confirm Dashboard status message shows "Restarting stack for new model…" in amber during restart, then clears.
5. Confirm model becomes Active after completion.

- [ ] **Step 8: Commit**

```bash
git add app/gui.py
git commit -m "feat: add dashboard activation feedback and richer model activation states"
```

---

## Task 13: Final migration of `app/chat.py` to theme

**Files:**
- Modify: `app/chat.py`

- [ ] **Step 1: Replace local constants with theme import**

Remove the local constants block (lines 22–38 in original):
```python
_GREEN   = "#107c10"
_RED     = "#a4262c"
...
_CHAT_BG = "#f3f4f6"
```
Add after existing imports:
```python
from app import theme
```

Replace all `_NAME` → `theme.NAME` throughout `chat.py`. Note the chat-specific ones:
- `_USER_BG` → `theme.USER_BG`
- `_ASSIST_BG` → `theme.ASSIST_BG`
- `_SYSTEM_BG` → `theme.SYSTEM_BG`
- `_CHAT_BG` → `theme.CHAT_BG`

In `MessageBubble`, the class-level dicts use the constants:
```python
    _ROLE_COLORS   = {"user": theme.BLUE,  "assistant": theme.GREEN, "system": theme.TEXT2}
    _BORDER_COLORS = {"user": "#bfdbfe", "assistant": "#bbf7d0", "system": theme.BORDER}
    _BG_COLORS     = {"user": theme.USER_BG, "assistant": theme.ASSIST_BG, "system": theme.SYSTEM_BG}
```

- [ ] **Step 2: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass (smoke, theme, config, models, markdown).

- [ ] **Step 3: Final end-to-end manual verification**

```bash
python main.py
```

Verify each tab in order: Setup, Dashboard, Models, Chat (send a message, stop mid-stream, check markdown), Guide, About, Settings (device dropdown, save settings). No visual regressions.

- [ ] **Step 4: Commit**

```bash
git add app/chat.py
git commit -m "refactor: migrate chat to shared theme module"
```

---

## Self-Review Checklist

### Spec coverage

| Spec section | Covered by task |
|-------------|----------------|
| 1 — theme.py | Task 2, 3, 4, 5, 13 |
| 2a — duplicate method | Task 4 |
| 2b — log handles | Task 6 |
| 2c — import time | Task 5 |
| 2d — global status | Task 4 |
| 3a — tk.Text markdown | Task 10 |
| 3b — stop button | Task 11 |
| 3c — dynamic wraplength | Task 10 step 6 (`set_wrap`) |
| 4a — ovms_device config | Task 7 |
| 4b — device dropdown | Task 9 |
| 4c — GRAPH_TEMPLATE device | Task 8 |
| 5a — dashboard notify | Task 12 |
| 5b — activation button states | Task 12 step 6 |

All sections covered. ✓

### Type consistency

- `_apply_markdown(widget: tk.Text, text: str)` — defined Task 10, used Task 10 (finish) ✓
- `_auto_height(widget: tk.Text)` — defined Task 10, called inside `_apply_markdown` and `append` ✓
- `_insert_inline(widget, line)` — defined Task 10, called from `_apply_markdown` ✓
- `notify_status(text, color)` — defined Task 12 step 1, called Task 12 step 6 ✓
- `dashboard_notify_cb` kwarg — passed App→ModelsTab (Task 12 step 2), accepted ModelsTab (step 3), passed to ModelRow (step 4), accepted ModelRow (step 5) ✓
- `stop_event` kwarg on `stream_chat` — added Task 11 step 2, passed Task 11 steps 5 ✓
- `cfg.ovms_device` — defined Task 7, used Task 8 ✓

### Placeholder scan

No TBD, TODO, "similar to", "add appropriate" patterns found. ✓
