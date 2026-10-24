# Online Subtitle Generator

**Online Subtitle Generator** is a high-performance Windows desktop application that extracts natural, grammatically aligned English subtitles (`.srt`) from video and audio files using **Cloudflare Workers AI Whisper** (`@cf/openai/whisper`).

Equipped with a **Multi-Account Failover Pool** (supporting up to 10 Cloudflare accounts) and an intelligent subtitle segmenter, it is designed for continuous, resilient, overnight batch processing without interruptions.

---

## Key Features

- **Cloudflare Workers AI Whisper Integration:** High-accuracy automated speech recognition powered by Cloudflare's serverless AI infrastructure.
- **Multi-Account Failover Pool (Up to 10 Accounts):**
  - Configure up to 10 separate Cloudflare accounts (Account ID & API Token).
  - When Account #1 exhausts its daily free quota (10,000 Neurons), processing automatically switches to Account #2, #3, and beyond without halting your batch.
- **Intelligent Subtitle Segmentation & Formatting:**
  - **Grammar-Aware Splitting:** Avoids breaking sentences after prepositions, articles, or pronouns.
  - **Orphan Word Prevention:** Ensures short trailing words (e.g., `Yet.`, `Marriage?`) remain unified with their parent sentence.
  - **Speech Pause Detection:** Silence gaps $\ge 0.40$s accurately identify speaker turns.
  - **Dialogue Turn Formatting:** Fast exchanges are formatted with broadcast-standard hyphens (`- Speaker 1\n- Speaker 2`).
  - **Collision-Free Timestamps:** Eliminates overlapping cues and guarantees sequential display.
- **Batch Processing Manager:**
  - Queue multiple video files from a folder.
  - Configure custom start/end time ranges per video or process full movies.
  - Failure isolation: if one video encounters an issue, processing seamlessly continues to the next.
- **Hardware-Optimized & Portable:**
  - Bundled with static FFmpeg and FFprobe binaries.
  - Zero cloud plaintext credential storage (encrypted via Windows Credential Manager).
  - Portable mode supported.

---

## Installation & Setup

1. **Pre-built Portable Executable:**
   - Run `Online Subtitle Generator.exe` directly from `C:\Ali\Utility\Online Subtitle Generator\`.
2. **API Credentials:**
   - Click **🔑 Cloudflare Accounts (Pool)** on the top bar.
   - Enter your Cloudflare **Account ID** and **API Token** for Slot #1, #2, etc.
   - Click **Save Account**.

---

## Development

```bash
# Clone the repository
git clone https://github.com/YourUsername/Online-Subtitle-Generator.git
cd "Online Subtitle Generator"

# Install dependencies
pip install -r requirements.txt

# Run test suite
pytest

# Launch application
python app/main.py

# Build portable Windows executable
python packaging/build_windows.py
```

---

## License

MIT License. Designed and developed by Ali.
