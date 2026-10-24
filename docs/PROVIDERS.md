# Verified AI Providers & Model Registry

*Verification Date: October 2026*

This document provides verified technical documentation, endpoint definitions, pricing tiers, and capabilities for all speech-recognition (ASR) and machine translation providers supported by OnlineSub.

---

## 1. Google Gemini API

### Official Documentation
- **Audio Understanding**: [https://ai.google.dev/gemini-api/docs/audio](https://ai.google.dev/gemini-api/docs/audio)
- **API Overview & Pricing**: [https://ai.google.dev/pricing](https://ai.google.dev/pricing)
- **Base Endpoint**: `https://generativelanguage.googleapis.com/v1beta`

### Verified Models

#### `gemini-2.5-flash` (Recommended for ASR & Translation)
- **Type**: Multimodal audio and text generation.
- **ASR Capability**: Native audio understanding with millisecond timestamp extraction.
- **Translation Capability**: Superior contextual Persian translation preserving subtitle structure.
- **Free Tier**: 15 Requests Per Minute (RPM), 1,000,000 Tokens Per Minute (TPM), 1,500 Requests Per Day (RPD) on Google AI Studio.
- **Paid Tier**: \$0.075 / 1M input tokens.
- **Audio Limits**: Supports up to 1-2 hours of audio input per request (3600 seconds default chunking in OnlineSub).

#### `gemini-1.5-flash`
- **Type**: High-speed multimodal model.
- **Pricing & Limits**: Same free-tier allowances on AI Studio.

---

## 2. Cloudflare Workers AI

### Official Documentation
- **Workers AI Models**: [https://developers.cloudflare.com/workers-ai/models/](https://developers.cloudflare.com/workers-ai/models/)
- **Whisper Documentation**: [https://developers.cloudflare.com/workers-ai/models/whisper/](https://developers.cloudflare.com/workers-ai/models/whisper/)
- **Base Endpoint**: `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}`

### Verified Models

#### `@cf/openai/whisper` (ASR)
- **Input**: Binary audio stream (`application/octet-stream`).
- **Output**: JSON containing text and WebVTT cue timestamps.
- **Free Tier**: 10,000 Neurons per day free across Workers AI.
- **Paid Tier**: \$0.011 per 1,000 Neurons.
- **Chunking Recommendation**: Max 10 minutes (600s) per request to satisfy payload boundaries.

#### `@cf/meta/m2m100-1.2b` (Translation)
- **Input**: Text, source language (`english`), target language (`persian`).
- **Free Tier**: Included in 10,000 daily Neurons.

---

## 3. Hugging Face Serverless Inference API

### Official Documentation
- **Audio-to-Text API**: [https://huggingface.co/docs/api-inference/detailed_parameters#audio-to-text](https://huggingface.co/docs/api-inference/detailed_parameters#audio-to-text)
- **Base Endpoint**: `https://api-inference.huggingface.co/models/{model_id}`

### Verified Models

#### `openai/whisper-large-v3` (ASR)
- **Input**: Binary audio payload.
- **Parameters**: `return_timestamps=True`.
- **Free Tier**: Serverless queue accessible with free Hugging Face User Access Token.
- **Chunking Recommendation**: Max 5 minutes (300s) per request.

#### `facebook/m2m100_1.2B` (Translation)
- **Input**: `inputs`, `src_lang: "en"`, `tgt_lang: "fa"`.
- **Free Tier**: Serverless queue.

---

## 4. Local Faster-Whisper (Offline CPU)

### Official Documentation
- **Repository**: [https://github.com/SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- **Engine**: CTranslate2 optimized Whisper implementation with 8-bit quantization (`int8`).

### Verified Models
- `base`: ~1.0 GB RAM required. Fast, low resource utilization.
- `small`: ~2.0 GB RAM required. Balanced accuracy and speed.
- `medium`: ~5.0 GB RAM required. High quality.
- **Pricing**: 100% Free & completely offline. No API key or internet access required.
