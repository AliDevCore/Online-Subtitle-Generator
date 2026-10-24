# Verified Speech Recognition Provider Documentation

*Verification Date: October 2026*

Online Subtitle Generator utilizes **Cloudflare Workers AI** as its primary speech recognition engine for ultra-fast, cloud-hosted Whisper transcription.

---

## Cloudflare Workers AI (`@cf/openai/whisper`)

### Official Documentation
- **Workers AI Models**: [https://developers.cloudflare.com/workers-ai/models/](https://developers.cloudflare.com/workers-ai/models/)
- **Whisper Documentation**: [https://developers.cloudflare.com/workers-ai/models/whisper/](https://developers.cloudflare.com/workers-ai/models/whisper/)
- **Base Endpoint**: `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/openai/whisper`

### Model Capabilities
- **Architecture**: OpenAI Whisper neural automatic speech recognition running on Cloudflare edge GPUs.
- **Input**: Binary audio stream (`application/octet-stream`).
- **Output**: JSON payload with segmented timestamps and transcribed text cues.
- **Audio Limits**: Maximum recommended chunk length is 5 minutes (300 seconds) for optimal latency and response reliability.

### Official Quotas & Limits
- **Free Tier Allowance**: Cloudflare provides **10,000 Neurons per day free** across Workers AI models per account (equivalent to several hours of speech recognition audio per day).
- **Paid Tier**: \$0.011 per 1,000 Neurons above the free daily allowance.
- **Rate Limits**: Rate limits (HTTP 429) apply per token/account. The application handles rate limits automatically with exponential backoff and cool-down switching.

### Multi-Account High-Availability Pool
To support long-running overnight batch processing across large video libraries:
- Users can configure up to 10 Cloudflare accounts in the pool.
- If an account encounters quota exhaustion (HTTP 429), it is placed into a temporary cool-down and transcription automatically fails over to the next configured account in the pool.
- Account credentials are validated on usage. Invalid tokens (HTTP 401/403) are reported cleanly rather than causing infinite retry loops.
