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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
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
