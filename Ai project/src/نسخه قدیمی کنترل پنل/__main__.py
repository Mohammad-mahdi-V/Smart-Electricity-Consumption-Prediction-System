"""
main.py

Entry point:
    python src/control_panel/main.py

This file is intentionally import-light and uses no relative imports
(it's a script, not a package member) -- its only job is to put the
project's src/ directory on sys.path so `control_panel` and the
existing project modules it wraps (predictor, model, monthly_retrainer,
...) are all importable, then hand off to control_panel.app.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

CONTROL_PANEL_DIR = Path(__file__).resolve().parent
SRC_DIR = CONTROL_PANEL_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def main() -> None:
    from PySide6.QtWidgets import QApplication

    from control_panel.app import MainWindow

    app = QApplication(sys.argv)

    window = MainWindow()

    # Qt has no direct equivalent of Tkinter's root.report_callback_exception
    # -- sys.excepthook is the standard place to catch anything an event
    # handler / slot raises without letting it crash the whole app.
    def _except_hook(exc_type, exc_value, exc_tb) -> None:
        window.on_uncaught_exception(exc_type, exc_value, exc_tb)
        traceback.print_exception(exc_type, exc_value, exc_tb)

    sys.excepthook = _except_hook

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
