"""
Tests for FFmpegService binary discovery, fallback media probing, and audio compression.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from app.services.ffmpeg_service import FFmpegService, find_media_tool


def test_find_media_tool_discovery():
    ffmpeg_bin = find_media_tool("ffmpeg")
    assert Path(ffmpeg_bin).exists()
    assert "ffmpeg" in str(ffmpeg_bin).lower()

    ffprobe_bin = find_media_tool("ffprobe")
    assert Path(ffprobe_bin).exists()
    assert "ffprobe" in str(ffprobe_bin).lower()


def test_ffmpeg_fallback_probing():
    service = FFmpegService()

    # Mock ffmpeg -hide_banner -i output with typical stream information
    mock_stderr = (
        "Input #0, matroska,webm, from 'test.mkv':\n"
        "  Duration: 00:05:30.25, start: 0.000000, bitrate: 1500 kb/s\n"
        "  Stream #0:0(eng): Video: h264\n"
        "  Stream #0:1(eng): Audio: aac (LC), 48000 Hz, stereo, fltp\n"
    )

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr=mock_stderr, stdout="")
        res = service._probe_media_via_ffmpeg(Path("test.mkv"))

        assert res["duration_seconds"] == 330.25
        assert res["duration_minutes"] == pytest.approx(5.504, 0.01)
        assert res["has_audio"] is True
        assert len(res["audio_streams"]) >= 1
