"""
Local Faster-Whisper ASR provider for offline speech recognition on Windows CPU.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional, Tuple, Any, List
from app.core.config import VERIFIED_ASR_PROVIDERS
from app.core.types import SubtitleFile, SubtitleCue, ProviderInfo
from app.providers.base import BaseASRProvider

logger = logging.getLogger("OnlineSub.LocalWhisper")


class LocalWhisperASRProvider(BaseASRProvider):
    """Local offline speech recognition using faster-whisper CTranslate2 engine."""

    # Approximate RAM requirements for model sizes in GB
    MODEL_RAM_ESTIMATES = {
        "tiny": 0.5,
        "base": 1.0,
        "small": 2.0,
        "medium": 5.0,
        "large-v3": 10.0,
    }

    def __init__(self, model_id: str = "base", api_key: Optional[str] = None, **kwargs: Any):
        super().__init__(model_id, api_key, **kwargs)
        self.cpu_threads = kwargs.get("cpu_threads", 4)
        self._model_instance = None

    def get_info(self) -> ProviderInfo:
        for p in VERIFIED_ASR_PROVIDERS:
            if p.provider_id == "local_whisper" and p.model_id == self.model_id:
                return p
        return ProviderInfo(
            provider_id="local_whisper",
            display_name="Local Faster-Whisper (Offline CPU)",
            model_id=self.model_id,
            model_display_name=f"Local Whisper ({self.model_id})",
            pipeline="ASR",
            is_free=True,
            pricing_desc="100% Free & Offline (Local CPU execution)",
            free_tier_desc="Runs entirely on your local machine; no API key needed",
            supports_timestamps=True,
            max_duration_sec=7200,
            requires_key=False,
            doc_url="https://github.com/SYSTRAN/faster-whisper",
        )

    def validate_credentials(self) -> Tuple[bool, str]:
        # Local model does not require an API key
        try:
            import faster_whisper
            return True, "faster-whisper runtime available."
        except ImportError:
            return False, "faster-whisper is not installed. Install with 'pip install faster-whisper'."

    def _get_model(self):
        if self._model_instance is None:
            from faster_whisper import WhisperModel
            threads = max(1, int(self.cpu_threads))
            logger.info(f"Loading local faster-whisper model '{self.model_id}' (device=cpu, threads={threads}, compute_type=int8)...")
            self._model_instance = WhisperModel(
                self.model_id,
                device="cpu",
                compute_type="int8",
                cpu_threads=threads
            )
        return self._model_instance

    def transcribe(
        self,
        audio_path: Path,
        start_offset_seconds: float,
        duration_seconds: float,
        cancel_token: Optional[Any] = None
    ) -> SubtitleFile:
        valid, msg = self.validate_credentials()
        if not valid:
            raise RuntimeError(msg)

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        model = self._get_model()

        logger.info(f"Transcribing audio with local Whisper model '{self.model_id}'...")
        # vad_filter=True detects and filters out non-speech silence automatically
        segments, info = model.transcribe(
            str(audio_path),
            beam_size=5,
            language="en",
            task="transcribe",
            vad_filter=True
        )

        cues: List[SubtitleCue] = []
        cue_idx = 1
        offset_ms = int(start_offset_seconds * 1000)

        for segment in segments:
            if cancel_token and getattr(cancel_token, "is_cancelled", False):
                raise RuntimeError("Local transcription cancelled by user.")

            text = segment.text.strip()
            if not text:
                continue

            # start and end are in seconds relative to chunk audio
            start_ms = offset_ms + int(segment.start * 1000)
            end_ms = offset_ms + int(segment.end * 1000)

            cues.append(SubtitleCue(
                index=cue_idx,
                start_ms=start_ms,
                end_ms=end_ms,
                text=text
            ))
            cue_idx += 1

        return SubtitleFile(cues=cues, language="en")
