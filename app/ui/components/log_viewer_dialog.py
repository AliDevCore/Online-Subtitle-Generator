"""
Live Log Viewer dialog.
Displays sanitized, secret-redacted application logs with auto-scroll and file open shortcuts.
"""

from __future__ import annotations
import subprocess
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton, QApplication
)
from app.core.config import LOGS_DIR, get_app_icon
from app.services.logging_service import get_recent_logs


class LogViewerDialog(QDialog):
    """Dialog showing application runtime logs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OnlineSub — Application Logs")
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self.resize(750, 480)
        self._build_ui()
        self.refresh_logs()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.txt_logs = QPlainTextEdit()
        self.txt_logs.setReadOnly(True)
        layout.addWidget(self.txt_logs)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("btn_secondary")
        self.btn_refresh.clicked.connect(self.refresh_logs)
        btn_box.addWidget(self.btn_refresh)

        self.btn_copy = QPushButton("Copy All")
        self.btn_copy.setObjectName("btn_secondary")
        self.btn_copy.clicked.connect(self._copy_all)
        btn_box.addWidget(self.btn_copy)

        self.btn_open_file = QPushButton("Open Log File")
        self.btn_open_file.setObjectName("btn_secondary")
        self.btn_open_file.clicked.connect(self._open_log_file)
        btn_box.addWidget(self.btn_open_file)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_close)

        layout.addLayout(btn_box)

    def refresh_logs(self):
        lines = get_recent_logs(max_lines=300)
        self.txt_logs.setPlainText("\n".join(lines))
        self.txt_logs.verticalScrollBar().setValue(
            self.txt_logs.verticalScrollBar().maximum()
        )

    def _copy_all(self):
        QApplication.clipboard().setText(self.txt_logs.toPlainText())

    def _open_log_file(self):
        log_file = LOGS_DIR / "onlinesub.log"
        if log_file.exists():
            subprocess.run(["explorer", str(log_file)])
