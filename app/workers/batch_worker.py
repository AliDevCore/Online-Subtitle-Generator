"""
Background QThread workers for Batch Video Subtitle Generation.
Processes queues of videos sequentially with failure isolation and multi-account failover.
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional
from PySide6.QtCore import QThread, Signal
from app.core.credential_manager import CredentialManager
from app.services.batch_service import BatchService, BatchVideoItem


class QBatchLogHandler(logging.Handler):
    """Logging handler that captures real-time log records during batch runs and forwards them via Qt signal."""

    def __init__(self, emit_callback):
        super().__init__()
        self.emit_callback = emit_callback

    def emit(self, record: logging.LogRecord):
        try:
            # Filter to relevant application logs
            if not record.name.startswith(("OnlineSub", "OnlineSubtitleGenerator")):
                return

            time_str = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
            msg = record.getMessage()
            msg = CredentialManager.sanitize_text(msg)

            # Omit repetitive prefixes like [INFO] [OnlineSubtitleGenerator.ASRService]
            if record.levelno >= logging.ERROR:
                formatted = f"[{time_str}] [ERROR] {msg}"
            elif record.levelno >= logging.WARNING:
                formatted = f"[{time_str}] [WARNING] {msg}"
            else:
                formatted = f"[{time_str}] {msg}"

            self.emit_callback(formatted)
        except Exception:
            pass


class VideoBatchWorker(QThread):
    """Worker thread running batch video queue processing."""

    item_updated = Signal(str, int, int, str)        # (item_name, index, total, status)
    rate_limit_wait = Signal(str, int, int, str)     # (provider, remaining_sec, attempt, reason)
    rate_limit_cleared = Signal(str)                 # (provider)
    batch_finished = Signal(int, int)                # (successful_count, failed_count)
    log_emitted = Signal(str)                        # (clean_log_line)
    failed = Signal(str)

    def __init__(
        self,
        batch_service: BatchService,
        asr_provider: str = "cloudflare",
        asr_model: str = "@cf/openai/whisper-large-v3-turbo",
        parent=None
    ):
        super().__init__(parent)
        self.batch_service = batch_service
        self.asr_provider = asr_provider
        self.asr_model = asr_model
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def notify_rate_limit(self, provider_or_reason: str, remaining_sec: int = 0, attempt: int = 1, reason: str = ""):
        """Supports both (reason, remaining_sec) and (provider, remaining_sec, attempt, reason) signatures."""
        if isinstance(provider_or_reason, str) and remaining_sec > 0 and attempt == 1 and not reason:
            self.rate_limit_wait.emit("Cloudflare Workers AI", remaining_sec, 1, provider_or_reason)
        else:
            self.rate_limit_wait.emit(str(provider_or_reason), int(remaining_sec), int(attempt), str(reason))

    def notify_rate_limit_cleared(self, provider: str = "Cloudflare Workers AI"):
        self.rate_limit_cleared.emit(provider)

    def run(self):
        handler = QBatchLogHandler(self.log_emitted.emit)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        try:
            def on_item(item: BatchVideoItem, idx: int, total: int):
                self.item_updated.emit(item.name, idx, total, item.status.value)

            items = self.batch_service.run_video_batch(
                asr_provider=self.asr_provider,
                asr_model=self.asr_model,
                item_callback=on_item,
                cancel_token=self
            )

            success_cnt = sum(1 for it in items if it.status.value == "COMPLETED")
            failed_cnt = sum(1 for it in items if it.status.value in ("FAILED", "CANCELLED"))
            self.batch_finished.emit(success_cnt, failed_cnt)

        except Exception as e:
            self.failed.emit(str(e))
        finally:
            root_logger.removeHandler(handler)
