# OnlineSub User Guide

Welcome to **OnlineSub**! This guide walks you through extracting video audio, generating English subtitles, and translating them into natural Persian.

---

## 1. Quick Walkthrough

### Step 1: Ingest Local Video
1. Click **Browse Video...** and select a media file (`.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, etc.).
2. The media duration and audio track details will appear automatically.

### Step 2: Set Time Range
- Enter the **Start Time** and **End Time** in minutes. Decimal values are fully supported (for example, `12.5` = 12 minutes and 30 seconds).
- Click **Entire Video** if you want to transcribe the whole file from start to finish.
- *Timeline Guarantee*: Subtitle timestamps in the generated `.srt` will preserve the original video offset (e.g., if you choose minute 15 to 20, the first subtitle starts at `00:15:00,000`).

### Step 3: Choose AI Providers
- **Pipeline A (ASR)**: Select your speech recognition model (e.g., `Gemini 2.5 Flash`, `Cloudflare Whisper`, or offline `Local Whisper Base`).
- **Pipeline B (Translation)**: Select your translation model independently (e.g., `Gemini 2.5 Flash` or `Meta M2M100`).
- If you haven't entered your API key yet, click **🔑 API Credentials** at the top right to configure it.

### Step 4: Generate Subtitles
- Click **🎬 Generate English SRT**.
- The progress bar displays the active stage (audio slicing, chunking, AI transcription).
- Once completed, OnlineSub will ask if you would like to translate the generated subtitle into Persian immediately.

---

## 2. Translating an Existing SRT File

You do not need the original video to translate subtitles:
1. Click **🌐 Translate Existing SRT...**.
2. Pick any English `.srt` file from your computer.
3. Select your desired translation model in Pipeline B.
4. The translated file will be saved beside the source with a `.fa.srt` extension.

---

## 3. Configuring API Credentials

Click **🔑 API Credentials** on the top toolbar:
- Enter your **Google Gemini API Key** (from [Google AI Studio](https://aistudio.google.com/)).
- Enter your **Cloudflare API Token** & **Account ID** (from [Cloudflare Dashboard](https://dash.cloudflare.com/)).
- Enter your **Hugging Face Token** (from [Hugging Face Settings](https://huggingface.co/settings/tokens)).
- Click **Save to Windows Credential Manager**.
- Keys are masked in the UI and never saved in plaintext files.

---

## 4. Batch Processing

To process multiple videos unattended:
1. Click **📁 Process Batch...**.
2. Click **Add Videos...** and select multiple files.
3. Check **Translate all to Persian** if desired.
4. Click **Accept Queue & Close**, then run the batch.
5. If one video fails (e.g. corrupt audio), the application logs the error and safely continues processing the remaining videos.
