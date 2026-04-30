"""
about.py - About tab.

Explains OpenVINO, OVMS, and this application.
Detects and shows available hardware (CPU / GPU / NPU).
"""

import re
import tkinter as tk
import customtkinter as ctk
from pathlib import Path

from app.config import cfg
from app import theme

APP_VERSION = "1.0.0"
APP_AUTHOR  = "AnsCodeLab"
APP_REPO    = "github.com/AnsCodeLab/openvino-manager"


# Helpers

_DESCRIPTIONS = {
    "CPU": "General-purpose inference - always available, any model",
    "GPU": "Arc iGPU - best throughput, shared system RAM as VRAM",
    "NPU": "Intel AI Boost - lowest power draw, ideal for always-on tasks",
}


def _detect_devices() -> list[tuple[str, str, str]]:
    """
    Returns list of (device_token, full_name, description).

    Fast path: parse the OVMS log (the server already printed the device
    list on startup). Instant file read — no OpenVINO cold-start delay.

    Slow fallback: direct openvino import for full device names when the
    log is unavailable (takes 15-30 s on first call, use sparingly).
    """
    # 1. Parse OVMS log — instant
    try:
        log = Path(cfg.ovms_log)
        if log.is_file():
            text = log.read_text(encoding="utf-8", errors="replace")
            for line in reversed(text.splitlines()):
                m = re.search(r"Available devices for Open VINO:\s*(.+)", line)
                if m:
                    tokens = [t.strip() for t in m.group(1).split(",")]
                    # Try to extract full names printed on separate lines
                    # e.g. "CPU: Intel(R) Core(TM) Ultra 7 155H"
                    names: dict[str, str] = {}
                    for l2 in text.splitlines():
                        for tok in tokens:
                            n = re.search(
                                rf"\b{re.escape(tok)}\b[^:]*:\s*(.+)", l2
                            )
                            if n and tok not in names:
                                names[tok] = n.group(1).strip()
                    return [
                        (t, names.get(t, t), _DESCRIPTIONS.get(t, ""))
                        for t in tokens
                    ]
    except Exception:
        pass

    # 2. Subprocess via OVMS bundled Python — works in installed exe
    try:
        import subprocess
        ovms_py = Path(cfg.ovms_exe).parent / "python" / "python.exe"
        if ovms_py.is_file():
            script = (
                "import openvino as ov; core = ov.Core();\n"
                "[print(d+'|'+(core.get_property(d,'FULL_DEVICE_NAME') or d))"
                " for d in core.available_devices]"
            )
            r = subprocess.run(
                [str(ovms_py), "-c", script],
                capture_output=True, text=True, timeout=20,
            )
            if r.returncode == 0:
                results = []
                for line in r.stdout.strip().splitlines():
                    if "|" in line:
                        tok, name = line.split("|", 1)
                        tok, name = tok.strip(), name.strip()
                        results.append((tok, name, _DESCRIPTIONS.get(tok, "")))
                if results:
                    return results
    except Exception:
        pass

    # 3. Direct openvino import — works in dev environment
    try:
        import openvino as ov
        core = ov.Core()
        return [
            (d, core.get_property(d, "FULL_DEVICE_NAME"),
             _DESCRIPTIONS.get(d, ""))
            for d in core.available_devices
        ]
    except Exception:
        pass

    return [("?", "Could not detect. Start the OVMS stack first.", "")]


# Reusable card

class _Card(ctk.CTkFrame):
    def __init__(self, master, **kw):
        kw.setdefault("fg_color", theme.CARD)
        kw.setdefault("corner_radius", 8)
        kw.setdefault("border_width", 1)
        kw.setdefault("border_color", theme.BORDER)
        super().__init__(master, **kw)

    def add_heading(self, text: str, color: str = theme.BLUE):
        ctk.CTkLabel(self, text=text,
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=color, anchor="w",
                     ).pack(fill="x", padx=18, pady=(16, 4))
        return self

    def add_body(self, text: str):
        ctk.CTkLabel(self, text=text,
                     font=ctk.CTkFont(size=12), text_color=theme.TEXT2,
                     anchor="w", justify="left", wraplength=860,
                     ).pack(fill="x", padx=18, pady=(0, 14))
        return self

    def add_divider(self):
        ctk.CTkFrame(self, height=1, fg_color=theme.BORDER).pack(
            fill="x", padx=18, pady=4)
        return self


# About Tab

class AboutTab(ctk.CTkFrame):

    def __init__(self, master, **kw):
        kw.setdefault("fg_color", theme.BG)
        super().__init__(master, **kw)
        self._build_ui()

    def _build_ui(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG, corner_radius=0)
        scroll.pack(fill="both", expand=True)

        inner = ctk.CTkFrame(scroll, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)

        self._build_hero(inner)
        self._build_openvino(inner)
        self._build_ovms(inner)
        self._build_app_info(inner)

    # Hero

    def _build_hero(self, parent):
        hero = ctk.CTkFrame(parent, fg_color=theme.BANNER, corner_radius=10)
        hero.pack(fill="x", pady=(0, 14))

        # Title row
        top = ctk.CTkFrame(hero, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(22, 6))

        ctk.CTkLabel(top, text="OpenVINO Manager",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="#f8fafc").pack(side="left")

        ctk.CTkLabel(top, text=f"  v{APP_VERSION}",
                     font=ctk.CTkFont(size=13),
                     text_color=theme.MUTED).pack(side="left", padx=10)

        ctk.CTkLabel(hero,
                     text="A desktop GUI for managing OpenVINO Model Server. "
                          "Download models, start the server, and connect your "
                          "IDE to a local AI backend running on your hardware with Intel OpenVINO acceleration.",
                     font=ctk.CTkFont(size=13), text_color=theme.MUTED,
                     anchor="w", justify="left", wraplength=860,
                     ).pack(fill="x", padx=24, pady=(0, 20))

    # OpenVINO explanation

    def _build_openvino(self, parent):
        card = _Card(parent)
        card.pack(fill="x", pady=(0, 12))
        card.add_heading("What is OpenVINO?", theme.BLUE)
        card.add_body(
            "OpenVINO (Open Visual Inference and Neural network Optimization) is an "
            "open-source toolkit from Intel for optimizing and deploying AI inference. "
            "It lets you run large language models, vision models, and speech models "
            "directly on Intel hardware: CPU, integrated GPU (Arc), or the built-in "
            "NPU (Neural Processing Unit) - without needing a discrete GPU."
        )
        card.add_divider()
        card.add_heading("Why OpenVINO instead of Ollama?", theme.BLUE)
        card.add_body(
            "Ollama uses llama.cpp which does not support Intel Arc iGPU on Windows. "
            "It falls back to CPU-only inference. OpenVINO is purpose-built for Intel "
            "silicon and can run models on the CPU, the Arc iGPU (shared system RAM acts "
            "as VRAM), or the NPU for low-power tasks. On a machine with 32 GB RAM, "
            "the iGPU can use up to ~20 GB as effective VRAM."
        )

        # Feature pills
        pills = ctk.CTkFrame(card, fg_color="transparent")
        pills.pack(fill="x", padx=18, pady=(0, 16))
        for text, color, bg in [
            ("CPU inference",    "#1e40af", "#dbeafe"),
            ("Arc iGPU support", "#065f46", "#d1fae5"),
            ("NPU support",      "#374151", "#f3f4f6"),
            ("INT4 / INT8 quant",  "#92400e", "#fef3c7"),
            ("Windows native",   "#1e40af", "#dbeafe"),
        ]:
            ctk.CTkLabel(pills, text=text,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         fg_color=bg, text_color=color,
                         corner_radius=6, padx=8, pady=3,
                         ).pack(side="left", padx=(0, 6))

    # OVMS explanation

    def _build_ovms(self, parent):
        card = _Card(parent)
        card.pack(fill="x", pady=(0, 12))
        card.add_heading("What is OpenVINO Model Server (OVMS)?", theme.BLUE)
        card.add_body(
            "OVMS is Intel's production-grade model serving binary. It wraps OpenVINO "
            "inference in an HTTP/gRPC server and exposes an OpenAI-compatible REST API "
            "at /v3/chat/completions. This is the same format used by ChatGPT, Claude, and "
            "other hosted services. Any tool that supports a custom OpenAI "
            "base URL (Continue.dev, OpenCode, LangChain, the openai Python SDK, curl) "
            "can talk to your local model without any code changes."
        )
        card.add_divider()

        # How it fits together
        card.add_heading("How this app fits together", theme.BLUE)

        steps = [
            ("1", f"OVMS loads the model onto your device and listens on port {cfg.ovms_rest_port}.",  theme.BLUE),
            ("2", f"A thin proxy on port {cfg.proxy_port} clamps max_tokens so requests never exceed the model's context window.", theme.BLUE),
            ("3", f"Your IDE extension (Continue.dev or OpenCode) connects to localhost:{cfg.proxy_port}/v3 — just like it would to the OpenAI API.", theme.GREEN),
        ]
        for num, text, color in steps:
            row = ctk.CTkFrame(card, fg_color=theme.CARD2, corner_radius=6,
                               border_width=1, border_color=theme.BORDER)
            row.pack(fill="x", padx=16, pady=(0, 6))

            dot = tk.Canvas(row, width=28, height=28,
                            bg=theme.CARD2, highlightthickness=0)
            dot.pack(side="left", padx=(12, 10), pady=10)
            dot.create_oval(2, 2, 26, 26, fill=theme.BLUE, outline="")
            dot.create_text(14, 14, text=num, fill="white",
                            font=("Segoe UI", 11, "bold"))

            ctk.CTkLabel(row, text=text, font=ctk.CTkFont(size=12),
                         text_color=theme.TEXT2, anchor="w", justify="left",
                         wraplength=820).pack(side="left", padx=(0, 12),
                                              pady=10, fill="x", expand=True)

        ctk.CTkFrame(card, fg_color="transparent", height=8).pack()

    # Hardware note (detail moved to Dashboard)

    # App info

    def _build_app_info(self, parent):
        card = _Card(parent)
        card.pack(fill="x", pady=(0, 4))

        info_row = ctk.CTkFrame(card, fg_color="transparent")
        info_row.pack(fill="x", padx=18, pady=16)

        for label, value, color in [
            ("Application",  "OpenVINO Manager", theme.TEXT),
            ("Version",      f"v{APP_VERSION}",    theme.BLUE),
            ("Author",       APP_AUTHOR,            theme.TEXT),
            ("Repository",   APP_REPO,              theme.TEXT),
            ("License",      "MIT",                 theme.TEXT),
        ]:
            col = ctk.CTkFrame(info_row, fg_color="transparent")
            col.pack(side="left", expand=True, fill="x")
            ctk.CTkLabel(col, text=label,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=theme.MUTED).pack(anchor="w")
            ctk.CTkLabel(col, text=value,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=color).pack(anchor="w")

        card.add_divider()

        ctk.CTkLabel(card,
                     text="Built with Python · customtkinter · OpenVINO GenAI · "
                          "OpenVINO Model Server · HuggingFace Hub",
                     font=ctk.CTkFont(size=11), text_color=theme.MUTED,
                     anchor="w").pack(fill="x", padx=18, pady=(4, 16))
