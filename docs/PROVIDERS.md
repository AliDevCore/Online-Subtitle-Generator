# Verified Speech Recognition Provider Documentation

*Verification Date: October 2026*

Online Subtitle Generator utilizes **Cloudflare Workers AI** as its primary speech recognition engine for ultra-fast, cloud-hosted Whisper transcription.

---

## Cloudflare Workers AI (`@cf/openai/whisper-large-v3-turbo`)

### Official Documentation
- **Workers AI Models**: [https://developers.cloudflare.com/workers-ai/models/](https://developers.cloudflare.com/workers-ai/models/)
- **Whisper Large v3 Turbo Documentation**: [https://developers.cloudflare.com/workers-ai/models/whisper-large-v3-turbo/](https://developers.cloudflare.com/workers-ai/models/whisper-large-v3-turbo/)
- **Base Endpoint**: `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/openai/whisper-large-v3-turbo`

### Model Capabilities
- **Architecture**: OpenAI Whisper Large v3 Turbo neural automatic speech recognition running on Cloudflare edge GPUs.
- **Input**: Base64 JSON payload with native `vad_filter: true` and `condition_on_previous_text: false`.
- **Output**: JSON payload with segmented timestamps, word breakdown, and transcribed text cues.
- **Audio Limits**: Maximum recommended chunk length is 5 minutes (300 seconds) for optimal latency and response reliability.

### Official Quotas & Limits
- **Free Tier Allowance**: Cloudflare provides **10,000 Neurons per day free** across Workers AI models per account (equivalent to ~214 minutes / 3.5+ hours of audio per account daily at 46.6 Neurons/min).
- **Paid Tier**: \$0.0005 per audio minute ($0.011 per 1,000 Neurons).
- **Rate Limits**: Rate limits (HTTP 429) apply per token/account. The application handles rate limits automatically with exponential backoff and cool-down switching.

### Multi-Account High-Availability Pool
To support long-running overnight batch processing across large video libraries:
- Users can configure up to 10 Cloudflare accounts in the pool.
- If an account encounters quota exhaustion (HTTP 429), it is placed into a temporary cool-down and transcription automatically fails over to the next configured account in the pool.
- Account credentials are validated on usage. Invalid tokens (HTTP 401/403) are reported cleanly rather than causing infinite retry loops.
