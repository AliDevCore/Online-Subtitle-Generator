"""
Background QThread worker for Pipeline A (ASR).
Keeps the PySide6 user interface responsive while performing media extraction and transcription.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional
from PySide6.QtCore import QThread, Signal

from app.core.types import TimeRange
from app.services.asr_service import ASRService

logger = logging.getLogger("OnlineSubtitleGenerator.Worker")


class ASRWorker(QThread):
    """Worker thread executing ASR audio extraction and transcription."""

    progress = Signal(str, int)          # (stage_description, percentage)
    progress_updated = Signal(str, int)  # alias for backwards compatibility
    rate_limit_wait = Signal(str, int, int, str)     # (provider, remaining_sec, attempt, reason)
    rate_limit_cleared = Signal(str)                 # (provider)
    finished = Signal(str)               # (output_srt_path)
    failed = Signal(str)                 # (error_message)

    def __init__(
        self,
        asr_service: ASRService,
        video_path: Path | str,
        time_range: TimeRange,
        provider_id: str = "cloudflare",
        model_id: str = "@cf/openai/whisper",
        output_path: Optional[Path | str] = None,
        output_srt_path: Optional[Path | str] = None,
        parent=None
    ):
        super().__init__(parent)
        self.asr_service = asr_service
        self.video_path = video_path
        self.time_range = time_range
        self.provider_id = provider_id
        self.model_id = model_id
        self.output_srt_path = output_path or output_srt_path
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def notify_rate_limit(self, provider: str, remaining_sec: int, attempt: int, reason: str):
        self.rate_limit_wait.emit(provider, remaining_sec, attempt, reason)

    def notify_rate_limit_cleared(self, provider: str):
        self.rate_limit_cleared.emit(provider)

    def run(self):
        try:
            def on_progress(stage: str, pct: int):
                self.progress.emit(stage, pct)
                self.progress_updated.emit(stage, pct)

            out_file = self.asr_service.run_transcription(
                video_path=self.video_path,
                time_range=self.time_range,
                provider_id=self.provider_id,
                model_id=self.model_id,
                output_srt_path=self.output_srt_path,
                progress_callback=on_progress,
                cancel_token=self
            )
            if self.is_cancelled:
                self.failed.emit("Operation cancelled by user.")
            else:
                self.finished.emit(str(out_file))
        except Exception as e:
            logger.error(f"ASRWorker execution error: {e}", exc_info=True)
            self.failed.emit(str(e))
