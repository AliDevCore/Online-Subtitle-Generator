"""
Rotating logging service with automatic secret redaction and diagnostic export.
"""

from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Optional
from app.core.config import LOGS_DIR
from app.core.credential_manager import CredentialManager


class RedactingFormatter(logging.Formatter):
    """Logging formatter that intercepts and redacts API keys and tokens."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return CredentialManager.sanitize_text(original)


def setup_logging(log_file: Optional[Path] = None, level: int = logging.INFO) -> logging.Logger:
    """Initialize root application logger with rotating file and console handlers."""
    if log_file is None:
        log_file = LOGS_DIR / "onlinesub.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid adding duplicate handlers on multiple calls
    if root_logger.handlers:
        return logging.getLogger("OnlineSub")

    formatter = RedactingFormatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Rotating file handler (5 MB, 5 backups)
    file_handler = RotatingFileHandler(
        str(log_file), maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    return logging.getLogger("OnlineSub")


def get_recent_logs(max_lines: int = 250) -> List[str]:
    """Retrieve sanitized recent log lines for GUI display."""
    log_file = LOGS_DIR / "onlinesub.log"
    if not log_file.exists():
        return []
    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-max_lines:]
    except Exception as e:
        return [f"Error reading logs: {e}"]
