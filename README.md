# OVMS GUI Manager

A desktop GUI application for managing an OpenVINO Model Server (OVMS) instance on Windows.
Built with Python 3.12 and CustomTkinter.

## Installation

Download the latest installer from Releases and run it. The app installs to:

```
%LOCALAPPDATA%\Programs\OVMS Manager\
```

All runtime data (models, workspace, logs, config) is stored under:

```
%LOCALAPPDATA%\OVMS Manager\
  models\          downloaded model files
  ovms\            OVMS binary (auto-installed via Setup tab)
  workspace\       OVMS config.json and graph.pbtxt
  env\             Python venv (auto-created via Setup tab)
  logs\            server and proxy log files
  config.json      app settings
```

## First Run

On first launch the app asks whether to auto-start the OVMS stack on every open.
If any components are missing, the **Setup tab** guides you through installing them.

## Development

```bat
pip install -r requirements.txt
python main.py
```

or double-click `run.bat` (auto-detects Python from `%USERPROFILE%\openvino-env` or PATH).

## Features

### Dashboard Tab
- **Status cards** — live green/red indicators for OVMS, proxy, and active model.
- **Start Stack / Stop Stack** — single button to start or stop both processes.
- **Log viewer** — last 25 lines of the OVMS log, auto-refreshed every 2 seconds.

### Models Tab
- Curated list of OpenVINO-optimised coding and reasoning models.
- Per-row **Download** button — downloads from HuggingFace Hub with a live progress bar.
- **Activate** button — rewrites `graph.pbtxt` and `config.json`, then restarts OVMS.

## Curated Model Library

| Display Name | HuggingFace Repo | Size | Notes |
|---|---|---|---|
| Qwen2.5-Coder-7B | OpenVINO/Qwen2.5-Coder-7B-Instruct-int4-ov | ~4 GB | Best coding |
| Qwen3-8B | OpenVINO/Qwen3-8B-int4-ov | ~4 GB | General |
| Qwen3-8B (NPU) | OpenVINO/Qwen3-8B-int4-cw-ov | ~4 GB | NPU optimised |
| DeepSeek-R1-7B | OpenVINO/DeepSeek-R1-Distill-Qwen-7B-int4-cw-ov | ~4 GB | Reasoning |
| DeepSeek-R1-1.5B | OpenVINO/DeepSeek-R1-Distill-Qwen-1.5B-int4-cw-ov | ~1 GB | Fast, lightweight |
| Phi-3.5-mini | OpenVINO/Phi-3.5-mini-instruct-int4-cw-ov | ~2 GB | Efficient |

## Architecture

```
main.py              Entry point, logging setup
app/
  gui.py             CustomTkinter window, tabs, status cards, model rows
  server.py          OVMS + proxy subprocess management, health polling
  models.py          Model catalog, HuggingFace download, config writing
  config.py          JSON-backed settings, all paths under %LOCALAPPDATA%
  installer.py       Component detection and auto-installation
  log_viewer.py      Auto-refreshing log tail widget
```

## How model activation works

1. `workspace\graph.pbtxt` is rewritten with the selected model's local path.
2. `workspace\config.json` is rewritten to reference that graph.
3. OVMS is restarted to pick up the new configuration.

OVMS serves on REST port **8000**; the proxy (OpenAI-compatible) serves on port **8001**.
