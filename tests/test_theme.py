"""
Test dark theme consistency and QDialog/QMessageBox styling.
"""

import sys
import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QLabel, QPushButton
from PySide6.QtGui import QPalette, QColor
from app.ui.styles import apply_dark_theme, DARK_THEME_QSS, get_dark_palette
from app.ui.components.credentials_dialog import CredentialsDialog


def test_dark_palette_values():
    palette = get_dark_palette()
    assert palette.color(QPalette.ColorRole.Window).name() == "#1e1e24"
    assert palette.color(QPalette.ColorRole.WindowText).name() == "#f0f0f5"
    assert palette.color(QPalette.ColorRole.Base).name() == "#181a20"
    assert palette.color(QPalette.ColorRole.Highlight).name() == "#0284c7"


def test_dialog_styling(qtbot):
    app = QApplication.instance() or QApplication(sys.argv)
    apply_dark_theme(app)

    dialog = CredentialsDialog()
    qtbot.addWidget(dialog)

    # Verify background color via palette or style
    pal = dialog.palette()
    assert pal.color(QPalette.ColorRole.Window).name() == "#1e1e24"
    assert pal.color(QPalette.ColorRole.WindowText).name() == "#f0f0f5"

    # Verify QMessageBox palette
    msg = QMessageBox()
    qtbot.addWidget(msg)
    assert msg.palette().color(QPalette.ColorRole.Window).name() == "#1e1e24"
