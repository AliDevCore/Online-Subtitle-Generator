"""
FFmpeg and FFprobe media extraction, audio analysis, and subprocess service.
Provides robust binary discovery, automatic fallback media probing, and high-efficiency audio compression.
"""

from __future__ import annotations
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

from app.core.config import CACHE_DIR

logger = logging.getLogger("OnlineSub.FFmpeg")


def _is_working_binary(bin_path: Path | str, tool_name: str) -> bool:
    """Validate that the binary actually runs and is not a broken shim or missing file."""
    try:
        p = Path(bin_path)
        if not p.is_file():
            return False
        # Avoid tiny broken shims (< 1MB) unless verified
        res = subprocess.run([str(p), "-version"], capture_output=True, text=True, timeout=4)
        return res.returncode == 0 and tool_name.lower() in res.stdout.lower()
    except Exception:
        return False


def find_media_tool(tool_name: str, custom_path: Optional[str] = None) -> Path:
    """
    Discover FFmpeg / FFprobe executable with comprehensive search order:
    1. Custom path if provided and valid.
    2. Beside the running executable or script (exe_dir / tool_name.exe).
    3. Under bin subdirectory (exe_dir / bin / tool_name.exe).
    4. Chocolatey tools library path: C:\\ProgramData\\chocolatey\\lib\\ffmpeg\\tools\\ffmpeg\\bin\\
    5. System PATH via shutil.which, strictly verifying it runs cleanly.
    """
    candidates: List[Path] = []

    # 1. Custom path
    if custom_path:
        candidates.append(Path(custom_path))

    # 2. Executable / script directory
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / f"{tool_name}.exe")
        candidates.append(exe_dir / "bin" / f"{tool_name}.exe")
        if hasattr(sys, "_MEIPASS"):
            meipass = Path(sys._MEIPASS)
            candidates.append(meipass / f"{tool_name}.exe")
            candidates.append(meipass / "bin" / f"{tool_name}.exe")
    else:
        root_dir = Path(__file__).resolve().parent.parent.parent
        candidates.append(root_dir / f"{tool_name}.exe")
        candidates.append(root_dir / "bin" / f"{tool_name}.exe")

    # 3. Known chocolatey real binaries directory
    choco_real = Path(r"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin") / f"{tool_name}.exe"
    candidates.append(choco_real)

    # 4. System PATH
    system_path = shutil.which(tool_name)
    if system_path:
        candidates.append(Path(system_path))

    for cand in candidates:
        if cand and _is_working_binary(cand, tool_name):
            logger.info(f"Discovered working {tool_name} binary at: {cand}")
            return cand.resolve()

    # Fallback to plain name
    return Path(tool_name)


class FFmpegService:
    """Manages audio extraction, metadata inspection, format conversion, and audio compression."""

    def __init__(self, ffmpeg_path: Optional[str] = None, ffprobe_path: Optional[str] = None):
        self.ffmpeg_path = str(find_media_tool("ffmpeg", ffmpeg_path))
        self.ffprobe_path = str(find_media_tool("ffprobe", ffprobe_path))

    def probe_media(self, video_path: Path | str) -> Dict[str, Any]:
        """
        Probe media file to extract duration, format, and audio stream details.
        Uses ffprobe when available, and automatically falls back to ffmpeg if ffprobe fails.
        """
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video file does not exist: {path}")

        # Attempt 1: ffprobe JSON parsing
        try:
            cmd = [
                self.ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(path)
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(res.stdout)

            duration_sec = 0.0
            fmt = data.get("format", {})
            if "duration" in fmt:
                try:
                    duration_sec = float(fmt["duration"])
                except (ValueError, TypeError):
                    pass

            audio_streams = []
            for s in data.get("streams", []):
                if s.get("codec_type") == "audio":
                    audio_streams.append({
                        "index": s.get("index"),
                        "codec_name": s.get("codec_name"),
                        "channels": s.get("channels"),
                        "sample_rate": s.get("sample_rate"),
                        "language": s.get("tags", {}).get("language", "und")
                    })

            if duration_sec <= 0 and audio_streams:
                for s in data.get("streams", []):
                    if s.get("codec_type") == "audio" and "duration" in s:
                        try:
                            duration_sec = float(s["duration"])
                            break
                        except Exception:
                            pass

            return {
                "file_path": str(path),
                "file_name": path.name,
                "duration_seconds": duration_sec,
                "duration_minutes": duration_sec / 60.0,
                "has_audio": len(audio_streams) > 0,
                "audio_streams": audio_streams,
                "format_name": fmt.get("format_name", "unknown")
            }

        except Exception as e:
            logger.warning(f"ffprobe failed ({e}), falling back to direct ffmpeg parsing...")
            return self._probe_media_via_ffmpeg(path)

    def _probe_media_via_ffmpeg(self, path: Path) -> Dict[str, Any]:
        """Fallback media prober using 'ffmpeg -hide_banner -i <file>' stderr parsing."""
        cmd = [self.ffmpeg_path, "-hide_banner", "-i", str(path)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = res.stderr or res.stdout

        # Parse duration: Duration: 00:24:30.50, ...
        duration_sec = 0.0
        dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
        if dur_match:
            hours = int(dur_match.group(1))
            minutes = int(dur_match.group(2))
            seconds = float(dur_match.group(3))
            duration_sec = hours * 3600 + minutes * 60 + seconds

        # Parse audio streams: Stream #0:1(eng): Audio: aac ...
        has_audio = False
        audio_streams = []
        stream_matches = re.finditer(r"Stream\s*#(\d+:\d+)(?:\((.*?)\))?:\s*Audio:\s*([^,\n\r]+)", output)
        for m in stream_matches:
            has_audio = True
            audio_streams.append({
                "index": m.group(1),
                "codec_name": m.group(3).strip(),
                "channels": 2,
                "sample_rate": 44100,
                "language": m.group(2) or "und"
            })

        if not has_audio and "Audio:" in output:
            has_audio = True
            audio_streams.append({
                "index": "0:1",
                "codec_name": "audio",
                "channels": 2,
                "sample_rate": 44100,
                "language": "und"
            })

        return {
            "file_path": str(path),
            "file_name": path.name,
            "duration_seconds": duration_sec,
            "duration_minutes": duration_sec / 60.0,
            "has_audio": has_audio,
            "audio_streams": audio_streams,
            "format_name": path.suffix.lstrip(".").lower()
        }

    def extract_audio_segment(
        self,
        video_path: Path | str,
        start_seconds: float,
        duration_seconds: float,
        output_format: str = "mp3",  # High-efficiency MP3 default to reduce upload bandwidth
        bitrate: str = "64k",        # 64 kbps mono is optimal for speech ASR
        sample_rate: int = 16000,
        channels: int = 1,
        cancel_token: Optional[Any] = None
    ) -> Path:
        """
        Extract only the requested segment from the video into a highly compressed audio file.
        Uses libmp3lame compression to drastically reduce file size and upload time.
        """
        video = Path(video_path)
        if not video.exists():
            raise FileNotFoundError(f"Video file not found: {video}")

        import uuid
        out_filename = f"audio_{uuid.uuid4().hex[:8]}_{int(start_seconds)}_{int(duration_seconds)}.{output_format}"
        out_path = CACHE_DIR / out_filename

        # Build ffmpeg extraction command with compression
        cmd = [
            self.ffmpeg_path,
            "-y",  # overwrite
            "-ss", f"{start_seconds:.3f}",
            "-i", str(video),
            "-t", f"{duration_seconds:.3f}",
            "-vn",  # no video
            "-sn",  # no subtitles
        ]

        if output_format == "mp3":
            cmd.extend([
                "-acodec", "libmp3lame",
                "-b:a", str(bitrate),
                "-ar", str(sample_rate),
                "-ac", str(channels),
            ])
        elif output_format == "wav":
            cmd.extend([
                "-acodec", "pcm_s16le",
                "-ar", str(sample_rate),
                "-ac", str(channels),
            ])
        else:
            cmd.extend([
                "-ar", str(sample_rate),
                "-ac", str(channels),
            ])

        cmd.append(str(out_path))

        logger.info(f"Extracting compressed audio segment [{start_seconds:.2f}s, +{duration_seconds:.2f}s] ({output_format.upper()} @ {bitrate})...")

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        stderr_output = ""
        try:
            while True:
                if cancel_token and getattr(cancel_token, "is_cancelled", False):
                    proc.kill()
                    if out_path.exists():
                        try:
                            out_path.unlink()
                        except Exception:
                            pass
                    raise RuntimeError("Audio extraction cancelled by user.")
                try:
                    _, stderr_output = proc.communicate(timeout=0.3)
                    break
                except subprocess.TimeoutExpired:
                    continue

            if proc.returncode != 0:
                raise RuntimeError(f"FFmpeg extraction failed (code {proc.returncode}): {stderr_output}")

        except Exception as e:
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass
            if out_path.exists():
                try:
                    out_path.unlink()
                except Exception:
                    pass
            raise e

        if not out_path.exists() or out_path.stat().st_size == 0:
            raise RuntimeError("FFmpeg completed but audio output file is empty or missing.")

        size_kb = out_path.stat().st_size / 1024
        logger.info(f"Extracted audio ready: {out_path.name} ({size_kb:.1f} KB)")
        return out_path

    def compress_audio_file(
        self,
        input_audio_path: Path | str,
        output_format: str = "mp3",
        bitrate: str = "64k",
        sample_rate: int = 16000
    ) -> Path:
        """
        Compress an existing audio file (such as large PCM WAV) into lightweight MP3 before sending over network.
        """
        inp = Path(input_audio_path)
        if not inp.exists():
            raise FileNotFoundError(f"Input audio does not exist: {inp}")

        # If already a compressed mp3 under 10MB, return directly
        if inp.suffix.lower() == f".{output_format}" and inp.stat().st_size < 10 * 1024 * 1024:
            return inp

        out_path = CACHE_DIR / f"compressed_{inp.stem}.{output_format}"
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(inp),
            "-vn",
            "-acodec", "libmp3lame",
            "-b:a", str(bitrate),
            "-ar", str(sample_rate),
            "-ac", "1",
            str(out_path)
        ]
        logger.info(f"Compressing audio '{inp.name}' ({inp.stat().st_size / 1024:.1f} KB) to {output_format}...")
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Compressed audio ready: {out_path.name} ({out_path.stat().st_size / 1024:.1f} KB)")
        return out_path
