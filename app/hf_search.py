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
