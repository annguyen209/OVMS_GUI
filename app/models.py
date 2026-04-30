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
      device: "{device}"
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
    notes:        str  = ""
    broken:       bool = False  # known incompatibility with current OV version

    # Runtime state (not persisted)
    download_progress: float = field(default=0.0, compare=False)   # 0.0 – 100.0
    is_downloading:    bool  = field(default=False, compare=False)

    @property
    def repo_folder_name(self) -> str:
        """Last component of the HF repo ID — used as the default local folder name."""
        return self.hf_repo_id.split("/")[-1]

    @property
    def local_path(self) -> Path:
        """
        Return the path where the model lives on disk, or the intended download
        path if it hasn't been downloaded yet.

        Searches (in priority order):
          1. models_dir / repo_folder_name           (standard)
          2. models_dir / org / repo_folder_name     (OVMS pull-mode layout)
          3. Any subdirectory (up to 2 levels) whose name matches
             repo_folder_name case-insensitively and contains openvino_model.xml
        Falls back to option 1 if nothing found.
        """
        base = cfg.models_dir
        folder = self.repo_folder_name

        # 1. Standard path
        p1 = base / folder
        if p1.is_dir() and _has_model_files(p1):
            return p1

        # 2. Org-prefixed path (e.g. models/OpenVINO/Qwen3-8B-int4-ov)
        org = self.hf_repo_id.split("/")[0]
        p2 = base / org / folder
        if p2.is_dir() and _has_model_files(p2):
            return p2

        # 3. Broad scan: any dir with openvino_model.xml whose name
        #    matches (exact, prefix, or suffix) the repo folder name
        folder_lower = folder.lower()
        if base.is_dir():
            for candidate in base.rglob("openvino_model.xml"):
                d = candidate.parent
                d_lower = d.name.lower()
                if (d_lower == folder_lower
                        or folder_lower.startswith(d_lower)
                        or d_lower.startswith(folder_lower)):
                    return d

        # Default: standard path (will be created on download)
        return p1

    @property
    def is_downloaded(self) -> bool:
        """True if a valid OpenVINO model directory exists on disk."""
        return _has_model_files(self.local_path)

    @property
    def model_name_for_config(self) -> str:
        """The name written into config.json's mediapipe_config_list."""
        return self.repo_folder_name


def _has_model_files(path: Path) -> bool:
    """Return True if *path* is a directory containing openvino_model.xml."""
    return path.is_dir() and (path / "openvino_model.xml").is_file()


CURATED_MODELS: list[ModelInfo] = [
    ModelInfo(
        hf_repo_id="OpenVINO/Qwen2.5-Coder-7B-Instruct-int4-ov",
        display_name="Qwen2.5-Coder-7B",
        size_label="~4 GB",
        notes="Coding specialist. Confirmed working on CPU.",
    ),
    ModelInfo(
        hf_repo_id="OpenVINO/Qwen3-8B-int4-ov",
        display_name="Qwen3-8B",
        size_label="~4 GB",
        notes="Latest Qwen3 architecture. Use CPU device.",
    ),
    ModelInfo(
        hf_repo_id="OpenVINO/Qwen3-8B-int4-cw-ov",
        display_name="Qwen3-8B (NPU)",
        size_label="~4 GB",
        notes="Channel-wise quantization for NPU/CPU. Use CPU or NPU device.",
    ),
    ModelInfo(
        hf_repo_id="OpenVINO/DeepSeek-R1-Distill-Qwen-7B-int4-cw-ov",
        display_name="DeepSeek-R1-7B",
        size_label="~4 GB",
        notes="Reasoning model. Confirmed working on CPU.",
    ),
    ModelInfo(
        hf_repo_id="OpenVINO/DeepSeek-R1-Distill-Qwen-1.5B-int4-cw-ov",
        display_name="DeepSeek-R1-1.5B",
        size_label="~1 GB",
        notes="Lightweight reasoning. Confirmed working on CPU.",
    ),
    ModelInfo(
        hf_repo_id="OpenVINO/Phi-3.5-mini-instruct-int4-ov",
        display_name="Phi-3.5-mini",
        size_label="~2 GB",
        notes="Efficient general model. Use CPU device.",
    ),
    ModelInfo(
        hf_repo_id="OpenVINO/Phi-3.5-mini-instruct-int4-cw-ov",
        display_name="Phi-3.5-mini (NPU)",
        size_label="~2 GB",
        notes="Channel-wise quantization for NPU/CPU. Use CPU or NPU device.",
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
    graph_content = GRAPH_TEMPLATE.format(
        model_path=model_path_str,
        device=cfg.ovms_device,
    )

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
    cancel_event: threading.Event | None = None,
) -> threading.Thread:
    """
    Start a background thread that downloads *model* from HuggingFace Hub.
    Progress is reported via *on_progress(model, percent)*.
    Completion is reported via *on_done(model, success, message)*.
    Set cancel_event to cancel the download mid-way.
    Returns the Thread object (already started).
    """
    thread = threading.Thread(
        target=_download_worker,
        args=(model, on_progress, on_done, cancel_event),
        daemon=True,
        name=f"dl-{model.repo_folder_name}",
    )
    thread.start()
    return thread


def _download_worker(
    model: ModelInfo,
    on_progress: ProgressCallback | None,
    on_done: DoneCallback | None,
    cancel_event: threading.Event | None = None,
):
    model.is_downloading = True
    model.download_progress = 0.0

    # Verify huggingface_hub is importable; if not, guide user to check setup
    try:
        from huggingface_hub import snapshot_download as _sd_check  # noqa: F401
        logger.info("Download: huggingface_hub import OK for %s", model.hf_repo_id)
    except ImportError as ie:
        model.is_downloading = False
        logger.error("Download: huggingface_hub ImportError: %s", ie)
        if on_done:
            on_done(model, False,
                    "huggingface_hub not found. Go to Setup tab and reinstall the Python environment.")
        return

    try:
        from huggingface_hub import snapshot_download, HfFileSystem

        # Get expected total bytes for accurate byte-based progress
        total_bytes = 0
        try:
            fs = HfFileSystem()
            entries = fs.ls(model.hf_repo_id, detail=True)
            total_bytes = sum(e.get("size", 0) for e in entries if isinstance(e, dict))
            logger.info("Download: total_bytes=%d for %s", total_bytes, model.hf_repo_id)
        except Exception as e:
            logger.warning("Download: could not get file sizes (%s), using file count fallback", e)

        cfg.models_dir.mkdir(parents=True, exist_ok=True)
        local_dir = cfg.models_dir / model.repo_folder_name
        logger.info("Download: local_dir=%s", local_dir)

        # Clean up stale zero-byte lock/incomplete files from a previous
        # interrupted download so snapshot_download can start fresh.
        dl_cache = local_dir / ".cache" / "huggingface" / "download"
        if dl_cache.is_dir():
            stale = [f for f in dl_cache.iterdir()
                     if f.is_file() and f.stat().st_size == 0]
            for f in stale:
                try:
                    f.unlink()
                except Exception:
                    pass
            logger.info("Download: cleared %d stale lock files", len(stale))

        done_event = threading.Event()
        exc_holder: list = [None]

        logger.info("Download: starting snapshot_download thread")

        def _dl():
            try:
                logger.info("Download: snapshot_download begin repo=%s dir=%s",
                             model.hf_repo_id, local_dir)
                snapshot_download(
                    repo_id=model.hf_repo_id,
                    local_dir=str(local_dir),
                )
                logger.info("Download: snapshot_download finished OK")
            except Exception as e:
                logger.error("Download: snapshot_download FAILED: %s", e)
                exc_holder[0] = e
            finally:
                done_event.set()

        threading.Thread(target=_dl, daemon=True, name=f"hf-{model.repo_folder_name}").start()

        # Poll local_dir for downloaded bytes while download runs in background.
        # Include .incomplete staging files — they contain actual data being
        # written by snapshot_download before the atomic rename to final paths.
        while not done_event.is_set():
            if cancel_event and cancel_event.is_set():
                model.is_downloading = False
                logger.info("Download cancelled: %s", model.hf_repo_id)
                if on_done:
                    on_done(model, False, "Download cancelled.")
                return
            if local_dir.is_dir():
                downloaded = sum(
                    f.stat().st_size for f in local_dir.rglob("*")
                    if f.is_file() and f.suffix != ".lock"
                )
                if total_bytes > 0:
                    pct = min(98.0, downloaded / total_bytes * 100.0)
                else:
                    n = sum(1 for f in local_dir.rglob("*")
                            if f.is_file() and f.suffix != ".lock")
                    pct = min(98.0, n / 15 * 100.0)
                model.download_progress = pct
                if on_progress:
                    on_progress(model, pct)
            done_event.wait(timeout=1.5)

        if exc_holder[0]:
            raise exc_holder[0]

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
