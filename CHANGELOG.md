# Changelog

## [1.0.0] - 2026-10-23

### Added
- Complete Windows desktop application built with PySide6.
- Independent Speech-to-Text (ASR) and Machine Translation pipelines.
- Multi-provider support: Google Gemini, Cloudflare Workers AI, Hugging Face Inference, Local Faster-Whisper.
- Subtitle generation in valid SubRip (.srt) format with HH:MM:SS,mmm timestamps.
- Decimal minute time range entry with millisecond precision and timeline offset preservation.
- Local performance controller (CPU Usage Target 100%, Process Priority, CPU Threads, RAM Limit).
- Strict separation between local resource controls and remote cloud API processing.
- Windows Credential Manager integration for secure API key storage.
- Audio chunking with overlap and chronological merge reconciliation.
- Resumable SQLite job engine and batch processing dialog.
- Standalone portable Windows packaging script and GitHub release workflow.
