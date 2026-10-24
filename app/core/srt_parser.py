"""
SRT parser, validator, normalizer, and serializer.
Adheres strictly to the SRT standard (HH:MM:SS,mmm --> HH:MM:SS,mmm) and UTF-8 encoding.
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import List, Tuple, Optional
from app.core.types import SubtitleCue, SubtitleFile


# Regex pattern to match timestamp lines: 00:00:00,000 --> 00:00:00,000
TIMESTAMP_PATTERN = re.compile(
    r"^(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})(.*)$"
)


class SRTParser:
    """Parser and validator for SubRip (.srt) subtitle files."""

    @staticmethod
    def parse_text(text: str, default_language: str = "en") -> SubtitleFile:
        """Parse raw SRT text into a SubtitleFile object."""
        # Strip Byte Order Mark (BOM) if present
        if text.startswith("\ufeff"):
            text = text[1:]

        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        raw_blocks = text.strip().split("\n\n")

        cues: List[SubtitleCue] = []
        cue_index = 1

        for block in raw_blocks:
            lines = [line.strip() for line in block.split("\n") if line.strip()]
            if not lines:
                continue

            # Check if first line is cue index number
            ts_line_idx = 0
            if lines[0].isdigit():
                ts_line_idx = 1

            if ts_line_idx >= len(lines):
                continue

            match = TIMESTAMP_PATTERN.match(lines[ts_line_idx])
            if not match:
                # Attempt to search within lines in case of formatting anomalies
                found = False
                for idx, line in enumerate(lines):
                    m = TIMESTAMP_PATTERN.match(line)
                    if m:
                        match = m
                        ts_line_idx = idx
                        found = True
                        break
                if not found:
                    continue

            start_str = match.group(1)
            end_str = match.group(2)
            start_ms = SubtitleCue.timestamp_to_ms(start_str)
            end_ms = SubtitleCue.timestamp_to_ms(end_str)

            # Subtitle text consists of remaining lines
            text_lines = lines[ts_line_idx + 1:]
            cue_text = "\n".join(text_lines).strip()

            cues.append(SubtitleCue(
                index=cue_index,
                start_ms=start_ms,
                end_ms=end_ms,
                text=cue_text
            ))
            cue_index += 1

        return SubtitleFile(cues=cues, language=default_language)

    @classmethod
    def parse_file(cls, file_path: Path | str, encoding: str = "utf-8") -> SubtitleFile:
        """Read and parse an SRT file from disk."""
        path = Path(file_path)
        try:
            content = path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            # Fallback to utf-8-sig or latin-1
            try:
                content = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                content = path.read_text(encoding="latin-1")
        return cls.parse_text(content)

    @staticmethod
    def write_file(subtitle_file: SubtitleFile, output_path: Path | str, overwrite: bool = False) -> Path:
        """Write SubtitleFile to disk using standard UTF-8 encoding."""
        path = Path(output_path)
        if path.exists() and not overwrite:
            raise FileExistsError(f"Target file already exists: {path}")

        path.parent.mkdir(parents=True, exist_ok=True)
        content = subtitle_file.to_srt()
        path.write_text(content, encoding="utf-8")
        return path

    @staticmethod
    def validate_cues(cues: List[SubtitleCue], time_range: Optional[Tuple[float, float]] = None) -> List[str]:
        """
        Validate subtitle cues for compliance:
        - Non-empty text
        - Positive duration (end_ms > start_ms)
        - Monotonic chronological start times
        - Check within time bounds if specified
        """
        issues = []
        if not cues:
            return ["No subtitle cues found."]

        prev_end = -1
        for i, cue in enumerate(cues, 1):
            if cue.end_ms <= cue.start_ms:
                issues.append(f"Cue #{i}: Duration non-positive ({cue.start_str} to {cue.end_str})")
            if not cue.text.strip():
                issues.append(f"Cue #{i}: Empty text")
            if cue.start_ms < prev_end:
                issues.append(f"Cue #{i}: Overlaps previous cue ({cue.start_str} < {SubtitleCue.ms_to_timestamp(prev_end)})")
            prev_end = cue.end_ms

            if time_range:
                start_s, end_s = time_range
                start_ms_bound = int(start_s * 1000)
                end_ms_bound = int(end_s * 1000)
                if cue.start_ms < start_ms_bound - 1000:
                    issues.append(f"Cue #{i}: Start time {cue.start_str} precedes requested segment start")
                if cue.end_ms > end_ms_bound + 2000:
                    issues.append(f"Cue #{i}: End time {cue.end_str} exceeds requested segment end")

        return issues
