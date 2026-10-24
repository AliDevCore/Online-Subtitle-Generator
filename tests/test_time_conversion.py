"""
Tests for time range handling, decimal minute conversion, and timeline offsets.
"""

import pytest
from app.core.types import TimeRange, SubtitleCue


def test_time_range_from_decimal_minutes():
    tr = TimeRange.from_minutes(12.5, 15.75)
    assert tr.start_seconds == 750.0
    assert tr.end_seconds == 945.0
    assert tr.duration_seconds == 195.0
    assert tr.start_minutes == 12.5
    assert tr.end_minutes == 15.75


def test_time_range_validation_valid():
    tr = TimeRange.from_minutes(1.0, 5.0)
    valid, err = tr.validate(video_duration_seconds=600.0)
    assert valid is True
    assert err == ""


def test_time_range_validation_negative_start():
    tr = TimeRange(-10.0, 50.0)
    valid, err = tr.validate()
    assert valid is False
    assert "cannot be negative" in err


def test_time_range_validation_end_before_start():
    tr = TimeRange(100.0, 50.0)
    valid, err = tr.validate()
    assert valid is False
    assert "must be greater than start" in err


def test_time_range_validation_exceeds_video():
    tr = TimeRange(10.0, 700.0)
    valid, err = tr.validate(video_duration_seconds=600.0)
    assert valid is False
    assert "exceeds video duration" in err


def test_subtitle_cue_timestamp_conversion():
    # 01:23:45,678
    # 1h = 3600s, 23m = 1380s, 45s = 45s => 5025s = 5,025,000ms + 678ms = 5025678ms
    ms = SubtitleCue.timestamp_to_ms("01:23:45,678")
    assert ms == 5025678

    ts = SubtitleCue.ms_to_timestamp(ms)
    assert ts == "01:23:45,678"


def test_subtitle_cue_shift_offset():
    cue = SubtitleCue(index=1, start_ms=1000, end_ms=4000, text="Test phrase")
    # Shift by 15 minutes (900,000 ms)
    offset_ms = 900000
    shifted = cue.shift(offset_ms)
    assert shifted.start_ms == 901000
    assert shifted.end_ms == 904000
    assert shifted.start_str == "00:15:01,000"
    assert shifted.end_str == "00:15:04,000"
    assert shifted.text == "Test phrase"
