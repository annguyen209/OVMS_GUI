"""
chat.py - Chat tab for testing the active model via the proxy endpoint.

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
from app.tools import TOOL_DEFINITIONS, execute_tool, parse_text_tool_call

logger = logging.getLogger(__name__)

_GREEN   = "#107c10"
_RED     = "#a4262c"
_AMBER   = "#c55000"
_MUTED   = "#6b7280"
_TEXT    = "#111827"
_TEXT2   = "#374151"
_BLUE    = "#0078d4"
_BLUE_H  = "#106ebe"
_BORDER  = "#e5e7eb"
_BORDER2 = "#d1d5db"
_CARD    = "#ffffff"
_CARD2   = "#f9fafb"

_USER_BG   = "#eff6ff"   # very light blue
_ASSIST_BG = "#ffffff"   # white
_SYSTEM_BG = "#f9fafb"   # gray-50
_CHAT_BG   = "#f3f4f6"   # gray-100


# ---------------------------------------------------------------------------
# Streaming helper
# ---------------------------------------------------------------------------

_BASE = lambda: f"http://localhost:{cfg.proxy_port}/v3/chat/completions"


def stream_chat(
    messages: list[dict],
    model: str,
    on_chunk: Callable[[str], None],
    on_done: Callable[[], None],
    on_error: Callable[[str], None],
    max_tokens: int = 2048,
    use_tools: bool = False,
    on_tool_call: Callable[[str, str], None] | None = None,
):
    """
    Send a chat request, optionally with tool use (agentic loop).

    If use_tools=True:
      1. Non-streaming call with tool definitions
      2. Execute any tool_calls the model requests (up to 5 rounds)
      3. Stream the final response
    If use_tools=False:
      Plain streaming request (original behaviour).
    on_tool_call(tool_name, result) - called when a tool executes (for UI display)
    """
    def _worker():
        try:
            with httpx.Client(timeout=120) as client:
                msgs = list(messages)

                if use_tools:
                    # Agentic loop — up to 5 rounds
                    for _ in range(5):
                        payload = {
                            "model": model,
                            "messages": msgs,
                            "max_tokens": max_tokens,
                            "tools": TOOL_DEFINITIONS,
                            "tool_choice": "auto",
                            "stream": False,
                        }
                        r = client.post(_BASE(), json=payload, timeout=120)
                        if r.status_code != 200:
                            on_error(f"HTTP {r.status_code}: {r.text[:300]}")
                            return

                        data     = r.json()
                        choice   = data["choices"][0]
                        msg      = choice["message"]
                        finish   = choice.get("finish_reason", "")
                        content  = msg.get("content") or ""

                        # --- Structured tool_calls (proper function calling) ---
                        tool_calls = (msg.get("tool_calls")
                                      or choice.get("tool_calls")
                                      or [])

                        # --- Text-based tool call (model outputs JSON in content) ---
                        text_tc = None
                        if not tool_calls and content:
                            text_tc = parse_text_tool_call(content)

                        logger.debug("Tool round finish=%s structured=%d text=%s",
                                     finish, len(tool_calls), text_tc)

                        if not tool_calls and not text_tc:
                            # No tool call — deliver the content as final answer
                            if content:
                                on_chunk(content)
                            on_done()
                            return

                        if tool_calls:
                            # Structured tool_calls path
                            msgs.append({
                                "role": "assistant",
                                "content": content,
                                "tool_calls": tool_calls,
                            })
                            for tc in tool_calls:
                                fn   = tc.get("function", {})
                                name = fn.get("name", "unknown")
                                args = fn.get("arguments", "{}")
                                result = execute_tool(name, args)
                                if on_tool_call:
                                    on_tool_call(name, result)
                                msgs.append({
                                    "role":         "tool",
                                    "tool_call_id": tc.get("id", "0"),
                                    "content":      result,
                                })
                        else:
                            # Text-based tool call path
                            name   = text_tc["name"]
                            args   = text_tc["arguments"]
                            result = execute_tool(name, args)
                            if on_tool_call:
                                on_tool_call(name, result)
                            # Feed result back as a user turn (model will understand)
                            msgs.append({"role": "assistant", "content": content})
                            msgs.append({
                                "role":    "user",
                                "content": f"Tool result for {name}:\n{result}",
                            })

                    on_error("Tool call limit reached (5 rounds).")
                    return

                # Plain streaming (no tools)
                payload = {
                    "model": model,
                    "messages": msgs,
                    "max_tokens": max_tokens,
                    "stream": True,
                }
                with client.stream("POST", _BASE(), json=payload, timeout=120) as resp:
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
                            content = (chunk["choices"][0]
                                       .get("delta", {}).get("content", ""))
                            if content:
                                on_chunk(content)
                        except (json.JSONDecodeError, KeyError):
                            continue
                on_done()

        except httpx.ConnectError:
            on_error(f"Cannot connect. Is the proxy running on port "
                     f"{cfg.proxy_port}? Start the stack first.")
        except Exception as exc:
            on_error(str(exc))

    threading.Thread(target=_worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Message bubble widget
# ---------------------------------------------------------------------------

class MessageBubble(ctk.CTkFrame):
    """A single chat message card with Copy and optional Retry buttons."""

    _ROLE_COLORS  = {"user": _BLUE,  "assistant": _GREEN, "system": _TEXT2}
    _BORDER_COLORS = {"user": "#bfdbfe", "assistant": "#bbf7d0", "system": _BORDER}
    _BG_COLORS     = {"user": _USER_BG,  "assistant": _ASSIST_BG, "system": _SYSTEM_BG}

    def __init__(self, master, role: str, content: str = "",
                 on_retry=None, **kwargs):
        kwargs.setdefault("fg_color",      self._BG_COLORS.get(role, _ASSIST_BG))
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("border_width",  1)
        kwargs.setdefault("border_color",  self._BORDER_COLORS.get(role, _BORDER))
        super().__init__(master, **kwargs)
        self._role     = role
        self._on_retry = on_retry

        # Header: role label + action buttons
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(8, 2))

        ctk.CTkLabel(hdr, text=role.capitalize(),
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=self._ROLE_COLORS.get(role, _MUTED),
                     anchor="w").pack(side="left")

        # Retry button (assistant only)
        if role == "assistant" and on_retry:
            ctk.CTkButton(hdr, text="Retry", width=48, height=20,
                          font=ctk.CTkFont(size=10),
                          fg_color=_CARD2, hover_color=_BORDER,
                          border_width=1, border_color=_BORDER2,
                          text_color=_TEXT2,
                          command=on_retry,
                          ).pack(side="right", padx=(4, 0))

        # Copy button (all roles)
        self._copy_lbl = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(size=10),
                                       text_color=_GREEN)
        self._copy_lbl.pack(side="right", padx=(0, 4))
        ctk.CTkButton(hdr, text="Copy", width=48, height=20,
                      font=ctk.CTkFont(size=10),
                      fg_color=_CARD2, hover_color=_BORDER,
                      border_width=1, border_color=_BORDER2,
                      text_color=_TEXT2,
                      command=self._copy,
                      ).pack(side="right", padx=(0, 2))

        # Content
        self._text_var = tk.StringVar(value=content)
        self._label = ctk.CTkLabel(
            self,
            textvariable=self._text_var,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=_TEXT,
            anchor="w",
            justify="left",
            wraplength=700,
        )
        self._label.pack(anchor="w", padx=14, pady=(0, 10), fill="x")

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self._text_var.get())
        self._copy_lbl.configure(text="Copied")
        self.after(2000, lambda: self._copy_lbl.configure(text=""))

    def append(self, text: str):
        self._text_var.set(self._text_var.get() + text)

    def get_text(self) -> str:
        return self._text_var.get()

    def set_wrap(self, width: int):
        self._label.configure(wraplength=max(200, width - 100))


# ---------------------------------------------------------------------------
# Chat Tab
# ---------------------------------------------------------------------------

class ChatTab(ctk.CTkFrame):

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self._messages: list[dict] = []
        self._bubbles:  list[MessageBubble] = []
        self._streaming = False
        self._active_bubble: MessageBubble | None = None
        self._ime_composing = False   # True while Windows IME is mid-composition

        self._build_ui()
        self.bind("<Configure>", self._on_resize)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ---- Top bar ----
        top = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=0, height=48,
                           border_width=1, border_color=_BORDER)
        top.pack(fill="x")
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="Model:", font=ctk.CTkFont(size=12),
                     text_color=_MUTED).pack(side="left", padx=(14, 4), pady=12)

        self._model_entry = ctk.CTkEntry(top, font=ctk.CTkFont(size=12), width=280, height=30)
        self._model_entry.pack(side="left", pady=9)
        self._refresh_model_name()

        ctk.CTkButton(
            top, text="Refresh", width=60, height=30, font=ctk.CTkFont(size=11),
            fg_color=_CARD2, hover_color=_BORDER,
            border_width=1, border_color=_BORDER2,
            text_color=_TEXT2,
            command=self._refresh_model_name,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            top, text="Clear", width=70, height=30, font=ctk.CTkFont(size=12),
            fg_color=_CARD2, hover_color=_BORDER,
            border_width=1, border_color=_BORDER2,
            text_color=_TEXT2,
            command=self._clear,
        ).pack(side="right", padx=14)

        # Tools toggle
        self._tools_var = ctk.BooleanVar(value=False)
        ctk.CTkLabel(top, text="Web tools:",
                     font=ctk.CTkFont(size=11), text_color=_MUTED,
                     ).pack(side="right", padx=(0, 4))
        ctk.CTkSwitch(top, text="", variable=self._tools_var,
                      width=40, button_color=_BLUE, progress_color=_BLUE,
                      ).pack(side="right", padx=(0, 4))

        ctk.CTkLabel(top, text="System prompt:", font=ctk.CTkFont(size=12),
                     text_color=_MUTED).pack(side="right", padx=(0, 4))

        self._sys_entry = ctk.CTkEntry(top, font=ctk.CTkFont(size=12), width=240, height=30,
                                       placeholder_text="Optional system message")
        self._sys_entry.pack(side="right", pady=9)

        # ---- Scrollable message area ----
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=_CHAT_BG, corner_radius=0)
        self._scroll.pack(fill="both", expand=True)

        # ---- Status bar ----
        self._status = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11),
            text_color=_MUTED, anchor="w", height=22,
        )
        self._status.pack(fill="x", padx=14)

        # ---- Input row ----
        # Use tk.Frame + tk.Text for the input so Vietnamese IME works natively.
        # CTkTextbox intercepts key events that break IME character composition.
        input_row = tk.Frame(self, bg=_CARD,
                             highlightthickness=1,
                             highlightbackground=_BORDER,
                             highlightcolor=_BORDER,
                             height=72)
        input_row.pack(fill="x", side="bottom")
        input_row.pack_propagate(False)

        # Plain tk.Text — full IME support, full Unicode, no event interception
        self._input = tk.Text(
            input_row,
            font=("Segoe UI", 12),
            bg=_CARD2,
            fg=_TEXT,
            insertbackground=_TEXT,    # cursor colour
            relief="flat",
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_BLUE,
            wrap="word",
            height=3,
            padx=8,
            pady=6,
            undo=True,
        )
        self._input.pack(side="left", fill="both", expand=True,
                         padx=(12, 6), pady=10)

        self._input.bind("<<CompositionStart>>",
                         lambda e: setattr(self, "_ime_composing", True))
        self._input.bind("<<CompositionEnd>>",
                         lambda e: setattr(self, "_ime_composing", False))
        # Use add="+" so our handler runs alongside the default handler,
        # not instead of it. The default handler lets Unikey/EVKey flush
        # the composed character before we read the text.
        self._input.bind("<Return>",       self._on_enter, add="+")
        # Ctrl+Enter inserts a newline for multi-line messages
        self._input.bind("<Control-Return>", lambda e: self._input.insert("insert", "\n"))

        self._send_btn = ctk.CTkButton(
            input_row,
            text="Send",
            width=80,
            height=50,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=_BLUE,
            hover_color=_BLUE_H,
            text_color="#ffffff",
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
        if self._ime_composing:
            return          # let IME use Enter to confirm the composition
        self._send()
        # Do NOT return "break" — let the default handler run so Unikey/EVKey
        # can flush any pending composed character. _send() clears the box,
        # so the newline the default handler inserts is immediately deleted.

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

        use_tools = self._tools_var.get()

        # Placeholder bubble for the response
        self._active_bubble = self._add_bubble("assistant", "",
                                               on_retry=self._retry)
        self._streaming = True
        self._send_btn.configure(state="disabled", text="...")
        status_text = "Thinking (web tools on)..." if use_tools else "Generating..."
        self._status.configure(text=status_text, text_color=_AMBER)

        stream_chat(
            messages=self._messages,
            model=self._current_model(),
            on_chunk=self._on_chunk,
            on_done=self._on_done,
            on_error=self._on_error,
            use_tools=use_tools,
            on_tool_call=self._on_tool_call,
        )

    def _scroll_to_bottom(self):
        def _do():
            try:
                self._scroll.update_idletasks()
                self._scroll._parent_canvas.yview_moveto(1.0)
            except Exception:
                pass
        self.after(30, _do)

    def _add_bubble(self, role: str, content: str,
                    on_retry=None) -> MessageBubble:
        bubble = MessageBubble(self._scroll, role=role, content=content,
                               on_retry=on_retry)
        bubble.pack(fill="x", padx=10, pady=4)
        self._bubbles.append(bubble)
        self._scroll_to_bottom()
        return bubble

    def _retry(self):
        """Re-run the last user message."""
        if self._streaming:
            return
        # Find last user message
        last_user = None
        for msg in reversed(self._messages):
            if msg["role"] == "user":
                last_user = msg["content"]
                break
        if not last_user:
            return
        # Remove the last assistant response from history
        if self._messages and self._messages[-1]["role"] == "assistant":
            self._messages.pop()
        # Remove the last assistant bubble from UI
        if self._bubbles and self._bubbles[-1]._role == "assistant":
            self._bubbles[-1].destroy()
            self._bubbles.pop()

        self._active_bubble = self._add_bubble(
            "assistant", "", on_retry=self._retry)
        self._streaming = True
        self._send_btn.configure(state="disabled", text="...")
        self._status.configure(text="Retrying...", text_color=_AMBER)

        stream_chat(
            messages=self._messages,
            model=self._current_model(),
            on_chunk=self._on_chunk,
            on_done=self._on_done,
            on_error=self._on_error,
            use_tools=self._tools_var.get(),
            on_tool_call=self._on_tool_call,
        )

    # ------------------------------------------------------------------
    # Streaming callbacks (called from background thread - use .after)
    # ------------------------------------------------------------------

    def _on_tool_call(self, name: str, result: str):
        """Show a compact tool-call notice in the chat."""
        label = {
            "get_current_time": "Getting current time",
            "get_weather":      "Fetching weather",
            "web_search":       "Searching the web",
            "fetch_url":        "Fetching URL",
        }.get(name, f"Calling {name}")
        self.after(0, lambda: self._status.configure(
            text=f"{label}...", text_color=_BLUE))

    def _on_chunk(self, text: str):
        self.after(0, lambda t=text: self._apply_chunk(t))

    def _apply_chunk(self, text: str):
        if self._active_bubble:
            self._active_bubble.append(text)
            self._scroll_to_bottom()

    def _on_done(self):
        self.after(0, self._finish)

    def _finish(self):
        self._streaming = False
        self._send_btn.configure(state="normal", text="Send")
        self._status.configure(text="", text_color=_MUTED)

        if self._active_bubble:
            content = self._active_bubble.get_text()
            self._messages.append({"role": "assistant", "content": content})
            self._scroll_to_bottom()
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
