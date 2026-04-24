"""
guide.py — Integration guide tab.

Shows users how to connect to the running OVMS endpoint via:
  - Direct REST API  (curl, Python OpenAI SDK, JS/TS)
  - Continue.dev VS Code extension
  - OpenCode CLI

All code snippets use live values from cfg (port, model name).
"""

import tkinter as tk
import customtkinter as ctk

from app.config import cfg
from app.models import read_active_model_name

# ── Palette (mirrors light theme in gui.py) ───────────────────────────────
_BG      = "#f1f5f9"
_CARD    = "#ffffff"
_BORDER  = "#e2e8f0"
_TEXT    = "#0f172a"
_TEXT2   = "#334155"
_MUTED   = "#94a3b8"
_GREEN   = "#16a34a"
_BLUE    = "#2563eb"
_CODE_BG = "#1e293b"   # dark slate — code block bg
_CODE_FG = "#e2e8f0"   # light text on dark code block
_TAG_BLUE   = "#dbeafe"
_TAG_GREEN  = "#dcfce7"
_TAG_PURPLE = "#ede9fe"


# ── Helpers ───────────────────────────────────────────────────────────────

def _active_model() -> str:
    return read_active_model_name() or "qwen2.5-coder-7b"

def _base_url() -> str:
    return f"http://localhost:{cfg.proxy_port}/v3"


# ── Reusable widgets ──────────────────────────────────────────────────────

class _Tag(ctk.CTkLabel):
    """Small pill badge."""
    _COLORS = {
        "blue":   (_TAG_BLUE,   _BLUE),
        "green":  (_TAG_GREEN,  _GREEN),
        "purple": (_TAG_PURPLE, "#7c3aed"),
    }

    def __init__(self, master, text: str, color: str = "blue", **kw):
        bg, fg = self._COLORS.get(color, (_TAG_BLUE, _BLUE))
        super().__init__(master, text=text,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         fg_color=bg, text_color=fg,
                         corner_radius=6, padx=6, pady=2, **kw)


class _SectionCard(ctk.CTkFrame):
    """Titled section card with a left accent bar."""

    def __init__(self, master, title: str, subtitle: str = "",
                 tags: list[tuple[str, str]] | None = None, **kw):
        kw.setdefault("fg_color", _CARD)
        kw.setdefault("corner_radius", 14)
        kw.setdefault("border_width", 1)
        kw.setdefault("border_color", _BORDER)
        super().__init__(master, **kw)

        # Header row
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=18, pady=(16, 4))

        ctk.CTkLabel(hdr, text=title,
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=_TEXT).pack(side="left")

        if tags:
            for t, c in tags:
                _Tag(hdr, t, c).pack(side="left", padx=(8, 0))

        if subtitle:
            ctk.CTkLabel(self, text=subtitle,
                         font=ctk.CTkFont(size=12), text_color=_MUTED,
                         anchor="w", wraplength=860).pack(fill="x", padx=18, pady=(0, 10))

        # Content area — children should pack into self
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.pack(fill="x", padx=18, pady=(0, 16))

    @property
    def body(self) -> ctk.CTkFrame:
        return self._body


class _CodeBlock(ctk.CTkFrame):
    """Dark-background monospace code block with a Copy button."""

    def __init__(self, master, label: str, code_fn, **kw):
        """
        label   — displayed above the block
        code_fn — callable() → str  so values update when tab is opened
        """
        kw.setdefault("fg_color", "transparent")
        super().__init__(master, **kw)
        self._code_fn = code_fn

        # Label row
        lbl_row = ctk.CTkFrame(self, fg_color="transparent")
        lbl_row.pack(fill="x", pady=(8, 2))
        ctk.CTkLabel(lbl_row, text=label,
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=_TEXT2).pack(side="left")

        # Code frame
        code_frame = ctk.CTkFrame(self, fg_color=_CODE_BG, corner_radius=10)
        code_frame.pack(fill="x")

        self._textbox = ctk.CTkTextbox(
            code_frame,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=_CODE_BG,
            text_color=_CODE_FG,
            wrap="none",
            state="normal",
            border_width=0,
            height=1,            # will be resized after insert
        )
        self._textbox.pack(fill="x", padx=12, pady=(10, 4))

        copy_row = ctk.CTkFrame(code_frame, fg_color="transparent")
        copy_row.pack(fill="x", padx=8, pady=(0, 6))
        self._copied_lbl = ctk.CTkLabel(copy_row, text="",
                                        font=ctk.CTkFont(size=10),
                                        text_color=_GREEN)
        self._copied_lbl.pack(side="left", padx=4)
        ctk.CTkButton(copy_row, text="Copy", width=60, height=24,
                      font=ctk.CTkFont(size=11),
                      fg_color="#334155", hover_color="#475569",
                      text_color="#f8fafc",
                      command=self._copy).pack(side="right", padx=4)

        self.refresh()

    def refresh(self):
        code = self._code_fn()
        lines = code.count("\n") + 1
        self._textbox.configure(state="normal", height=lines * 20 + 8)
        self._textbox.delete("1.0", "end")
        self._textbox.insert("end", code)
        self._textbox.configure(state="disabled")

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self._code_fn())
        self._copied_lbl.configure(text="✓ Copied!")
        self.after(2000, lambda: self._copied_lbl.configure(text=""))


class _Step(ctk.CTkFrame):
    """Numbered instruction step."""

    def __init__(self, master, number: int, text: str, **kw):
        kw.setdefault("fg_color", "transparent")
        super().__init__(master, **kw)

        # Number circle
        canvas = tk.Canvas(self, width=26, height=26,
                           bg=_CARD, highlightthickness=0)
        canvas.pack(side="left", anchor="n", pady=2)
        canvas.create_oval(1, 1, 25, 25, fill=_BLUE, outline="")
        canvas.create_text(13, 13, text=str(number),
                           fill="white", font=("Segoe UI", 10, "bold"))

        ctk.CTkLabel(self, text=text,
                     font=ctk.CTkFont(size=12), text_color=_TEXT2,
                     anchor="w", justify="left",
                     wraplength=800).pack(side="left", padx=(10, 0), pady=4)


# ── Guide Tab ─────────────────────────────────────────────────────────────

class GuideTab(ctk.CTkFrame):

    def __init__(self, master, **kw):
        kw.setdefault("fg_color", _BG)
        super().__init__(master, **kw)
        self._code_blocks: list[_CodeBlock] = []
        self._build_ui()

    def _build_ui(self):
        # Master scroll area
        scroll = ctk.CTkScrollableFrame(self, fg_color=_BG, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        inner = ctk.CTkFrame(scroll, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)

        self._build_overview(inner)
        self._build_api(inner)
        self._build_continue(inner)
        self._build_opencode(inner)

    # ── Overview ──────────────────────────────────────────────────────────

    def _build_overview(self, parent):
        card = _SectionCard(parent, "Quick Reference",
                            subtitle="Your local OVMS stack exposes an OpenAI-compatible endpoint. "
                                     "Any tool that supports a custom OpenAI base URL works out of the box.")
        card.pack(fill="x", pady=(0, 12))

        row = ctk.CTkFrame(card.body, fg_color="transparent")
        row.pack(fill="x")
        row.columnconfigure((0, 1), weight=1)

        for col, (lbl, fn, accent) in enumerate([
            ("Base URL",    _base_url,     _BLUE),
            ("Active Model", _active_model, _GREEN),
        ]):
            f = ctk.CTkFrame(row, fg_color=_BG, corner_radius=10,
                             border_width=1, border_color=_BORDER)
            f.grid(row=0, column=col, padx=(0 if col else 0, 6 if col == 0 else 0), sticky="ew")
            ctk.CTkLabel(f, text=lbl, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=accent).pack(anchor="w", padx=12, pady=(8, 2))
            var = tk.StringVar(value=fn())
            ctk.CTkLabel(f, textvariable=var,
                         font=ctk.CTkFont(family="Consolas", size=13),
                         text_color=_TEXT).pack(anchor="w", padx=12, pady=(0, 8))
            # Keep var refreshable
            setattr(self, f"_var_{col}", (var, fn))

    # ── REST API ──────────────────────────────────────────────────────────

    def _build_api(self, parent):
        card = _SectionCard(
            parent, "REST API",
            subtitle="Use any HTTP client or OpenAI-compatible SDK. "
                     "Point base_url to the proxy and set api_key to any non-empty string.",
            tags=[("OpenAI-compatible", "blue"), ("Streaming", "green")],
        )
        card.pack(fill="x", pady=(0, 12))

        blocks = [
            ("cURL",
             lambda: f"""curl {_base_url()}/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{{
    "model": "{_active_model()}",
    "messages": [{{"role": "user", "content": "Write hello world in Python"}}],
    "max_tokens": 512,
    "stream": false
  }}'"""),
            ("Python — openai SDK",
             lambda: f"""from openai import OpenAI

client = OpenAI(
    base_url="{_base_url()}",
    api_key="unused",
)

response = client.chat.completions.create(
    model="{_active_model()}",
    messages=[{{"role": "user", "content": "Write hello world in Python"}}],
    max_tokens=512,
)
print(response.choices[0].message.content)"""),
            ("Python — streaming",
             lambda: f"""from openai import OpenAI

client = OpenAI(base_url="{_base_url()}", api_key="unused")

with client.chat.completions.stream(
    model="{_active_model()}",
    messages=[{{"role": "user", "content": "Explain binary search"}}],
    max_tokens=1024,
) as stream:
    for chunk in stream.text_stream:
        print(chunk, end="", flush=True)"""),
            ("JavaScript / TypeScript",
             lambda: f"""import OpenAI from "openai";

const client = new OpenAI({{
  baseURL: "{_base_url()}",
  apiKey: "unused",
}});

const response = await client.chat.completions.create({{
  model: "{_active_model()}",
  messages: [{{ role: "user", content: "Write hello world in Python" }}],
}});

console.log(response.choices[0].message.content);"""),
        ]

        for label, fn in blocks:
            cb = _CodeBlock(card.body, label, fn)
            cb.pack(fill="x", pady=(0, 4))
            self._code_blocks.append(cb)

    # ── Continue.dev ──────────────────────────────────────────────────────

    def _build_continue(self, parent):
        card = _SectionCard(
            parent, "Continue.dev  —  VS Code Extension",
            subtitle="AI-powered code completion and chat inside VS Code. "
                     "Supports inline autocomplete, chat, and edit modes.",
            tags=[("VS Code", "blue"), ("Autocomplete", "green"), ("Chat", "purple")],
        )
        card.pack(fill="x", pady=(0, 12))

        steps = [
            "Open VS Code → Extensions (Ctrl+Shift+X) → search 'Continue' → Install.",
            "Click the Continue icon in the sidebar, then open its settings.",
            "Select 'Open config file' (or press Ctrl+Shift+P → 'Continue: Open config').",
            "Replace (or merge) the content with the YAML below, then save.",
            "The model appears in Continue's model picker immediately — no restart needed.",
        ]
        for i, s in enumerate(steps, 1):
            _Step(card.body, i, s).pack(fill="x", pady=2)

        cb = _CodeBlock(
            card.body, "~/.continue/config.yaml",
            lambda: f"""name: Local Assistant
version: 1.0.0
schema: v1
models:
  - name: OVMS {_active_model()}
    provider: openai
    model: {_active_model()}
    apiKey: unused
    apiBase: {_base_url()}
    roles:
      - chat
      - edit
      - apply
      - autocomplete
    capabilities:
      - tool_use
    autocompleteOptions:
      maxPromptTokens: 500
      debounceDelay: 124
      modelTimeout: 400
      onlyMyCode: true
      useCache: true
context:
  - provider: code
  - provider: docs
  - provider: diff
  - provider: terminal
  - provider: problems
  - provider: folder
  - provider: codebase""",
        )
        cb.pack(fill="x", pady=(8, 0))
        self._code_blocks.append(cb)

        note = ctk.CTkFrame(card.body, fg_color="#eff6ff", corner_radius=8,
                            border_width=1, border_color="#bfdbfe")
        note.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(note,
                     text="💡  Tip: apiBase uses port 8001 (the proxy) so max_tokens is "
                          "automatically clamped to fit within the model's context window.",
                     font=ctk.CTkFont(size=11), text_color="#1e40af",
                     anchor="w", wraplength=840, justify="left",
                     ).pack(anchor="w", padx=12, pady=8)

    # ── OpenCode ──────────────────────────────────────────────────────────

    def _build_opencode(self, parent):
        card = _SectionCard(
            parent, "OpenCode  —  Terminal AI Coding Agent",
            subtitle="A terminal-based AI coding assistant. "
                     "Reads your codebase, edits files, and runs commands autonomously.",
            tags=[("Terminal", "blue"), ("Agent", "purple")],
        )
        card.pack(fill="x", pady=(0, 12))

        steps = [
            "Install OpenCode — see opencode.ai for the latest installer.",
            "Create or edit the global config file shown below.",
            'Run "opencode" in your project directory, then press "/" to pick the model.',
            "Select  OVMS Local → " + _active_model() + "  from the list.",
        ]
        for i, s in enumerate(steps, 1):
            _Step(card.body, i, s).pack(fill="x", pady=2)

        cb = _CodeBlock(
            card.body, "~/.config/opencode/opencode.json",
            lambda: f"""{{
  "$schema": "https://opencode.ai/config.json",
  "provider": {{
    "ovms": {{
      "npm": "@ai-sdk/openai-compatible",
      "name": "OVMS Local",
      "options": {{
        "baseURL": "{_base_url()}"
      }},
      "models": {{
        "{_active_model()}": {{
          "name": "{_active_model()} (Arc iGPU)",
          "contextLength": 32768,
          "maxTokens": 8192
        }}
      }}
    }}
  }}
}}""",
        )
        cb.pack(fill="x", pady=(8, 0))
        self._code_blocks.append(cb)

        note = ctk.CTkFrame(card.body, fg_color="#f0fdf4", corner_radius=8,
                            border_width=1, border_color="#bbf7d0")
        note.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(note,
                     text="💡  Tip: contextLength and maxTokens tell OpenCode how much "
                          "room the model has, preventing the 'exceeds max length' error.",
                     font=ctk.CTkFont(size=11), text_color="#166534",
                     anchor="w", wraplength=840, justify="left",
                     ).pack(anchor="w", padx=12, pady=8)

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def on_show(self):
        """Call when the tab becomes visible to refresh dynamic values."""
        for cb in self._code_blocks:
            cb.refresh()
        # Refresh quick-reference vars
        for attr in ("_var_0", "_var_1"):
            pair = getattr(self, attr, None)
            if pair:
                var, fn = pair
                var.set(fn())
