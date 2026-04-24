# OVMS GUI Manager

A desktop GUI application for managing an OpenVINO Model Server (OVMS) instance on Windows.
Built with Python 3.12 and CustomTkinter.

## Prerequisites

| Requirement | Path |
|---|---|
| Python 3.12 (openvino-env) | `C:\Users\annguyen209\openvino-env\Scripts\python.exe` |
| OVMS binary | `C:\Users\annguyen209\ovms\ovms.exe` |
| OVMS setupvars | `C:\Users\annguyen209\ovms\setupvars.bat` |
| OVMS config | `C:\Users\annguyen209\ovms-workspace\config.json` |
| Graph template | `C:\Users\annguyen209\ovms-workspace\graph.pbtxt` |
| Proxy script | `C:\Users\annguyen209\ovms-proxy.py` |
| Models directory | `C:\Users\annguyen209\models\` |

## Installation

Open a terminal in this directory and run:

```bat
C:\Users\annguyen209\openvino-env\Scripts\pip.exe install -r requirements.txt
```

## Running

Double-click `run.bat`, or:

```bat
C:\Users\annguyen209\openvino-env\Scripts\python.exe main.py
```

## Features

### Dashboard Tab
- **Status cards** — live green/red indicators for OVMS, the proxy, and the active model name.
- **Start Stack / Stop Stack** — single button to start or stop both OVMS and the proxy.
- **Log viewer** — last 20 lines of `ovms-server.log`, auto-refreshed every 2 seconds.

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
  log_viewer.py      Auto-refreshing log tail widget
```

## How model activation works

1. `graph.pbtxt` is rewritten with the selected model's local path.
2. `config.json` is rewritten to reference that graph and use the model folder name.
3. OVMS is restarted to pick up the new configuration.

OVMS serves on REST port **8000**; the proxy (OpenAI-compatible) serves on port **8001**.
