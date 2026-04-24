"""
about.py — About tab.

Explains OpenVINO, OVMS, and this application.
Detects and shows available hardware (CPU / GPU / NPU).
"""

import threading
import tkinter as tk
import customtkinter as ctk

from app.config import cfg

_BG     = "#f1f5f9"
_CARD   = "#ffffff"
_CARD2  = "#f8fafc"
_BORDER = "#e2e8f0"
_TEXT   = "#0f172a"
_TEXT2  = "#334155"
_MUTED  = "#94a3b8"
_GREEN  = "#16a34a"
_BLUE   = "#2563eb"
_PURPLE = "#7c3aed"
_AMBER  = "#d97706"

APP_VERSION = "1.0.0"
APP_AUTHOR  = "anzdev4life"
APP_REPO    = "github.com/annguyen209/OVMS_GUI"


# ── Helpers ───────────────────────────────────────────────────────────────

def _detect_devices() -> list[tuple[str, str, str]]:
    """
    Returns list of (device_token, full_name, description) tuples.
    Runs openvino in the configured venv so it doesn't block the GUI.
    Falls back to a placeholder if detection fails.
    """
    import subprocess, json
    script = (
        "import openvino as ov, json;"
        "core=ov.Core();"
        "devs=core.available_devices;"
        "out=[{"
        "'token':d,"
        "'name':core.get_property(d,'FULL_DEVICE_NAME'),"
        "'type':d"
        "} for d in devs];"
        "print(json.dumps(out))"
    )
    try:
        r = subprocess.run(
            [cfg.python_exe, "-c", script],
            capture_output=True, text=True, timeout=20,
        )
        if r.returncode == 0:
            data = json.loads(r.stdout.strip())
            descriptions = {
                "CPU": "General-purpose inference — always available",
                "GPU": "Arc iGPU — best throughput for mid-size LLMs",
                "NPU": "Intel AI Boost — lowest power draw, always-on tasks",
            }
            return [(d["token"], d["name"],
                     descriptions.get(d["token"], "")) for d in data]
    except Exception:
        pass
    return [("?", "Could not detect — is OpenVINO installed?", "")]


# ── Reusable card ─────────────────────────────────────────────────────────

class _Card(ctk.CTkFrame):
    def __init__(self, master, **kw):
        kw.setdefault("fg_color", _CARD)
        kw.setdefault("corner_radius", 14)
        kw.setdefault("border_width", 1)
        kw.setdefault("border_color", _BORDER)
        super().__init__(master, **kw)

    def add_heading(self, text: str, color: str = _TEXT):
        ctk.CTkLabel(self, text=text,
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=color, anchor="w",
                     ).pack(fill="x", padx=18, pady=(16, 4))
        return self

    def add_body(self, text: str):
        ctk.CTkLabel(self, text=text,
                     font=ctk.CTkFont(size=12), text_color=_TEXT2,
                     anchor="w", justify="left", wraplength=860,
                     ).pack(fill="x", padx=18, pady=(0, 14))
        return self

    def add_divider(self):
        ctk.CTkFrame(self, height=1, fg_color=_BORDER).pack(
            fill="x", padx=18, pady=4)
        return self


# ── About Tab ─────────────────────────────────────────────────────────────

class AboutTab(ctk.CTkFrame):

    def __init__(self, master, **kw):
        kw.setdefault("fg_color", _BG)
        super().__init__(master, **kw)
        self._build_ui()
        # Detect hardware in background so the tab opens instantly
        threading.Thread(target=self._load_devices, daemon=True).start()

    def _build_ui(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color=_BG, corner_radius=0)
        scroll.pack(fill="both", expand=True)

        inner = ctk.CTkFrame(scroll, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)

        self._build_hero(inner)
        self._build_openvino(inner)
        self._build_ovms(inner)
        self._build_hardware(inner)
        self._build_app_info(inner)

    # ── Hero ──────────────────────────────────────────────────────────────

    def _build_hero(self, parent):
        hero = ctk.CTkFrame(parent, fg_color=_TEXT, corner_radius=16)
        hero.pack(fill="x", pady=(0, 14))

        # Logo row
        top = ctk.CTkFrame(hero, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(22, 6))

        dot = tk.Canvas(top, width=16, height=16,
                        bg=_TEXT, highlightthickness=0)
        dot.pack(side="left", padx=(0, 12))
        dot.create_oval(1, 1, 15, 15, fill=_GREEN, outline="")

        ctk.CTkLabel(top, text="OVMS Manager",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="#f8fafc").pack(side="left")

        ctk.CTkLabel(top, text=f"v{APP_VERSION}",
                     font=ctk.CTkFont(size=13),
                     text_color="#64748b").pack(side="left", padx=10)

        ctk.CTkLabel(hero,
                     text="A desktop GUI for managing OpenVINO Model Server — "
                          "download models, start the server, and connect your "
                          "IDE to a local AI backend running entirely on your Intel hardware.",
                     font=ctk.CTkFont(size=13), text_color="#94a3b8",
                     anchor="w", justify="left", wraplength=860,
                     ).pack(fill="x", padx=24, pady=(0, 20))

    # ── OpenVINO explanation ──────────────────────────────────────────────

    def _build_openvino(self, parent):
        card = _Card(parent)
        card.pack(fill="x", pady=(0, 12))
        card.add_heading("What is OpenVINO?", _BLUE)
        card.add_body(
            "OpenVINO™ (Open Visual Inference and Neural network Optimization) is an "
            "open-source toolkit from Intel for optimizing and deploying AI inference. "
            "It lets you run large language models, vision models, and speech models "
            "directly on Intel hardware — CPU, integrated GPU (Arc), or the built-in "
            "NPU (Neural Processing Unit) — without needing a discrete GPU."
        )
        card.add_divider()
        card.add_heading("Why OpenVINO instead of Ollama?", _BLUE)
        card.add_body(
            "Ollama uses llama.cpp which does not support Intel Arc iGPU on Windows — "
            "it falls back to CPU-only inference. OpenVINO is purpose-built for Intel "
            "silicon and can dispatch work to the Arc iGPU (shared system RAM acts as "
            "VRAM), the NPU for low-power always-on tasks, or all three devices in "
            "parallel via the AUTO device. On a machine with 32 GB RAM, this means "
            "up to ~20 GB of effective VRAM for the iGPU."
        )

        # Feature pills
        pills = ctk.CTkFrame(card, fg_color="transparent")
        pills.pack(fill="x", padx=18, pady=(0, 16))
        for text, color, bg in [
            ("CPU inference",    "#1e40af", "#dbeafe"),
            ("Arc iGPU support", "#065f46", "#d1fae5"),
            ("NPU support",      "#581c87", "#ede9fe"),
            ("INT4 / INT8 quant",  "#78350f", "#fef3c7"),
            ("Windows native",   "#1e3a5f", "#e0f2fe"),
        ]:
            ctk.CTkLabel(pills, text=text,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         fg_color=bg, text_color=color,
                         corner_radius=6, padx=8, pady=3,
                         ).pack(side="left", padx=(0, 6))

    # ── OVMS explanation ──────────────────────────────────────────────────

    def _build_ovms(self, parent):
        card = _Card(parent)
        card.pack(fill="x", pady=(0, 12))
        card.add_heading("What is OpenVINO Model Server (OVMS)?", _PURPLE)
        card.add_body(
            "OVMS is Intel's production-grade model serving binary. It wraps OpenVINO "
            "inference in an HTTP/gRPC server and exposes an OpenAI-compatible REST API "
            "at /v3/chat/completions — the same format used by ChatGPT, Claude, and "
            "other hosted services. This means any tool that supports a custom OpenAI "
            "base URL (Continue.dev, OpenCode, LangChain, the openai Python SDK, curl) "
            "can talk to your local model without any code changes."
        )
        card.add_divider()

        # How it fits together
        card.add_heading("How this app fits together", _PURPLE)

        steps = [
            ("1", "OVMS loads the model onto the Arc iGPU and listens on port 8000.",  _BLUE),
            ("2", "A thin proxy on port 8001 clamps max_tokens so requests never exceed the model's context window.", _PURPLE),
            ("3", "Your IDE extension (Continue.dev or OpenCode) connects to localhost:8001/v3 — just like it would to the OpenAI API.", _GREEN),
        ]
        for num, text, color in steps:
            row = ctk.CTkFrame(card, fg_color=_CARD2, corner_radius=8,
                               border_width=1, border_color=_BORDER)
            row.pack(fill="x", padx=16, pady=(0, 6))

            dot = tk.Canvas(row, width=28, height=28,
                            bg=_CARD2, highlightthickness=0)
            dot.pack(side="left", padx=(12, 10), pady=10)
            dot.create_oval(2, 2, 26, 26, fill=color, outline="")
            dot.create_text(14, 14, text=num, fill="white",
                            font=("Segoe UI", 11, "bold"))

            ctk.CTkLabel(row, text=text, font=ctk.CTkFont(size=12),
                         text_color=_TEXT2, anchor="w", justify="left",
                         wraplength=820).pack(side="left", padx=(0, 12),
                                              pady=10, fill="x", expand=True)

        ctk.CTkFrame(card, fg_color="transparent", height=8).pack()

    # ── Hardware ──────────────────────────────────────────────────────────

    def _build_hardware(self, parent):
        card = _Card(parent)
        card.pack(fill="x", pady=(0, 12))

        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=18, pady=(16, 8))
        ctk.CTkLabel(hdr, text="Detected Hardware",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=_AMBER).pack(side="left")
        self._hw_spinner = ctk.CTkLabel(hdr, text="detecting…",
                                        font=ctk.CTkFont(size=11),
                                        text_color=_MUTED)
        self._hw_spinner.pack(side="left", padx=10)

        self._hw_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._hw_frame.pack(fill="x", padx=16, pady=(0, 14))

    def _load_devices(self):
        devices = _detect_devices()
        self.after(0, lambda: self._render_devices(devices))

    def _render_devices(self, devices):
        self._hw_spinner.configure(text="")
        colors = {"CPU": _BLUE, "GPU": _GREEN, "NPU": _PURPLE}
        icons  = {"CPU": "⚙", "GPU": "◈", "NPU": "⚡"}
        descs  = {
            "CPU": "General-purpose inference — always available, any model",
            "GPU": "Arc iGPU — best throughput, shared system RAM as VRAM",
            "NPU": "Intel AI Boost — lowest power, ideal for always-on tasks",
        }

        for token, name, _ in devices:
            color = colors.get(token, _MUTED)
            icon  = icons.get(token, "•")
            desc  = descs.get(token, "")

            row = ctk.CTkFrame(self._hw_frame, fg_color=_CARD2,
                               corner_radius=10, border_width=1,
                               border_color=_BORDER)
            row.pack(fill="x", pady=3)

            left = ctk.CTkFrame(row, fg_color="transparent")
            left.pack(side="left", fill="x", expand=True,
                      padx=14, pady=10)

            title = ctk.CTkFrame(left, fg_color="transparent")
            title.pack(anchor="w")
            ctk.CTkLabel(title, text=icon,
                         font=ctk.CTkFont(size=15),
                         text_color=color).pack(side="left", padx=(0, 6))
            ctk.CTkLabel(title, text=token,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=color).pack(side="left")

            ctk.CTkLabel(left, text=name,
                         font=ctk.CTkFont(family="Consolas", size=11),
                         text_color=_TEXT2, anchor="w").pack(anchor="w")
            if desc:
                ctk.CTkLabel(left, text=desc,
                             font=ctk.CTkFont(size=11),
                             text_color=_MUTED, anchor="w").pack(anchor="w")

            # Device badge
            ctk.CTkLabel(row, text=f'device="{token}"',
                         font=ctk.CTkFont(family="Consolas", size=11),
                         fg_color="#f1f5f9", text_color=color,
                         corner_radius=6, padx=8, pady=4,
                         ).pack(side="right", padx=14)

    # ── App info ──────────────────────────────────────────────────────────

    def _build_app_info(self, parent):
        card = _Card(parent)
        card.pack(fill="x", pady=(0, 4))

        info_row = ctk.CTkFrame(card, fg_color="transparent")
        info_row.pack(fill="x", padx=18, pady=16)

        for label, value, color in [
            ("Application",  "OVMS Manager",       _TEXT),
            ("Version",      f"v{APP_VERSION}",     _BLUE),
            ("Author",       APP_AUTHOR,             _PURPLE),
            ("Repository",   APP_REPO,               _GREEN),
            ("License",      "MIT",                  _MUTED),
        ]:
            col = ctk.CTkFrame(info_row, fg_color="transparent")
            col.pack(side="left", expand=True, fill="x")
            ctk.CTkLabel(col, text=label,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=_MUTED).pack(anchor="w")
            ctk.CTkLabel(col, text=value,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=color).pack(anchor="w")

        card.add_divider()

        ctk.CTkLabel(card,
                     text="Built with Python · customtkinter · OpenVINO GenAI · "
                          "OpenVINO Model Server · HuggingFace Hub",
                     font=ctk.CTkFont(size=11), text_color=_MUTED,
                     anchor="w").pack(fill="x", padx=18, pady=(4, 16))
