"""
setup_tab.py - Setup / first-run tab.

Shows a checklist of required components, lets the user install missing
ones with a single click, and streams installation output in a live log.
"""

import tkinter as tk
import threading
import customtkinter as ctk

from app import installer
from app import theme


# Component row

class _ComponentRow(ctk.CTkFrame):

    def __init__(self, master, name: str, check_fn, install_fn,
                 on_log, on_refresh, uninstall_fn=None, on_check_done=None, **kw):
        kw.setdefault("fg_color", theme.CARD)
        kw.setdefault("corner_radius", 8)
        kw.setdefault("border_width", 1)
        kw.setdefault("border_color", theme.BORDER)
        super().__init__(master, **kw)

        self._name          = name
        self._check_fn      = check_fn
        self._install_fn    = install_fn
        self._uninstall_fn  = uninstall_fn
        self._on_log        = on_log
        self._on_refresh    = on_refresh
        self._on_check_done = on_check_done  # called with (ok) when check finishes
        self._busy          = False

        self._build()
        self.after(500, self.refresh)

    def _build(self):
        indicator_wrap = ctk.CTkFrame(self, fg_color="transparent", width=20, height=40)
        indicator_wrap.pack(side="left", padx=(14, 8), pady=14)
        indicator_wrap.pack_propagate(False)

        self._status_dot = ctk.CTkFrame(indicator_wrap, width=10, height=10,
                                        fg_color=theme.MUTED, corner_radius=5)
        self._status_dot.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(self, text=self._name,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=theme.TEXT, anchor="w",
                     ).pack(side="left", fill="x", expand=True)

        self._status_lbl = ctk.CTkLabel(self, text="Checking...",
                                        font=ctk.CTkFont(size=12),
                                        text_color=theme.MUTED, width=130,
                                        anchor="e")
        self._status_lbl.pack(side="left", padx=8)

        # Remove button — only shown when component is installed
        self._remove_btn = ctk.CTkButton(
            self, text="Remove", width=80, height=30,
            font=ctk.CTkFont(size=12),
            fg_color=theme.CARD2, hover_color="#fee2e2",
            border_width=1, border_color=theme.BORDER2,
            text_color=theme.RED,
            command=self._uninstall,
        )
        self._remove_btn.pack(side="right", padx=(4, 4), pady=10)
        self._remove_btn.pack_forget()  # hidden until installed

        # Install button
        self._btn = ctk.CTkButton(self, text="Install", width=90, height=30,
                                  font=ctk.CTkFont(size=12),
                                  fg_color=theme.BLUE, hover_color=theme.BLUE_H,
                                  border_width=1, border_color=theme.BLUE,
                                  text_color="#ffffff",
                                  command=self._install)
        self._btn.pack(side="right", padx=(0, 14), pady=10)

    def refresh(self):
        """Kick off a background check - never blocks the main thread."""
        if self._busy:
            return
        # Show short name so user sees exactly what is being verified
        short = self._name.split("(")[0].strip()
        self._status_lbl.configure(text=f"Checking {short}...", text_color=theme.MUTED)
        self._status_dot.configure(fg_color=theme.AMBER)
        threading.Thread(target=self._check_bg, daemon=True).start()

    def _check_bg(self):
        try:
            ok = self._check_fn()
        except Exception:
            ok = False
        try:
            self.after(0, lambda: self._apply_result(ok))
            if self._on_check_done:
                self.after(0, lambda: self._on_check_done(ok))
        except RuntimeError:
            pass

    def _apply_result(self, ok: bool):
        if ok:
            self._status_dot.configure(fg_color=theme.GREEN)
            self._status_lbl.configure(text="Installed", text_color=theme.GREEN)
            self._btn.configure(state="disabled", fg_color=theme.CARD2,
                                border_width=1, border_color=theme.BORDER2,
                                text_color=theme.MUTED, text="Done")
            # Show Remove button if an uninstall function was provided
            if self._uninstall_fn:
                self._remove_btn.configure(text="Remove", state="normal")
                self._remove_btn.pack(side="right", padx=(4, 4), pady=10,
                                      before=self._btn)
        else:
            self._status_dot.configure(fg_color=theme.RED)
            self._status_lbl.configure(text="Not found", text_color=theme.RED)
            self._remove_btn.pack_forget()
            if not self._busy:
                self._btn.configure(state="normal", fg_color=theme.BLUE,
                                    hover_color=theme.BLUE_H,
                                    text_color="#ffffff", text="Install")

    def _install(self):
        if self._busy:
            return
        self._busy = True
        self._btn.configure(state="disabled", text="Installing...",
                            fg_color=theme.AMBER, text_color="#ffffff")
        self._status_dot.configure(fg_color=theme.AMBER)
        self._status_lbl.configure(text="Installing...", text_color=theme.AMBER)

        def _done(ok: bool, msg: str):
            self._busy = False
            self.after(0, self.refresh)
            self.after(0, self._on_refresh)

        self._install_fn(self._on_log, _done)

    def _uninstall(self):
        if self._busy or not self._uninstall_fn:
            return
        import tkinter.messagebox as _mb
        from app.config import cfg as _cfg
        import os as _os

        # Warn if the component lives outside the app-managed directory
        app_base = _os.path.normcase(
            _os.environ.get("LOCALAPPDATA", "") + "\\OVMS Manager\\"
        )
        py_path  = _os.path.normcase(_cfg.python_exe)
        ovms_path = _os.path.normcase(_cfg.ovms_exe)
        external = not (py_path.startswith(app_base) or ovms_path.startswith(app_base))

        msg = f"Remove '{self._name}'?\n\nThis cannot be undone."
        if external:
            msg = (
                f"Remove '{self._name}'?\n\n"
                "Warning: this component appears to be installed outside the app's "
                "managed folder and may be shared with other software.\n\n"
                "Removing it here will only uninstall the packages from that Python "
                "environment, not delete the interpreter itself.\n\n"
                "Continue?"
            )

        if not _mb.askyesno("Remove Component", msg, icon="warning"):
            return
        self._busy = True
        self._remove_btn.configure(state="disabled", text="Removing...")
        self._btn.configure(state="disabled")
        self._status_dot.configure(fg_color=theme.AMBER)
        self._status_lbl.configure(text="Removing...", text_color=theme.AMBER)

        def _done(ok: bool, msg: str):
            self._busy = False
            self.after(0, self.refresh)
            self.after(0, self._on_refresh)

        self._uninstall_fn(self._on_log, _done)


# Setup Tab

class SetupTab(ctk.CTkFrame):

    def __init__(self, master, on_all_ok=None, on_missing=None, **kw):
        kw.setdefault("fg_color", theme.BG)
        super().__init__(master, **kw)
        self._on_all_ok       = on_all_ok
        self._on_missing      = on_missing
        self._rows: list[_ComponentRow] = []
        self._check_results: dict = {}
        self._rows_pending    = 0
        self._missing_shown   = False  # fire on_missing only once per session
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # Header card
        header_card = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=8,
                                   border_width=1, border_color=theme.BORDER)
        header_card.pack(fill="x", padx=20, pady=(20, 0))

        hdr = ctk.CTkFrame(header_card, fg_color="transparent")
        hdr.pack(fill="x", padx=18, pady=(16, 4))
        ctk.CTkLabel(hdr, text="First-Run Setup",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=theme.TEXT).pack(side="left")
        self._all_badge = ctk.CTkLabel(hdr, text="",
                                       font=ctk.CTkFont(size=11, weight="bold"),
                                       fg_color="#f0fdf4", text_color=theme.GREEN,
                                       corner_radius=6, padx=8, pady=2)
        self._all_badge.pack(side="left", padx=10)

        ctk.CTkLabel(header_card,
                     text="OpenVINO Manager needs these components to run. "
                          "Click Install next to any missing item, or use "
                          "Install All to set up everything automatically.",
                     font=ctk.CTkFont(size=12), text_color=theme.MUTED,
                     anchor="w", wraplength=860, justify="left",
                     ).pack(fill="x", padx=18, pady=(0, 14))

        # Install All button
        btn_row = ctk.CTkFrame(header_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(0, 16))

        self._install_all_btn = ctk.CTkButton(
            btn_row, text="Install All", width=140, height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=theme.BLUE, hover_color=theme.BLUE_H,
            border_width=1, border_color=theme.BLUE,
            text_color="#ffffff",
            command=self._install_all,
        )
        self._install_all_btn.pack(side="left")

        self._global_status = ctk.CTkLabel(
            btn_row, text="", font=ctk.CTkFont(size=12),
            text_color=theme.MUTED, anchor="w",
        )
        self._global_status.pack(side="left", padx=14)

        # Component checklist
        self._list_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._list_frame.pack(fill="x", padx=20, pady=12)

        # (name, check_fn, install_fn, uninstall_fn)
        _components = [
            ("Python 3.x venv",
             installer.check_venv,
             installer.install_venv,
             installer.uninstall_venv),
            ("OpenVINO packages (openvino, openvino-genai)",
             installer.check_openvino,
             installer.install_openvino,
             installer.uninstall_openvino),
            ("Proxy and GUI dependencies (fastapi, httpx, customtkinter...)",
             installer.check_proxy_deps,
             lambda log, done: installer.install_all_pip(log, done),
             installer.uninstall_proxy_deps),
            ("OVMS binary (ovms.exe)",
             installer.check_ovms,
             installer.install_ovms,
             installer.uninstall_ovms),
        ]

        for name, check_fn, install_fn, uninstall_fn in _components:
            row = _ComponentRow(
                self._list_frame, name, check_fn, install_fn,
                on_log=self._append_log,
                on_refresh=self.refresh,
                uninstall_fn=uninstall_fn,
                on_check_done=lambda ok, n=name: self._on_row_check_done(n, ok),
            )
            row.pack(fill="x", pady=4)
            self._rows.append(row)

        # Live log
        log_lbl = ctk.CTkFrame(self, fg_color="transparent")
        log_lbl.pack(fill="x", padx=20, pady=(4, 2))
        ctk.CTkLabel(log_lbl, text="INSTALLATION LOG",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=theme.MUTED).pack(side="left")
        ctk.CTkFrame(log_lbl, height=1, fg_color=theme.BORDER
                     ).pack(side="left", fill="x", expand=True, padx=(8, 0))

        self._log_box = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=theme.CODE_BG,
            text_color=theme.CODE_FG,
            wrap="word",
            state="disabled",
            height=180,
            corner_radius=8,
        )
        self._log_box.pack(fill="x", padx=20, pady=(0, 20))
        self._append_log("Ready. Click Install or Install All to begin.")

    # Actions

    def _set_all_rows_busy(self, busy: bool):
        """Disable/enable all individual row Install buttons during Install All."""
        for row in self._rows:
            if busy:
                row._btn.configure(state="disabled")
                row._remove_btn.configure(state="disabled")
            else:
                row._btn.configure(state="normal")
                row._remove_btn.configure(state="normal")

    def _install_all(self):
        self._install_all_btn.configure(state="disabled", text="Installing...",
                                        fg_color=theme.AMBER)
        self._global_status.configure(text="Running full install...",
                                      text_color=theme.AMBER)
        self._set_all_rows_busy(True)

        def _done(ok: bool, msg: str):
            def _ui():
                self._set_all_rows_busy(False)
                self._install_all_btn.configure(state="normal",
                                                text="Install All",
                                                fg_color=theme.BLUE,
                                                hover_color=theme.BLUE_H)
                self._global_status.configure(
                    text=msg,
                    text_color=theme.GREEN if ok else theme.RED,
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

    # Refresh

    def refresh(self):
        """Trigger background checks on all rows; aggregate when all finish."""
        self._global_status.configure(text="Checking components...", text_color=theme.AMBER)
        self._check_results.clear()
        self._rows_pending = len(self._rows)
        for row in self._rows:
            row.refresh()

    def _on_row_check_done(self, name: str, ok: bool):
        """Called by each row when its check finishes."""
        self._check_results[name] = ok
        if self._rows_pending <= 0:
            return  # stale callback from a row's own 500 ms self-refresh cycle
        self._rows_pending -= 1
        if self._rows_pending == 0:
            self._refresh_aggregate()

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
                                      fg_color="#f0fdf4", text_color=theme.GREEN)
            self._install_all_btn.configure(state="disabled",
                                            text="All installed",
                                            fg_color=theme.CARD2,
                                            border_width=1,
                                            border_color=theme.BORDER2,
                                            text_color=theme.MUTED)
            self._global_status.configure(text="All components ready.",
                                          text_color=theme.GREEN)
            self._missing_shown = False
            if self._on_all_ok:
                self._on_all_ok()
        else:
            self._global_status.configure(text="Some components missing.",
                                          text_color=theme.AMBER)
            if self._on_missing and not self._missing_shown:
                self._missing_shown = True
                self._on_missing()
            self._all_badge.configure(
                text="Some components missing — click Install to set up",
                fg_color="#fff7ed", text_color=theme.AMBER,
            )
