"""
main.py — Entry point for the OVMS GUI Manager.

Run with:  python main.py
or simply double-click run.bat.
"""

import logging
import sys
import os

# Ensure the project root is on the path so `app` package resolves correctly
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _configure_logging():
    from pathlib import Path
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    # Always write to a log file so errors are visible in the installed app
    # (installed app has no console — stdout is discarded).
    try:
        log_dir = Path(os.environ.get("LOCALAPPDATA", "~")).expanduser() / "OVMS Manager" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        handlers.append(fh)
    except Exception:
        pass

    # Fix SSL certificate path in PyInstaller frozen environment so requests
    # can verify HTTPS connections (certifi path changes after extraction).
    if getattr(sys, "frozen", False):
        try:
            import certifi
            os.environ.setdefault("SSL_CERT_FILE",       certifi.where())
            os.environ.setdefault("REQUESTS_CA_BUNDLE",  certifi.where())
        except Exception:
            pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


def main():
    _configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting OVMS GUI Manager...")

    # Build icon assets before opening the window
    try:
        from app.icon import build_icon
        build_icon()
    except Exception:
        pass

    try:
        from app.gui import App
    except ImportError as exc:
        print(
            f"\nFailed to import GUI modules: {exc}\n"
            "Please install dependencies first:\n"
            "  pip install -r requirements.txt"
        )
        sys.exit(1)

    app = App()
    app.mainloop()
    logger.info("Application closed.")


if __name__ == "__main__":
    main()
