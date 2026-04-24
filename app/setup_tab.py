"""
setup_tab.py — Setup / first-run tab.

Shows a checklist of required components, lets the user install missing
ones with a single click, and streams installation output in a live log.
"""

import tkinter as tk
import threading
import customtkinter as ctk

from app import installer

# ── Palette ───────────────────────────────────────────────────────────────
_BG     = "#f1f5f9"
_CARD   = "#ffffff"
_CARD2  = "#f8fafc"
_BORDER = "#e2e8f0"
_TEXT   = "#0f172a"
_TEXT2  = "#334155"
_MUTED  = "#94a3b8"
_GREEN  = "#16a34a"
_RED    = "#dc2626"
_YELLOW = "#d97706"
_BLUE   = "#2563eb"
_CODE_BG = "#1e293b"
_CODE_FG = "#e2e8f0"


# ── Component row ─────────────────────────────────────────────────────────

class _ComponentRow(ctk.CTkFrame):

    def __init__(self, master, name: str, check_fn, install_fn,
                 on_log, on_refresh, **kw):
        kw.setdefault("fg_color", _CARD)
        kw.setdefault("corner_radius", 10)
        kw.setdefault("border_width", 1)
        kw.setdefault("border_color", _BORDER)
        super().__init__(master, **kw)

        self._name       = name
        self._check_fn   = check_fn
        self._install_fn = install_fn
        self._on_log     = on_log
        self._on_refresh = on_refresh
        self._busy       = False

        self._build()
        # Delay until mainloop is running before spawning check threads
        self.after(600, self.refresh)

    def _build(self):
        # Status dot
        self._canvas = tk.Canvas(self, width=14, height=14,
                                 bg=_CARD, highlightthickness=0)
        self._canvas.pack(side="left", padx=(14, 8), pady=14)
        self._dot = self._canvas.create_oval(2, 2, 12, 12,
                                             fill=_MUTED, outline="")

        # Name
        ctk.CTkLabel(self, text=self._name,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=_TEXT, anchor="w",
                     ).pack(side="left", fill="x", expand=True)

        # Status label
        self._status_lbl = ctk.CTkLabel(self, text="Checking…",
                                        font=ctk.CTkFont(size=12),
                                        text_color=_MUTED, width=130,
                                        anchor="e")
        self._status_lbl.pack(side="left", padx=8)

        # Install button
        self._btn = ctk.CTkButton(self, text="Install", width=90, height=30,
                                  font=ctk.CTkFont(size=12),
                                  command=self._install)
        self._btn.pack(side="right", padx=14, pady=10)

    def refresh(self):
        """Kick off a background check — never blocks the main thread."""
        if self._busy:
            return
        self._status_lbl.configure(text="Checking…", text_color=_MUTED)
        self._canvas.itemconfigure(self._dot, fill=_MUTED)
        threading.Thread(target=self._check_bg, daemon=True).start()

    def _check_bg(self):
        ok = self._check_fn()
        try:
            self.after(0, lambda: self._apply_result(ok))
        except RuntimeError:
            pass  # widget destroyed or mainloop not yet running

    def _apply_result(self, ok: bool):
        if ok:
            self._canvas.itemconfigure(self._dot, fill=_GREEN)
            self._status_lbl.configure(text="Installed", text_color=_GREEN)
            self._btn.configure(state="disabled", fg_color=_BORDER,
                                text_color=_MUTED, text="✓ Done")
        else:
            self._canvas.itemconfigure(self._dot, fill=_RED)
            self._status_lbl.configure(text="Not found", text_color=_RED)
            if not self._busy:
                self._btn.configure(state="normal", fg_color=_BLUE,
                                    text_color="#ffffff", text="Install")

    def _install(self):
        if self._busy:
            return
        self._busy = True
        self._btn.configure(state="disabled", text="Installing…",
                            fg_color=_YELLOW, text_color="#ffffff")
        self._canvas.itemconfigure(self._dot, fill=_YELLOW)
        self._status_lbl.configure(text="Installing…", text_color=_YELLOW)

        def _done(ok: bool, msg: str):
            self._busy = False
            self.after(0, self.refresh)
            self.after(0, self._on_refresh)

        self._install_fn(self._on_log, _done)


# ── Setup Tab ─────────────────────────────────────────────────────────────

class SetupTab(ctk.CTkFrame):

    def __init__(self, master, on_all_ok=None, **kw):
        kw.setdefault("fg_color", _BG)
        super().__init__(master, **kw)
        self._on_all_ok = on_all_ok   # called when every component is installed
        self._rows: list[_ComponentRow] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # Header card
        header_card = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=14,
                                   border_width=1, border_color=_BORDER)
        header_card.pack(fill="x", padx=20, pady=(20, 0))

        hdr = ctk.CTkFrame(header_card, fg_color="transparent")
        hdr.pack(fill="x", padx=18, pady=(16, 4))
        ctk.CTkLabel(hdr, text="First-Run Setup",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=_TEXT).pack(side="left")
        self._all_badge = ctk.CTkLabel(hdr, text="",
                                       font=ctk.CTkFont(size=11, weight="bold"),
                                       fg_color="#dcfce7", text_color=_GREEN,
                                       corner_radius=6, padx=8, pady=2)
        self._all_badge.pack(side="left", padx=10)

        ctk.CTkLabel(header_card,
                     text="OVMS Manager needs these components to run. "
                          "Click Install next to any missing item, or use "
                          "Install All to set up everything automatically.",
                     font=ctk.CTkFont(size=12), text_color=_MUTED,
                     anchor="w", wraplength=860, justify="left",
                     ).pack(fill="x", padx=18, pady=(0, 14))

        # Install All button
        btn_row = ctk.CTkFrame(header_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(0, 16))

        self._install_all_btn = ctk.CTkButton(
            btn_row, text="Install All", width=140, height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=_BLUE, hover_color="#1d4ed8",
            command=self._install_all,
        )
        self._install_all_btn.pack(side="left")

        self._global_status = ctk.CTkLabel(
            btn_row, text="", font=ctk.CTkFont(size=12),
            text_color=_MUTED, anchor="w",
        )
        self._global_status.pack(side="left", padx=14)

        # Component checklist
        self._list_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._list_frame.pack(fill="x", padx=20, pady=12)

        _components = [
            ("Python 3.12 venv",
             installer.check_venv,
             installer.install_venv),
            ("OpenVINO packages  (openvino, openvino-genai)",
             installer.check_openvino,
             installer.install_openvino),
            ("Proxy & GUI dependencies  (fastapi, httpx, customtkinter…)",
             installer.check_proxy_deps,
             lambda log, done: installer.install_all_pip(log, done)),
            ("OVMS binary  (ovms.exe)",
             installer.check_ovms,
             installer.install_ovms),
        ]

        for name, check_fn, install_fn in _components:
            row = _ComponentRow(
                self._list_frame, name, check_fn, install_fn,
                on_log=self._append_log,
                on_refresh=self.refresh,
            )
            row.pack(fill="x", pady=4)
            self._rows.append(row)

        # Live log
        log_lbl = ctk.CTkFrame(self, fg_color="transparent")
        log_lbl.pack(fill="x", padx=20, pady=(4, 2))
        ctk.CTkLabel(log_lbl, text="INSTALLATION LOG",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=_MUTED).pack(side="left")
        ctk.CTkFrame(log_lbl, height=1, fg_color=_BORDER
                     ).pack(side="left", fill="x", expand=True, padx=(8, 0))

        self._log_box = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=_CODE_BG,
            text_color=_CODE_FG,
            wrap="word",
            state="disabled",
            height=180,
            corner_radius=10,
        )
        self._log_box.pack(fill="x", padx=20, pady=(0, 20))
        self._append_log("Ready. Click Install or Install All to begin.")

    # ── Actions ───────────────────────────────────────────────────────────

    def _install_all(self):
        self._install_all_btn.configure(state="disabled", text="Installing…",
                                        fg_color=_YELLOW)
        self._global_status.configure(text="Running full install…",
                                      text_color=_YELLOW)

        def _done(ok: bool, msg: str):
            def _ui():
                self._install_all_btn.configure(state="normal",
                                                text="Install All",
                                                fg_color=_BLUE)
                self._global_status.configure(
                    text=msg,
                    text_color=_GREEN if ok else _RED,
                )
                self.refresh()
            self.after(0, _ui)

        installer.install_everything(self._append_log, _done)

    def _append_log(self, line: str):
        def _ui():
            self._log_box.configure(state="normal")
            self._log_box.insert("end", line + "\n")
            self._log_box.see("end")
            self._log_box.configure(state="disabled")
        try:
            self.after(0, _ui)
        except Exception:
            pass

    # ── Refresh ───────────────────────────────────────────────────────────

    def refresh(self):
        """Trigger background checks on all rows; aggregate result when done."""
        for row in self._rows:
            row.refresh()
        # After all per-row background checks fire, do the aggregate check
        # Use a delay longer than a typical subprocess call (~3 s)
        self.after(4000, self._refresh_aggregate)

    def _refresh_aggregate(self):
        """Run aggregate all_ok() check in background, update badge."""
        threading.Thread(target=self._aggregate_bg, daemon=True).start()

    def _aggregate_bg(self):
        ok = installer.all_ok()
        try:
            self.after(0, lambda: self._apply_aggregate(ok))
        except RuntimeError:
            pass

    def _apply_aggregate(self, ok: bool):
        if ok:
            self._all_badge.configure(text="All components installed",
                                      fg_color="#dcfce7", text_color=_GREEN)
            self._install_all_btn.configure(state="disabled",
                                            text="✓ All installed",
                                            fg_color=_BORDER,
                                            text_color=_MUTED)
            if self._on_all_ok:
                self._on_all_ok()
        else:
            self._all_badge.configure(
                text="Checking components…",
                fg_color="#fef9c3", text_color=_AMBER,
            )
