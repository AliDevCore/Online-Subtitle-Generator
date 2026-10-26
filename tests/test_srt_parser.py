"""
Tests for SRT parser, validator, normalizer, and serializer.
"""

from pathlib import Path
import pytest
from app.core.srt_parser import SRTParser
from app.core.types import SubtitleCue, SubtitleFile


def test_parse_valid_srt(sample_srt_text):
    sub = SRTParser.parse_text(sample_srt_text)
    assert len(sub.cues) == 3
    assert sub.cues[0].index == 1
    assert sub.cues[0].start_str == "00:00:01,000"
    assert sub.cues[0].end_str == "00:00:04,500"
    assert sub.cues[0].text == "Hello and welcome to the tutorial."

    assert sub.cues[2].text == "Let's get started right away."


def test_srt_roundtrip_serialization(sample_srt_text, tmp_path):
    sub = SRTParser.parse_text(sample_srt_text)
    out_file = tmp_path / "output.srt"
    SRTParser.write_file(sub, out_file)

    assert out_file.exists()
    reparsed = SRTParser.parse_file(out_file)
    assert len(reparsed.cues) == len(sub.cues)
    for c1, c2 in zip(sub.cues, reparsed.cues):
        assert c1.start_ms == c2.start_ms
        assert c1.end_ms == c2.end_ms
        assert c1.text == c2.text


def test_parse_with_bom():
    text_with_bom = "\ufeff1\n00:00:00,100 --> 00:00:02,000\nBOM Test\n"
    sub = SRTParser.parse_text(text_with_bom)
    assert len(sub.cues) == 1
    assert sub.cues[0].text == "BOM Test"


def test_validate_cues():
    valid_cues = [
        SubtitleCue(1, 1000, 3000, "First cue"),
        SubtitleCue(2, 3500, 5000, "Second cue")
    ]
    issues = SRTParser.validate_cues(valid_cues)
    assert len(issues) == 0

    bad_cues = [
        SubtitleCue(1, 4000, 2000, "Inverted timestamps"),
        SubtitleCue(2, 5000, 6000, "")
    ]
    issues = SRTParser.validate_cues(bad_cues)
    assert len(issues) >= 2


def test_clean_trailing_punctuation():
    # Exclamation mark stripped
    assert SRTParser.clean_trailing_punctuation("Listen!") == "Listen"
    # Period stripped
    assert SRTParser.clean_trailing_punctuation("I didn't hear you.") == "I didn't hear you"
    # Comma stripped
    assert SRTParser.clean_trailing_punctuation("I tried to ring the bell,") == "I tried to ring the bell"
    # Persian comma stripped
    assert SRTParser.clean_trailing_punctuation("سلام،") == "سلام"
    # Question marks strictly preserved
    assert SRTParser.clean_trailing_punctuation("Where's Mom?") == "Where's Mom?"
    assert SRTParser.clean_trailing_punctuation("چطوری؟") == "چطوری؟"
    # Internal punctuation preserved
    assert SRTParser.clean_trailing_punctuation("Oh, hi. Hey!") == "Oh, hi. Hey"
    # Multiple trailing punctuation marks stripped
    assert SRTParser.clean_trailing_punctuation("Really?!...") == "Really?"
    # HTML tag handling
    assert SRTParser.clean_trailing_punctuation("<i>Listen!</i>") == "<i>Listen</i>"
