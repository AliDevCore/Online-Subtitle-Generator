# Changelog

## [1.0.0] - 2026-10-24

### Added
- Complete Windows desktop application built with PySide6.
- Cloud-hosted Speech-to-Text (ASR) via Cloudflare Workers AI Whisper (`@cf/openai/whisper`).
- Multi-Account High-Availability Failover Pool supporting up to 10 Cloudflare accounts with automatic token switching on quota exhaustion.
- Intelligent subtitle segmentation and punctuation formatting adhering to standard subtitle conventions.
- Boundary overlap reconciliation to eliminate duplicate sentences across chunk boundaries.
- Precise time range selection in minutes with automatic duration clamping.
- Encrypted credential storage via Windows Credential Manager with thread-safe in-memory caching.
- Batch processing dialog supporting folder queues, custom time ranges, and failure isolation.
- Bundled static FFmpeg and FFprobe binaries with hidden console execution (`CREATE_NO_WINDOW`).
- Portable mode support and automated GitHub Actions release packaging.
