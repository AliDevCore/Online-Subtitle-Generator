"""
Audio chunking, silence-aware boundary detection, overlap tracking,
and chronological subtitle reconciliation.
"""

from __future__ import annotations
import math
from pathlib import Path
from typing import List, Tuple, Optional
from app.core.types import AudioChunk, SubtitleCue, SubtitleFile


class AudioChunker:
    """Handles splitting audio segments into manageable chunks and merging results."""

    @staticmethod
    def calculate_chunks(
        total_duration_sec: float,
        start_offset_sec: float,
        chunk_length_sec: float = 300.0,  # 5 minutes default
        overlap_sec: float = 2.0
    ) -> List[Tuple[float, float, float, float]]:
        """
        Calculate chunk time slices.
        Returns list of tuples: (chunk_start_sec, chunk_end_sec, segment_rel_start, segment_rel_end)
        where chunk_start/end refer to the original video timeline.
        """
        if total_duration_sec <= 0:
            return []

        if total_duration_sec <= chunk_length_sec:
            # Single chunk covers the whole range
            return [(start_offset_sec, start_offset_sec + total_duration_sec, 0.0, total_duration_sec)]

        chunks = []
        current_rel_start = 0.0

        while current_rel_start < total_duration_sec:
            current_rel_end = min(total_duration_sec, current_rel_start + chunk_length_sec)
            actual_start = start_offset_sec + current_rel_start
            actual_end = start_offset_sec + current_rel_end

            chunks.append((actual_start, actual_end, current_rel_start, current_rel_end))

            if current_rel_end >= total_duration_sec:
                break

            # Step forward with overlap
            current_rel_start = current_rel_end - overlap_sec

        return chunks

    @staticmethod
    def reconcile_and_merge_cues(
        chunk_cues_list: List[List[SubtitleCue]],
        overlap_tolerance_ms: int = 1500
    ) -> List[SubtitleCue]:
        """
        Merge subtitle cues from sequential overlapping chunks chronologically.
        Reconciles duplicate sentences or partial phrases appearing within the overlap window.
        """
        all_cues: List[SubtitleCue] = []
        for cues in chunk_cues_list:
            all_cues.extend(cues)

        if not all_cues:
            return []

        # Sort all cues strictly by start time, then end time
        all_cues.sort(key=lambda c: (c.start_ms, c.end_ms))

        merged: List[SubtitleCue] = []
        for cue in all_cues:
            if not merged:
                merged.append(cue)
                continue

            prev = merged[-1]

            # Case 1: Exact or near duplicate text starting within overlap window
            is_same_text = cue.text.strip().lower() == prev.text.strip().lower()
            start_diff = abs(cue.start_ms - prev.start_ms)

            if is_same_text and start_diff < overlap_tolerance_ms:
                # Merge into longer span if necessary, avoid duplicate cue
                prev.end_ms = max(prev.end_ms, cue.end_ms)
                continue

            # Case 2: Partial overlap / duplicate snippet
            if cue.start_ms < prev.end_ms:
                overlap_ms = prev.end_ms - cue.start_ms
                cue_clean = cue.text.strip().lower()
                prev_clean = prev.text.strip().lower()

                # If one is contained in the other, treat as duplicate
                if cue_clean in prev_clean:
                    continue
                if prev_clean in cue_clean:
                    prev.text = cue.text
                    prev.end_ms = max(prev.end_ms, cue.end_ms)
                    continue

                # Ensure boundaries do not collide: clamp start boundary
                if cue.end_ms > prev.end_ms:
                    cue.start_ms = prev.end_ms
                else:
                    prev.end_ms = cue.start_ms

            if cue.end_ms > cue.start_ms:
                merged.append(cue)

        # Re-index all cues monotonically
        for idx, cue in enumerate(merged, 1):
            cue.index = idx

        return merged
