"""
OnlineSub — Main Application Entry Point
"""

from __future__ import annotations
import sys
import os
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

from app.core.config import APP_NAME, APP_VERSION, APP_AUTHOR, get_app_icon
from app.services.logging_service import setup_logging
from app.ui.styles import apply_dark_theme
from app.ui.main_window import MainWindow


def main():
    """Application main entry point."""
    logger = setup_logging()
    logger.info(f"Starting {APP_NAME} v{APP_VERSION} on Windows (Python {sys.version.split()[0]})...")

    # Set explicit AppUserModelID on Windows for proper taskbar and titlebar icon rendering
    if sys.platform == "win32":
        try:
            import ctypes
            app_id = f"{APP_AUTHOR}.{APP_NAME}.v{APP_VERSION}"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass

    # High DPI scaling configuration for modern Windows displays
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_AUTHOR)

    # Apply global Dark Theme and Palette across all windows and dialogs
    apply_dark_theme(app)

    # Set Application Icon globally
    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    window = MainWindow()
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
