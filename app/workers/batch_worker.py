"""
Background QThread workers for Batch Video Subtitle Generation.
Processes queues of videos sequentially with failure isolation and multi-account failover.
"""

from __future__ import annotations
from typing import Optional
from PySide6.QtCore import QThread, Signal
from app.services.batch_service import BatchService, BatchVideoItem


class VideoBatchWorker(QThread):
    """Worker thread running batch video queue processing."""

    item_updated = Signal(str, int, int, str)        # (item_name, index, total, status)
    rate_limit_wait = Signal(str, int, int, str)     # (provider, remaining_sec, attempt, reason)
    rate_limit_cleared = Signal(str)                 # (provider)
    batch_finished = Signal(int, int)                # (successful_count, failed_count)
    failed = Signal(str)

    def __init__(
        self,
        batch_service: BatchService,
        asr_provider: str = "cloudflare",
        asr_model: str = "@cf/openai/whisper",
        parent=None
    ):
        super().__init__(parent)
        self.batch_service = batch_service
        self.asr_provider = asr_provider
        self.asr_model = asr_model
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def notify_rate_limit(self, reason: str, remaining_sec: int = 0):
        self.rate_limit_wait.emit("Cloudflare Workers AI", remaining_sec, 1, reason)

    def notify_rate_limit_cleared(self, provider: str = "Cloudflare Workers AI"):
        self.rate_limit_cleared.emit(provider)

    def run(self):
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
