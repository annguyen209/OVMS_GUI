"""
gui.py — Main CustomTkinter window with tabbed layout.

Tabs:
  1. Dashboard  — server status cards, start/stop button, log tail
  2. Models     — curated model library with download + activate actions
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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_GREEN  = "#2ecc71"
_RED    = "#e74c3c"
_YELLOW = "#f1c40f"
_BLUE   = "#3b82f6"
_GRAY   = "#4a4a5a"
_BG     = "#0f0f1a"
_CARD   = "#1a1a2e"
_CARD2  = "#16213e"
_BORDER = "#2a2a3e"
_TEXT   = "#e2e8f0"
_MUTED  = "#64748b"

_POLL_MS = 3000
APP_VERSION = "1.0.0"
APP_AUTHOR  = "anzdev4life"


# ---------------------------------------------------------------------------
# Section header helper
# ---------------------------------------------------------------------------

def _section_header(parent, text: str):
    f = ctk.CTkFrame(parent, fg_color="transparent")
    f.pack(fill="x", padx=18, pady=(14, 4))
    ctk.CTkLabel(f, text=text, font=ctk.CTkFont(size=11, weight="bold"),
                 text_color=_MUTED).pack(side="left")
    ctk.CTkFrame(f, height=1, fg_color=_BORDER).pack(side="left", fill="x",
                                                       expand=True, padx=(10, 0))


# ---------------------------------------------------------------------------
# Status card  (dot + title + value)
# ---------------------------------------------------------------------------

class StatusCard(ctk.CTkFrame):
    def __init__(self, master, title: str, icon: str = "", **kwargs):
        kwargs.setdefault("corner_radius", 12)
        kwargs.setdefault("fg_color", _CARD)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", _BORDER)
        super().__init__(master, **kwargs)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 4))

        if icon:
            ctk.CTkLabel(top, text=icon, font=ctk.CTkFont(size=16),
                         text_color=_MUTED).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(top, text=title, font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=_MUTED, anchor="w").pack(side="left")

        # Status dot
        self._canvas = tk.Canvas(top, width=10, height=10,
                                 bg=_CARD, highlightthickness=0)
        self._canvas.pack(side="right")
        self._dot = self._canvas.create_oval(1, 1, 9, 9, fill=_GRAY, outline="")

        self._value_lbl = ctk.CTkLabel(
            self, text="—", font=ctk.CTkFont(size=18, weight="bold"),
            text_color=_TEXT, anchor="w",
        )
        self._value_lbl.pack(anchor="w", padx=14, pady=(0, 12))

    def set_status(self, text: str, color: str = _GRAY):
        self._canvas.itemconfigure(self._dot, fill=color)
        self._canvas.configure(bg=_CARD)
        self._value_lbl.configure(text=text, text_color=color if color != _GRAY else _TEXT)


# ---------------------------------------------------------------------------
# Endpoint panel
# ---------------------------------------------------------------------------

class EndpointPanel(ctk.CTkFrame):
    """Shows the OpenAI-compatible endpoint URL + model for copy-paste."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("corner_radius", 12)
        kwargs.setdefault("fg_color", _CARD2)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", _BORDER)
        super().__init__(master, **kwargs)

        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(10, 6))
        ctk.CTkLabel(hdr, text="OpenAI-Compatible Endpoint",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=_MUTED).pack(side="left")
        ctk.CTkLabel(hdr, text="Use in Continue.dev · OpenCode · any OpenAI SDK",
                     font=ctk.CTkFont(size=10), text_color=_MUTED).pack(side="right")

        # Rows
        self._url_var   = tk.StringVar()
        self._model_var = tk.StringVar()

        self._build_row("Base URL", self._url_var,   _BLUE)
        self._build_row("Model",    self._model_var, _YELLOW)

        self.refresh()

    def _build_row(self, label: str, var: tk.StringVar, accent: str):
        row = ctk.CTkFrame(self, fg_color="#111128", corner_radius=8)
        row.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(row, text=label, width=72,
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=accent, anchor="w").pack(side="left", padx=(10, 6), pady=8)

        lbl = ctk.CTkLabel(row, textvariable=var,
                           font=ctk.CTkFont(family="Consolas", size=12),
                           text_color=_TEXT, anchor="w")
        lbl.pack(side="left", fill="x", expand=True, pady=8)

        ctk.CTkButton(row, text="Copy", width=56, height=26,
                      font=ctk.CTkFont(size=11),
                      fg_color=_BORDER, hover_color="#3a3a5a",
                      command=lambda v=var: self._copy(v.get()),
                      ).pack(side="right", padx=8, pady=6)

    def _copy(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)

    def refresh(self):
        model = read_active_model_name() or "—"
        self._url_var.set(f"http://localhost:{cfg.proxy_port}/v3")
        self._model_var.set(model)


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

        self._card_ovms  = StatusCard(cards, "OVMS Server", icon="⚙")
        self._card_proxy = StatusCard(cards, "Proxy",       icon="⇄")
        self._card_model = StatusCard(cards, "Active Model",icon="◈")

        self._card_ovms .grid(row=0, column=0, padx=(0, 5), pady=0, sticky="nsew")
        self._card_proxy.grid(row=0, column=1, padx=5,      pady=0, sticky="nsew")
        self._card_model.grid(row=0, column=2, padx=(5, 0), pady=0, sticky="nsew")

        # ---- Endpoint panel ----
        _section_header(self, "ENDPOINT")
        self._endpoint_panel = EndpointPanel(self)
        self._endpoint_panel.pack(fill="x", padx=16, pady=(0, 4))

        # ---- Controls ----
        _section_header(self, "CONTROLS")

        ctrl = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=12,
                             border_width=1, border_color=_BORDER)
        ctrl.pack(fill="x", padx=16, pady=(0, 4))

        btn_row = ctk.CTkFrame(ctrl, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=12)

        self._action_btn = ctk.CTkButton(
            btn_row, text="Start Stack", width=160, height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=_GREEN, hover_color="#27ae60",
            corner_radius=8, command=self._on_action_click,
        )
        self._action_btn.pack(side="left")

        self._status_msg = ctk.CTkLabel(
            btn_row, text="", font=ctk.CTkFont(size=12),
            text_color=_MUTED, anchor="w", wraplength=560,
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
                                    _YELLOW if model_name else _GRAY)
        self._endpoint_panel.refresh()

        if not self._stack_busy:
            if ovms_up or proxy_up:
                self._action_btn.configure(text="Stop Stack",
                                           fg_color=_RED, hover_color="#c0392b")
            else:
                self._action_btn.configure(text="Start Stack",
                                           fg_color=_GREEN, hover_color="#27ae60")

    # ------------------------------------------------------------------
    # Button
    # ------------------------------------------------------------------

    def _on_action_click(self):
        if self._stack_busy:
            return
        stopping = self._server.ovms_running or self._server.proxy_running
        self._stack_busy = True
        self._action_btn.configure(state="disabled", text="Please wait…", fg_color=_GRAY)
        self._status_msg.configure(text="Working…", text_color=_YELLOW)

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
        kwargs.setdefault("fg_color", "#1e1e2e")
        kwargs.setdefault("corner_radius", 8)
        super().__init__(master, **kwargs)
        self._model    = model
        self._server   = server
        self._notify   = notify_cb   # callable(message, color)
        self._dl_thread: threading.Thread | None = None

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        self.columnconfigure(0, weight=4)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.columnconfigure(3, weight=2)

        # Name + notes
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.grid(row=0, column=0, sticky="w", padx=(12, 4), pady=10)

        ctk.CTkLabel(
            info_frame,
            text=self._model.display_name,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(anchor="w")

        if self._model.notes:
            ctk.CTkLabel(
                info_frame,
                text=self._model.notes,
                font=ctk.CTkFont(size=11),
                text_color="#888899",
                anchor="w",
            ).pack(anchor="w")

        # Size
        ctk.CTkLabel(
            self,
            text=self._model.size_label,
            font=ctk.CTkFont(size=12),
            text_color="#aaaacc",
        ).grid(row=0, column=1, padx=4, pady=10)

        # Status label
        self._status_lbl = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=12),
        )
        self._status_lbl.grid(row=0, column=2, padx=4, pady=10)

        # Progress bar (hidden until downloading)
        self._progress_bar = ctk.CTkProgressBar(self, width=160, height=12)
        self._progress_bar.set(0)

        # Action button
        self._btn = ctk.CTkButton(
            self,
            text="",
            width=130,
            height=34,
            font=ctk.CTkFont(size=12),
            command=self._on_btn_click,
        )
        self._btn.grid(row=0, column=3, padx=(4, 12), pady=10)

    def refresh(self):
        """Update status label and button text to reflect current model state."""
        model = self._model

        if model.is_downloading:
            pct = model.download_progress
            self._status_lbl.configure(text=f"Downloading {pct:.0f}%", text_color=_YELLOW)
            self._progress_bar.set(pct / 100.0)
            self._progress_bar.grid(row=1, column=0, columnspan=4, padx=12, pady=(0, 8), sticky="ew")
            self._btn.configure(text="Downloading…", state="disabled", fg_color=_GRAY)
        elif model.is_downloaded:
            self._status_lbl.configure(text="Downloaded", text_color=_GREEN)
            self._progress_bar.grid_remove()
            self._btn.configure(
                text="Activate",
                state="normal",
                fg_color="#3a7ebf",
                hover_color="#2a6eaf",
            )
        else:
            self._status_lbl.configure(text="Not downloaded", text_color=_GRAY)
            self._progress_bar.grid_remove()
            self._btn.configure(
                text="Download",
                state="normal",
                fg_color="#5a5a8f",
                hover_color="#4a4a7f",
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
        self._notify(f"Starting download: {self._model.display_name}", "#f39c12")

        self._dl_thread = download_model(
            self._model,
            on_progress=self._on_progress,
            on_done=self._on_done,
        )

    def _on_progress(self, model: ModelInfo, pct: float):
        # Called from background thread — schedule GUI update on main thread
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
                    f"Download failed: {model.display_name} — {message}",
                    _RED,
                )
        self.after(0, _update)

    # ------------------------------------------------------------------
    # Activate
    # ------------------------------------------------------------------

    def _activate(self):
        self._btn.configure(state="disabled", text="Activating…")
        self._notify(f"Activating {self._model.display_name}…", _YELLOW)

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

        # Column headers
        header = ctk.CTkFrame(self, fg_color="#13131f", corner_radius=6)
        header.pack(fill="x", padx=16, pady=(0, 6))
        header.columnconfigure(0, weight=4)
        header.columnconfigure(1, weight=1)
        header.columnconfigure(2, weight=1)
        header.columnconfigure(3, weight=2)

        for col, text in enumerate(("Model", "Size", "Status", "Action")):
            ctk.CTkLabel(
                header,
                text=text,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#888899",
            ).grid(row=0, column=col, padx=12 if col == 0 else 4, pady=6, sticky="w")

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

    def _notify(self, message: str, color: str = "#aaaaaa"):
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
            text="Paths & Ports",
            font=ctk.CTkFont(size=15, weight="bold"),
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
                    command=lambda k=key, t=kind: self._browse(k, t),
                )
                btn.grid(row=row_idx, column=2, padx=(0, 8), pady=6)

        # Save button
        save_row = ctk.CTkFrame(self, fg_color="transparent")
        save_row.pack(fill="x", padx=20, pady=(4, 16))

        self._save_status = ctk.CTkLabel(
            save_row, text="", font=ctk.CTkFont(size=12), text_color="#aaaaaa"
        )
        self._save_status.pack(side="left", padx=(0, 16))

        ctk.CTkButton(
            save_row,
            text="Save Settings",
            width=160,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
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
            # Convert port fields to int
            for _, _, kind in self._FIELDS:
                pass
            field_kind = next(k for k, l, k2 in self._FIELDS if k == key)[2] if False else \
                         next((kind for k, l, kind in self._FIELDS if k == key), "text")
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
            self.iconbitmap(default="")
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

        banner = ctk.CTkFrame(self, height=56, fg_color="#080814", corner_radius=0)
        banner.pack(fill="x", side="top")
        banner.pack_propagate(False)

        # Left: logo dot + title
        left = ctk.CTkFrame(banner, fg_color="transparent")
        left.pack(side="left", padx=18, pady=10)

        dot_canvas = tk.Canvas(left, width=12, height=12, bg="#080814", highlightthickness=0)
        dot_canvas.pack(side="left", padx=(0, 10))
        dot_canvas.create_oval(1, 1, 11, 11, fill=_GREEN, outline="")

        ctk.CTkLabel(left, text="OVMS Manager",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=_TEXT).pack(side="left")

        ctk.CTkLabel(left, text="  ·  OpenVINO Model Server",
                     font=ctk.CTkFont(size=12), text_color=_MUTED).pack(side="left")

        # Right: quit button
        ctk.CTkButton(
            banner, text="Quit", width=64, height=30,
            font=ctk.CTkFont(size=11),
            fg_color=_BORDER, hover_color=_RED, corner_radius=6,
            command=self._quit,
        ).pack(side="right", padx=18)

        # Footer
        footer = ctk.CTkFrame(self, height=28, fg_color="#080814", corner_radius=0)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        ctk.CTkLabel(
            footer,
            text=f"OVMS Manager  v{APP_VERSION}",
            font=ctk.CTkFont(size=10),
            text_color=_MUTED,
        ).pack(side="left", padx=16)

        ctk.CTkLabel(
            footer,
            text=f"by {APP_AUTHOR}",
            font=ctk.CTkFont(size=10),
            text_color=_MUTED,
        ).pack(side="right", padx=16)

        ctk.CTkFrame(footer, width=1, fg_color=_BORDER).pack(side="right")

        ctk.CTkLabel(
            footer,
            text="github.com/annguyen209/OVMS_GUI",
            font=ctk.CTkFont(size=10),
            text_color=_MUTED,
        ).pack(side="right", padx=16)

        self._tabs = ctk.CTkTabview(self, anchor="nw")
        self._tabs.pack(fill="both", expand=True, padx=12, pady=(12, 4))

        self._tabs.add("Dashboard")
        self._tabs.add("Models")
        self._tabs.add("Chat")
        self._tabs.add("Settings")

        self._dashboard = DashboardTab(self._tabs.tab("Dashboard"), server=self._server)
        self._dashboard.pack(fill="both", expand=True)

        self._models_tab = ModelsTab(self._tabs.tab("Models"), server=self._server)
        self._models_tab.pack(fill="both", expand=True)

        self._chat_tab = ChatTab(self._tabs.tab("Chat"))
        self._chat_tab.pack(fill="both", expand=True)

        self._settings_tab = SettingsTab(self._tabs.tab("Settings"))
        self._settings_tab.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _setup_tray(self):
        try:
            from PIL import Image, ImageDraw
            import pystray

            # Draw a simple green circle icon
            img = Image.new("RGB", (64, 64), color="#0d0d1a")
            draw = ImageDraw.Draw(img)
            draw.ellipse([8, 8, 56, 56], fill="#2ecc71")

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
