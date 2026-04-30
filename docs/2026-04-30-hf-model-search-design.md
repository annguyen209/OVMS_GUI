# HuggingFace Model Search Design

**Date:** 2026-04-30
**Scope:** Add a HuggingFace model search panel to the Models tab
**Approach:** B — keep curated list, add collapsible HF search panel below it

---

## Goal

Let users discover and add OpenVINO LLM models from HuggingFace directly inside the app, without hardcoding a fixed list or requiring manual repo ID entry.

---

## Architecture

One new file: `app/hf_search.py` — encapsulates the HF API call and result parsing.
One modified file: `app/gui.py` — adds `HFSearchPanel` widget to `ModelsTab`.

No changes to existing `ModelRow`, `ModelInfo`, or download logic.

---

## Section 1: Search Panel UI

### Placement

Collapsible panel at the bottom of `ModelsTab`, below the custom model input and above the tab's bottom edge. Default state: **collapsed**.

### Collapsed state

```
┌─────────────────────────────────────────────────────────┐
│  Search HuggingFace Models                    [Expand ▾]│
└─────────────────────────────────────────────────────────┘
```

A single card with a toggle button. Clicking "Expand" reveals the full panel.

### Expanded state

```
┌─────────────────────────────────────────────────────────┐
│  Search HuggingFace Models                    [Close ▴] │
├─────────────────────────────────────────────────────────┤
│  [_________________________]  [Text Gen ▾]  [Search]    │
│                                                         │
│  (results area — scrollable)                            │
│  ┌──────────────────────────────────────────────────┐   │
│  │ OpenVINO/Qwen2.5-7B-Instruct-int4-ov   4.2k ↓ [Add] │
│  │ OpenVINO/Llama-3.2-1B-int4-ov          2.1k ↓ [Add] │
│  │ ...                                                  │
│  └──────────────────────────────────────────────────┘   │
│                               [Load more (20 shown)]    │
└─────────────────────────────────────────────────────────┘
```

### Controls

| Control | Behaviour |
|---------|-----------|
| Search field | Free text; Enter key triggers search |
| Filter dropdown | Text Generation / Code Generation / Reasoning (maps to `pipeline_tag`) |
| Search button | Triggers API call in background thread |
| Load more | Fetches next 20 results (increments `offset`) |
| Add | Creates ModelInfo, adds ModelRow to scroll list; button becomes "Added" (disabled) |

### States

- **Idle**: empty results area, placeholder text "Search for OpenVINO LLM models on HuggingFace"
- **Searching**: spinner label "Searching…"
- **Results**: list of result rows
- **Error**: inline message "Could not reach HuggingFace. Check your connection." (no dialog)
- **No results**: "No models found. Try a different query."

---

## Section 2: HF API Integration (`app/hf_search.py`)

### Endpoint

```
GET https://huggingface.co/api/models
  ?filter=openvino
  &pipeline_tag=<tag>
  &sort=downloads
  &direction=-1
  &search=<query>
  &limit=20
  &offset=<offset>
```

`pipeline_tag` values:
- "Text Generation" → `text-generation`
- "Code Generation" → `text-generation` + search appended with "coder"
- "Reasoning" → `text-generation` + search appended with "reasoning"

### Response → ModelInfo mapping

| HF field | Use |
|----------|-----|
| `modelId` | `hf_repo_id` |
| last segment of `modelId` | `display_name` (max 40 chars) |
| `downloads` | shown in result row as "X.Xk ↓" |
| — | `size_label = "?"` |
| — | `notes = ""` |

### API function signature

```python
def search_hf_models(
    query: str,
    pipeline_tag: str = "text-generation",
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[dict], str]:
    """
    Returns (results, error_message).
    results: list of {"model_id", "downloads"} dicts.
    error_message: empty string on success.
    Runs synchronously — caller must use a background thread.
    """
```

### Error handling

- `httpx.ConnectError` / `httpx.TimeoutException` → return `([], "Could not reach HuggingFace.")`
- Non-200 status → return `([], f"HuggingFace returned {status}.")`
- JSON parse error → return `([], "Unexpected response format.")`

---

## Section 3: Model Addition Flow

`HFSearchPanel._add(model_id, downloads)`:
1. Creates `ModelInfo(hf_repo_id=model_id, display_name=<last segment>, size_label="?", notes="")`
2. Calls `self._models_tab._add_from_hf(model)` — new method on `ModelsTab` (same logic as `_add_custom_model` but without clearing any input fields)
3. Marks the result row's [Add] button as "Added" (disabled, green text) so the user can't double-add

`ModelsTab._add_from_hf(model: ModelInfo)`:
- Appends a new `ModelRow` to `self._scroll` and `self._rows`
- Shows notification: "Added: {display_name}"

---

## Files Changed

| File | Action |
|------|--------|
| `app/hf_search.py` | **Create** — `search_hf_models()` function |
| `app/gui.py` | Modify — add `HFSearchPanel` class + wire into `ModelsTab._build_ui` + add `ModelsTab._add_from_hf` |

---

## Out of Scope

- Showing model file size from HF (requires per-model API call, too slow)
- Filtering by quantization format (int4, int8, fp16)
- Model card preview
- Authentication for gated models
