"""
Modern stylesheet and UI styling for OnlineSub desktop application.
Clean, high-contrast, accessible dark theme adhering to modern Windows 10/11 aesthetics.
Ensures 100% theme consistency across Main Window, all Dialogs, Popups, and MessageBoxes.
"""

from __future__ import annotations
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication

DARK_THEME_QSS = """
/* Global Window & Dialog Backgrounds */
QMainWindow, QDialog, QMessageBox {
    background-color: #1e1e24;
    color: #f0f0f5;
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    font-size: 13px;
}

QWidget {
    color: #e2e8f0;
    font-family: "Segoe UI", system-ui, sans-serif;
}

/* Modal Dialogs explicitly */
QDialog {
    background-color: #1e1e24;
}

/* QMessageBox Styling */
QMessageBox {
    background-color: #1e1e24;
    color: #f0f0f5;
}

QMessageBox QLabel {
    color: #f0f0f5;
    font-size: 13px;
    font-weight: 500;
    min-width: 240px;
}

QMessageBox QPushButton {
    min-width: 80px;
    padding: 7px 16px;
    background-color: #0284c7;
    color: #ffffff;
    border-radius: 6px;
    font-weight: 600;
}

QMessageBox QPushButton:hover {
    background-color: #0369a1;
}

/* Group Boxes / Cards */
QGroupBox {
    border: 1px solid #334155;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 18px;
    padding-left: 14px;
    padding-right: 14px;
    padding-bottom: 14px;
    font-weight: 600;
    font-size: 13px;
    color: #38bdf8;
    background-color: #252836;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    background-color: #1e1e24;
    color: #38bdf8;
    border-radius: 3px;
}

QLabel {
    color: #cbd5e1;
}

/* Text Inputs, Spinners, Dropdowns */
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background-color: #181a20;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 26px;
    color: #f8fafc;
    selection-background-color: #0284c7;
    selection-color: #ffffff;
}

QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #38bdf8;
    background-color: #1a1e29;
}

QComboBox QAbstractItemView {
    background-color: #1e1e24;
    border: 1px solid #334155;
    color: #f8fafc;
    selection-background-color: #0284c7;
    selection-color: #ffffff;
    outline: none;
    padding: 4px;
}

/* Buttons */
QPushButton {
    background-color: #0284c7;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    min-height: 24px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #0369a1;
}

QPushButton:pressed {
    background-color: #075985;
}

QPushButton:disabled,
QPushButton#btn_primary:disabled,
QPushButton#btn_secondary:disabled,
QPushButton#btn_success:disabled,
QPushButton#btn_danger:disabled {
    background-color: #27272a !important;
    color: #71717a !important;
    border: 1px solid #3f3f46 !important;
}

QPushButton#btn_secondary {
    background-color: #334155;
    color: #e2e8f0;
}

QPushButton#btn_secondary:hover {
    background-color: #475569;
}

QPushButton#btn_danger {
    background-color: #dc2626;
    color: #ffffff;
}

QPushButton#btn_danger:hover {
    background-color: #b91c1c;
}

QPushButton#btn_success {
    background-color: #16a34a;
    color: #ffffff;
}

QPushButton#btn_success:hover {
    background-color: #15803d;
}

/* CheckBoxes & RadioButtons */
QCheckBox, QRadioButton {
    color: #e2e8f0;
    spacing: 8px;
    font-size: 13px;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #475569;
    border-radius: 4px;
    background-color: #181a20;
}

QRadioButton::indicator {
    border-radius: 8px;
}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #38bdf8;
}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: #0284c7;
    border-color: #38bdf8;
}

/* Progress Bar */
QProgressBar {
    border: 1px solid #334155;
    border-radius: 6px;
    text-align: center;
    background-color: #181a20;
    color: #ffffff;
    font-weight: bold;
    height: 20px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #38bdf8);
    border-radius: 5px;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: #181a20;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #475569;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #64748b;
}

QScrollBar:horizontal {
    border: none;
    background: #181a20;
    height: 10px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #475569;
    min-width: 20px;
    border-radius: 5px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    height: 0px;
    width: 0px;
}

/* Text Editors & Logs */
QTextEdit, QPlainTextEdit {
    background-color: #111318;
    border: 1px solid #334155;
    border-radius: 6px;
    color: #e2e8f0;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
}

/* Tables & Lists */
QTableWidget, QTableView {
    background-color: #181a20;
    border: 1px solid #334155;
    gridline-color: #2d3748;
    color: #f1f5f9;
    selection-background-color: #0284c7;
    selection-color: #ffffff;
}

QHeaderView::section {
    background-color: #252836;
    color: #94a3b8;
    padding: 6px;
    border: 1px solid #334155;
    font-weight: 600;
}

/* Menus & Tooltips */
QMenu {
    background-color: #1e1e24;
    color: #f0f0f5;
    border: 1px solid #334155;
    padding: 4px;
}

QMenu::item:selected {
    background-color: #0284c7;
    color: #ffffff;
}

QToolTip {
    background-color: #0f172a;
    color: #f8fafc;
    border: 1px solid #475569;
    padding: 4px 8px;
    border-radius: 4px;
}
"""


def get_dark_palette() -> QPalette:
    """Constructs a consistent high-contrast dark QPalette for Qt widgets and native dialogs."""
    palette = QPalette()
    dark_bg = QColor(30, 30, 36)        # #1e1e24
    card_bg = QColor(37, 40, 54)        # #252836
    input_bg = QColor(24, 26, 32)       # #181a20
    text_color = QColor(240, 240, 245)  # #f0f0f5
    sub_text = QColor(148, 163, 184)    # #94a3b8
    accent = QColor(2, 132, 199)        # #0284c7

    palette.setColor(QPalette.ColorRole.Window, dark_bg)
    palette.setColor(QPalette.ColorRole.WindowText, text_color)
    palette.setColor(QPalette.ColorRole.Base, input_bg)
    palette.setColor(QPalette.ColorRole.AlternateBase, card_bg)
    palette.setColor(QPalette.ColorRole.ToolTipBase, dark_bg)
    palette.setColor(QPalette.ColorRole.ToolTipText, text_color)
    palette.setColor(QPalette.ColorRole.Text, text_color)
    palette.setColor(QPalette.ColorRole.Button, card_bg)
    palette.setColor(QPalette.ColorRole.ButtonText, text_color)
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    return palette


def apply_dark_theme(app: QApplication):
    """Applies global dark palette and unified stylesheet to the entire QApplication."""
    app.setStyle("Fusion")  # Fusion provides the most consistent cross-platform dark-styling
    app.setPalette(get_dark_palette())
    app.setStyleSheet(DARK_THEME_QSS)
