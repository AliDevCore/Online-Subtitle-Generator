"""
Subtitle refinement and spelling correction service powered by Google Gemini and Cloudflare Workers AI LLMs.
Uses Gemini Flash Multi-Model Rotation Pool (gemini-3.5-flash-lite, gemini-3-flash-preview, gemini-3.8-flash)
and Cloudflare Workers AI (@cf/google/gemma-4-26b-a4b-it) to fix spelling mistakes, homophone errors,
grammar, and half-spaces (نیم‌فاصله) while strictly preserving cue timestamps.
"""

from __future__ import annotations
import json
import logging
import re
import time
from typing import List, Optional, Callable, Any, Dict, Set
import requests

from app.core.config import get_active_account_index, set_active_account_index
from app.core.credential_manager import CredentialManager
from app.core.types import SubtitleCue, SubtitleFile

logger = logging.getLogger("OnlineSubtitleGenerator.SubtitleRefiner")

CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4/accounts"
DEFAULT_CLOUDFLARE_MODEL = "@cf/google/gemma-4-26b-a4b-it"
DEFAULT_REFINER_MODEL = DEFAULT_CLOUDFLARE_MODEL
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

GEMINI_FLASH_ROTATION_POOL: List[str] = [
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
]

# Re-use quota cooldown tracking from provider level
_LLM_EXHAUSTED_UNTIL: Dict[int, float] = {}
_LLM_INVALID_ACCOUNTS: set[int] = set()


class SubtitleRefinerService:
    """Refines subtitle text using Google Gemini or Cloudflare Workers AI."""

    _active_gemini_account_index: Optional[int] = None

    def __init__(self, cloudflare_model_id: str = DEFAULT_CLOUDFLARE_MODEL):
        self.cloudflare_model_id = cloudflare_model_id

    def get_active_engine_name(self) -> str:
        """Return the active AI proofreading engine based on configured credentials."""
        gemini_accounts = [a for a in CredentialManager.get_gemini_accounts() if a.get("configured")]
        if gemini_accounts:
            return "Google Gemini Flash"
        return "Cloudflare Workers AI (Gemma 4 26B)"

    def _execute_gemini_request(
        self,
        system_prompt: str,
        user_prompt: str,
        cancel_token: Optional[Any] = None,
        max_cycles: int = 3
    ) -> str:
        """Call Google Gemini API with 2-layer multi-model and multi-account rotation."""
        all_accounts = [a for a in CredentialManager.get_gemini_accounts() if a.get("configured")]
        if not all_accounts:
            raise ValueError("No valid Google Gemini API keys configured.")

        # Reorder so active account is tried first
        if self._active_gemini_account_index is not None:
            active = [a for a in all_accounts if a["index"] == self._active_gemini_account_index]
            others = [a for a in all_accounts if a["index"] != self._active_gemini_account_index]
            ordered_accounts = active + others
        else:
            ordered_accounts = list(all_accounts)

        full_prompt = f"{system_prompt}\n\nInput Subtitle Cues to Refine:\n{user_prompt}"
        payload = {
            "contents": [
                {
                    "parts": [{"text": full_prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1
            }
        }

        candidates = list(GEMINI_FLASH_ROTATION_POOL)
        invalid_accounts: Set[int] = set()
        deprecated_models: Set[str] = set()
        cycle = 0
        wait_delay = 20

        while cycle < max_cycles:
            if cancel_token and getattr(cancel_token, "is_cancelled", False):
                raise RuntimeError("Operation cancelled by user.")

            active_model_pool = [m for m in candidates if m not in deprecated_models]
            if not active_model_pool:
                active_model_pool = candidates[:1]

            for acct in ordered_accounts:
                acct_idx = acct["index"]
                if acct_idx in invalid_accounts:
                    continue

                api_key = acct["api_key"]
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key
                }

                for model in active_model_pool:
                    if cancel_token and getattr(cancel_token, "is_cancelled", False):
                        raise RuntimeError("Operation cancelled by user.")

                    url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
                    try:
                        resp = requests.post(url, json=payload, headers=headers, timeout=45)

                        if resp.status_code == 200:
                            data = resp.json()
                            candidates_list = data.get("candidates", [])
                            if candidates_list:
                                candidate = candidates_list[0]
                                parts = candidate.get("content", {}).get("parts", [])
                                if parts and any("text" in p for p in parts):
                                    SubtitleRefinerService._active_gemini_account_index = acct_idx
                                    full_text = "".join(p.get("text", "") for p in parts)
                                    return full_text

                        # 404: Model retired or renamed
                        if resp.status_code == 404:
                            deprecated_models.add(model)
                            continue

                        # 400, 401, 403: Invalid API key
                        if resp.status_code in (400, 401, 403):
                            resp_err = resp.text.lower()
                            if "key" in resp_err or "auth" in resp_err or "unauthorized" in resp_err:
                                invalid_accounts.add(acct_idx)
                                break

                        # Rate Limit / Demand Spike (429, 503)
                        is_rate_limited = (resp.status_code in (429, 503))
                        resp_lower = resp.text.lower()
                        if not is_rate_limited and any(w in resp_lower for w in ("rate limit", "quota", "resource_exhausted", "unavailable")):
                            is_rate_limited = True

                        if is_rate_limited:
                            logger.info(f"Gemini model '{model}' busy/rate-limited on Account #{acct_idx}. Rotating...")
                            continue

                        logger.warning(f"Gemini error ({resp.status_code}) on model '{model}': {resp.text[:150]}")
                        continue

                    except requests.RequestException as e:
                        logger.warning(f"Network error on Gemini Account #{acct_idx} (model {model}): {e}")
                        continue

            if len(invalid_accounts) >= len(ordered_accounts):
                raise RuntimeError("All Google Gemini API keys failed authentication.")

            cycle += 1
            if cycle >= max_cycles:
                break
            time.sleep(min(wait_delay, 10))

        raise RuntimeError("Google Gemini refinement pool temporarily unavailable.")

    def _execute_cloudflare_request(
        self,
        system_prompt: str,
        user_prompt: str,
        cancel_token: Optional[Any] = None
    ) -> str:
        """Call Cloudflare Workers AI LLM with multi-account rotation and quota failover."""
        global _LLM_EXHAUSTED_UNTIL, _LLM_INVALID_ACCOUNTS

        all_accounts = [a for a in CredentialManager.get_cloudflare_accounts() if a.get("configured")]
        if not all_accounts:
            raise ValueError("No valid Cloudflare accounts configured.")

        active_idx = get_active_account_index()
        sorted_accounts = sorted(
            all_accounts,
            key=lambda a: (0 if a["index"] == active_idx else (1 if a["index"] > active_idx else 2), a["index"])
        )

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 4096,
            "temperature": 0.1
        }

        cycle = 0
        max_wait_cycles = 3
        wait_delay = 30

        while cycle < max_wait_cycles:
            for acct in sorted_accounts:
                if cancel_token and getattr(cancel_token, "is_cancelled", False):
                    raise RuntimeError("Operation cancelled by user.")

                idx = acct["index"]
                if idx in _LLM_INVALID_ACCOUNTS:
                    continue

                now = time.time()
                if idx in _LLM_EXHAUSTED_UNTIL and now < _LLM_EXHAUSTED_UNTIL[idx]:
                    continue

                acct_id = acct["account_id"]
                token = acct["api_key"]
                url = f"{CLOUDFLARE_API_BASE}/{acct_id}/ai/run/{self.cloudflare_model_id}"
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }

                try:
                    resp = requests.post(url, headers=headers, json=payload, timeout=90)
                except requests.RequestException as e:
                    logger.warning(f"Network error on LLM Account #{idx}: {e}")
                    continue

                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except Exception:
                        continue

                    if data.get("success", False) or "result" in data:
                        set_active_account_index(idx)
                        res = data.get("result", {})
                        if isinstance(res, dict):
                            # Handle OpenAI-compatible choices response
                            choices = res.get("choices", [])
                            if choices and isinstance(choices, list):
                                return choices[0].get("message", {}).get("content", "") or ""
                            return res.get("response", "") or ""
                        elif isinstance(res, str):
                            return res
                        return ""
                    else:
                        errors = data.get("errors", [])
                        err_msg = "; ".join(e.get("message", "") for e in errors)
                        if "neuron" in err_msg.lower() or "limit" in err_msg.lower():
                            _LLM_EXHAUSTED_UNTIL[idx] = time.time() + 43200
                            continue
                        else:
                            logger.warning(f"LLM error on Account #{idx}: {err_msg}")
                            continue

                elif resp.status_code == 429:
                    _LLM_EXHAUSTED_UNTIL[idx] = time.time() + 43200
                    continue

                elif resp.status_code in (401, 403):
                    _LLM_INVALID_ACCOUNTS.add(idx)
                    continue

            cycle += 1
            if cycle >= max_wait_cycles:
                break
            time.sleep(min(wait_delay, 10))

        raise RuntimeError("Cloudflare LLM refinement accounts temporarily unavailable.")

    def _execute_llm_request(
        self,
        system_prompt: str,
        user_prompt: str,
        cancel_token: Optional[Any] = None
    ) -> str:
        """Route to Google Gemini if configured, otherwise fallback to Cloudflare Workers AI."""
        gemini_accounts = [a for a in CredentialManager.get_gemini_accounts() if a.get("configured")]
        if gemini_accounts:
            try:
                return self._execute_gemini_request(system_prompt, user_prompt, cancel_token=cancel_token)
            except Exception as e:
                logger.warning(f"Gemini refinement failed ({e}), attempting Cloudflare fallback...")
                cloudflare_accounts = [a for a in CredentialManager.get_cloudflare_accounts() if a.get("configured")]
                if cloudflare_accounts:
                    return self._execute_cloudflare_request(system_prompt, user_prompt, cancel_token=cancel_token)
                raise e
        return self._execute_cloudflare_request(system_prompt, user_prompt, cancel_token=cancel_token)

    def _build_system_prompt(self, language: str) -> str:
        lang_code = language.strip().lower()
        base_prompt = (
            "You are an expert subtitle proofreader and linguistic editor.\n"
            "Your task is to correct spelling errors, typos, wrong homophones, punctuation, and grammatical mistakes in the provided subtitle cues.\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. You MUST keep the exact line prefix format '[index] <text>'. Do NOT add, remove, or reorder any index.\n"
            "2. Only fix spelling, homophones, typos, and punctuation. Do NOT summarize, delete words, or change the intended meaning.\n"
            "3. Be fast, direct, and concise. Do NOT output internal thoughts, chain-of-thought reasoning, markdown blocks, or thinking tags.\n"
            "4. Output ONLY the numbered lines without any markdown formatting, preamble, code blocks, or explanations."
        )

        if lang_code == "fa":
            return base_prompt + (
                "\n\nPersian Language Specific Rules:\n"
                "- Fix all homophone spelling mistakes (حروف هم‌صدا like گذاردن/گزاردن, راضی/رازی, تصویر/تصفیر, هاله/خاله, اعداد/عداد, ظهر/زهر, ص/س/ث, ز/ض/ظ/ذ, ق/غ, ه/ح).\n"
                "- Use correct half-space (نیم‌فاصله) where appropriate (e.g. می‌رود، کلمه‌ها، بی‌نقص، سال‌ها).\n"
                "- Preserve natural conversational/spoken tone (e.g. if the speaker said 'میخوایم' or 'عجیبن', fix typos or wrong letters without turning it into artificial formal text, but fix 'راجب' to 'راجع‌به' and 'گذارش' to 'گزارش').\n"
                "- Add commas and question marks correctly based on sentence structure."
            )
        elif lang_code == "ar":
            return base_prompt + (
                "\n\nArabic Language Specific Rules:\n"
                "- Fix hamza mistakes (أ/إ/آ/ا) and taa marbuta/ha (ة/ه).\n"
                "- Fix homophones and common colloquial spelling errors.\n"
                "- Ensure accurate Arabic punctuation (، ؟)."
            )
        else:
            return base_prompt + (
                "\n\nGeneral Rules:\n"
                "- Fix spelling errors, typos, capitalization, and punctuation.\n"
                "- Fix common homophones (e.g., their/there/they're, its/it's)."
            )

    def refine_cues(
        self,
        cues: List[SubtitleCue],
        language: str = "en",
        batch_size: int = 150,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        cancel_token: Optional[Any] = None
    ) -> List[SubtitleCue]:
        """
        Refine subtitle cues text using AI (Gemini Flash or Cloudflare Gemma) in batches.
        Strictly preserves original timestamps and cue counts.
        """
        if not cues:
            return cues

        total_cues = len(cues)
        system_prompt = self._build_system_prompt(language)
        batches = [cues[i:i + batch_size] for i in range(0, total_cues, batch_size)]
        total_batches = len(batches)
        engine_name = self.get_active_engine_name()

        logger.info(f"Refining {total_cues} subtitle cues with {engine_name} across {total_batches} batches...")

        for b_idx, batch in enumerate(batches, 1):
            if cancel_token and getattr(cancel_token, "is_cancelled", False):
                raise RuntimeError("Operation cancelled by user.")

            pct = 85 + int((b_idx / total_batches) * 12)
            if progress_callback:
                progress_callback(
                    f"Refining subtitles with {engine_name} [Batch {b_idx}/{total_batches}]...",
                    pct
                )

            # Build line-by-line input
            lines = [f"[{c.index}] {c.text.strip()}" for c in batch]
            user_prompt = "\n".join(lines)

            try:
                raw_output = self._execute_llm_request(system_prompt, user_prompt, cancel_token=cancel_token)
                refined_map = self._parse_llm_output(raw_output)

                # Update cues with refined text
                for c in batch:
                    if c.index in refined_map and refined_map[c.index].strip():
                        c.text = refined_map[c.index].strip()

            except Exception as e:
                logger.warning(f"Batch {b_idx} LLM refinement skipped due to error: {e}")
                # Fallback to original cues for this batch

        return cues

    @staticmethod
    def _parse_llm_output(output_text: str) -> Dict[int, str]:
        """Parse '[index] text' or 'index. text' response lines from LLM."""
        clean_text = output_text.strip()
        # Remove any markdown code fences if present
        clean_text = re.sub(r"^```[a-zA-Z]*\n", "", clean_text)
        clean_text = re.sub(r"\n```$", "", clean_text)

        result: Dict[int, str] = {}
        for line in clean_text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^\[?(\d+)\]?[:.]?\s*(.+)$", line)
            if m:
                idx = int(m.group(1))
                txt = m.group(2).strip()
                result[idx] = txt
        return result
