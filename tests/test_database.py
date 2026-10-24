"""
Tests for SQLite job tracking and chunk resumability.
"""

from app.core.database import Database
from app.core.types import AudioChunk, SubtitleCue, JobStatus


def test_job_lifecycle(temp_database):
    db = temp_database
    job_id = "test_job_123"

    db.create_job(
        job_id=job_id,
        video_path="C:/videos/sample.mp4",
        pipeline="ASR",
        start_seconds=0.0,
        end_seconds=120.0,
        asr_provider="gemini",
        asr_model="gemini-2.5-flash",
        output_srt_path="C:/videos/sample.en.srt"
    )

    job = db.get_job(job_id)
    assert job is not None
    assert job["id"] == job_id
    assert job["status"] == JobStatus.PENDING.value

    # Update to extracting
    db.update_job_status(job_id, JobStatus.EXTRACTING)
    assert db.get_job(job_id)["status"] == JobStatus.EXTRACTING.value

    # Save chunk
    chunk = AudioChunk(
        index=1,
        file_path="C:/temp/chunk_1.wav",
        start_seconds=0.0,
        end_seconds=60.0,
        duration_seconds=60.0,
        status="COMPLETED",
        cues=[SubtitleCue(1, 1000, 4000, "Hello chunk 1")]
    )
    db.save_chunk(job_id, chunk)

    chunks = db.get_chunks(job_id)
    assert len(chunks) == 1
    assert chunks[0].index == 1
    assert len(chunks[0].cues) == 1
    assert chunks[0].cues[0].text == "Hello chunk 1"

    # Mark completed
    db.update_job_status(job_id, JobStatus.COMPLETED)
    assert db.get_job(job_id)["status"] == JobStatus.COMPLETED.value
