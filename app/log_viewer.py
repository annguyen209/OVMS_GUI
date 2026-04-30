"""
log_viewer.py - Scrollable log tail widget.

Provides a reusable CTkTextbox-based widget that tails a log file
and refreshes itself on a configurable interval.
"""

import logging
import os
from pathlib import Path

import customtkinter as ctk

from app import theme

logger = logging.getLogger(__name__)

_TAIL_LINES = 20          # number of lines to show
_REFRESH_MS  = 2000       # milliseconds between refreshes


class LogViewerWidget(ctk.CTkFrame):
    """
    A self-refreshing log tail widget.

    Usage::

        viewer = LogViewerWidget(parent, log_path=r"C:\\...\\server.log")
        viewer.pack(fill="both", expand=True)
        viewer.start()     # begin auto-refresh
        viewer.stop()      # call on destroy
    """

    def __init__(
        self,
        master,
        log_path: str | Path,
        tail_lines: int = _TAIL_LINES,
        refresh_ms: int = _REFRESH_MS,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._log_path   = Path(log_path)
        self._tail_lines = tail_lines
        self._refresh_ms = refresh_ms
        self._after_id   = None
        self._running    = False

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Header row
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=4, pady=(4, 0))

        ctk.CTkLabel(
            header,
            text=f"Log: {self._log_path.name}",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).pack(side="left")

        self._status_label = ctk.CTkLabel(
            header,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="e",
        )
        self._status_label.pack(side="right")

        # Text box
        self._textbox = ctk.CTkTextbox(
            self,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled",
            fg_color=theme.CARD2,
            text_color=theme.TEXT2,
            border_width=1,
            border_color=theme.BORDER,
        )
        self._textbox.pack(fill="both", expand=True, padx=4, pady=4)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Begin the auto-refresh loop (safe to call multiple times)."""
        if not self._running:
            self._running = True
            self._schedule_refresh()

    def stop(self):
        """Cancel pending refresh callbacks."""
        self._running = False
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _schedule_refresh(self):
        if self._running:
            self._after_id = self.after(self._refresh_ms, self._refresh)

    def _refresh(self):
        """Read the tail of the log file and update the text box."""
        try:
            lines = self._tail_file()
            self._set_text(lines)
            self._status_label.configure(text="")
        except FileNotFoundError:
            self._set_text(["Waiting for server to start..."])
            self._status_label.configure(text="not started", text_color="gray")
        except Exception as exc:
            logger.debug("Log viewer refresh error: %s", exc)
            self._status_label.configure(text="read error", text_color="red")
        finally:
            self._schedule_refresh()

    def _tail_file(self) -> list[str]:
        """Return the last *_tail_lines* lines of the log file."""
        size = os.path.getsize(self._log_path)
        if size == 0:
            return ["Waiting for server output..."]

        # Read from the end - chunk approach for large files
        chunk_size = min(size, 32 * 1024)  # read at most 32 KB from the end
        with open(self._log_path, "rb") as fh:
            fh.seek(-chunk_size, 2)
            raw = fh.read()

        text  = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        return lines[-self._tail_lines:]

    def _set_text(self, lines: list[str]):
        content = "\n".join(lines)
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.insert("end", content)
        self._textbox.see("end")           # auto-scroll to bottom
        self._textbox.configure(state="disabled")

    # ------------------------------------------------------------------
    # Convenience: force an immediate refresh from outside
    # ------------------------------------------------------------------

    def refresh_now(self):
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
        self._refresh()
