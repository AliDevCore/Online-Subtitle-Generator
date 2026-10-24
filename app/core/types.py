"""
Core data types and structures for OnlineSub.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


class JobStatus(str, Enum):
    PENDING = "PENDING"
    EXTRACTING = "EXTRACTING"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSLATING = "TRANSLATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PipelineType(str, Enum):
    ASR = "ASR"
    TRANSLATION = "TRANSLATION"
    BATCH = "BATCH"


@dataclass
class TimeRange:
    start_seconds: float
    end_seconds: float

    @classmethod
    def from_minutes(cls, start_min: float, end_min: float) -> TimeRange:
        return cls(start_seconds=float(start_min) * 60.0, end_seconds=float(end_min) * 60.0)

    @property
    def start_minutes(self) -> float:
        return self.start_seconds / 60.0

    @property
    def end_minutes(self) -> float:
        return self.end_seconds / 60.0

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.end_seconds - self.start_seconds)

    def clamp_to_duration(self, video_duration_seconds: Optional[float]) -> TimeRange:
        """Return a new TimeRange clamped to the media file duration."""
        if video_duration_seconds is None or video_duration_seconds <= 0:
            return self
        new_start = max(0.0, min(self.start_seconds, video_duration_seconds))
        new_end = max(new_start + 0.1, min(self.end_seconds, video_duration_seconds))
        return TimeRange(start_seconds=new_start, end_seconds=new_end)

    def validate(self, video_duration_seconds: Optional[float] = None) -> tuple[bool, str]:
        if self.start_seconds < 0:
            return False, "Start time cannot be negative."
        if self.end_seconds <= self.start_seconds:
            return False, f"End time ({self.end_seconds / 60.0:.2f}m) must be greater than start time ({self.start_seconds / 60.0:.2f}m)."
        if video_duration_seconds is not None and video_duration_seconds > 0:
            if self.start_seconds >= video_duration_seconds:
                return False, f"Start time ({self.start_seconds / 60.0:.2f}m) exceeds video duration ({video_duration_seconds / 60.0:.2f}m)."
            # If user selected up to the ceil rounded minute (e.g. 25m for 24.2m video),
            # clamp gracefully instead of rejecting!
            if self.end_seconds > video_duration_seconds + 60.0:
                return False, f"End time ({self.end_seconds / 60.0:.2f}m) exceeds video duration ({video_duration_seconds / 60.0:.2f}m)."
            elif self.end_seconds > video_duration_seconds:
                self.end_seconds = video_duration_seconds
        return True, ""


@dataclass
class SubtitleCue:
    index: int
    start_ms: int
    end_ms: int
    text: str

    @staticmethod
    def ms_to_timestamp(ms: int) -> str:
        if ms < 0:
            ms = 0
        total_seconds = ms // 1000
        milliseconds = ms % 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    @staticmethod
    def timestamp_to_ms(ts: str) -> int:
        ts = ts.strip().replace('.', ',')
        parts = ts.split(':')
        if len(parts) == 3:
            h = int(parts[0])
            m = int(parts[1])
            sec_parts = parts[2].split(',')
            s = int(sec_parts[0])
            ms = int(sec_parts[1]) if len(sec_parts) > 1 else 0
            return (h * 3600 + m * 60 + s) * 1000 + ms
        elif len(parts) == 2:
            m = int(parts[0])
            sec_parts = parts[1].split(',')
            s = int(sec_parts[0])
            ms = int(sec_parts[1]) if len(sec_parts) > 1 else 0
            return (m * 60 + s) * 1000 + ms
        return 0

    @property
    def start_str(self) -> str:
        return self.ms_to_timestamp(self.start_ms)

    @property
    def end_str(self) -> str:
        return self.ms_to_timestamp(self.end_ms)

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)

    def shift(self, offset_ms: int) -> SubtitleCue:
        return SubtitleCue(
            index=self.index,
            start_ms=max(0, self.start_ms + offset_ms),
            end_ms=max(0, self.end_ms + offset_ms),
            text=self.text
        )

    def to_srt_block(self) -> str:
        return f"{self.index}\n{self.start_str} --> {self.end_str}\n{self.text.strip()}\n"


@dataclass
class SubtitleFile:
    cues: List[SubtitleCue] = field(default_factory=list)
    language: str = "en"

    def to_srt(self) -> str:
        blocks = []
        for i, cue in enumerate(self.cues, 1):
            cue.index = i
            blocks.append(cue.to_srt_block())
        return "\n".join(blocks).strip() + "\n"

    def shift_all(self, offset_ms: int) -> SubtitleFile:
        return SubtitleFile(
            cues=[cue.shift(offset_ms) for cue in self.cues],
            language=self.language
        )

    def validate(self) -> tuple[bool, List[str]]:
        errors = []
        if not self.cues:
            return False, ["Subtitle file contains no cues."]
        prev_end = -1
        for i, cue in enumerate(self.cues, 1):
            if cue.end_ms <= cue.start_ms:
                errors.append(f"Cue #{i}: end time ({cue.end_str}) is not after start time ({cue.start_str}).")
            if not cue.text.strip():
                errors.append(f"Cue #{i} contains empty text.")
            if cue.start_ms < prev_end:
                # Overlap warning / issue
                pass
            prev_end = cue.end_ms
        return len(errors) == 0, errors


@dataclass
class AudioChunk:
    index: int
    file_path: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    status: str = "PENDING"
    raw_response: str = ""
    cues: List[SubtitleCue] = field(default_factory=list)


@dataclass
class ProviderInfo:
    provider_id: str
    display_name: str
    model_id: str
    model_display_name: str
    pipeline: str  # "ASR" or "TRANSLATION"
    is_free: bool
    pricing_desc: str
    free_tier_desc: str
    supports_timestamps: bool
    max_duration_sec: int
    requires_key: bool
    doc_url: str
    verification_date: str = "2026-10"


@dataclass
class PerformanceSettings:
    cpu_usage_target: int = 100       # 25, 50, 75, 100 (%)
    process_priority: str = "Normal"  # "Below Normal", "Normal", "Above Normal"
    cpu_threads: str = "Automatic"    # "Automatic" or string integer
    ram_limit: str = "Automatic"      # "Automatic" or string integer in MB
    affinity_cpus: Optional[List[int]] = None  # None = all CPUs

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_usage_target": self.cpu_usage_target,
            "process_priority": self.process_priority,
            "cpu_threads": self.cpu_threads,
            "ram_limit": self.ram_limit,
            "affinity_cpus": self.affinity_cpus,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PerformanceSettings:
        return cls(
            cpu_usage_target=data.get("cpu_usage_target", 100),
            process_priority=data.get("process_priority", "Normal"),
            cpu_threads=data.get("cpu_threads", "Automatic"),
            ram_limit=data.get("ram_limit", "Automatic"),
            affinity_cpus=data.get("affinity_cpus", None),
        )


@dataclass
class SystemInfo:
    cpu_name: str
    physical_cores: int
    logical_cores: int
    total_ram_gb: float
    available_ram_gb: float
    has_gpu: bool = False
    gpu_name: str = "None"


@dataclass
class ChunkingSettings:
    """Configurable audio chunking settings for Cloudflare Workers AI ASR."""
    enabled: bool = True
    cloudflare_minutes: float = 5.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "cloudflare_minutes": self.cloudflare_minutes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ChunkingSettings:
        return cls(
            enabled=data.get("enabled", True),
            cloudflare_minutes=float(data.get("cloudflare_minutes", 5.0)),
        )

    def get_chunk_duration_seconds(self, provider_id: str = "cloudflare") -> Optional[float]:
        """
        Return chunk duration in seconds for Cloudflare.
        If chunking is disabled, returns None (single-request mode).
        """
        if not self.enabled:
            return None
        return max(0.5, float(self.cloudflare_minutes)) * 60.0

