"""
models.py — Model catalog, download logic, and OVMS config writing.

Responsibilities:
- Define the curated list of OpenVINO coding models.
- Download models from HuggingFace Hub with per-file progress callbacks.
- Rewrite graph.pbtxt and config.json to activate a model.
- Detect which model is currently configured as active.
"""

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.config import cfg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# graph.pbtxt template  (GPU, matches the spec exactly)
# ---------------------------------------------------------------------------
GRAPH_TEMPLATE = """\
input_stream: "HTTP_REQUEST_PAYLOAD:input"
output_stream: "HTTP_RESPONSE_PAYLOAD:output"

node: {{
  name: "LLMExecutor"
  calculator: "HttpLLMCalculator"
  input_stream: "LOOPBACK:loopback"
  input_stream: "HTTP_REQUEST_PAYLOAD:input"
  input_side_packet: "LLM_NODE_RESOURCES:llm"
  output_stream: "LOOPBACK:loopback"
  output_stream: "HTTP_RESPONSE_PAYLOAD:output"
  input_stream_info: {{
    tag_index: 'LOOPBACK:0',
    back_edge: true
  }}
  node_options: {{
    [type.googleapis.com/mediapipe.LLMCalculatorOptions]: {{
      models_path: "{model_path}"
      device: "GPU"
      cache_size: 4
      enable_prefix_caching: true
    }}
  }}
  input_stream_handler {{
    input_stream_handler: "SyncSetInputStreamHandler",
    options {{
      [mediapipe.SyncSetInputStreamHandlerOptions.ext] {{
        sync_set {{
          tag_index: "LOOPBACK:0"
        }}
      }}
    }}
  }}
}}
"""

# ---------------------------------------------------------------------------
# Model catalog
# ---------------------------------------------------------------------------

@dataclass
class ModelInfo:
    hf_repo_id:   str          # e.g. "OpenVINO/Qwen2.5-Coder-7B-Instruct-int4-ov"
    display_name: str          # shown in the UI
    size_label:   str          # human-readable size string
    notes:        str = ""

    # Runtime state (not persisted)
    download_progress: float = field(default=0.0, compare=False)   # 0.0 – 100.0
    is_downloading:    bool  = field(default=False, compare=False)

    @property
    def repo_folder_name(self) -> str:
        """Last component of the HF repo ID — used as the local folder name."""
        return self.hf_repo_id.split("/")[-1]

    @property
    def local_path(self) -> Path:
        return cfg.models_dir / self.repo_folder_name

    @property
    def is_downloaded(self) -> bool:
        """True if the local directory exists and is non-empty."""
        p = self.local_path
        if not p.is_dir():
            return False
        # Consider downloaded if there's at least one file inside
        return any(p.iterdir())

    @property
    def model_name_for_config(self) -> str:
        """The name written into config.json's mediapipe_config_list."""
        return self.repo_folder_name


CURATED_MODELS: list[ModelInfo] = [
    ModelInfo(
        hf_repo_id="OpenVINO/Qwen2.5-Coder-7B-Instruct-int4-ov",
        display_name="Qwen2.5-Coder-7B",
        size_label="~4 GB",
        notes="Best coding, currently active",
    ),
    ModelInfo(
        hf_repo_id="OpenVINO/Qwen3-8B-int4-ov",
        display_name="Qwen3-8B",
        size_label="~4 GB",
        notes="General, has detokenizer issue",
    ),
    ModelInfo(
        hf_repo_id="OpenVINO/Qwen3-8B-int4-cw-ov",
        display_name="Qwen3-8B (NPU)",
        size_label="~4 GB",
        notes="NPU optimized",
    ),
    ModelInfo(
        hf_repo_id="OpenVINO/DeepSeek-R1-Distill-Qwen-7B-int4-cw-ov",
        display_name="DeepSeek-R1-7B",
        size_label="~4 GB",
        notes="Reasoning",
    ),
    ModelInfo(
        hf_repo_id="OpenVINO/DeepSeek-R1-Distill-Qwen-1.5B-int4-cw-ov",
        display_name="DeepSeek-R1-1.5B",
        size_label="~1 GB",
        notes="Fast, lightweight",
    ),
    ModelInfo(
        hf_repo_id="OpenVINO/Phi-3.5-mini-instruct-int4-cw-ov",
        display_name="Phi-3.5-mini",
        size_label="~2 GB",
        notes="Efficient",
    ),
]


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def read_active_model_name() -> str:
    """
    Parse config.json and return the name of the currently configured model,
    or an empty string if the config does not exist / cannot be parsed.
    """
    try:
        config_path = cfg.config_json
        if not config_path.is_file():
            return ""
        with config_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        entries = data.get("mediapipe_config_list", [])
        if entries:
            return entries[0].get("name", "")
    except Exception as exc:
        logger.warning("Could not read active model from config.json: %s", exc)
    return ""


def activate_model(model: ModelInfo) -> tuple[bool, str]:
    """
    Rewrite graph.pbtxt and config.json to make *model* the active model.
    Returns (success, message).
    """
    if not model.is_downloaded:
        return False, f"Model '{model.display_name}' is not downloaded yet."

    graph_path  = cfg.graph_pbtxt
    config_path = cfg.config_json

    # 1. Write graph.pbtxt
    model_path_str = model.local_path.as_posix()
    graph_content = GRAPH_TEMPLATE.format(model_path=model_path_str)

    try:
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        graph_path.write_text(graph_content, encoding="utf-8")
        logger.info("Wrote graph.pbtxt for model %s", model.display_name)
    except Exception as exc:
        msg = f"Failed to write graph.pbtxt: {exc}"
        logger.error(msg)
        return False, msg

    # 2. Write config.json
    config_data = {
        "model_config_list": [],
        "mediapipe_config_list": [
            {
                "name": model.model_name_for_config,
                "graph_path": str(graph_path).replace("\\", "\\\\"),
            }
        ],
    }

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("w", encoding="utf-8") as fh:
            json.dump(config_data, fh, indent=2)
        logger.info("Wrote config.json for model %s", model.display_name)
    except Exception as exc:
        msg = f"Failed to write config.json: {exc}"
        logger.error(msg)
        return False, msg

    return True, f"Model '{model.display_name}' activated."


# ---------------------------------------------------------------------------
# Download logic
# ---------------------------------------------------------------------------

# Type alias for the progress callback:  callback(model, percent: float)
ProgressCallback = Callable[[ModelInfo, float], None]
# Completion callback: callback(model, success: bool, message: str)
DoneCallback     = Callable[[ModelInfo, bool, str], None]


def download_model(
    model: ModelInfo,
    on_progress: ProgressCallback | None = None,
    on_done: DoneCallback | None = None,
) -> threading.Thread:
    """
    Start a background thread that downloads *model* from HuggingFace Hub.
    Progress is reported via *on_progress(model, percent)*.
    Completion is reported via *on_done(model, success, message)*.
    Returns the Thread object (already started).
    """
    thread = threading.Thread(
        target=_download_worker,
        args=(model, on_progress, on_done),
        daemon=True,
        name=f"dl-{model.repo_folder_name}",
    )
    thread.start()
    return thread


def _download_worker(
    model: ModelInfo,
    on_progress: ProgressCallback | None,
    on_done: DoneCallback | None,
):
    model.is_downloading = True
    model.download_progress = 0.0

    try:
        from huggingface_hub import snapshot_download
        from huggingface_hub import HfFileSystem

        # --- Determine total size for progress calculation ---
        total_files = 0
        completed_files = 0

        try:
            fs = HfFileSystem()
            file_list = fs.ls(model.hf_repo_id, detail=False)
            total_files = max(len(file_list), 1)
        except Exception:
            total_files = 1  # fallback: can't enumerate, progress will be coarse

        def _tqdm_progress_callback(info):
            """
            huggingface_hub passes a tqdm-like object.
            We intercept file-level completion events.
            """
            nonlocal completed_files
            # info is a dict with keys like 'downloaded_file_path', etc.
            if isinstance(info, dict) and info.get("event") == "file_downloaded":
                completed_files += 1
                pct = min(100.0, (completed_files / total_files) * 100.0)
                model.download_progress = pct
                if on_progress:
                    on_progress(model, pct)

        cfg.models_dir.mkdir(parents=True, exist_ok=True)

        local_dir = cfg.models_dir / model.repo_folder_name

        # Use huggingface_hub >= 0.23 tqdm_class hook for progress
        # For older versions we fall back to polling
        _run_snapshot_download(model, local_dir, on_progress, total_files)

        model.download_progress = 100.0
        model.is_downloading = False
        logger.info("Download complete: %s -> %s", model.hf_repo_id, local_dir)
        if on_done:
            on_done(model, True, f"Downloaded to {local_dir}")

    except Exception as exc:
        model.is_downloading = False
        logger.exception("Download failed for %s", model.hf_repo_id)
        if on_done:
            on_done(model, False, str(exc))


def _run_snapshot_download(
    model: ModelInfo,
    local_dir: Path,
    on_progress: ProgressCallback | None,
    total_files: int,
):
    """
    Perform the actual snapshot_download, piggybacking on the file-level
    progress mechanism available in huggingface_hub >= 0.22.

    Strategy:
    - Wrap tqdm so each completed file updates the progress bar.
    - If the tqdm hook is unavailable, fall back to a polling approach that
      counts files appearing in local_dir.
    """
    # Try the newer `hf_transfer`-aware callback (hf_hub >= 0.22)
    try:
        from huggingface_hub import snapshot_download
        from huggingface_hub.utils import tqdm as hf_tqdm

        _completed = [0]

        class _TrackingTqdm(hf_tqdm):
            """Subclass that fires our callback on each file completion."""
            def update(self, n=1):
                super().update(n)
                # Each 'file' tqdm bar represents one file
                if self.total and self.n >= self.total:
                    _completed[0] += 1
                    pct = min(100.0, (_completed[0] / max(total_files, 1)) * 100.0)
                    model.download_progress = pct
                    if on_progress:
                        on_progress(model, pct)

        snapshot_download(
            repo_id=model.hf_repo_id,
            local_dir=str(local_dir),
            local_dir_use_symlinks=False,
            tqdm_class=_TrackingTqdm,
        )

    except TypeError:
        # tqdm_class kwarg not supported in this version – use polling fallback
        _snapshot_download_with_polling(model, local_dir, on_progress, total_files)


def _snapshot_download_with_polling(
    model: ModelInfo,
    local_dir: Path,
    on_progress: ProgressCallback | None,
    total_files: int,
):
    """
    Fallback: launch snapshot_download in a sub-thread, poll the local_dir
    for new files, and report progress based on file count.
    """
    from huggingface_hub import snapshot_download
    import threading as _threading

    done_event = _threading.Event()
    exc_holder = [None]

    def _dl():
        try:
            snapshot_download(
                repo_id=model.hf_repo_id,
                local_dir=str(local_dir),
                local_dir_use_symlinks=False,
            )
        except Exception as e:
            exc_holder[0] = e
        finally:
            done_event.set()

    t = _threading.Thread(target=_dl, daemon=True)
    t.start()

    while not done_event.is_set():
        if local_dir.is_dir():
            n = sum(1 for _ in local_dir.rglob("*") if _.is_file())
            pct = min(99.0, (n / max(total_files, 1)) * 100.0)
            model.download_progress = pct
            if on_progress:
                on_progress(model, pct)
        done_event.wait(timeout=2)

    if exc_holder[0]:
        raise exc_holder[0]
