# Performance & Optimization Guide

Online Subtitle Generator is architected for speed, low local system overhead, and high batch reliability.

---

## 1. Cloud-Offloaded Computation

Unlike local Whisper models that demand several gigabytes of VRAM or high CPU usage, Online Subtitle Generator offloads speech recognition entirely to Cloudflare Workers AI GPUs:
- **Local CPU Usage**: Typically $< 5\%$ during operation, only briefly peaking when FFmpeg extracts audio segments.
- **Local Memory**: Footprint remains under ~150 MB throughout execution.
- **Portability**: Runs smoothly on low-power laptops and budget Windows machines without dedicated graphics cards.

---

## 2. Audio Chunker Optimization

- **Chunk Sizing**: 5-minute segments (300 seconds) balance network transfer latency with Whisper's contextual accuracy.
- **Micro-Chunk Elimination**: Trailing audio tails shorter than 20 seconds are merged into the previous chunk, eliminating unnecessary single-sentence network requests.
- **Boundary Overlap**: 2-second overlap with suffix-prefix phrase matching prevents clipped words or duplicated boundary cues.

---

## 3. High-Throughput Batch Processing

- **Thread-Safe Keyring Caching**: In-memory credential caching eliminates repeated Windows DPAPI calls during logging and progress tracking, reducing UI latency.
- **Hidden Subprocess Windows**: FFmpeg and FFprobe calls execute with `CREATE_NO_WINDOW` and redirected streams, preventing flickering command prompt popups on Windows.
- **Sticky Account Rotation**: The multi-account failover system retains the last active successful account for subsequent chunks and files, minimizing switching overhead.
