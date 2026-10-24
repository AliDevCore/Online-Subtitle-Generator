# Online Subtitle Generator - User Guide

Welcome to **Online Subtitle Generator**! This guide walks you through extracting audio from videos, configuring AI speech recognition, and generating clean, grammatically aligned English subtitles (`.srt`).

---

## 1. Quick Walkthrough

### Step 1: Select Media File
1. Click **Browse Video...** and choose any media file (`.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, etc.).
2. The media duration and stream information will be detected and displayed automatically.

### Step 2: Set Time Range
- Enter the **Start Time** and **End Time** in minutes (integers).
- Click **Entire Video** to transcribe the whole file from beginning to end.
- Subtitle timestamps preserve the original video timeline offset.

### Step 3: Configure Cloudflare Credentials
- Click **🔑 Cloudflare Accounts (Pool)** on the top bar.
- Add your Cloudflare **Account ID** and **API Token** (slot 1 to 10).
- Multiple accounts provide high-availability failover: if Account #1 reaches its daily free quota, the application automatically switches to Account #2 without halting the job.
- Credentials are encrypted and stored securely in Windows Credential Manager.

### Step 4: Generate Subtitles
- Click **🎬 Generate English Subtitle**.
- The progress bar shows real-time progress (audio extraction, 5-minute chunking, and Cloudflare Whisper transcription).
- Once finished, the `.en.srt` file is saved beside the video file.

---

## 2. Batch Processing

To process multiple video files automatically:
1. Click **📁 Batch Folder...** on the main window.
2. Select a folder containing your video files.
3. Review or customize the start/end minutes for each video in the queue.
4. Click **Start Batch**. The batch engine will process files sequentially with full failure isolation and automatic multi-account failover.
