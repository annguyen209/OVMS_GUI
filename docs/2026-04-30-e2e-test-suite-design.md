# E2E Test Suite Design

**Date:** 2026-04-30
**Scope:** Automated end-to-end GUI test suite for OpenVINO Manager
**Approach:** App Test Harness — visible app window + floating test panel, real services, no mocks

---

## Goals

- Run every major user flow automatically without human interaction
- App window stays visible so failures can be watched live
- Test panel overlays the app showing step-by-step progress, pass/fail, elapsed time
- Continue on failure: mark step ❌, skip dependents, keep running

---

## Architecture

Three new files. One environment-gated hook in `App.__init__`. No changes to existing app logic.

```
tests/
  e2e/
    __init__.py
    runner.py       ← test definitions + orchestration loop
    panel.py        ← floating CTkToplevel test panel UI
app/
  test_harness.py   ← actions + wait helpers that drive the widget tree
```

**Entry point:**
```bash
OVMS_E2E_TEST=1 python tests/e2e/runner.py
```

**Bootstrap sequence:**
1. `runner.py` creates `App()` — normal maximized window, full UI
2. Creates `TestPanel(app)` — floating window, top-right of screen, always-on-top
3. Creates `TestHarness(app)` — stores refs to internal widgets
4. User clicks **Run All** in the panel
5. Runner chains steps via `app.after(0, next_step)` — never blocks tkinter event loop

**Hook in `App.__init__`** (last line):
```python
if os.environ.get("OVMS_E2E_TEST"):
    from app.test_harness import TestHarness
    self._test_harness = TestHarness(self)
```

---

## TestHarness API (`app/test_harness.py`)

```python
class TestHarness:
    setup:     SetupHarness
    models:    ModelsHarness
    dashboard: DashboardHarness
    chat:      ChatHarness
    settings:  SettingsHarness

    def tab(self, name: str) -> "TestHarness"
    def wait(self, condition_fn, timeout=60, poll=0.5) -> None  # raises TestTimeout
```

### SetupHarness
```python
install_all()                       # clicks Install All button
wait_all_ok(timeout=120)            # polls until badge == "All components installed"
remove(component_name: str)         # clicks Remove on matching row
install(component_name: str)        # clicks Install on matching row
status(component_name: str) -> str  # "Installed" | "Not found" | "Checking..."
```

### ModelsHarness
```python
download(display_name: str)                    # clicks Download on matching row
cancel(display_name: str)                      # clicks Cancel on matching row
activate(display_name: str)                    # clicks Activate on matching row
state(display_name: str) -> str                # "Not downloaded" | "Downloading X%" | "Downloaded" | "Active"
wait_downloaded(display_name: str, timeout=600)
wait_active(display_name: str, timeout=60)
```

### DashboardHarness
```python
start_stack()
stop_stack()
wait_running(timeout=60)     # polls until ovms_running and proxy_running
wait_stopped(timeout=30)
ovms_status() -> str         # "Running" | "Stopped"
proxy_status() -> str        # "Running" | "Stopped"
```

### ChatHarness
```python
set_model(name: str)
send(text: str)
wait_response(timeout=120)   # polls until _streaming == False
stop()                       # clicks Stop button
last_response() -> str       # text of last assistant bubble
clear()
```

### SettingsHarness
```python
set_device(device: str)      # selects in dropdown (GPU/CPU/NPU/AUTO)
get_device() -> str
save()                       # clicks Save Settings
```

### Exceptions
```python
class TestTimeout(Exception):
    step_name: str
    elapsed: float
```

---

## Test Panel UI (`tests/e2e/panel.py`)

`CTkToplevel`, always-on-top, positioned top-right of screen.

```
┌─────────────────────────────────────────────┐
│  OpenVINO Manager — E2E Tests          [×]  │
│─────────────────────────────────────────────│
│  ████████████████░░░░░░  7 / 12   0:02:14  │
│─────────────────────────────────────────────│
│  ▶ Running: Download Phi-3.5-mini...        │
│─────────────────────────────────────────────│
│  ✅  Fresh state check              0.3s   │
│  ✅  Install All components        42.1s   │
│  ✅  Remove Python venv             1.2s   │
│  ✅  Reinstall Python venv         38.4s   │
│  ✅  Download Phi-3.5-mini        84.2s   │
│  ✅  Cancel download (DeepSeek)    12.1s   │
│  ⏳  Activate Phi-3.5-mini         ...     │
│  ○   Dashboard: verify running             │
│  ○   Chat: send message                    │
│  ○   Chat: stop streaming                  │
│  ○   Settings: change device               │
│  ○   Stop stack                            │
│─────────────────────────────────────────────│
│  [Run All]  [Stop]        Passed: 6  ❌ 0  │
└─────────────────────────────────────────────┘
```

**Step states:**
- `○` pending
- `⏳` running (animated label)
- `✅` passed (green)
- `❌` failed (red, shows error on hover or in log area)
- `⊘` skipped — dependency failed (grey)

**Controls:**
- **Run All** — starts full suite from step 1
- **Stop** — aborts after current step finishes
- Scrollable step list

---

## Test Suite (`tests/e2e/runner.py`)

### Step definition
```python
@dataclass
class Step:
    id: str
    label: str
    fn: Callable[[TestHarness], None]
    depends_on: list[str] = field(default_factory=list)
    timeout: int = 60
    desc: str = ""
```

### 12 test steps

| # | ID | Label | Depends on | Timeout |
|---|----|-------|------------|---------|
| 1 | `fresh_state` | Fresh state check | — | 10s |
| 2 | `install_all` | Install All components | — | 300s |
| 3 | `remove_venv` | Remove Python venv | install_all | 30s |
| 4 | `reinstall_venv` | Reinstall Python venv | remove_venv | 120s |
| 5 | `download_model` | Download Phi-3.5-mini (~2 GB) | install_all | 600s |
| 6 | `cancel_download` | Cancel download (DeepSeek-R1-1.5B) | install_all | 60s |
| 7 | `activate_model` | Activate Phi-3.5-mini | download_model | 60s |
| 8 | `verify_stack` | Dashboard: verify stack running | activate_model | 60s |
| 9 | `chat_send` | Chat: send message | verify_stack | 120s |
| 10 | `chat_stop` | Chat: stop streaming | verify_stack | 30s |
| 11 | `settings_device` | Settings: change device | — | 10s |
| 12 | `stop_stack` | Stop stack | verify_stack | 30s |

### Step implementations (summary)

**fresh_state**: Navigate to Dashboard, assert OVMS Stopped, Proxy Stopped, Active Model None.

**install_all**: `harness.tab("Setup").setup.install_all()` → `setup.wait_all_ok(300)`.

**remove_venv**: `setup.remove("Python 3.x venv")` → `harness.wait(lambda: setup.status("Python 3.x venv") == "Not found", 30)`.

**reinstall_venv**: `setup.install("Python 3.x venv")` → `harness.wait(lambda: setup.status("Python 3.x venv") == "Installed", 120)`.

**download_model**: `harness.tab("Models").models.download("Phi-3.5-mini")` → `models.wait_downloaded("Phi-3.5-mini", 600)`.

**cancel_download**: `models.download("DeepSeek-R1-1.5B")` → wait 5s → `models.cancel("DeepSeek-R1-1.5B")` → `harness.wait(lambda: models.state("DeepSeek-R1-1.5B") == "Not downloaded", 30)`.

**activate_model**: `models.activate("Phi-3.5-mini")` → `models.wait_active("Phi-3.5-mini", 60)`.

**verify_stack**: `harness.tab("Dashboard")` → `dashboard.wait_running(60)` → assert both status cards green.

**chat_send**: `harness.tab("Chat").chat.set_model(...)` → `chat.send("Say hello in one sentence")` → `chat.wait_response(120)` → assert `last_response()` non-empty.

**chat_stop**: `chat.send("Write a very long essay about artificial intelligence")` → sleep 2s → `chat.stop()` → assert status shows "Stopped."

**settings_device**: `harness.tab("Settings").settings.set_device("CPU")` → assert `get_device() == "CPU"` → `settings.set_device("GPU")`.

**stop_stack**: `dashboard.stop_stack()` → `dashboard.wait_stopped(30)` → assert both Stopped.

### Runner orchestration loop

```python
def _run_next(self, idx: int):
    if idx >= len(TESTS):
        self._panel.finish(self._results)
        return
    step = TESTS[idx]
    if self._should_skip(step):
        self._results[step.id] = SKIPPED
        self._panel.mark(step, SKIPPED)
        self._app.after(0, lambda: self._run_next(idx + 1))
        return
    self._panel.mark(step, RUNNING)
    start = time.time()
    try:
        step.fn(self._harness)
        elapsed = time.time() - start
        self._results[step.id] = PASSED
        self._panel.mark(step, PASSED, elapsed=elapsed)
    except (TestTimeout, AssertionError, Exception) as e:
        elapsed = time.time() - start
        self._results[step.id] = FAILED
        self._panel.mark(step, FAILED, error=str(e), elapsed=elapsed)
    self._app.after(0, lambda: self._run_next(idx + 1))

def _should_skip(self, step: Step) -> bool:
    return any(self._results.get(dep) == FAILED for dep in step.depends_on)
```

---

## Files Changed / Created

| File | Action |
|------|--------|
| `app/test_harness.py` | **Create** |
| `tests/e2e/__init__.py` | **Create** |
| `tests/e2e/runner.py` | **Create** |
| `tests/e2e/panel.py` | **Create** |
| `app/gui.py` | Modify — add env-gated harness hook in `App.__init__` |

---

## Out of Scope

- Screenshot/visual regression testing
- Performance benchmarks
- Network failure simulation
- Multi-model concurrent test
