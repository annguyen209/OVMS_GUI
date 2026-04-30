"""
chat.py - Chat tab for testing the active model via the proxy endpoint.

Connects to http://localhost:{proxy_port}/v3/chat/completions with streaming.
"""

import json
import logging
import re as _re
import threading
import tkinter as tk
from typing import Callable

import customtkinter as ctk
import httpx

from app.config import cfg
from app.models import read_active_model_name, CURATED_MODELS
from app.tools import TOOL_DEFINITIONS, execute_tool, parse_text_tool_call
from app import theme

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Streaming helper
# ---------------------------------------------------------------------------

_BASE = lambda: f"http://localhost:{cfg.proxy_port}/v3/chat/completions"


def _apply_markdown(widget: "tk.Text", text: str) -> None:
    """
    Clear *widget* and re-insert *text* with markdown formatting tags applied.
    Expected tags on widget: bold, italic, code_inline, code_block, heading
    """
    widget.configure(state="normal")
    widget.delete("1.0", "end")

    parts = _re.split(r"```(?:[a-zA-Z]*\n?)?(.*?)```", text, flags=_re.DOTALL)

    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            widget.insert("end", part.strip(), "code_block")
            widget.insert("end", "\n")
        else:
            lines = part.split("\n")
            for line_no, line in enumerate(lines):
                if line_no > 0:
                    widget.insert("end", "\n")
                _insert_inline(widget, line)

    widget.configure(state="disabled")
    _auto_height(widget)


def _insert_inline(widget: "tk.Text", line: str) -> None:
    """Insert one line with inline markdown tags."""
    m = _re.match(r"^(#{1,3})\s+(.+)$", line)
    if m:
        widget.insert("end", m.group(2), "heading")
        return

    pattern = _re.compile(
        r"`([^`]+)`"
        r"|\*\*\*(.+?)\*\*\*"
        r"|\*\*(.+?)\*\*"
        r"|___(.+?)___"
        r"|\*(.+?)\*"
        r"|__(.+?)__"
        r"|_([^_]+)_"
    )
    pos = 0
    for match in pattern.finditer(line):
        if match.start() > pos:
            widget.insert("end", line[pos:match.start()])
        g = match.groups()
        if g[0] is not None:
            widget.insert("end", g[0], "code_inline")
        elif g[1] is not None:
            widget.insert("end", g[1], ("bold", "italic"))
        elif g[2] is not None:
            widget.insert("end", g[2], "bold")
        elif g[3] is not None:
            widget.insert("end", g[3], "bold")
        elif g[4] is not None:
            widget.insert("end", g[4], "italic")
        elif g[5] is not None:
            widget.insert("end", g[5], "bold")
        elif g[6] is not None:
            widget.insert("end", g[6], "italic")
        pos = match.end()
    if pos < len(line):
        widget.insert("end", line[pos:])


def _auto_height(widget: "tk.Text") -> None:
    """Resize tk.Text to fit its content."""
    lines = int(widget.index("end-1c").split(".")[0])
    widget.configure(height=max(1, lines))


def _strip_think_tags(text: str) -> str:
    """Remove reasoning blocks from model output.

    Handles three forms:
      <think>...</think>   - complete block
      <think>...           - unclosed opening tag (streaming cut off)
      ...</think>          - no opening tag (model omitted it)
    """
    # Complete blocks
    text = _re.sub(r"<think>.*?</think>\s*", "", text, flags=_re.DOTALL)
    # Orphaned closing tag - strip everything up to and including </think>
    text = _re.sub(r"^.*?</think>\s*", "", text, flags=_re.DOTALL)
    # Orphaned opening tag - strip from <think> to end (unfinished reasoning)
    text = _re.sub(r"<think>.*$", "", text, flags=_re.DOTALL)
    return text.strip()


def stream_chat(
    messages: list[dict],
    model: str,
    on_chunk: Callable[[str], None],
    on_done: Callable[[], None],
    on_error: Callable[[str], None],
    max_tokens: int = 2048,
    use_tools: bool = False,
    on_tool_call: Callable[[str, str], None] | None = None,
    on_messages_update: Callable[[list[dict]], None] | None = None,
    stop_event: "threading.Event | None" = None,
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
                    # Agentic loop - up to 5 rounds
                    for _ in range(5):
                        if stop_event and stop_event.is_set():
                            if on_messages_update:
                                on_messages_update(msgs)
                            on_done()
                            return
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
                            # No tool call - deliver the content as final answer
                            if content:
                                on_chunk(content)
                            # Sync full message history (includes tool turns) back to caller
                            if on_messages_update:
                                on_messages_update(msgs)
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
                    if on_messages_update:
                        on_messages_update(msgs)
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
                        if stop_event and stop_event.is_set():
                            break
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

    _ROLE_COLORS  = {"user": theme.BLUE,  "assistant": theme.GREEN, "system": theme.TEXT2}
    _BORDER_COLORS = {"user": "#bfdbfe", "assistant": "#bbf7d0", "system": theme.BORDER}
    _BG_COLORS     = {"user": theme.USER_BG,  "assistant": theme.ASSIST_BG, "system": theme.SYSTEM_BG}

    def __init__(self, master, role: str, content: str = "",
                 on_retry=None, **kwargs):
        kwargs.setdefault("fg_color",      self._BG_COLORS.get(role, theme.ASSIST_BG))
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("border_width",  1)
        kwargs.setdefault("border_color",  self._BORDER_COLORS.get(role, theme.BORDER))
        super().__init__(master, **kwargs)
        self._role     = role
        self._on_retry = on_retry

        # Header: role label + action buttons
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(8, 2))

        ctk.CTkLabel(hdr, text=role.capitalize(),
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=self._ROLE_COLORS.get(role, theme.MUTED),
                     anchor="w").pack(side="left")

        # Retry button (assistant only)
        if role == "assistant" and on_retry:
            ctk.CTkButton(hdr, text="Retry", width=48, height=20,
                          font=ctk.CTkFont(size=10),
                          fg_color=theme.CARD2, hover_color=theme.BORDER,
                          border_width=1, border_color=theme.BORDER2,
                          text_color=theme.TEXT2,
                          command=on_retry,
                          ).pack(side="right", padx=(4, 0))

        # Copy button (all roles)
        self._copy_lbl = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(size=10),
                                       text_color=theme.GREEN)
        self._copy_lbl.pack(side="right", padx=(0, 4))
        ctk.CTkButton(hdr, text="Copy", width=48, height=20,
                      font=ctk.CTkFont(size=10),
                      fg_color=theme.CARD2, hover_color=theme.BORDER,
                      border_width=1, border_color=theme.BORDER2,
                      text_color=theme.TEXT2,
                      command=self._copy,
                      ).pack(side="right", padx=(0, 2))

        # Content - tk.Text for markdown rendering
        self._textbox = tk.Text(
            self,
            font=("Segoe UI", 13),
            bg=self._BG_COLORS.get(role, theme.ASSIST_BG),
            fg=theme.TEXT,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            wrap="word",
            state="disabled",
            cursor="arrow",
            padx=14,
            pady=4,
            height=1,
        )
        self._textbox.pack(fill="x", padx=0, pady=(0, 4))

        # Stats line - response time + token count (assistant only)
        self._stats_lbl: ctk.CTkLabel | None = None
        if role == "assistant":
            self._stats_lbl = ctk.CTkLabel(
                self, text="",
                font=ctk.CTkFont(size=10),
                text_color=theme.MUTED,
                anchor="e",
            )
            self._stats_lbl.pack(fill="x", padx=14, pady=(0, 6))

        self._textbox.tag_configure("bold",        font=("Segoe UI", 13, "bold"))
        self._textbox.tag_configure("italic",      font=("Segoe UI", 13, "italic"))
        self._textbox.tag_configure("code_inline", font=("Consolas", 12), background="#f1f5f9")
        self._textbox.tag_configure("code_block",  font=("Consolas", 12),
                                    background=theme.CODE_BG, foreground=theme.CODE_FG)
        self._textbox.tag_configure("heading",     font=("Segoe UI", 15, "bold"))

        if content:
            _apply_markdown(self._textbox, content)

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.get_text())
        self._copy_lbl.configure(text="Copied")
        self.after(2000, lambda: self._copy_lbl.configure(text=""))

    def append(self, text: str):
        self._textbox.configure(state="normal")
        self._textbox.insert("end", text)
        self._textbox.configure(state="disabled")
        _auto_height(self._textbox)

    def get_text(self) -> str:
        return self._textbox.get("1.0", "end-1c")

    def set_wrap(self, pixel_width: int):
        chars = max(40, (pixel_width - 120) // 8)
        self._textbox.configure(width=chars)

    def set_stats(self, elapsed: float, tokens: int):
        """Show response time and token estimate on the bubble (assistant only)."""
        if self._stats_lbl is None:
            return
        tok_per_s = tokens / elapsed if elapsed > 0 else 0
        self._stats_lbl.configure(
            text=f"{elapsed:.1f}s  ·  ~{tokens} tok  ·  ~{tok_per_s:.0f} tok/s"
        )


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
        self._response_start: float = 0.0
        self._stop_event = threading.Event()

        self._build_ui()
        self.bind("<Configure>", self._on_resize)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ---- Top bar ----
        top = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=0, height=48,
                           border_width=1, border_color=theme.BORDER)
        top.pack(fill="x")
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="Model:", font=ctk.CTkFont(size=12),
                     text_color=theme.MUTED).pack(side="left", padx=(14, 4), pady=12)

        self._model_combo = ctk.CTkComboBox(
            top,
            values=[""],
            font=ctk.CTkFont(size=12),
            width=300, height=30,
            fg_color=theme.CARD2,
            border_color=theme.BORDER2,
            button_color=theme.BORDER2,
            button_hover_color=theme.BORDER,
            dropdown_fg_color=theme.CARD,
            dropdown_hover_color=theme.CARD2,
            dropdown_text_color=theme.TEXT,
            text_color=theme.TEXT,
        )
        self._model_combo.pack(side="left", pady=9)

        self._refresh_btn = ctk.CTkButton(
            top, text="Refresh", width=60, height=30, font=ctk.CTkFont(size=11),
            fg_color=theme.CARD2, hover_color=theme.BORDER,
            border_width=1, border_color=theme.BORDER2,
            text_color=theme.TEXT2,
            command=self._on_refresh_click,
        )
        self._refresh_btn.pack(side="left", padx=4)

        ctk.CTkButton(
            top, text="Clear", width=70, height=30, font=ctk.CTkFont(size=12),
            fg_color=theme.CARD2, hover_color=theme.BORDER,
            border_width=1, border_color=theme.BORDER2,
            text_color=theme.TEXT2,
            command=self._clear,
        ).pack(side="right", padx=14)

        # Tools toggle
        self._tools_var = ctk.BooleanVar(value=True)
        ctk.CTkLabel(top, text="Web search:",
                     font=ctk.CTkFont(size=11), text_color=theme.MUTED,
                     ).pack(side="right", padx=(0, 4))
        ctk.CTkSwitch(top, text="", variable=self._tools_var,
                      width=40, button_color=theme.BLUE, progress_color=theme.BLUE,
                      ).pack(side="right", padx=(0, 4))

        ctk.CTkLabel(top, text="System prompt:", font=ctk.CTkFont(size=12),
                     text_color=theme.MUTED).pack(side="right", padx=(0, 4))

        self._sys_entry = ctk.CTkEntry(top, font=ctk.CTkFont(size=12), width=240, height=30,
                                       placeholder_text="Optional system message")
        self._sys_entry.pack(side="right", pady=9)

        # ---- Scrollable message area ----
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=theme.CHAT_BG, corner_radius=0)
        self._scroll.pack(fill="both", expand=True)

        # ---- Status bar ----
        self._status = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11),
            text_color=theme.MUTED, anchor="w", height=22,
        )
        self._status.pack(fill="x", padx=14)

        # ---- Input row ----
        # Use tk.Frame + tk.Text for the input so Vietnamese IME works natively.
        # CTkTextbox intercepts key events that break IME character composition.
        input_row = tk.Frame(self, bg=theme.CARD,
                             highlightthickness=1,
                             highlightbackground=theme.BORDER,
                             highlightcolor=theme.BORDER,
                             height=72)
        input_row.pack(fill="x", side="bottom")
        input_row.pack_propagate(False)

        # Plain tk.Text - full IME support, full Unicode, no event interception
        self._input = tk.Text(
            input_row,
            font=("Segoe UI", 12),
            bg=theme.CARD2,
            fg=theme.TEXT,
            insertbackground=theme.TEXT,    # cursor colour
            relief="flat",
            highlightthickness=1,
            highlightbackground=theme.BORDER,
            highlightcolor=theme.BLUE,
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
            fg_color=theme.BLUE,
            hover_color=theme.BLUE_H,
            text_color="#ffffff",
            command=self._send,
        )
        self._send_btn.pack(side="right", padx=(0, 12), pady=10)
        self._refresh_model_name()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _on_refresh_click(self):
        self._refresh_model_name()
        self._refresh_btn.configure(text="✓", text_color=theme.GREEN)
        self.after(1200, lambda: self._refresh_btn.configure(text="Refresh", text_color=theme.TEXT2))

    def _refresh_model_name(self):
        active = read_active_model_name()
        names: list[str] = []
        if active:
            names.append(active)
        for m in CURATED_MODELS:
            name = m.model_name_for_config
            if m.is_downloaded and name not in names:
                names.append(name)
        if names:
            self._model_combo.configure(values=names)
            current = self._model_combo.get()
            if not current or current not in names:
                self._model_combo.set(names[0])
            self._send_btn.configure(state="normal")
            self._status.configure(text="")
        else:
            self._model_combo.configure(values=[""])
            self._model_combo.set("")
            self._send_btn.configure(state="disabled")
            self._status.configure(
                text="No model active - go to Models tab to download and activate one.",
                text_color=theme.AMBER,
            )

    def _current_model(self) -> str:
        return self._model_combo.get().strip() or read_active_model_name() or ""

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
        # Do NOT return "break" - let the default handler run so Unikey/EVKey
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
        self._response_start = __import__("time").time()
        self._stop_event.clear()
        self._send_btn.configure(
            text="Stop", fg_color=theme.RED, hover_color="#8c1c22",
            state="normal", command=self._stop_streaming,
        )
        status_text = "Thinking (web tools on)..." if use_tools else "Generating..."
        self._status.configure(text=status_text, text_color=theme.AMBER)

        stream_chat(
            messages=self._messages,
            model=self._current_model(),
            on_chunk=self._on_chunk,
            on_done=self._on_done,
            on_error=self._on_error,
            use_tools=use_tools,
            on_tool_call=self._on_tool_call,
            on_messages_update=self._on_messages_update,
            stop_event=self._stop_event,
        )

    def _stop_streaming(self):
        """Signal the worker thread to stop streaming."""
        self._stop_event.set()
        self._send_btn.configure(state="disabled", text="Stopping...")

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
        self._response_start = __import__("time").time()
        self._stop_event.clear()
        self._send_btn.configure(
            text="Stop", fg_color=theme.RED, hover_color="#8c1c22",
            state="normal", command=self._stop_streaming,
        )
        self._status.configure(text="Retrying...", text_color=theme.AMBER)

        stream_chat(
            messages=self._messages,
            model=self._current_model(),
            on_chunk=self._on_chunk,
            on_done=self._on_done,
            on_error=self._on_error,
            use_tools=self._tools_var.get(),
            on_tool_call=self._on_tool_call,
            on_messages_update=self._on_messages_update,
            stop_event=self._stop_event,
        )

    # ------------------------------------------------------------------
    # Streaming callbacks (called from background thread - use .after)
    # ------------------------------------------------------------------

    def _on_messages_update(self, msgs: list[dict]):
        """Sync full message list (including tool turns) back from the worker."""
        self.after(0, lambda: setattr(self, "_messages", list(msgs)))

    def _on_tool_call(self, name: str, result: str):
        """Show a compact tool-call notice in the chat."""
        label = {
            "get_current_time": "Getting current time",
            "get_weather":      "Fetching weather",
            "web_search":       "Searching the web",
            "fetch_url":        "Fetching URL",
        }.get(name, f"Calling {name}")
        self.after(0, lambda: self._status.configure(
            text=f"{label}...", text_color=theme.BLUE))

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
        self._send_btn.configure(
            state="normal", text="Send",
            fg_color=theme.BLUE, hover_color=theme.BLUE_H,
            command=self._send,
        )
        if self._stop_event.is_set():
            self._status.configure(text="Stopped.", text_color=theme.MUTED)
            self.after(2000, lambda: self._status.configure(text=""))
        else:
            self._show_response_stats()

        if self._active_bubble:
            raw     = self._active_bubble.get_text()
            display = _strip_think_tags(raw)   # remove <think>...</think> from display
            _apply_markdown(self._active_bubble._textbox, display)
            if not self._messages or self._messages[-1].get("role") != "assistant":
                self._messages.append({"role": "assistant", "content": raw})  # keep full for context
            self._scroll_to_bottom()
        self._active_bubble = None

    def _on_error(self, msg: str):
        self.after(0, lambda: self._show_error(msg))

    def _show_response_stats(self):
        """Show response time and token estimate on the active bubble."""
        import time as _t
        elapsed = _t.time() - self._response_start
        if elapsed <= 0 or not self._active_bubble:
            self._status.configure(text="", text_color=theme.MUTED)
            return
        raw    = self._active_bubble.get_text()
        tokens = max(1, len(raw) // 4)
        self._active_bubble.set_stats(elapsed, tokens)
        self._status.configure(text="", text_color=theme.MUTED)

    def _show_error(self, msg: str):
        self._streaming = False
        self._send_btn.configure(
            state="normal", text="Send",
            fg_color=theme.BLUE, hover_color=theme.BLUE_H,
            command=self._send,
        )
        friendly = self._friendly_error(msg)
        self._status.configure(text=f"Error: {friendly}", text_color=theme.RED)
        if self._active_bubble:
            self._active_bubble.append(f"\n[Error: {friendly}]")
        self._active_bubble = None

    @staticmethod
    def _friendly_error(msg: str) -> str:
        m = msg.lower()
        if "connection refused" in m or "connect" in m and "error" in m:
            return "Cannot connect - start the stack on the Dashboard first."
        if "422" in m:
            return "The model rejected the request. Check the model is loaded."
        if "404" in m:
            return "Model not found. Activate a model on the Models tab."
        if "500" in m:
            return "Server error - the model may have crashed. Check the log."
        if "timeout" in m or "timed out" in m:
            return "Request timed out. The model may still be loading."
        return msg
