"""
gui.py - Main CustomTkinter window with tabbed layout.

Tabs:
  1. Dashboard  - server status cards, start/stop button, log tail
  2. Models     - curated model library with download + activate actions
"""

import logging
import threading
import tkinter as tk
from tkinter import filedialog
from pathlib import Path

import customtkinter as ctk

from app.server import ServerManager
from app.models import CURATED_MODELS, ModelInfo, download_model, activate_model, read_active_model_name
from app.log_viewer import LogViewerWidget
from app.config import cfg
from app.chat import ChatTab
from app.guide import GuideTab
from app.setup_tab import SetupTab
from app.about import AboutTab, _detect_devices
from app import installer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Palette - enterprise light theme
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

_BG      = "#f3f4f6"   # page background (gray-100)
_CARD    = "#ffffff"   # card surfaces
_CARD2   = "#f9fafb"   # secondary surfaces (gray-50)
_BORDER  = "#e5e7eb"   # borders (gray-200)
_BORDER2 = "#d1d5db"   # stronger borders (gray-300)
_TEXT    = "#111827"   # primary text (gray-900)
_TEXT2   = "#374151"   # secondary text (gray-700)
_MUTED   = "#6b7280"   # muted/placeholder (gray-500)
_BLUE    = "#0078d4"   # Microsoft blue (primary action)
_BLUE_H  = "#106ebe"   # blue hover
_GREEN   = "#107c10"   # Microsoft green (success/running)
_RED     = "#a4262c"   # Microsoft red (error/stopped)
_AMBER   = "#c55000"   # Microsoft orange (warning/active model)
_BANNER  = "#1b1f23"   # banner background (near-black)
_FOOTER  = "#1b1f23"   # footer background

_POLL_MS = 3000
APP_VERSION = "1.0.0"
APP_AUTHOR  = "anzdev4life"


# ---------------------------------------------------------------------------
# Section header helper
# ---------------------------------------------------------------------------

def _section_header(parent, text: str):
    ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont(size=10, weight="bold"),
        text_color=_MUTED,
        anchor="w",
    ).pack(fill="x", padx=18, pady=(14, 4))


# ---------------------------------------------------------------------------
# Status card  (status bar rect + title + value)
# ---------------------------------------------------------------------------

class StatusCard(ctk.CTkFrame):
    def __init__(self, master, title: str, **kwargs):
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("fg_color", _CARD)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", _BORDER)
        super().__init__(master, **kwargs)

        # Left-edge colored status bar (3px wide, full card height)
        self._status_bar = ctk.CTkFrame(self, width=3, fg_color=_MUTED,
                                        corner_radius=0)
        self._status_bar.pack(side="left", fill="y")

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(side="left", fill="both", expand=True, padx=(10, 14), pady=14)

        ctk.CTkLabel(inner, text=title,
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=_MUTED, anchor="w").pack(anchor="w")

        self._value_lbl = ctk.CTkLabel(
            inner, text="...",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=_TEXT, anchor="w",
        )
        self._value_lbl.pack(anchor="w", pady=(4, 0))

    def set_status(self, text: str, color: str = _MUTED):
        self._status_bar.configure(fg_color=color)
        self._value_lbl.configure(
            text=text,
            text_color=color if color != _MUTED else _TEXT,
        )


# ---------------------------------------------------------------------------
# Endpoint panel
# ---------------------------------------------------------------------------

class EndpointPanel(ctk.CTkFrame):
    """Shows the OpenAI-compatible endpoint URL + model for copy-paste."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("fg_color", _CARD)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", _BORDER)
        super().__init__(master, **kwargs)

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 6))
        ctk.CTkLabel(hdr, text="OpenAI-Compatible Endpoint",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=_TEXT2).pack(side="left")
        ctk.CTkLabel(hdr, text="Continue.dev, OpenCode, any OpenAI SDK client",
                     font=ctk.CTkFont(size=10), text_color=_MUTED).pack(side="right")

        self._url_var   = tk.StringVar()
        self._model_var = tk.StringVar()

        self._build_row("Base URL", self._url_var,   _BLUE)
        self._build_row("Model",    self._model_var, _GREEN)

        self.refresh()

    def _build_row(self, label: str, var: tk.StringVar, accent: str):
        row = ctk.CTkFrame(self, fg_color=_CARD2, corner_radius=6,
                           border_width=1, border_color=_BORDER2)
        row.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(row, text=label, width=72,
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=accent, anchor="w").pack(side="left", padx=(12, 6), pady=9)

        ctk.CTkLabel(row, textvariable=var,
                     font=ctk.CTkFont(family="Consolas", size=12),
                     text_color=_TEXT, anchor="w").pack(side="left", fill="x", expand=True)

        ctk.CTkButton(row, text="Copy", width=56, height=28,
                      font=ctk.CTkFont(size=11),
                      fg_color=_CARD2, hover_color=_BORDER,
                      border_width=1, border_color=_BORDER2,
                      text_color=_TEXT2,
                      command=lambda v=var: self._copy(v.get()),
                      ).pack(side="right", padx=8, pady=5)

    def _copy(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)

    def refresh(self):
        model = read_active_model_name() or "None"
        self._url_var.set(f"http://localhost:{cfg.proxy_port}/v3")
        self._model_var.set(model)


# ---------------------------------------------------------------------------
# Hardware info bar
# ---------------------------------------------------------------------------

class HardwareBar(ctk.CTkFrame):
    """Compact one-line hardware summary: CPU / GPU / NPU device names."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", _CARD)
        kwargs.setdefault("corner_radius", 6)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", _BORDER)
        kwargs.setdefault("height", 32)
        super().__init__(master, **kwargs)
        self.pack_propagate(False)

        self._inner = ctk.CTkFrame(self, fg_color="transparent")
        self._inner.pack(fill="both", expand=True, padx=12, pady=0)

        self._placeholder = ctk.CTkLabel(
            self._inner, text="Detecting hardware...",
            font=ctk.CTkFont(size=11), text_color=_MUTED, anchor="w",
        )
        self._placeholder.pack(side="left", pady=0)

        # Detect after mainloop starts — log parse is instant
        self.after(200, lambda: threading.Thread(
            target=self._detect, daemon=True).start())

    def _detect(self):
        devices = _detect_devices()
        try:
            self.after(0, lambda: self._render(devices))
        except RuntimeError:
            pass

    def _render(self, devices):
        self._placeholder.destroy()

        _token_colors  = {"CPU": _BLUE, "GPU": _GREEN, "NPU": _AMBER}
        _token_labels  = {
            "CPU": "Processor",
            "GPU": "Integrated GPU",
            "NPU": "Neural Processor",
        }
        _token_subtitles = {
            "CPU": "General-purpose inference",
            "GPU": "Arc iGPU — shared RAM as VRAM",
            "NPU": "Intel AI Boost — low power",
        }

        for i, (token, name, desc) in enumerate(devices):
            if i > 0:
                ctk.CTkFrame(self._inner, width=1, fg_color=_BORDER
                             ).pack(side="left", fill="y", padx=14, pady=2)

            color   = _token_colors.get(token, _MUTED)
            display = name if name != token else _token_subtitles.get(token, token)
            label   = _token_labels.get(token, token)

            # Everything on one line: [TOKEN]  label  display
            ctk.CTkLabel(self._inner, text=token,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=color).pack(side="left")
            ctk.CTkLabel(self._inner,
                         text=f"  {label}   {display}",
                         font=ctk.CTkFont(size=11),
                         text_color=_TEXT2).pack(side="left")


# ---------------------------------------------------------------------------
# Dashboard Tab
# ---------------------------------------------------------------------------

class DashboardTab(ctk.CTkFrame):

    def __init__(self, master, server: ServerManager, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._server = server
        self._stack_busy = False

        self._build_ui()
        self._schedule_poll()

    def _build_ui(self):
        # ---- Status cards ----
        _section_header(self, "SERVER STATUS")

        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.pack(fill="x", padx=16, pady=(0, 4))
        cards.columnconfigure((0, 1, 2), weight=1)

        self._card_ovms  = StatusCard(cards, "OVMS Server")
        self._card_proxy = StatusCard(cards, "Proxy")
        self._card_model = StatusCard(cards, "Active Model")

        self._card_ovms .grid(row=0, column=0, padx=(0, 5), pady=0, sticky="nsew")
        self._card_proxy.grid(row=0, column=1, padx=5,      pady=0, sticky="nsew")
        self._card_model.grid(row=0, column=2, padx=(5, 0), pady=0, sticky="nsew")

        # ---- Hardware info ----
        _section_header(self, "HARDWARE")
        HardwareBar(self).pack(fill="x", padx=16, pady=(0, 4))

        # ---- Endpoint panel ----
        _section_header(self, "ENDPOINT")
        self._endpoint_panel = EndpointPanel(self)
        self._endpoint_panel.pack(fill="x", padx=16, pady=(0, 4))

        # ---- Controls ----
        _section_header(self, "CONTROLS")

        ctrl = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=8,
                             border_width=1, border_color=_BORDER)
        ctrl.pack(fill="x", padx=16, pady=(0, 4))

        btn_row = ctk.CTkFrame(ctrl, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=12)

        self._action_btn = ctk.CTkButton(
            btn_row, text="Start Stack", width=160, height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=_BLUE, hover_color=_BLUE_H,
            corner_radius=6, command=self._on_action_click,
        )
        self._action_btn.pack(side="left")

        self._status_msg = ctk.CTkLabel(
            btn_row, text="", font=ctk.CTkFont(size=12),
            text_color=_TEXT2, anchor="w", wraplength=560,
        )
        self._status_msg.pack(side="left", padx=14, fill="x", expand=True)

        # ---- Log ----
        _section_header(self, "SERVER LOG")
        self._log_viewer = LogViewerWidget(
            self, log_path=cfg.ovms_log, tail_lines=25, refresh_ms=2000,
        )
        self._log_viewer.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self._log_viewer.start()

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _schedule_poll(self):
        self.after(_POLL_MS, self._poll)

    def _poll(self):
        self._refresh_cards()
        self._schedule_poll()

    def _refresh_cards(self):
        ovms_up    = self._server.ovms_running
        proxy_up   = self._server.proxy_running
        model_name = read_active_model_name()

        self._card_ovms.set_status("Running" if ovms_up else "Stopped",
                                   _GREEN if ovms_up else _RED)
        self._card_proxy.set_status("Running" if proxy_up else "Stopped",
                                    _GREEN if proxy_up else _RED)
        self._card_model.set_status(model_name or "None",
                                    _AMBER if model_name else _MUTED)
        self._endpoint_panel.refresh()

        if not self._stack_busy:
            if ovms_up or proxy_up:
                self._action_btn.configure(text="Stop Stack",
                                           fg_color=_RED, hover_color="#8c1c22")
            else:
                self._action_btn.configure(text="Start Stack",
                                           fg_color=_BLUE, hover_color=_BLUE_H)

    # ------------------------------------------------------------------
    # Button
    # ------------------------------------------------------------------

    def _on_action_click(self):
        if self._stack_busy:
            return
        stopping = self._server.ovms_running or self._server.proxy_running
        self._stack_busy = True
        self._action_btn.configure(state="disabled", text="Please wait...", fg_color=_MUTED)
        self._status_msg.configure(text="Working...", text_color=_AMBER)

        def _worker():
            ok, msg = self._server.stop_stack() if stopping else self._server.start_stack()
            self.after(0, lambda: self._on_action_done(ok, msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_action_done(self, ok: bool, msg: str):
        self._stack_busy = False
        self._status_msg.configure(text=msg,
                                   text_color=_GREEN if ok else _RED)
        self._action_btn.configure(state="normal")
        self._refresh_cards()

    def on_destroy(self):
        self._log_viewer.stop()


# ---------------------------------------------------------------------------
# Model row widget
# ---------------------------------------------------------------------------

class ModelRow(ctk.CTkFrame):
    """
    One row in the model library table.
    Layout: [Name + notes] [size] [status] [button]
    """

    def __init__(self, master, model: ModelInfo, server: ServerManager, notify_cb, **kwargs):
        kwargs.setdefault("fg_color", _CARD)
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", _BORDER)
        super().__init__(master, **kwargs)
        self._model    = model
        self._server   = server
        self._notify   = notify_cb   # callable(message, color)
        self._dl_thread: threading.Thread | None = None

        self._build_ui()
        self.refresh()

    # Shared weight ratios - header reads these too so columns align
    _WEIGHTS = (5, 1, 2, 2)

    def _build_ui(self):
        for col, w in enumerate(self._WEIGHTS):
            self.columnconfigure(col, weight=w, uniform="table_cols")

        # Name + notes
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.grid(row=0, column=0, sticky="nsew", padx=(14, 8), pady=10)

        ctk.CTkLabel(
            info_frame,
            text=self._model.display_name,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=_TEXT,
            anchor="w",
        ).pack(anchor="w")

        if self._model.notes:
            ctk.CTkLabel(
                info_frame,
                text=self._model.notes,
                font=ctk.CTkFont(size=11),
                text_color=_MUTED,
                anchor="w",
            ).pack(anchor="w")

        # Size
        ctk.CTkLabel(
            self,
            text=self._model.size_label,
            font=ctk.CTkFont(size=12),
            text_color=_TEXT2,
            anchor="center",
        ).grid(row=0, column=1, sticky="ew", padx=4, pady=10)

        # Status
        self._status_lbl = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=12),
            anchor="center",
        )
        self._status_lbl.grid(row=0, column=2, sticky="ew", padx=4, pady=10)

        # Progress bar
        self._progress_bar = ctk.CTkProgressBar(self, height=10)
        self._progress_bar.set(0)

        # Action button
        self._btn = ctk.CTkButton(
            self,
            text="",
            height=34,
            font=ctk.CTkFont(size=12),
            corner_radius=6,
            command=self._on_btn_click,
        )
        self._btn.grid(row=0, column=3, sticky="ew", padx=(4, 14), pady=10)

    def refresh(self):
        """Update status label and button text to reflect current model state."""
        model = self._model

        if model.is_downloading:
            pct = model.download_progress
            self._status_lbl.configure(text=f"Downloading {pct:.0f}%", text_color=_AMBER)
            self._progress_bar.set(pct / 100.0)
            self._progress_bar.grid(row=1, column=0, columnspan=4, padx=12, pady=(0, 8), sticky="ew")
            self._btn.configure(text="Downloading...", state="disabled", fg_color=_AMBER,
                                text_color="#ffffff")
        elif model.is_downloaded:
            self._status_lbl.configure(text="Downloaded", text_color=_GREEN)
            self._progress_bar.grid_remove()
            self._btn.configure(
                text="Activate",
                state="normal",
                fg_color=_BLUE,
                hover_color=_BLUE_H,
                text_color="#ffffff",
            )
        else:
            self._status_lbl.configure(text="Not downloaded", text_color=_RED)
            self._progress_bar.grid_remove()
            self._btn.configure(
                text="Download",
                state="normal",
                fg_color=_CARD2,
                hover_color=_BORDER,
                border_width=1,
                border_color=_BORDER2,
                text_color=_TEXT2,
            )

    def _on_btn_click(self):
        model = self._model

        if model.is_downloading:
            return

        if model.is_downloaded:
            self._activate()
        else:
            self._start_download()

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _start_download(self):
        self._model.is_downloading = True
        self._model.download_progress = 0.0
        self.refresh()
        self._notify(f"Starting download: {self._model.display_name}", _AMBER)

        self._dl_thread = download_model(
            self._model,
            on_progress=self._on_progress,
            on_done=self._on_done,
        )

    def _on_progress(self, model: ModelInfo, pct: float):
        # Called from background thread - schedule GUI update on main thread
        self.after(0, self.refresh)

    def _on_done(self, model: ModelInfo, success: bool, message: str):
        def _update():
            self.refresh()
            if success:
                self._notify(
                    f"Download complete: {model.display_name}",
                    _GREEN,
                )
            else:
                self._notify(
                    f"Download failed: {model.display_name}. {message}",
                    _RED,
                )
        self.after(0, _update)

    # ------------------------------------------------------------------
    # Activate
    # ------------------------------------------------------------------

    def _activate(self):
        self._btn.configure(state="disabled", text="Activating...")
        self._notify(f"Activating {self._model.display_name}...", _AMBER)

        def _worker():
            ok, msg = activate_model(self._model)
            if ok and (self._server.ovms_running or self._server.proxy_running):
                # Restart OVMS so the new config takes effect
                self._server.stop_stack()
                import time; time.sleep(1)
                ok2, msg2 = self._server.start_stack()
                if not ok2:
                    msg += f" (restart warning: {msg2})"

            self.after(0, lambda: self._on_activate_done(ok, msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_activate_done(self, ok: bool, msg: str):
        self._btn.configure(state="normal")
        self.refresh()
        color = _GREEN if ok else _RED
        self._notify(msg, color)


# ---------------------------------------------------------------------------
# Models Tab
# ---------------------------------------------------------------------------

class ModelsTab(ctk.CTkFrame):

    def __init__(self, master, server: ServerManager, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._server = server
        self._rows: list[ModelRow] = []

        self._build_ui()
        self._schedule_refresh()

    def _build_ui(self):
        # Notification bar
        self._notif_bar = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=12),
            anchor="w",
            height=28,
        )
        self._notif_bar.pack(fill="x", padx=20, pady=(12, 4))

        # Column headers - same weights as ModelRow so columns align
        header = ctk.CTkFrame(self, fg_color=_CARD2, corner_radius=6,
                              border_width=1, border_color=_BORDER)
        header.pack(fill="x", padx=16, pady=(0, 6))
        for col, w in enumerate(ModelRow._WEIGHTS):
            header.columnconfigure(col, weight=w, uniform="table_cols")

        col_defs = [
            (0, "Model",  "w",      14,  0),
            (1, "Size",   "center",  4,  4),
            (2, "Status", "center",  4,  4),
            (3, "Action", "center",  4, 14),
        ]
        for col, text, anchor, px_l, px_r in col_defs:
            ctk.CTkLabel(
                header,
                text=text,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=_MUTED,
                anchor=anchor,
            ).grid(row=0, column=col, padx=(px_l, px_r), pady=8, sticky="ew")

        # Scrollable list area
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            label_text="",
        )
        self._scroll.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # Create one ModelRow per curated model
        for model in CURATED_MODELS:
            row = ModelRow(
                self._scroll,
                model=model,
                server=self._server,
                notify_cb=self._notify,
            )
            row.pack(fill="x", pady=4)
            self._rows.append(row)

    def _notify(self, message: str, color: str = _MUTED):
        self._notif_bar.configure(text=message, text_color=color)

    def _schedule_refresh(self):
        self.after(2000, self._refresh_rows)

    def _refresh_rows(self):
        for row in self._rows:
            if not row.winfo_exists():
                continue
            row.refresh()
        self._schedule_refresh()


# ---------------------------------------------------------------------------
# Settings Tab
# ---------------------------------------------------------------------------

class SettingsTab(ctk.CTkFrame):
    """Form for editing all configurable paths and ports."""

    # (key, label, type)  type = "dir" | "file" | "port" | "text"
    _FIELDS = [
        ("models_dir",    "Models Directory",       "dir"),
        ("ovms_exe",      "OVMS Executable",        "file"),
        ("ovms_workspace","OVMS Workspace Directory","dir"),
        ("setupvars",     "setupvars.bat Path",     "file"),
        ("python_exe",    "Python Executable",      "file"),
        ("proxy_script",  "Proxy Script",           "file"),
        ("ovms_log",      "OVMS Log File",          "text"),
        ("proxy_log",     "Proxy Log File",         "text"),
        ("ovms_rest_port","OVMS REST Port",         "port"),
        ("proxy_port",    "Proxy Port",             "port"),
    ]

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._entries: dict[str, ctk.CTkEntry] = {}
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(
            self,
            text="Paths and Ports",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=_TEXT,
            anchor="w",
        ).pack(fill="x", padx=20, pady=(16, 8))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        scroll.columnconfigure(1, weight=1)

        for row_idx, (key, label, kind) in enumerate(self._FIELDS):
            ctk.CTkLabel(
                scroll,
                text=label,
                font=ctk.CTkFont(size=12),
                text_color=_TEXT2,
                anchor="w",
                width=200,
            ).grid(row=row_idx, column=0, sticky="w", padx=(8, 12), pady=6)

            entry = ctk.CTkEntry(scroll, font=ctk.CTkFont(size=12))
            entry.insert(0, str(cfg.get(key, "")))
            entry.grid(row=row_idx, column=1, sticky="ew", padx=(0, 8), pady=6)
            self._entries[key] = entry

            if kind in ("dir", "file"):
                btn = ctk.CTkButton(
                    scroll,
                    text="Browse",
                    width=70,
                    height=28,
                    font=ctk.CTkFont(size=11),
                    fg_color=_BLUE,
                    hover_color=_BLUE_H,
                    command=lambda k=key, t=kind: self._browse(k, t),
                )
                btn.grid(row=row_idx, column=2, padx=(0, 8), pady=6)

        # Save button
        save_row = ctk.CTkFrame(self, fg_color="transparent")
        save_row.pack(fill="x", padx=20, pady=(4, 16))

        self._save_status = ctk.CTkLabel(
            save_row, text="", font=ctk.CTkFont(size=12), text_color=_MUTED
        )
        self._save_status.pack(side="left", padx=(0, 16))

        ctk.CTkButton(
            save_row,
            text="Save Settings",
            width=160,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=_BLUE,
            hover_color=_BLUE_H,
            command=self._save,
        ).pack(side="right")

    def _browse(self, key: str, kind: str):
        current = self._entries[key].get()
        if kind == "dir":
            path = filedialog.askdirectory(initialdir=current or "/", title=f"Select {key}")
        else:
            path = filedialog.askopenfilename(initialdir=str(Path(current).parent) if current else "/", title=f"Select {key}")
        if path:
            entry = self._entries[key]
            entry.delete(0, "end")
            entry.insert(0, path)

    def _save(self):
        updates = {}
        for key, entry in self._entries.items():
            val = entry.get().strip()
            field_kind = next((kind for k, l, kind in self._FIELDS if k == key), "text")
            if field_kind == "port":
                try:
                    val = int(val)
                except ValueError:
                    self._save_status.configure(text=f"Invalid port for {key}", text_color=_RED)
                    return
            updates[key] = val

        cfg.update(updates)
        self._save_status.configure(text="Saved.", text_color=_GREEN)
        self.after(3000, lambda: self._save_status.configure(text=""))


# ---------------------------------------------------------------------------
# Main Application Window
# ---------------------------------------------------------------------------

class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("OVMS Model Server Manager")
        self.geometry("1000x720")
        self.minsize(800, 600)

        try:
            from app.icon import ICON_PATH
            if ICON_PATH.is_file():
                self.iconbitmap(str(ICON_PATH))
        except Exception:
            pass

        self._server = ServerManager()
        self._tray_icon = None

        self._build_ui()
        self._setup_tray()
        # Minimize to tray on close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.configure(fg_color=_BG)

        banner = ctk.CTkFrame(self, height=56, fg_color=_BANNER, corner_radius=0)
        banner.pack(fill="x", side="top")
        banner.pack_propagate(False)

        left = ctk.CTkFrame(banner, fg_color="transparent")
        left.pack(side="left", padx=18, pady=10)

        ctk.CTkLabel(left, text="OVMS Manager",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#f8fafc").pack(side="left")

        ctk.CTkLabel(left, text="  OpenVINO Model Server",
                     font=ctk.CTkFont(size=12), text_color=_MUTED).pack(side="left")

        ctk.CTkButton(
            banner, text="Quit", width=64, height=30,
            font=ctk.CTkFont(size=11),
            fg_color=_BANNER, hover_color=_RED, corner_radius=6,
            border_width=1, border_color="#374151",
            text_color="#f8fafc",
            command=self._quit,
        ).pack(side="right", padx=18)

        # Footer
        footer = ctk.CTkFrame(self, height=28, fg_color=_FOOTER, corner_radius=0)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        ctk.CTkLabel(
            footer,
            text=f"OVMS Manager  v{APP_VERSION}",
            font=ctk.CTkFont(size=10),
            text_color=_MUTED,
        ).pack(side="left", padx=16)

        ctk.CTkLabel(
            footer, text=f"by {APP_AUTHOR}",
            font=ctk.CTkFont(size=10),
            text_color=_MUTED,
        ).pack(side="right", padx=16)

        ctk.CTkFrame(footer, width=1, fg_color="#374151").pack(side="right")

        ctk.CTkLabel(
            footer, text="github.com/annguyen209/OVMS_GUI",
            font=ctk.CTkFont(size=10),
            text_color=_MUTED,
        ).pack(side="right", padx=16)

        self._tabs = ctk.CTkTabview(self, anchor="nw")
        self._tabs.pack(fill="both", expand=True, padx=12, pady=(12, 4))

        self._tabs.add("Setup")
        self._tabs.add("Dashboard")
        self._tabs.add("Models")
        self._tabs.add("Chat")
        self._tabs.add("Guide")
        self._tabs.add("About")
        self._tabs.add("Settings")

        self._setup_tab = SetupTab(
            self._tabs.tab("Setup"),
            on_all_ok=lambda: self.after(0, lambda: self._tabs.set("Dashboard")),
        )
        self._setup_tab.pack(fill="both", expand=True)

        self._dashboard = DashboardTab(self._tabs.tab("Dashboard"), server=self._server)
        self._dashboard.pack(fill="both", expand=True)

        self._models_tab = ModelsTab(self._tabs.tab("Models"), server=self._server)
        self._models_tab.pack(fill="both", expand=True)

        self._chat_tab = ChatTab(self._tabs.tab("Chat"))
        self._chat_tab.pack(fill="both", expand=True)

        self._guide_tab = GuideTab(self._tabs.tab("Guide"))
        self._guide_tab.pack(fill="both", expand=True)

        self._about_tab = AboutTab(self._tabs.tab("About"))
        self._about_tab.pack(fill="both", expand=True)

        self._settings_tab = SettingsTab(self._tabs.tab("Settings"))
        self._settings_tab.pack(fill="both", expand=True)

        # Auto-select Setup tab if anything is missing
        if not installer.all_ok():
            self._tabs.set("Setup")

        self._tabs.configure(command=self._on_tab_change)

    def _on_tab_change(self):
        tab = self._tabs.get()
        if tab == "Guide":
            self._guide_tab.on_show()
        elif tab == "Setup":
            self._setup_tab.refresh()

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _setup_tray(self):
        try:
            import pystray
            from app.icon import get_tray_image
            img = get_tray_image(64)

            menu = pystray.Menu(
                pystray.MenuItem("Show", self._tray_show, default=True),
                pystray.MenuItem("Quit", self._tray_quit),
            )
            self._tray_icon = pystray.Icon("OVMS Manager", img, "OVMS Manager", menu)
            threading.Thread(target=self._tray_icon.run, daemon=True).start()

        except Exception as exc:
            logger.warning("System tray unavailable: %s", exc)
            self._tray_icon = None

    def _tray_show(self):
        self.after(0, self._show_window)

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _tray_quit(self):
        self.after(0, self._quit)

    # ------------------------------------------------------------------
    # Close / Quit
    # ------------------------------------------------------------------

    def _on_close(self):
        """Minimize to tray instead of quitting."""
        self.withdraw()

    def _quit(self):
        """Actually exit the application."""
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        try:
            self._dashboard.on_destroy()
        except Exception:
            pass
        try:
            self._server.shutdown()
        except Exception:
            pass
        self.destroy()
