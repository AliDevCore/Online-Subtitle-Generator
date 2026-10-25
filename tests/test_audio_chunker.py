"""
Tests for AudioChunker time slicing and chronological cue merging.
"""

from app.core.audio_chunker import AudioChunker
from app.core.types import SubtitleCue


def test_calculate_chunks_short_duration():
    # If duration is 120s and chunk_length is 300s -> single chunk
    chunks = AudioChunker.calculate_chunks(
        total_duration_sec=120.0,
        start_offset_sec=60.0,
        chunk_length_sec=300.0
    )
    assert len(chunks) == 1
    actual_st, actual_end, rel_st, rel_end = chunks[0]
    assert actual_st == 60.0
    assert actual_end == 180.0
    assert rel_st == 0.0
    assert rel_end == 120.0


def test_calculate_chunks_multi_segments():
    # 700s total duration, 300s chunk length, 2s overlap
    chunks = AudioChunker.calculate_chunks(
        total_duration_sec=700.0,
        start_offset_sec=0.0,
        chunk_length_sec=300.0,
        overlap_sec=2.0
    )
    assert len(chunks) >= 3
    # Chunk 1: [0, 300]
    # Chunk 2: [298, 598]
    # Chunk 3: [596, 700]
    assert chunks[0][0] == 0.0
    assert chunks[0][1] == 300.0
    assert chunks[1][0] == 298.0


def test_reconcile_and_merge_overlapping_cues():
    chunk1_cues = [
        SubtitleCue(1, 1000, 3000, "Hello world"),
        SubtitleCue(2, 3500, 5000, "Boundary sentence")
    ]
    chunk2_cues = [
        # Duplicate of boundary sentence due to overlap
        SubtitleCue(1, 3520, 5010, "Boundary sentence"),
        SubtitleCue(2, 6000, 8000, "Next sentence")
    ]

    merged = AudioChunker.reconcile_and_merge_cues([chunk1_cues, chunk2_cues])
    assert len(merged) == 3
    assert merged[0].text == "Hello world"
    assert merged[1].text == "Boundary sentence"
    assert merged[2].text == "Next sentence"
    assert merged[0].index == 1
    assert merged[1].index == 2
    assert merged[2].index == 3


def test_reconcile_phrase_overlap_across_chunks():
    """Verify suffix-prefix word overlap merging across chunk boundaries."""
    chunk1_cues = [
        SubtitleCue(1, 1000, 3000, "First cue"),
        SubtitleCue(2, 298000, 300000, "and then we went to the store")
    ]
    chunk2_cues = [
        SubtitleCue(1, 299500, 302000, "we went to the store and bought milk"),
        SubtitleCue(2, 305000, 307000, "Last cue")
    ]

    merged = AudioChunker.reconcile_and_merge_cues([chunk1_cues, chunk2_cues])
    assert len(merged) == 3
    assert merged[0].text == "First cue"
    assert merged[1].text == "and then we went to the store and bought milk"
    assert merged[2].text == "Last cue"


def test_preserve_short_dialogue_responses():
    """Verify that short natural responses (No, So, Sure, Me) are NEVER dropped."""
    dialogue_cues = [
        SubtitleCue(1, 1000, 3000, "I know that."),
        SubtitleCue(2, 3200, 4000, "No."),
        SubtitleCue(3, 4200, 6000, "She is a good person."),
        SubtitleCue(4, 6300, 7000, "So?"),
        SubtitleCue(5, 7200, 9000, "Are you sure?"),
        SubtitleCue(6, 9200, 10000, "Sure.")
    ]
    merged = AudioChunker.reconcile_and_merge_cues([dialogue_cues])
    assert len(merged) == 6
    assert [c.text for c in merged] == [
        "I know that.",
        "No.",
        "She is a good person.",
        "So?",
        "Are you sure?",
        "Sure."
    ]


def test_chunk_boundary_truncation_merge():
    """Verify that boundary partial sentence truncation merges cleanly."""
    chunk1_cues = [
        SubtitleCue(1, 298000, 299500, "Hello ladies and")
    ]
    chunk2_cues = [
        SubtitleCue(1, 298050, 301000, "Hello ladies and gentlemen"),
        SubtitleCue(2, 302000, 304000, "Next sentence")
    ]
    merged = AudioChunker.reconcile_and_merge_cues([chunk1_cues, chunk2_cues])
    assert len(merged) == 2
    assert merged[0].text == "Hello ladies and gentlemen"
    assert merged[0].end_ms == 301000
    assert merged[1].text == "Next sentence"

