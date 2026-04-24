"""
chat.py — Chat tab for testing the active model via the proxy endpoint.

Connects to http://localhost:{proxy_port}/v3/chat/completions with streaming.
"""

import json
import logging
import threading
import tkinter as tk
from typing import Callable

import customtkinter as ctk
import httpx

from app.config import cfg
from app.models import read_active_model_name

logger = logging.getLogger(__name__)

_GREEN  = "#2ecc71"
_RED    = "#e74c3c"
_YELLOW = "#f39c12"
_GRAY   = "#555566"
_USER_BG   = "#1a3a5c"
_ASSIST_BG = "#1e1e2e"
_SYSTEM_BG = "#2a1e3a"


# ---------------------------------------------------------------------------
# Streaming helper
# ---------------------------------------------------------------------------

def stream_chat(
    messages: list[dict],
    model: str,
    on_chunk: Callable[[str], None],
    on_done: Callable[[], None],
    on_error: Callable[[str], None],
    max_tokens: int = 2048,
):
    """Send a streaming chat request in a background thread."""
    def _worker():
        url = f"http://localhost:{cfg.proxy_port}/v3/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": True,
        }
        try:
            with httpx.Client(timeout=120) as client:
                with client.stream("POST", url, json=payload, timeout=120) as resp:
                    if resp.status_code != 200:
                        on_error(f"HTTP {resp.status_code}: {resp.read().decode()[:200]}")
                        return
                    for line in resp.iter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            content = chunk["choices"][0].get("delta", {}).get("content", "")
                            if content:
                                on_chunk(content)
                        except (json.JSONDecodeError, KeyError):
                            continue
            on_done()
        except httpx.ConnectError:
            on_error("Cannot connect — is the proxy running on port "
                     f"{cfg.proxy_port}? Start the stack first.")
        except Exception as exc:
            on_error(str(exc))

    threading.Thread(target=_worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Message bubble widget
# ---------------------------------------------------------------------------

class MessageBubble(ctk.CTkFrame):
    """A single chat message displayed as a coloured card."""

    def __init__(self, master, role: str, content: str = "", **kwargs):
        bg = {"user": _USER_BG, "assistant": _ASSIST_BG, "system": _SYSTEM_BG}.get(role, _ASSIST_BG)
        kwargs.setdefault("fg_color", bg)
        kwargs.setdefault("corner_radius", 10)
        super().__init__(master, **kwargs)

        role_colors = {"user": "#7eb8f7", "assistant": "#a0e0a0", "system": "#c8a8e8"}
        ctk.CTkLabel(
            self,
            text=role.capitalize(),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=role_colors.get(role, "#aaaaaa"),
            anchor="w",
        ).pack(anchor="w", padx=12, pady=(8, 2))

        self._text_var = tk.StringVar(value=content)
        self._label = ctk.CTkLabel(
            self,
            textvariable=self._text_var,
            font=ctk.CTkFont(size=13),
            anchor="w",
            justify="left",
            wraplength=700,
        )
        self._label.pack(anchor="w", padx=12, pady=(0, 10), fill="x")

    def append(self, text: str):
        self._text_var.set(self._text_var.get() + text)

    def set_wrap(self, width: int):
        self._label.configure(wraplength=max(200, width - 80))


# ---------------------------------------------------------------------------
# Chat Tab
# ---------------------------------------------------------------------------

class ChatTab(ctk.CTkFrame):

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self._messages: list[dict] = []          # OpenAI-format history
        self._bubbles:  list[MessageBubble] = []
        self._streaming = False
        self._active_bubble: MessageBubble | None = None

        self._build_ui()
        self.bind("<Configure>", self._on_resize)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ---- Top bar: model name + controls ----
        top = ctk.CTkFrame(self, fg_color="#13131f", corner_radius=0, height=44)
        top.pack(fill="x")
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="Model:", font=ctk.CTkFont(size=12),
                     text_color="#888899").pack(side="left", padx=(14, 4), pady=10)

        self._model_entry = ctk.CTkEntry(top, font=ctk.CTkFont(size=12), width=280, height=28)
        self._model_entry.pack(side="left", pady=8)
        self._refresh_model_name()

        ctk.CTkButton(
            top, text="↺", width=32, height=28, font=ctk.CTkFont(size=14),
            fg_color="transparent", hover_color="#2a2a3a",
            command=self._refresh_model_name,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            top, text="Clear", width=70, height=28, font=ctk.CTkFont(size=12),
            fg_color="#333344", hover_color="#444455",
            command=self._clear,
        ).pack(side="right", padx=14)

        ctk.CTkLabel(top, text="System prompt:", font=ctk.CTkFont(size=12),
                     text_color="#888899").pack(side="right", padx=(0, 4))

        self._sys_entry = ctk.CTkEntry(top, font=ctk.CTkFont(size=12), width=240, height=28,
                                       placeholder_text="Optional system message")
        self._sys_entry.pack(side="right", pady=8)

        # ---- Scrollable message area ----
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="#111120", corner_radius=0)
        self._scroll.pack(fill="both", expand=True)

        # ---- Status bar ----
        self._status = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11),
            text_color="#888899", anchor="w", height=20,
        )
        self._status.pack(fill="x", padx=14)

        # ---- Input row ----
        input_row = ctk.CTkFrame(self, fg_color="#13131f", corner_radius=0, height=70)
        input_row.pack(fill="x", side="bottom")
        input_row.pack_propagate(False)

        self._input = ctk.CTkTextbox(
            input_row,
            font=ctk.CTkFont(size=13),
            height=50,
            fg_color="#1e1e2e",
            border_width=1,
            border_color="#333344",
            wrap="word",
        )
        self._input.pack(side="left", fill="both", expand=True, padx=(12, 6), pady=10)
        # Bind on the inner tk.Text widget — CTkTextbox doesn't propagate bindings
        self._input._textbox.bind("<Return>", self._on_enter)
        self._input._textbox.bind("<Shift-Return>", lambda e: "break")

        self._send_btn = ctk.CTkButton(
            input_row,
            text="Send",
            width=80,
            height=50,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._send,
        )
        self._send_btn.pack(side="right", padx=(0, 12), pady=10)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _refresh_model_name(self):
        name = read_active_model_name() or "qwen2.5-coder-7b"
        self._model_entry.delete(0, "end")
        self._model_entry.insert(0, name)

    def _current_model(self) -> str:
        return self._model_entry.get().strip() or read_active_model_name() or "qwen2.5-coder-7b"

    def _clear(self):
        self._messages.clear()
        for b in self._bubbles:
            b.destroy()
        self._bubbles.clear()
        self._active_bubble = None
        self._status.configure(text="")

    def _on_resize(self, event):
        for b in self._bubbles:
            b.set_wrap(event.width)

    # ------------------------------------------------------------------
    # Send / receive
    # ------------------------------------------------------------------

    def _on_enter(self, event):
        self._send()
        return "break"  # suppress the newline that Enter would insert

    def _send(self):
        if self._streaming:
            return

        text = self._input.get("1.0", "end").strip()
        if not text:
            return

        self._input.delete("1.0", "end")

        # Build message list with optional system prompt
        if not self._messages:
            sys_text = self._sys_entry.get().strip()
            if sys_text:
                self._messages.append({"role": "system", "content": sys_text})
                self._add_bubble("system", sys_text)

        self._messages.append({"role": "user", "content": text})
        self._add_bubble("user", text)

        # Placeholder bubble for the streaming response
        self._active_bubble = self._add_bubble("assistant", "")
        self._streaming = True
        self._send_btn.configure(state="disabled", text="…")
        self._status.configure(text="Generating…", text_color=_YELLOW)

        stream_chat(
            messages=self._messages,
            model=self._current_model(),
            on_chunk=self._on_chunk,
            on_done=self._on_done,
            on_error=self._on_error,
        )

    def _scroll_to_bottom(self):
        try:
            self._scroll._parent_canvas.yview_moveto(1.0)
        except Exception:
            try:
                self._scroll.update_idletasks()
                self._scroll._parent_canvas.yview_moveto(1.0)
            except Exception:
                pass

    def _add_bubble(self, role: str, content: str) -> MessageBubble:
        bubble = MessageBubble(self._scroll, role=role, content=content)
        bubble.pack(fill="x", padx=10, pady=4)
        self._bubbles.append(bubble)
        self._scroll_to_bottom()
        return bubble

    # ------------------------------------------------------------------
    # Streaming callbacks (called from background thread → use .after)
    # ------------------------------------------------------------------

    def _on_chunk(self, text: str):
        self.after(0, lambda t=text: self._apply_chunk(t))

    def _apply_chunk(self, text: str):
        if self._active_bubble:
            self._active_bubble.append(text)
            self._scroll._parent_canvas.yview_moveto(1.0)

    def _on_done(self):
        self.after(0, self._finish)

    def _finish(self):
        self._streaming = False
        self._send_btn.configure(state="normal", text="Send")
        self._status.configure(text="", text_color="#888899")

        # Record the full assistant response in history
        if self._active_bubble:
            content = self._active_bubble._text_var.get()
            self._messages.append({"role": "assistant", "content": content})
        self._active_bubble = None

    def _on_error(self, msg: str):
        self.after(0, lambda: self._show_error(msg))

    def _show_error(self, msg: str):
        self._streaming = False
        self._send_btn.configure(state="normal", text="Send")
        self._status.configure(text=f"Error: {msg}", text_color=_RED)
        if self._active_bubble:
            self._active_bubble.append(f"\n[Error: {msg}]")
        self._active_bubble = None
