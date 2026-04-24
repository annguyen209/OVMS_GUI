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
# Theme
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_GREEN  = "#2ecc71"
_RED    = "#e74c3c"
_YELLOW = "#f39c12"
_GRAY   = "#555566"

_POLL_MS = 3000   # GUI status-card refresh interval (ms)


# ---------------------------------------------------------------------------
# Status indicator (coloured dot + label)
# ---------------------------------------------------------------------------

class StatusCard(ctk.CTkFrame):
    """Small card: title label + coloured status dot + status text."""

    def __init__(self, master, title: str, **kwargs):
        kwargs.setdefault("corner_radius", 10)
        kwargs.setdefault("fg_color", "#1e1e2e")
        super().__init__(master, **kwargs)

        ctk.CTkLabel(
            self,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#aaaacc",
        ).pack(anchor="w", padx=14, pady=(10, 2))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(anchor="w", padx=14, pady=(0, 10))

        # Dot (a small canvas circle) – use standard tk.Canvas, not CTkCanvas
        self._canvas = tk.Canvas(
            row, width=14, height=14,
            bg="#1e1e2e", highlightthickness=0,
        )
        self._canvas.pack(side="left", padx=(0, 8))
        self._dot = self._canvas.create_oval(1, 1, 13, 13, fill=_GRAY, outline="")

        self._value_label = ctk.CTkLabel(
            row,
            text="Unknown",
            font=ctk.CTkFont(size=13),
        )
        self._value_label.pack(side="left")

    def set_status(self, text: str, color: str = _GRAY):
        self._canvas.itemconfigure(self._dot, fill=color)
        self._value_label.configure(text=text)


# ---------------------------------------------------------------------------
# Dashboard Tab
# ---------------------------------------------------------------------------

class DashboardTab(ctk.CTkFrame):

    def __init__(self, master, server: ServerManager, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._server = server
        self._stack_busy = False   # prevent double-click during start/stop

        self._build_ui()
        self._schedule_poll()

    def _build_ui(self):
        # ---- Status cards row ----
        cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        cards_frame.pack(fill="x", padx=16, pady=(16, 8))

        self._card_ovms   = StatusCard(cards_frame, "OVMS Server")
        self._card_proxy  = StatusCard(cards_frame, "Proxy")
        self._card_model  = StatusCard(cards_frame, "Active Model")

        for card in (self._card_ovms, self._card_proxy, self._card_model):
            card.pack(side="left", expand=True, fill="both", padx=6)

        # ---- Start / Stop button ----
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=8)

        self._action_btn = ctk.CTkButton(
            btn_frame,
            text="Start Stack",
            width=200,
            height=46,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#2ecc71",
            hover_color="#27ae60",
            command=self._on_action_click,
        )
        self._action_btn.pack(side="left", padx=6)

        self._status_msg = ctk.CTkLabel(
            btn_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#aaaaaa",
            anchor="w",
            wraplength=500,
        )
        self._status_msg.pack(side="left", padx=12, fill="x", expand=True)

        # ---- Log viewer ----
        log_label = ctk.CTkLabel(
            self,
            text="OVMS Server Log (last 20 lines)",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        log_label.pack(fill="x", padx=22, pady=(8, 2))

        self._log_viewer = LogViewerWidget(
            self,
            log_path=cfg.ovms_log,
            tail_lines=20,
            refresh_ms=2000,
        )
        self._log_viewer.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self._log_viewer.start()

    # ------------------------------------------------------------------
    # Status polling
    # ------------------------------------------------------------------

    def _schedule_poll(self):
        self.after(_POLL_MS, self._poll)

    def _poll(self):
        self._refresh_cards()
        self._schedule_poll()

    def _refresh_cards(self):
        ovms_up   = self._server.ovms_running
        proxy_up  = self._server.proxy_running
        model_name = read_active_model_name()

        if ovms_up:
            self._card_ovms.set_status("Running", _GREEN)
        else:
            self._card_ovms.set_status("Stopped", _RED)

        if proxy_up:
            self._card_proxy.set_status("Running", _GREEN)
        else:
            self._card_proxy.set_status("Stopped", _RED)

        if model_name:
            self._card_model.set_status(model_name, _YELLOW)
        else:
            self._card_model.set_status("None", _GRAY)

        # Update button appearance based on server state
        if not self._stack_busy:
            if ovms_up or proxy_up:
                self._action_btn.configure(
                    text="Stop Stack",
                    fg_color=_RED,
                    hover_color="#c0392b",
                )
            else:
                self._action_btn.configure(
                    text="Start Stack",
                    fg_color=_GREEN,
                    hover_color="#27ae60",
                )

    # ------------------------------------------------------------------
    # Button handler
    # ------------------------------------------------------------------

    def _on_action_click(self):
        if self._stack_busy:
            return

        ovms_up  = self._server.ovms_running
        proxy_up = self._server.proxy_running
        stopping = ovms_up or proxy_up

        self._stack_busy = True
        self._action_btn.configure(
            state="disabled",
            text="Please wait…",
            fg_color=_GRAY,
        )
        self._status_msg.configure(text="Working…", text_color="#f39c12")

        def _worker():
            if stopping:
                ok, msg = self._server.stop_stack()
            else:
                ok, msg = self._server.start_stack()

            # Schedule GUI update back on the main thread
            self.after(0, lambda: self._on_action_done(ok, msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_action_done(self, ok: bool, msg: str):
        self._stack_busy = False
        color = "#aaffaa" if ok else "#ffaaaa"
        self._status_msg.configure(text=msg, text_color=color)
        self._action_btn.configure(state="normal")
        # Immediately refresh status cards
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
        banner = ctk.CTkFrame(self, height=52, fg_color="#0d0d1a", corner_radius=0)
        banner.pack(fill="x", side="top")
        banner.pack_propagate(False)

        ctk.CTkLabel(
            banner,
            text="OVMS Model Server Manager",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#e0e0ff",
        ).pack(side="left", padx=20, pady=14)

        ctk.CTkLabel(
            banner,
            text="OpenVINO Model Server",
            font=ctk.CTkFont(size=11),
            text_color="#666688",
        ).pack(side="right", padx=20)

        self._tabs = ctk.CTkTabview(self, anchor="nw")
        self._tabs.pack(fill="both", expand=True, padx=12, pady=12)

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
