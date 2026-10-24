"""
Batch processing service for handling multiple video files in Online Subtitle Generator.
Ensures failure isolation, queue management, and resumable execution.
"""

from __future__ import annotations
import logging
import uuid
from pathlib import Path
from typing import List, Dict, Optional, Callable, Any

from app.core.database import Database
from app.core.types import TimeRange, JobStatus
from app.services.asr_service import ASRService

logger = logging.getLogger("OnlineSubtitleGenerator.BatchService")

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts", ".wmv", ".m4v"}


class BatchVideoItem:
    """Represents a video file job item in the ASR batch queue."""

    def __init__(
        self,
        video_path: Path | str,
        start_min: float = 0.0,
        end_min: Optional[float] = None,
        duration_seconds: float = 0.0
    ):
        self.item_id = uuid.uuid4().hex[:8]
        self.video_path = Path(video_path)
        self.start_min = float(start_min)
        self.end_min = float(end_min) if end_min is not None else None
        self.duration_seconds = float(duration_seconds)
        self.status: JobStatus = JobStatus.PENDING
        self.error_msg: Optional[str] = None
        self.generated_en_srt: Optional[Path] = None

    @property
    def name(self) -> str:
        return self.video_path.name

    @property
    def duration_str(self) -> str:
        if self.duration_seconds <= 0:
            return "Unknown"
        tot = int(self.duration_seconds)
        h = tot // 3600
        m = (tot % 3600) // 60
        s = tot % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "video_path": str(self.video_path),
            "start_min": self.start_min,
            "end_min": self.end_min,
            "duration_seconds": self.duration_seconds,
            "status": self.status.value,
            "error_msg": self.error_msg,
            "generated_en_srt": str(self.generated_en_srt) if self.generated_en_srt else None,
        }


# Backwards compatibility alias
BatchItem = BatchVideoItem


class BatchService:
    """Coordinates batch queueing and resilient execution for video files."""

    def __init__(
        self,
        asr_service: ASRService,
        translation_service: Any = None,
        database: Optional[Database] = None
    ):
        self.asr = asr_service
        self.db = database
        self.video_queue: List[BatchVideoItem] = []

    def clear_video_queue(self) -> None:
        self.video_queue.clear()

    clear_queue = clear_video_queue

    def add_video_file(
        self,
        video_path: Path | str,
        start_min: float = 0.0,
        end_min: Optional[float] = None
    ) -> BatchVideoItem:
        path = Path(video_path)
        dur = 0.0
        try:
            probe = self.asr.ffmpeg.probe_media(path)
            dur = probe["duration_seconds"]
        except Exception:
            pass

        item = BatchVideoItem(
            video_path=path,
            start_min=start_min,
            end_min=end_min,
            duration_seconds=dur
        )
        self.video_queue.append(item)
        return item

    add_video = add_video_file

    def scan_and_add_videos(
        self,
        folder_path: Path | str,
        recursive: bool = False
    ) -> List[BatchVideoItem]:
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            raise NotADirectoryError(f"Directory not found: {folder}")

        pattern = "**/*" if recursive else "*"
        found_items = []
        for p in folder.glob(pattern):
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
                if any(it.video_path.resolve() == p.resolve() for it in self.video_queue):
                    continue
                item = self.add_video_file(p)
                found_items.append(item)

        return found_items

    scan_folder = scan_and_add_videos

    def run_video_batch(
        self,
        asr_provider: str = "cloudflare",
        asr_model: str = "@cf/openai/whisper",
        item_callback: Optional[Callable[[BatchVideoItem, int, int], None]] = None,
        cancel_token: Optional[Any] = None,
        **kwargs: Any
    ) -> List[BatchVideoItem]:
        """Process all video items sequentially with failure isolation."""
        total = len(self.video_queue)
        logger.info(f"Starting Video ASR batch of {total} items...")

        for idx, item in enumerate(self.video_queue, 1):
            if cancel_token and getattr(cancel_token, "is_cancelled", False):
                logger.info("Video batch execution cancelled by user.")
                item.status = JobStatus.CANCELLED
                break

            if item.status == JobStatus.COMPLETED:
                continue

            try:
                if item_callback:
                    item_callback(item, idx, total)

                total_duration = item.duration_seconds
                if total_duration <= 0:
                    probe_res = self.asr.ffmpeg.probe_media(item.video_path)
                    total_duration = probe_res["duration_seconds"]
                    item.duration_seconds = total_duration

                end_sec = min(item.end_min * 60.0, total_duration) if (item.end_min and item.end_min > 0) else total_duration

                time_range = TimeRange(
                    start_seconds=item.start_min * 60.0,
                    end_seconds=end_sec
                )

                item.status = JobStatus.TRANSCRIBING
                en_srt = self.asr.run_transcription(
                    video_path=item.video_path,
                    time_range=time_range,
                    provider_id=asr_provider,
                    model_id=asr_model,
                    cancel_token=cancel_token
                )
                item.generated_en_srt = en_srt
                item.status = JobStatus.COMPLETED

            except Exception as e:
                logger.error(f"Failed to process video batch item {item.video_path.name}: {e}")
                item.status = JobStatus.FAILED
                item.error_msg = str(e)

            if item_callback:
                item_callback(item, idx, total)

        return self.video_queue

    run_batch = run_video_batch
