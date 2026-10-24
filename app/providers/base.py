"""
Base abstract classes and interfaces for ASR and Translation providers.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Tuple, Any
from app.core.types import SubtitleFile, ProviderInfo


class BaseASRProvider(ABC):
    """Abstract interface for Speech-to-Text / Automatic Speech Recognition providers."""

    def __init__(self, model_id: str, api_key: Optional[str] = None, **kwargs: Any):
        self.model_id = model_id
        self.api_key = api_key
        self.extra_config = kwargs

    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        start_offset_seconds: float,
        duration_seconds: float,
        cancel_token: Optional[Any] = None
    ) -> SubtitleFile:
        """
        Transcribe the audio file and return a SubtitleFile with timestamps aligned to original timeline.
        start_offset_seconds must be added to chunk timestamps so the final SRT timestamps
        match the original video playback timeline!
        """
        pass

    @abstractmethod
    def validate_credentials(self) -> Tuple[bool, str]:
        """Validate API key or local model prerequisites."""
        pass

    @abstractmethod
    def get_info(self) -> ProviderInfo:
        """Return provider and model metadata."""
        pass


class BaseTranslationProvider(ABC):
    """Abstract interface for Machine Translation providers."""

    def __init__(self, model_id: str, api_key: Optional[str] = None, **kwargs: Any):
        self.model_id = model_id
        self.api_key = api_key
        self.extra_config = kwargs

    @abstractmethod
    def translate(
        self,
        subtitle_file: SubtitleFile,
        target_language: str = "fa",
        cancel_token: Optional[Any] = None
    ) -> SubtitleFile:
        """
        Translate English SubtitleFile into target language (default Persian / fa).
        MUST preserve cue numbering, timestamps, ordering, and structure.
        """
        pass

    @abstractmethod
    def validate_credentials(self) -> Tuple[bool, str]:
        """Validate API key or local model prerequisites."""
        pass

    @abstractmethod
    def get_info(self) -> ProviderInfo:
        """Return provider and model metadata."""
        pass
