"""
Cloudflare Workers AI adapter for ASR (@cf/openai/whisper).
Features multi-account pool with automatic failover across up to 10 accounts on 429 / neuron quota exhaustion.
"""

from __future__ import annotations
import json
import logging
import time
from pathlib import Path
from typing import Optional, Tuple, Any, List, Dict
import requests

from app.core.config import VERIFIED_ASR_PROVIDERS
from app.core.config import get_active_account_index, set_active_account_index
from app.core.credential_manager import CredentialManager
from app.core.network_resilience import execute_with_resilience
from app.core.subtitle_segmenter import segment_words_into_cues, resegment_cues, is_hallucination_cue
from app.core.types import SubtitleFile, SubtitleCue, ProviderInfo
from app.providers.base import BaseASRProvider

logger = logging.getLogger("OnlineSubtitleGenerator.Cloudflare")

CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4/accounts"

# Module-level sticky account index and cooldown tracking across chunks and files
_EXHAUSTED_UNTIL: Dict[int, float] = {}
_INVALID_ACCOUNTS: set[int] = set()
_ACTIVE_ACCOUNT_INDEX: int = get_active_account_index()


def _parse_vtt_timestamp(ts: str) -> int:
    """Parse WebVTT timestamp to milliseconds."""
    ts = ts.strip().replace(",", ".")
    if not ts:
        return 0
    # Strip any trailing cue settings (e.g. '00:05.000 line:0% position:50%')
    ts = ts.split()[0]
    parts = ts.split(":")
    try:
        if len(parts) == 1:
            return int(float(parts[0]) * 1000)
        elif len(parts) == 2:
            return int(int(parts[0]) * 60000 + float(parts[1]) * 1000)
        elif len(parts) >= 3:
            return int(int(parts[0]) * 3600000 + int(parts[1]) * 60000 + float(parts[2]) * 1000)
    except Exception:
        return 0
    return 0


def _parse_cloudflare_vtt(vtt_text: str) -> List[SubtitleCue]:
    """Parse Cloudflare Whisper WebVTT response into structured SubtitleCues."""
    blocks = vtt_text.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n\n")
    cues: List[SubtitleCue] = []
    idx = 1
    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        # Strip header/NOTE lines without skipping cues that share the block
        lines = [l for l in lines if not l.startswith("WEBVTT") and not l.startswith("NOTE")]
        if not lines:
            continue

        ts_idx = -1
        for i, line in enumerate(lines):
            if "-->" in line:
                ts_idx = i
                break

        if ts_idx == -1:
            continue

        parts = lines[ts_idx].split("-->")
        st_ms = _parse_vtt_timestamp(parts[0])
        end_ms = _parse_vtt_timestamp(parts[1]) if len(parts) > 1 else st_ms + 2000

        text = " ".join(lines[ts_idx + 1:])
        if text.strip() and end_ms > st_ms and not is_hallucination_cue(text):
            cues.append(SubtitleCue(idx, st_ms, end_ms, text.strip()))
            idx += 1
    return cues


class CloudflareASRProvider(BaseASRProvider):
    """ASR using Cloudflare Workers AI Whisper with multi-account pool."""

    def __init__(self, model_id: str = "@cf/openai/whisper-large-v3-turbo", api_key: Optional[str] = None, **kwargs: Any):
        super().__init__(model_id, api_key, **kwargs)
        self.account_id = kwargs.get("account_id") or CredentialManager.get_credential("cloudflare", "account_id")

    def get_info(self) -> ProviderInfo:
        for p in VERIFIED_ASR_PROVIDERS:
            if p.provider_id == "cloudflare" and p.model_id == self.model_id:
                return p
        return ProviderInfo(
            provider_id="cloudflare",
            display_name="Cloudflare Workers AI",
            model_id=self.model_id,
            model_display_name="OpenAI Whisper Large v3 Turbo (@cf/openai/whisper-large-v3-turbo)",
            pipeline="ASR",
            is_free=True,
            pricing_desc="10,000 Neurons/day free; $0.0005 per audio minute (46.6 Neurons/min)",
            free_tier_desc="10k free daily Neurons on Cloudflare (~214 minutes daily per account)",
            supports_timestamps=True,
            max_duration_sec=300,
            requires_key=True,
            doc_url="https://developers.cloudflare.com/workers-ai/models/whisper-large-v3-turbo/",
        )

    def validate_credentials(self) -> Tuple[bool, str]:
        accounts = [a for a in CredentialManager.get_cloudflare_accounts() if a.get("configured")]
        if not accounts:
            if not self.api_key or len(self.api_key.strip()) < 10:
                return False, "No configured Cloudflare account found. Please configure API Token."
            if not self.account_id or len(self.account_id.strip()) < 10:
                return False, "No configured Cloudflare account found. Please configure Account ID."
        return True, "Cloudflare credentials configured."

    def _execute_transcribe_with_account_pool(
        self,
        audio_bytes: bytes,
        cancel_token: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Execute Whisper transcription using the pool of configured Cloudflare accounts.
        Features:
        - Sticky account rotation: maintains the last successful account across chunks.
        - Cooldown tracking: skips accounts that returned 429 / quota limit until their cooldown expires.
        - Fail-fast authentication: 401/403 marks account invalid immediately without infinite looping.
        - Fail-fast on 4xx client errors (400, 413).
        - Max wait cycle ceiling to prevent indefinite hangs.
        """
        global _ACTIVE_ACCOUNT_INDEX, _EXHAUSTED_UNTIL, _INVALID_ACCOUNTS

        all_accounts = [a for a in CredentialManager.get_cloudflare_accounts() if a.get("configured")]
        if not all_accounts and self.account_id and self.api_key:
            all_accounts = [{"index": 1, "account_id": self.account_id, "api_key": self.api_key, "configured": True}]

        if not all_accounts:
            raise ValueError("No valid Cloudflare accounts configured. Please add an account in Settings.")

        # Re-order accounts so that _ACTIVE_ACCOUNT_INDEX is tried first (sticky rotation)
        sorted_accounts = sorted(
            all_accounts,
            key=lambda a: (0 if a["index"] == _ACTIVE_ACCOUNT_INDEX else (1 if a["index"] > _ACTIVE_ACCOUNT_INDEX else 2), a["index"])
        )

        cycle = 0
        max_wait_cycles = 5
        wait_delay = 60

        while cycle < max_wait_cycles:
            for acct in sorted_accounts:
                if cancel_token and getattr(cancel_token, "is_cancelled", False):
                    raise RuntimeError("Operation cancelled by user.")

                idx = acct["index"]
                if idx in _INVALID_ACCOUNTS:
                    continue

                # Check if account is still in cooldown
                now = time.time()
                if idx in _EXHAUSTED_UNTIL and now < _EXHAUSTED_UNTIL[idx]:
                    logger.info(f"Skipping Cloudflare Account #{idx} (in quota cooldown for another {int(_EXHAUSTED_UNTIL[idx] - now)}s)...")
                    continue

                acct_id = acct["account_id"]
                token = acct["api_key"]

                url = f"{CLOUDFLARE_API_BASE}/{acct_id}/ai/run/{self.model_id}"
                is_turbo = "whisper-large-v3-turbo" in self.model_id.lower()

                logger.info(f"Sending audio ({len(audio_bytes) / 1024:.1f} KB) to Cloudflare (Account #{idx}) [{self.model_id}]...")

                try:
                    if is_turbo:
                        import base64
                        b64_audio = base64.b64encode(audio_bytes).decode("ascii")
                        payload = {
                            "audio": b64_audio,
                            "language": "en",
                            "vad_filter": False,
                            "condition_on_previous_text": False
                        }
                        headers = {
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json"
                        }
                        resp = requests.post(url, headers=headers, json=payload, timeout=120)
                    else:
                        headers = {
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/octet-stream"
                        }
                        resp = requests.post(url, headers=headers, data=audio_bytes, timeout=120)
                except requests.RequestException as e:
                    logger.warning(f"Network error on Cloudflare Account #{idx}: {e}")
                    continue

                # 1. Success 200
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except Exception as json_err:
                        logger.warning(f"Failed to parse Cloudflare JSON on Account #{idx}: {json_err}")
                        continue

                    if data.get("success", False) or "result" in data:
                        _ACTIVE_ACCOUNT_INDEX = idx  # Keep as sticky active account
                        set_active_account_index(idx)
                        if idx in _EXHAUSTED_UNTIL:
                            del _EXHAUSTED_UNTIL[idx]
                        if cancel_token and hasattr(cancel_token, "notify_rate_limit_cleared"):
                            try:
                                cancel_token.notify_rate_limit_cleared("Cloudflare Workers AI")
                            except Exception:
                                pass
                        return data.get("result", {})
                    else:
                        errors = data.get("errors", [])
                        err_msg = "; ".join(e.get("message", "") for e in errors) if errors else "Unknown API error"
                        if "neuron" in err_msg.lower() or "limit" in err_msg.lower():
                            logger.warning(f"Cloudflare Account #{idx} quota exhausted: {err_msg}")
                            _EXHAUSTED_UNTIL[idx] = time.time() + 43200  # 12 hours cooldown (until daily quota reset)
                            continue
                        else:
                            raise RuntimeError(f"Cloudflare error on Account #{idx}: {err_msg}")

                # 2. Rate limit / Quota (429)
                elif resp.status_code == 429:
                    logger.warning(f"Cloudflare Account #{idx} returned 429 Rate Limit / Quota Exceeded.")
                    _EXHAUSTED_UNTIL[idx] = time.time() + 43200  # 12 hours cooldown (until daily quota reset)
                    continue

                # 3. Authentication failure (401 / 403)
                elif resp.status_code in (401, 403):
                    logger.error(f"Cloudflare Account #{idx} authentication failed (HTTP {resp.status_code}).")
                    _INVALID_ACCOUNTS.add(idx)
                    # Check if all configured accounts are invalid
                    valid_remaining = [a for a in all_accounts if a["index"] not in _INVALID_ACCOUNTS]
                    if not valid_remaining:
                        raise RuntimeError(
                            f"Cloudflare Account #{idx} authentication failed (HTTP {resp.status_code}). "
                            f"Please check your Account ID and API Token in Settings."
                        )
                    continue

                # 4. Client error (400, 413, etc.) - Fail fast!
                elif 400 <= resp.status_code < 500:
                    err_snippet = resp.text[:200]
                    raise RuntimeError(f"Cloudflare rejected audio with HTTP {resp.status_code}: {err_snippet}")

                # 5. Server error (5xx)
                else:
                    logger.warning(f"Cloudflare Account #{idx} returned HTTP {resp.status_code}: {resp.text[:200]}")
                    continue

            # Check if all accounts are marked invalid
            valid_remaining = [a for a in all_accounts if a["index"] not in _INVALID_ACCOUNTS]
            if not valid_remaining:
                raise RuntimeError("All configured Cloudflare accounts have invalid credentials. Please update settings.")

            cycle += 1
            if cycle >= max_wait_cycles:
                break

            logger.warning(
                f"All {len(valid_remaining)} Cloudflare account(s) are currently rate-limited or exhausted. "
                f"Waiting {wait_delay}s before retrying (Attempt {cycle}/{max_wait_cycles})..."
            )

            for rem in range(wait_delay, 0, -1):
                if cancel_token and getattr(cancel_token, "is_cancelled", False):
                    raise RuntimeError("Operation cancelled by user.")
                if cancel_token and hasattr(cancel_token, "notify_rate_limit"):
                    try:
                        cancel_token.notify_rate_limit(
                            "Cloudflare Workers AI",
                            rem,
                            cycle,
                            f"All {len(valid_remaining)} Cloudflare accounts exhausted."
                        )
                    except TypeError:
                        cancel_token.notify_rate_limit(
                            f"All {len(valid_remaining)} Cloudflare accounts exhausted. Retrying in {rem}s...",
                            rem
                        )
                    except Exception:
                        pass
                time.sleep(1.0)

            wait_delay = min(wait_delay * 2, 300)

        raise RuntimeError(
            f"All Cloudflare accounts remained exhausted after {max_wait_cycles} retry attempts. "
            f"Free tier quotas reset daily at 00:00 UTC."
        )

    def transcribe(
        self,
        audio_path: Path,
        start_offset_seconds: float,
        duration_seconds: float,
        cancel_token: Optional[Any] = None
    ) -> SubtitleFile:
        valid, msg = self.validate_credentials()
        if not valid:
            raise ValueError(msg)

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        audio_bytes = audio_path.read_bytes()
        result = self._execute_transcribe_with_account_pool(audio_bytes, cancel_token=cancel_token)

        # 1. High-precision word-level sentence and pause-aware segmentation
        words = result.get("words", [])
        cues: List[SubtitleCue] = []
        if words:
            cues = segment_words_into_cues(words, pause_threshold_sec=0.40)

        # 2. If words array was not provided or empty, parse and resegment WebVTT
        if not cues and result.get("vtt"):
            vtt_text = result.get("vtt", "")
            raw_cues = _parse_cloudflare_vtt(vtt_text)
            cues = resegment_cues(raw_cues, pause_threshold_sec=0.40)

        # 3. Parse segments array if vtt was absent or empty
        if not cues and result.get("segments"):
            raw_cues = []
            for seg in result.get("segments", []):
                s_txt = seg.get("text", "").strip()
                s_st = int(float(seg.get("start", 0.0)) * 1000)
                s_end = int(float(seg.get("end", seg.get("start", 0.0) + 1.0)) * 1000)
                if s_txt and s_end > s_st and not is_hallucination_cue(s_txt):
                    raw_cues.append(SubtitleCue(len(raw_cues) + 1, s_st, s_end, s_txt))
            if raw_cues:
                cues = resegment_cues(raw_cues, pause_threshold_sec=0.40)

        # 4. Fallback to raw text if still empty
        if not cues:
            raw_text = result.get("text", "").strip()
            if raw_text and not is_hallucination_cue(raw_text):
                cues.append(SubtitleCue(
                    index=1,
                    start_ms=0,
                    end_ms=int(duration_seconds * 1000),
                    text=raw_text
                ))

        # Filter out any hallucination cues and re-index monotonically
        cues = [c for c in cues if not is_hallucination_cue(c.text)]
        for i, c in enumerate(cues, 1):
            c.index = i

        # Shift timestamps by start_offset_seconds
        offset_ms = int(start_offset_seconds * 1000)
        sub_file = SubtitleFile(cues=cues, language="en")
        if offset_ms > 0:
            sub_file = sub_file.shift_all(offset_ms)

        return sub_file
