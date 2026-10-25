"""
Audio chunking, silence-aware boundary detection, overlap tracking,
and chronological subtitle reconciliation.
"""

from __future__ import annotations
import math
import re
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
            # If the remaining tail after this chunk would be tiny (< 20s), absorb it into this chunk
            if total_duration_sec - current_rel_end < 20.0:
                current_rel_end = total_duration_sec

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
        overlap_tolerance_ms: int = 2000
    ) -> List[SubtitleCue]:
        """
        Merge subtitle cues from sequential overlapping chunks chronologically.
        Reconciles duplicate sentences or partial phrases appearing within the overlap window.
        Preserves all natural dialogues and short conversational responses (e.g. 'So?', 'Sure.', 'No.', 'Why?').
        """
        all_cues: List[SubtitleCue] = []
        from app.core.subtitle_segmenter import is_hallucination_cue
        for cues in chunk_cues_list:
            for c in cues:
                if not is_hallucination_cue(c.text):
                    all_cues.append(c)

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

            clean_cue = re.sub(r"[^\w\s]", "", cue.text.strip().lower())
            clean_prev = re.sub(r"[^\w\s]", "", prev.text.strip().lower())
            start_diff = abs(cue.start_ms - prev.start_ms)

            # Case 1: Exact or near-identical duplicate text starting within overlap window
            is_same_text = (clean_cue == clean_prev) and bool(clean_cue)
            if is_same_text and start_diff < overlap_tolerance_ms:
                # Merge into longer span, keep version with richer text/punctuation
                prev.end_ms = max(prev.end_ms, cue.end_ms)
                if len(cue.text.strip()) > len(prev.text.strip()):
                    prev.text = cue.text
                continue

            # Case 2: True temporal overlap at chunk boundary (cue.start_ms < prev.end_ms)
            # Only applies when cues actually collide in time, NEVER to separate consecutive cues!
            if cue.start_ms < prev.end_ms:
                # If they start virtually simultaneously (< 1000ms apart) and one is an exact full subphrase of the other:
                if start_diff < 1000 and clean_cue and clean_prev:
                    w_cue = clean_cue.split()
                    w_prev = clean_prev.split()
                    # Boundary truncation: e.g. "hello ladies and" vs "hello ladies and gentlemen"
                    if " ".join(w_cue) in " ".join(w_prev):
                        prev.end_ms = max(prev.end_ms, cue.end_ms)
                        continue
                    elif " ".join(w_prev) in " ".join(w_cue):
                        prev.text = cue.text
                        prev.end_ms = max(prev.end_ms, cue.end_ms)
                        continue

                # Suffix-prefix word overlap reconciliation across chunk boundaries
                # e.g. "and then we went to the store" + "we went to the store and bought milk"
                w_prev_raw = prev.text.split()
                w_cue_raw = cue.text.split()
                merged_phrase = None
                for k in range(min(len(w_prev_raw), len(w_cue_raw)), 1, -1):
                    if [w.lower().strip(".,!?:;\"'") for w in w_prev_raw[-k:]] == [w.lower().strip(".,!?:;\"'") for w in w_cue_raw[:k]]:
                        merged_phrase = " ".join(w_prev_raw + w_cue_raw[k:])
                        break

                if merged_phrase:
                    prev.text = merged_phrase
                    prev.end_ms = max(prev.end_ms, cue.end_ms)
                    continue

                # Non-duplicate overlapping boundary: clamp timestamps so they do not collide
                if cue.end_ms > prev.end_ms:
                    cue.start_ms = prev.end_ms
                else:
                    prev.end_ms = cue.start_ms

            if cue.end_ms > cue.start_ms:
                merged.append(cue)

        # Filter out any hallucinated cues and re-index all cues monotonically
        clean_merged = [c for c in merged if not is_hallucination_cue(c.text)]
        for idx, cue in enumerate(clean_merged, 1):
            cue.index = idx

        return clean_merged
