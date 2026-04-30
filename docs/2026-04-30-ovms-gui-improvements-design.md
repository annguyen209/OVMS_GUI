# OVMS GUI — Code Review & Improvement Design

**Date:** 2026-04-30  
**Scope:** Bug fixes, UX polish, shared theme, markdown rendering, device selector, activation feedback  
**Approach:** C (full improvement pass)

---

## 1. Shared Theme Module (`app/theme.py`)

### Problem
Color constants (`_BLUE`, `_RED`, `_CARD`, etc.) are copy-pasted across 6 files:
`gui.py`, `chat.py`, `setup_tab.py`, `about.py`, `guide.py`, `log_viewer.py`.
Any palette change requires editing every file.

### Solution
Create `app/theme.py` that exports all palette values as module-level constants (no leading underscore — public API):

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

Each of the 6 files removes its local constants block and adds:
```python
from app import theme
```
All references change from `_BLUE` → `theme.BLUE`, `_CARD` → `theme.CARD`, etc.

**Impact:** Mechanical find-and-replace per file. No logic changes.

---

## 2. Bug Fixes

### 2a — Duplicate `_refresh_aggregate` (`setup_tab.py`)

**Problem:** `_refresh_aggregate` is defined twice (lines 381 and 382). The second definition silently overrides the first. Dead code.

**Fix:** Delete lines 381–383 (the first definition). Keep the second definition unchanged.

### 2b — Log file handle leaks (`server.py`)

**Problem:** `_start_ovms` and `_start_proxy` open `log_fh` as local variables. They go out of scope immediately after `Popen`, relying on garbage collection to close them. On Windows, unclosed handles can block log file rotation and cause `PermissionError` on reopening.

**Fix:**
- Add `self._ovms_log_fh: IO | None = None` and `self._proxy_log_fh: IO | None = None` to `ServerManager.__init__`.
- In `_start_ovms`, assign `self._ovms_log_fh = log_fh` before `Popen`.
- In `_start_proxy`, assign `self._proxy_log_fh = log_fh` before `Popen`.
- In `stop_stack`, after stopping each process, close and null the corresponding handle:
  ```python
  if self._ovms_log_fh:
      self._ovms_log_fh.close()
      self._ovms_log_fh = None
  ```
- In `shutdown()`, close any remaining open handles.

### 2c — Inline `import time` in `gui.py`

**Problem:** `ModelRow._activate` worker lambda contains `import time; time.sleep(1)` inline.

**Fix:** Add `import time` to the top-level imports in `gui.py`. The `time.sleep(1)` call stays in the worker thread (it is intentional — waits for OVMS to finish shutting down before restart).

### 2d — Global status label not updated after all-ok (`setup_tab.py`)

**Problem:** When all components pass, `_apply_aggregate(True)` updates the badge but leaves `_global_status` showing stale "Checking components…" text.

**Fix:** Inside `_apply_aggregate`:
- When `ok=True`: `self._global_status.configure(text="All components ready.", text_color=theme.GREEN)`
- When `ok=False`: `self._global_status.configure(text="Some components missing.", text_color=theme.AMBER)`

---

## 3. Chat Tab Improvements (`app/chat.py`)

### 3a — Markdown rendering with `tk.Text` tags

**Problem:** `MessageBubble` uses a `CTkLabel` with `textvariable`. At stream completion, `_strip_markdown` replaces the displayed text — causing a visible flash and losing all formatting.

**Solution:** Replace the content `CTkLabel` with a `tk.Text` widget. A `_render_markdown(widget, text)` helper clears the widget and re-inserts the text with tag formatting applied.

**Tag definitions** (configured once per bubble on creation):

| Tag name | Applied to | Config |
|----------|-----------|--------|
| `bold` | `**text**` | `font weight="bold"` |
| `italic` | `*text*` | `font slant="italic"` |
| `code_inline` | `` `text` `` | `family="Consolas"`, `background="#f1f5f9"` |
| `code_block` | ```` ```block``` ```` | `family="Consolas"`, `background="#1e293b"`, `foreground="#e2e8f0"` |
| `heading` | `## Header` | `size=14, weight="bold"` |

**Streaming behaviour:**
- During streaming: `append(text)` inserts raw text directly into `tk.Text` using `widget.insert("end", text)` — no parse overhead per chunk.
- On `_finish()`: call `_render_markdown(widget, full_text)` once — clears and re-inserts with tags.
- `_strip_markdown` function and all calls to it are removed entirely.

**`MessageBubble` structural changes:**
- Remove `self._text_var = tk.StringVar()`
- Remove `self._label = ctk.CTkLabel(...)`
- Add `self._textbox = tk.Text(...)` — `state="disabled"`, `relief="flat"`, `wrap="word"`, `height=1` (auto-grows via `yscrollcommand` or frame resize)
- `append(text)`: enable → insert → disable
- `get_text()`: `self._textbox.get("1.0", "end-1c")`
- `set_wrap(width)`: `self._textbox.configure(width=max(40, (width - 120) // 8))`

### 3b — Stop/Cancel streaming button

**Problem:** Once streaming starts, the user cannot cancel it. The UI is locked until completion.

**Solution:**
- Add `self._stop_event = threading.Event()` to `ChatTab`.
- `_stop_event.clear()` before each `stream_chat` call.
- Pass `stop_event=self._stop_event` to `stream_chat`.
- In `stream_chat._worker` SSE loop: check `stop_event.is_set()` between each `line`; `break` if set.
- For the tool-call agentic loop: check `stop_event.is_set()` at the top of each round.
- While streaming, Send button changes to **Stop** (red, `fg_color=theme.RED`), calling `self._stop_event.set()`.
- On stop: partial response is kept. `_finish()` runs normally. Status label shows `"Stopped."` briefly, then clears.

**Button state machine:**
```
Idle        → [Send]  (blue)
Streaming   → [Stop]  (red)
After stop  → [Send]  (blue, re-enabled)
```

### 3c — Dynamic wraplength

**Problem:** `wraplength=700` hardcoded in `CTkLabel`. With the switch to `tk.Text`, wrapping is handled by `wrap="word"` + `width` in character columns.

**Fix:** `set_wrap(pixel_width)` sets `self._textbox.configure(width=max(40, (pixel_width - 120) // 8))`. Called from `ChatTab._on_resize` for all bubbles (existing call site, just the method body changes).

---

## 4. Device Selector for OVMS

### 4a — Config key (`app/config.py`)

Add to `DEFAULTS`:
```python
"ovms_device": "GPU",
```
Add typed property:
```python
@property
def ovms_device(self) -> str:
    return self._data.get("ovms_device", "GPU")
```

### 4b — Settings tab dropdown (`app/gui.py`)

Add a new section in `SettingsTab._build_ui`, after the scrollable path fields frame and before the Windows Startup label. Since the scrollable frame uses `fill="both", expand=True`, the device card must be packed **before** the scrollable frame in code order (pack order determines layout), so it appears above it — or alternatively, move it inside the scrollable frame as an extra row. Preferred: add it **inside the scrollable frame** as a clearly separated row after the port fields, so it scrolls with the rest of the settings.

```
┌─────────────────────────────────────────────────┐
│ Inference Device                                 │
│  [GPU ▾]   GPU / CPU / NPU / AUTO               │
│  Takes effect the next time you activate a model.│
└─────────────────────────────────────────────────┘
```

Implementation:
- `CTkOptionMenu` with values `["GPU", "CPU", "NPU", "AUTO"]`
- Initial value: `cfg.ovms_device`
- `command=lambda v: cfg.set("ovms_device", v)` — saves immediately, no Save button needed
- Muted `CTkLabel` hint below

### 4c — Device param in graph.pbtxt (`app/models.py`)

Change `GRAPH_TEMPLATE`:
```python
      device: "{device}"
```

Change `activate_model`:
```python
graph_content = GRAPH_TEMPLATE.format(
    model_path=model_path_str,
    device=cfg.ovms_device,
)
```

---

## 5. Model Activation Feedback (`app/gui.py`)

### 5a — Dashboard status during activation

**Problem:** Stack restarts silently during model activation. Dashboard shows no feedback.

**Solution:** Add `notify_status(text, color)` method to `DashboardTab`:
```python
def notify_status(self, text: str, color: str = theme.MUTED):
    self._status_msg.configure(text=text, text_color=color)
```

`App` passes a **separate** `dashboard_notify_cb=self._dashboard.notify_status` kwarg to `ModelsTab` (distinct from the existing `notify_cb` which drives the Models tab notification bar). `ModelsTab` stores it and passes it to each `ModelRow` as `dashboard_notify_cb`. `ModelRow` stores it as `self._notify_dashboard`.

In `ModelRow._activate._worker`:
1. Before `stop_stack()`: `self._notify_dashboard("Restarting stack for new model…", theme.AMBER)`
2. After `start_stack()`: `self._notify_dashboard("", theme.MUTED)` (clear)

### 5b — Richer activation button states

Button text progression (all while disabled):

| Stage | Text | Color |
|-------|------|-------|
| Click | `"Activating…"` | amber |
| Writing config | `"Applying model…"` | amber |
| Stopping stack | `"Stopping stack…"` | amber |
| Starting stack | `"Starting stack…"` | amber |
| Done (ok) | refreshed to `"Active"` | — |
| Done (error) | refreshed to `"Activate"` | — |

Each stage calls `self.after(0, lambda t=text, c=color: self._btn.configure(text=t, fg_color=c))`.

---

## Files Changed

| File | Change type |
|------|------------|
| `app/theme.py` | **New file** |
| `app/gui.py` | Theme import, `import time` move, Settings device dropdown, activation feedback, notify_status |
| `app/chat.py` | Theme import, `tk.Text` markdown, stop button, dynamic wrap |
| `app/setup_tab.py` | Theme import, remove duplicate method, fix global status |
| `app/about.py` | Theme import only |
| `app/guide.py` | Theme import only |
| `app/log_viewer.py` | Theme import only |
| `app/server.py` | Log handle management |
| `app/models.py` | Device param in GRAPH_TEMPLATE |
| `app/config.py` | `ovms_device` key + property |

---

## Out of Scope

- Real-time incremental markdown rendering during streaming (stream first, format on done)
- HuggingFace authentication tokens for gated models
- Async rewrite of streaming
- Dark mode support
