# HuggingFace Model Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a collapsible HuggingFace search panel to the Models tab so users can discover and add OpenVINO LLM models without a hardcoded list.

**Architecture:** Two changes — a new `app/hf_search.py` module that wraps the HF Hub API, and a new `HFSearchPanel` widget + `ModelsTab._add_from_hf` method in `app/gui.py`. The search panel sits below the existing custom model input and is collapsed by default.

**Tech Stack:** Python 3.x, httpx (already a dependency), customtkinter, threading (stdlib)

---

## File Map

| File | Action |
|------|--------|
| `app/hf_search.py` | **Create** — `search_hf_models()` + `FILTER_OPTIONS` |
| `app/gui.py` | Modify — add `HFSearchPanel` class + `ModelsTab._add_from_hf` + wire into `ModelsTab._build_ui` |
| `tests/test_hf_search.py` | **Create** — unit tests for the API wrapper |

---

## Task 1: `app/hf_search.py` — API wrapper

**Files:**
- Create: `app/hf_search.py`
- Create: `tests/test_hf_search.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_hf_search.py`:

```python
from unittest.mock import patch, MagicMock
import httpx as _httpx
import pytest


def test_successful_search():
    from app.hf_search import search_hf_models
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"modelId": "OpenVINO/Qwen2.5-7B-int4-ov", "downloads": 5000},
        {"modelId": "OpenVINO/Llama-3-8B-int4-ov", "downloads": 3000},
    ]
    with patch("app.hf_search.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
        results, error = search_hf_models("qwen")
    assert error == ""
    assert len(results) == 2
    assert results[0]["model_id"] == "OpenVINO/Qwen2.5-7B-int4-ov"
    assert results[0]["downloads"] == 5000


def test_connection_error():
    from app.hf_search import search_hf_models
    with patch("app.hf_search.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = \
            _httpx.ConnectError("fail")
        results, error = search_hf_models("qwen")
    assert results == []
    assert "Could not reach" in error


def test_timeout_error():
    from app.hf_search import search_hf_models
    with patch("app.hf_search.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = \
            _httpx.TimeoutException("timeout")
        results, error = search_hf_models("qwen")
    assert results == []
    assert "timed out" in error


def test_non_200_response():
    from app.hf_search import search_hf_models
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    with patch("app.hf_search.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
        results, error = search_hf_models("qwen")
    assert results == []
    assert "429" in error


def test_empty_query():
    from app.hf_search import search_hf_models
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []
    with patch("app.hf_search.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
        results, error = search_hf_models("")
    assert error == ""
    assert results == []


def test_filter_options_structure():
    from app.hf_search import FILTER_OPTIONS
    assert "Text Generation" in FILTER_OPTIONS
    assert "Code Generation" in FILTER_OPTIONS
    assert "Reasoning" in FILTER_OPTIONS
    for label, (tag, extra) in FILTER_OPTIONS.items():
        assert isinstance(tag, str) and tag
        assert isinstance(extra, str)


def test_offset_and_limit_passed():
    from app.hf_search import search_hf_models
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []
    with patch("app.hf_search.httpx.Client") as mock_client:
        get_mock = mock_client.return_value.__enter__.return_value.get
        get_mock.return_value = mock_resp
        search_hf_models("test", offset=20, limit=10)
    call_kwargs = get_mock.call_args
    params = call_kwargs[1].get("params") or call_kwargs[0][1]
    assert params["offset"] == 20
    assert params["limit"] == 10
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd D:/Project/OVMS_GUI
python -m pytest tests/test_hf_search.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.hf_search'`

- [ ] **Step 3: Create `app/hf_search.py`**

```python
"""
hf_search.py — HuggingFace Hub model search for OpenVINO models.
"""

import logging
from typing import Tuple

import httpx

logger = logging.getLogger(__name__)

HF_API_BASE = "https://huggingface.co/api/models"
_TIMEOUT    = 10.0

# Maps UI label → (pipeline_tag, extra_search_suffix)
FILTER_OPTIONS: dict[str, tuple[str, str]] = {
    "Text Generation": ("text-generation", ""),
    "Code Generation": ("text-generation", "coder"),
    "Reasoning":       ("text-generation", "reasoning"),
}


def search_hf_models(
    query: str,
    pipeline_tag: str = "text-generation",
    extra_search: str = "",
    offset: int = 0,
    limit: int = 20,
) -> Tuple[list[dict], str]:
    """
    Search HuggingFace Hub for OpenVINO LLM models.

    Returns (results, error_message).
    results: list of {"model_id": str, "downloads": int} dicts.
    error_message: empty string on success.

    Runs synchronously — caller must use a background thread.
    """
    search = query
    if extra_search and extra_search.lower() not in query.lower():
        search = f"{query} {extra_search}".strip()

    params: dict = {
        "filter":       "openvino",
        "pipeline_tag": pipeline_tag,
        "sort":         "downloads",
        "direction":    "-1",
        "limit":        limit,
        "offset":       offset,
    }
    if search:
        params["search"] = search

    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(HF_API_BASE, params=params)
        if resp.status_code != 200:
            return [], f"HuggingFace returned {resp.status_code}."
        data = resp.json()
        results = [
            {
                "model_id": item.get("modelId") or item.get("id", ""),
                "downloads": item.get("downloads", 0),
            }
            for item in data
            if item.get("modelId") or item.get("id")
        ]
        return results, ""
    except httpx.ConnectError:
        return [], "Could not reach HuggingFace. Check your connection."
    except httpx.TimeoutException:
        return [], "HuggingFace request timed out."
    except Exception as exc:
        logger.exception("HF search error")
        return [], f"Search error: {exc}"
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_hf_search.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add app/hf_search.py tests/test_hf_search.py
git commit -m "feat: add HuggingFace model search API wrapper"
```

---

## Task 2: `HFSearchPanel` widget + `ModelsTab._add_from_hf` in `app/gui.py`

**Files:**
- Modify: `app/gui.py`

This task adds the `HFSearchPanel` class (before `ModelsTab`) and a new `_add_from_hf` method on `ModelsTab`, then wires the panel into `ModelsTab._build_ui`.

- [ ] **Step 1: Add `HFSearchPanel` class to `app/gui.py`**

Find the line `class ModelsTab(ctk.CTkFrame):` and insert the full `HFSearchPanel` class immediately before it:

```python
# ---------------------------------------------------------------------------
# HuggingFace Model Search Panel
# ---------------------------------------------------------------------------

class HFSearchPanel(ctk.CTkFrame):
    """Collapsible panel for searching HuggingFace OpenVINO models."""

    def __init__(self, master, models_tab, **kwargs):
        kwargs.setdefault("fg_color",      theme.CARD)
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("border_width",  1)
        kwargs.setdefault("border_color",  theme.BORDER)
        super().__init__(master, **kwargs)
        self._models_tab    = models_tab
        self._expanded      = False
        self._offset        = 0
        self._last_query    = ""
        self._last_tag      = "text-generation"
        self._last_extra    = ""
        self._results_count = 0
        self._added_ids: set[str] = set()
        self._btn_map:   dict[str, ctk.CTkButton] = {}

        self._build_header()
        self._build_body()
        self._body.pack_forget()  # collapsed by default

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(
            hdr, text="Search HuggingFace Models",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=theme.TEXT2,
        ).pack(side="left")

        self._toggle_btn = ctk.CTkButton(
            hdr, text="Expand ▾", width=90, height=28,
            font=ctk.CTkFont(size=11),
            fg_color=theme.CARD2, hover_color=theme.BORDER,
            border_width=1, border_color=theme.BORDER2,
            text_color=theme.TEXT2,
            command=self._toggle,
        )
        self._toggle_btn.pack(side="right")

    def _build_body(self):
        self._body = ctk.CTkFrame(self, fg_color="transparent")

        # Search controls row
        search_row = ctk.CTkFrame(self._body, fg_color="transparent")
        search_row.pack(fill="x", padx=14, pady=(0, 6))

        self._search_entry = ctk.CTkEntry(
            search_row,
            font=ctk.CTkFont(size=12),
            placeholder_text="e.g. Qwen, Llama, Mistral…",
            height=30,
        )
        self._search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._search_entry.bind("<Return>", lambda e: self._search())

        from app.hf_search import FILTER_OPTIONS
        self._filter_labels = list(FILTER_OPTIONS.keys())
        self._filter_menu = ctk.CTkOptionMenu(
            search_row,
            values=self._filter_labels,
            font=ctk.CTkFont(size=11),
            width=140, height=30,
            fg_color=theme.CARD2,
            button_color=theme.BORDER2,
            button_hover_color=theme.BORDER,
            text_color=theme.TEXT,
            dropdown_fg_color=theme.CARD,
            dropdown_hover_color=theme.CARD2,
            dropdown_text_color=theme.TEXT,
        )
        self._filter_menu.set(self._filter_labels[0])
        self._filter_menu.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            search_row, text="Search", width=80, height=30,
            font=ctk.CTkFont(size=12),
            fg_color=theme.BLUE, hover_color=theme.BLUE_H,
            command=self._search,
        ).pack(side="left")

        # Status label
        self._status_lbl = ctk.CTkLabel(
            self._body,
            text="Search for OpenVINO LLM models on HuggingFace",
            font=ctk.CTkFont(size=11), text_color=theme.MUTED,
        )
        self._status_lbl.pack(fill="x", padx=14, pady=(0, 4))

        # Results area
        self._results_frame = ctk.CTkScrollableFrame(
            self._body, fg_color="transparent", height=200,
        )
        self._results_frame.pack(fill="x", padx=14, pady=(0, 4))

        # Load-more button (hidden until results overflow one page)
        self._load_more_btn = ctk.CTkButton(
            self._body, text="", width=160, height=28,
            font=ctk.CTkFont(size=11),
            fg_color=theme.CARD2, hover_color=theme.BORDER,
            border_width=1, border_color=theme.BORDER2,
            text_color=theme.TEXT2,
            command=self._load_more,
        )
        self._load_more_btn.pack(pady=(0, 10))
        self._load_more_btn.pack_forget()

    # ------------------------------------------------------------------
    # Toggle
    # ------------------------------------------------------------------

    def _toggle(self):
        if self._expanded:
            self._body.pack_forget()
            self._toggle_btn.configure(text="Expand ▾")
            self._expanded = False
        else:
            self._body.pack(fill="x")
            self._toggle_btn.configure(text="Close ▴")
            self._expanded = True

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _search(self, reset: bool = True):
        from app.hf_search import FILTER_OPTIONS
        query = self._search_entry.get().strip()
        label = self._filter_menu.get()
        pipeline_tag, extra_search = FILTER_OPTIONS.get(label, ("text-generation", ""))

        if reset:
            self._offset        = 0
            self._results_count = 0
            self._clear_results()

        self._last_query = query
        self._last_tag   = pipeline_tag
        self._last_extra = extra_search

        self._status_lbl.configure(text="Searching…", text_color=theme.AMBER)
        self._load_more_btn.pack_forget()

        import threading
        threading.Thread(
            target=self._fetch_worker,
            args=(query, pipeline_tag, extra_search, self._offset),
            daemon=True,
        ).start()

    def _fetch_worker(self, query, pipeline_tag, extra_search, offset):
        from app.hf_search import search_hf_models
        results, error = search_hf_models(
            query, pipeline_tag, extra_search, offset=offset, limit=20,
        )
        self.after(0, lambda: self._on_results(results, error))

    def _on_results(self, results: list, error: str):
        if error:
            self._status_lbl.configure(text=error, text_color=theme.RED)
            return
        if not results:
            self._status_lbl.configure(
                text="No models found. Try a different query.",
                text_color=theme.MUTED,
            )
            return

        self._offset        += len(results)
        self._results_count += len(results)

        for r in results:
            self._add_result_row(r["model_id"], r["downloads"])

        self._status_lbl.configure(
            text=f"{self._results_count} models found",
            text_color=theme.MUTED,
        )
        if len(results) == 20:
            self._load_more_btn.configure(
                text=f"Load more ({self._results_count} shown)")
            self._load_more_btn.pack(pady=(0, 10))
        else:
            self._load_more_btn.pack_forget()

    def _add_result_row(self, model_id: str, downloads: int):
        row = ctk.CTkFrame(
            self._results_frame, fg_color=theme.CARD2,
            corner_radius=6, border_width=1, border_color=theme.BORDER,
        )
        row.pack(fill="x", pady=2)
        row.columnconfigure(0, weight=1)

        dl_str  = f"{downloads/1000:.1f}k ↓" if downloads >= 1000 else f"{downloads} ↓"
        display = model_id.split("/")[-1]
        if len(display) > 45:
            display = display[:42] + "…"

        ctk.CTkLabel(
            row, text=display,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=theme.TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(10, 4), pady=6)

        ctk.CTkLabel(
            row, text=dl_str,
            font=ctk.CTkFont(size=10), text_color=theme.MUTED,
        ).grid(row=0, column=1, padx=4)

        is_added = model_id in self._added_ids
        add_btn  = ctk.CTkButton(
            row,
            text="Added" if is_added else "Add",
            width=60, height=26,
            font=ctk.CTkFont(size=11),
            fg_color=theme.CARD2 if is_added else theme.BLUE,
            hover_color=theme.BORDER if is_added else theme.BLUE_H,
            border_width=1 if is_added else 0,
            border_color=theme.BORDER2,
            text_color=theme.GREEN if is_added else "#ffffff",
            state="disabled" if is_added else "normal",
            command=lambda mid=model_id: self._on_add(mid),
        )
        add_btn.grid(row=0, column=2, padx=(4, 10), pady=4)
        self._btn_map[model_id] = add_btn

    def _on_add(self, model_id: str):
        from app.models import ModelInfo
        display = model_id.split("/")[-1][:40]
        model   = ModelInfo(
            hf_repo_id=model_id,
            display_name=display,
            size_label="?",
            notes="",
        )
        self._models_tab._add_from_hf(model)
        self._added_ids.add(model_id)
        btn = self._btn_map.get(model_id)
        if btn:
            btn.configure(
                text="Added", state="disabled",
                fg_color=theme.CARD2, border_width=1,
                border_color=theme.BORDER2, text_color=theme.GREEN,
            )

    def _load_more(self):
        self._search(reset=False)

    def _clear_results(self):
        for w in self._results_frame.winfo_children():
            w.destroy()
        self._btn_map.clear()
```

- [ ] **Step 2: Add `ModelsTab._add_from_hf` method**

In `ModelsTab`, find the `_add_custom_model` method and add `_add_from_hf` immediately after it:

```python
    def _add_from_hf(self, model: "ModelInfo"):
        """Add a model discovered via HF search to the models list."""
        row = ModelRow(
            self._scroll,
            model=model,
            server=self._server,
            notify_cb=self._notify,
            dashboard_notify_cb=self._dashboard_notify,
            dashboard_busy_cb=self._dashboard_busy,
        )
        row.pack(fill="x", pady=4)
        self._rows.append(row)
        self._notify(f"Added: {model.display_name}", theme.GREEN)
```

- [ ] **Step 3: Wire `HFSearchPanel` into `ModelsTab._build_ui`**

In `ModelsTab._build_ui`, find the call to `self._build_custom_panel()` and add the HF panel line immediately after it:

```python
        self._build_custom_panel()

        # HuggingFace search panel (collapsed by default)
        self._hf_panel = HFSearchPanel(self, models_tab=self)
        self._hf_panel.pack(fill="x", padx=16, pady=(0, 12))
```

- [ ] **Step 4: Verify imports**

```bash
cd D:/Project/OVMS_GUI
python -c "from app import gui; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: `41 passed` (34 existing + 7 new HF search tests)

- [ ] **Step 6: Manual smoke test**

```bash
python main.py
```

1. Open Models tab — confirm a "Search HuggingFace Models" card appears at the bottom with "Expand ▾" button
2. Click "Expand ▾" — confirm search field, filter dropdown, and Search button appear
3. Type "llama" and click Search — confirm results appear within 5 seconds
4. Click [Add] on a result — confirm a new model row appears in the main list, button becomes "Added" (green)
5. Click "Load more" if visible — confirm more results load
6. Type an invalid query (e.g. "xyznotamodel123") — confirm "No models found." message
7. Disconnect network, search — confirm "Could not reach HuggingFace." error message

- [ ] **Step 7: Commit**

```bash
git add app/gui.py
git commit -m "feat: add collapsible HuggingFace model search panel to Models tab"
```

---

## Self-Review

### Spec coverage

| Spec requirement | Covered |
|-----------------|---------|
| Collapsible panel below custom model input | Task 2 step 3 |
| Search field + filter dropdown + Search button | Task 2 step 1 (`_build_body`) |
| HF API call with filter=openvino + pipeline_tag + sort=downloads | Task 1 |
| Results show repo name + download count + [Add] button | Task 2 step 1 (`_add_result_row`) |
| [Add] creates ModelRow, button → "Added" (disabled) | Task 2 step 1 (`_on_add`) |
| Load more (20 at a time, offset pagination) | Task 2 step 1 (`_load_more`) |
| Error handling: no internet, timeout, 4xx/5xx | Task 1 (all branches) |
| "No results" message | Task 2 step 1 (`_on_results`) |
| `ModelsTab._add_from_hf` | Task 2 step 2 |

All spec sections covered. ✓

### Type consistency

- `search_hf_models(query, pipeline_tag, extra_search, offset, limit)` — defined Task 1, called in `_fetch_worker` Task 2 ✓
- `FILTER_OPTIONS: dict[str, tuple[str, str]]` — defined Task 1, unpacked as `(pipeline_tag, extra_search)` in Task 2 ✓
- `ModelInfo(hf_repo_id, display_name, size_label, notes)` — existing class, used in `_on_add` Task 2 ✓
- `ModelsTab._add_from_hf(model: ModelInfo)` — defined Task 2 step 2, called from `HFSearchPanel._on_add` Task 2 step 1 ✓
- `self._dashboard_notify`, `self._dashboard_busy` — both exist on `ModelsTab` from previous work ✓

### Placeholder scan

No TBD, TODO, "similar to", "add appropriate" patterns. ✓
