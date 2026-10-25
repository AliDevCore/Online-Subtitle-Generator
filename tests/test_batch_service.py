"""
Tests for BatchService video queue execution, folder scanning, and failure isolation.
"""

from pathlib import Path
from unittest.mock import MagicMock
from app.core.types import JobStatus
from app.services.batch_service import BatchService, BatchVideoItem


def test_batch_service_failure_isolation(tmp_path):
    mock_asr = MagicMock()

    vid1 = tmp_path / "vid1.mp4"
    vid2 = tmp_path / "vid2.mp4"
    vid1.write_bytes(b"dummy1")
    vid2.write_bytes(b"dummy2")

    mock_asr.ffmpeg.probe_media.return_value = {"duration_seconds": 120.0}

    # Simulate first item failing, second succeeding
    mock_asr.run_transcription.side_effect = [
        RuntimeError("Corrupt audio frame in vid1"),
        tmp_path / "vid2.en.srt"
    ]

    service = BatchService(asr_service=mock_asr)
    service.add_video_file(vid1)
    service.add_video_file(vid2)

    results = service.run_video_batch(
        asr_provider="cloudflare",
        asr_model="@cf/openai/whisper-large-v3-turbo"
    )

    assert len(results) == 2
    assert results[0].status == JobStatus.FAILED
    assert "Corrupt audio frame" in results[0].error_msg
    assert results[1].status == JobStatus.COMPLETED


def test_batch_video_folder_scan(tmp_path):
    mock_asr = MagicMock()
    mock_asr.ffmpeg.probe_media.return_value = {"duration_seconds": 300.0}

    v_dir = tmp_path / "videos"
    v_dir.mkdir()
    (v_dir / "ep01.mp4").write_bytes(b"dummy")
    (v_dir / "ep02.mkv").write_bytes(b"dummy")
    (v_dir / "notes.txt").write_bytes(b"skip me")

    service = BatchService(asr_service=mock_asr)
    items = service.scan_and_add_videos(v_dir)

    assert len(items) == 2
    names = [it.name for it in items]
    assert "ep01.mp4" in names
    assert "ep02.mkv" in names
