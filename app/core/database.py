"""
SQLite database for job tracking, resumability, and audio chunk persistence.
"""

from __future__ import annotations
import json
import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from app.core.config import DATABASE_FILE
from app.core.types import AudioChunk, SubtitleCue, JobStatus


class Database:
    """Thread-safe SQLite storage for jobs, chunks, and operation resumability."""

    def __init__(self, db_path: Path | str = DATABASE_FILE):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Jobs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    video_path TEXT NOT NULL,
                    pipeline TEXT NOT NULL,
                    status TEXT NOT NULL,
                    start_seconds REAL NOT NULL,
                    end_seconds REAL NOT NULL,
                    asr_provider TEXT,
                    asr_model TEXT,
                    translation_provider TEXT,
                    translation_model TEXT,
                    extracted_audio_path TEXT,
                    output_srt_path TEXT,
                    translated_srt_path TEXT,
                    error_message TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)

            # Chunks table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    job_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    start_seconds REAL NOT NULL,
                    end_seconds REAL NOT NULL,
                    duration_seconds REAL NOT NULL,
                    status TEXT NOT NULL,
                    raw_response TEXT,
                    cues_json TEXT,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (job_id, chunk_index),
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def create_job(
        self,
        job_id: str,
        video_path: str,
        pipeline: str,
        start_seconds: float,
        end_seconds: float,
        asr_provider: str = "",
        asr_model: str = "",
        translation_provider: str = "",
        translation_model: str = "",
        output_srt_path: str = ""
    ) -> None:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO jobs (
                    id, video_path, pipeline, status, start_seconds, end_seconds,
                    asr_provider, asr_model, translation_provider, translation_model,
                    output_srt_path, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id, video_path, pipeline, JobStatus.PENDING.value,
                start_seconds, end_seconds, asr_provider, asr_model,
                translation_provider, translation_model, output_srt_path,
                now, now
            ))
            conn.commit()

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None,
        extracted_audio_path: Optional[str] = None,
        output_srt_path: Optional[str] = None,
        translated_srt_path: Optional[str] = None
    ) -> None:
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            updates = ["status = ?", "updated_at = ?"]
            params: List[Any] = [status.value, now]

            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)
            if extracted_audio_path is not None:
                updates.append("extracted_audio_path = ?")
                params.append(extracted_audio_path)
            if output_srt_path is not None:
                updates.append("output_srt_path = ?")
                params.append(output_srt_path)
            if translated_srt_path is not None:
                updates.append("translated_srt_path = ?")
                params.append(translated_srt_path)

            params.append(job_id)
            cursor.execute(f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs ORDER BY updated_at DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def save_chunk(self, job_id: str, chunk: AudioChunk) -> None:
        now = time.time()
        cues_data = [
            {"index": c.index, "start_ms": c.start_ms, "end_ms": c.end_ms, "text": c.text}
            for c in chunk.cues
        ]
        cues_json = json.dumps(cues_data, ensure_ascii=False)
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO chunks (
                    job_id, chunk_index, file_path, start_seconds, end_seconds,
                    duration_seconds, status, raw_response, cues_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id, chunk.index, chunk.file_path, chunk.start_seconds,
                chunk.end_seconds, chunk.duration_seconds, chunk.status,
                chunk.raw_response, cues_json, now
            ))
            conn.commit()

    def get_chunks(self, job_id: str) -> List[AudioChunk]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM chunks WHERE job_id = ? ORDER BY chunk_index ASC",
                (job_id,)
            )
            rows = cursor.fetchall()
            chunks: List[AudioChunk] = []
            for r in rows:
                cues = []
                if r["cues_json"]:
                    try:
                        raw_cues = json.loads(r["cues_json"])
                        for rc in raw_cues:
                            cues.append(SubtitleCue(
                                index=rc["index"],
                                start_ms=rc["start_ms"],
                                end_ms=rc["end_ms"],
                                text=rc["text"]
                            ))
                    except Exception:
                        pass
                chunks.append(AudioChunk(
                    index=r["chunk_index"],
                    file_path=r["file_path"],
                    start_seconds=r["start_seconds"],
                    end_seconds=r["end_seconds"],
                    duration_seconds=r["duration_seconds"],
                    status=r["status"],
                    raw_response=r["raw_response"] or "",
                    cues=cues
                ))
            return chunks

    def delete_job(self, job_id: str) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM chunks WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            conn.commit()
