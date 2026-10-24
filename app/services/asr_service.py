"""
Pipeline A: Automatic Speech Recognition (ASR) service.
Coordinates video probing, audio segment extraction, chunking, transcription,
chronological merging, offset preservation, and SRT persistence.
"""

from __future__ import annotations
import logging
import uuid
from pathlib import Path
from typing import Optional, Callable, Any, List

from app.core.audio_chunker import AudioChunker
from app.core.config import CACHE_DIR
from app.core.database import Database
from app.core.resource_controller import ResourceController
from app.core.srt_parser import SRTParser
from app.core.types import TimeRange, SubtitleFile, SubtitleCue, AudioChunk, JobStatus
from app.providers import get_asr_provider
from app.services.ffmpeg_service import FFmpegService

logger = logging.getLogger("OnlineSub.ASRService")


class ASRService:
    """Orchestrates end-to-end English subtitle generation from local video."""

    def __init__(
        self,
        database: Optional[Database] = None,
        ffmpeg_service: Optional[FFmpegService] = None,
        resource_controller: Optional[ResourceController] = None
    ):
        self.db = database or Database()
        self.ffmpeg = ffmpeg_service or FFmpegService()
        self.resource_ctrl = resource_controller or ResourceController()

    @staticmethod
    def get_default_output_path(video_path: Path | str, suffix: str = ".en.srt", time_range: Optional[TimeRange] = None) -> Path:
        """Compute collision-safe output path beside source video."""
        vid = Path(video_path)
        base_name = vid.stem
        # For partial transcription, optionally include range in filename if non-zero start
        if time_range and (time_range.start_seconds > 0):
            st_m = int(time_range.start_minutes)
            end_m = int(time_range.end_minutes)
            name = f"{base_name}_{st_m}m-{end_m}m{suffix}"
        else:
            name = f"{base_name}{suffix}"

        candidate = vid.parent / name
        if not candidate.exists():
            return candidate

        # Collision-safe suffixing
        counter = 1
        while candidate.exists():
            clean_stem = name[:-len(suffix)]
            candidate = vid.parent / f"{clean_stem}_{counter}{suffix}"
            counter += 1
        return candidate

    def run_transcription(
        self,
        video_path: Path | str,
        time_range: TimeRange,
        provider_id: str,
        model_id: str,
        output_srt_path: Optional[Path | str] = None,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        cancel_token: Optional[Any] = None
    ) -> Path:
        """
        Execute full ASR workflow.
        Returns final path of validated English SRT file.
        """
        video = Path(video_path)
        if not video.exists():
            raise FileNotFoundError(f"Source video not found: {video}")

        job_id = job_id or uuid.uuid4().hex[:12]
        time_range_tuple = (time_range.start_seconds, time_range.end_seconds)

        if output_srt_path is None:
            output_srt_path = self.get_default_output_path(video, ".en.srt", time_range)
        output_path = Path(output_srt_path)

        # 1. Register job in database
        self.db.create_job(
            job_id=job_id,
            video_path=str(video),
            pipeline="ASR",
            start_seconds=time_range.start_seconds,
            end_seconds=time_range.end_seconds,
            asr_provider=provider_id,
            asr_model=model_id,
            output_srt_path=str(output_path)
        )

        def report(stage: str, percent: int):
            logger.info(f"[{percent}%] {stage}")
            if progress_callback:
                progress_callback(stage, percent)

        report("Probing video media streams...", 5)
        media_info = self.ffmpeg.probe_media(video)
        if not media_info["has_audio"]:
            self.db.update_job_status(job_id, JobStatus.FAILED, "No audio stream detected in media file.")
            raise RuntimeError("Selected video contains no audio stream.")

        # Clamp and validate time range against media duration
        time_range = time_range.clamp_to_duration(media_info["duration_seconds"])
        valid, err = time_range.validate(media_info["duration_seconds"])
        if not valid:
            self.db.update_job_status(job_id, JobStatus.FAILED, err)
            raise ValueError(err)

        # 2. Instantiate ASR Provider & determine chunking requirement
        provider = get_asr_provider(
            provider_id=provider_id,
            model_id=model_id,
            cpu_threads=self.resource_ctrl.get_effective_threads()
        )
        model_info = provider.get_info()

        from app.core.config import load_chunking_settings
        chunking_cfg = load_chunking_settings()
        chunk_seconds = chunking_cfg.get_chunk_duration_seconds(provider_id)
        segment_duration = time_range.duration_seconds

        chunk_cues_collection: List[List[SubtitleCue]] = []
        extracted_audio: Optional[Path] = None

        try:
            if chunk_seconds is None or segment_duration <= chunk_seconds:
                # Single-request processing (no chunking or within configured limit)
                report(f"Extracting audio segment ({time_range.start_minutes:.2f}m to {time_range.end_minutes:.2f}m)...", 15)
                self.db.update_job_status(job_id, JobStatus.EXTRACTING)

                self.resource_ctrl.throttle_if_needed(is_local_cpu_intensive=True)
                extracted_audio = self.ffmpeg.extract_audio_segment(
                    video_path=video,
                    start_seconds=time_range.start_seconds,
                    duration_seconds=time_range.duration_seconds,
                    output_format="mp3",
                    bitrate="64k",
                    sample_rate=16000,
                    channels=1,
                    cancel_token=cancel_token
                )
                self.db.update_job_status(job_id, JobStatus.TRANSCRIBING, extracted_audio_path=str(extracted_audio))

                report(f"Transcribing audio with {model_info.display_name}...", 40)
                
                sub_file = provider.transcribe(
                    audio_path=extracted_audio,
                    start_offset_seconds=time_range.start_seconds,
                    duration_seconds=segment_duration,
                    cancel_token=cancel_token
                )
                chunk_cues_collection.append(sub_file.cues)
                report("Transcription completed.", 85)
            else:
                # Chunked processing using user-configured chunk duration for this provider
                chunk_length = float(chunk_seconds)
                chunk_specs = AudioChunker.calculate_chunks(
                    total_duration_sec=segment_duration,
                    start_offset_sec=time_range.start_seconds,
                    chunk_length_sec=chunk_length,
                    overlap_sec=2.0
                )

                total_chunks = len(chunk_specs)
                chunk_min_str = f"{chunk_length / 60.0:.1f}".rstrip("0").rstrip(".")
                report(f"Splitting into {total_chunks} audio chunks (~{chunk_min_str} min each)...", 15)
                self.db.update_job_status(job_id, JobStatus.TRANSCRIBING)

                for idx, (actual_st, actual_end, rel_st, rel_end) in enumerate(chunk_specs, 1):
                    if cancel_token and getattr(cancel_token, "is_cancelled", False):
                        raise RuntimeError("Operation cancelled by user.")

                    chunk_dur = rel_end - rel_st
                    percent = 15 + int((idx / total_chunks) * 70)
                    report(f"Transcribing chunk {idx}/{total_chunks} [{actual_st/60.0:.2f}m - {actual_end/60.0:.2f}m]...", percent)

                    # Extract chunk audio
                    chunk_audio = self.ffmpeg.extract_audio_segment(
                        video_path=video,
                        start_seconds=actual_st,
                        duration_seconds=chunk_dur,
                        output_format="mp3",
                        bitrate="64k",
                        sample_rate=16000,
                        channels=1,
                        cancel_token=cancel_token
                    )

                    chunk_obj = AudioChunk(
                        index=idx,
                        file_path=str(chunk_audio),
                        start_seconds=actual_st,
                        end_seconds=actual_end,
                        duration_seconds=chunk_dur,
                        status="TRANSCRIBING"
                    )

                    chunk_sub = provider.transcribe(
                        audio_path=chunk_audio,
                        start_offset_seconds=actual_st,
                        duration_seconds=chunk_dur,
                        cancel_token=cancel_token
                    )

                    chunk_obj.status = "COMPLETED"
                    chunk_obj.cues = chunk_sub.cues
                    self.db.save_chunk(job_id, chunk_obj)
                    chunk_cues_collection.append(chunk_sub.cues)

                    # Cleanup chunk temp audio file
                    try:
                        if chunk_audio.exists():
                            chunk_audio.unlink()
                    except Exception:
                        pass

            # 5. Merge and reconcile overlapping chunks
            report("Merging cues and reconciling timestamps...", 90)
            final_cues = AudioChunker.reconcile_and_merge_cues(chunk_cues_collection)
            final_sub = SubtitleFile(cues=final_cues, language="en")

            # 6. Validate final SRT
            issues = SRTParser.validate_cues(final_sub.cues, time_range_tuple)
            if issues:
                logger.warning(f"SRT validation notes: {'; '.join(issues)}")

            # 7. Write to disk (with fallback to user Documents if directory is write-protected)
            report(f"Writing final English SRT to {output_path.name}...", 95)
            try:
                SRTParser.write_file(final_sub, output_path, overwrite=True)
            except (PermissionError, OSError) as write_err:
                fallback_dir = Path.home() / "Documents" / "Online Subtitle Generator"
                fallback_dir.mkdir(parents=True, exist_ok=True)
                output_path = fallback_dir / output_path.name
                logger.warning(f"Output directory not writable ({write_err}); saved to fallback: {output_path}")
                SRTParser.write_file(final_sub, output_path, overwrite=True)

            self.db.update_job_status(job_id, JobStatus.COMPLETED, output_srt_path=str(output_path))
            report("English SRT generated successfully!", 100)
            return output_path

        except Exception as e:
            is_cancel = (cancel_token and getattr(cancel_token, "is_cancelled", False)) or ("cancel" in str(e).lower())
            new_status = JobStatus.CANCELLED if is_cancel else JobStatus.FAILED
            self.db.update_job_status(job_id, new_status, str(e))
            raise

        finally:
            try:
                if extracted_audio and Path(extracted_audio).exists():
                    Path(extracted_audio).unlink()
            except Exception:
                pass
