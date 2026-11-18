"""
Subtitle refinement and spelling correction service powered by Cloudflare Workers AI LLMs.
Uses @cf/google/gemma-4-26b-a4b-it to fix spelling mistakes, homophone errors, grammar,
and half-spaces (نیم‌فاصله) while strictly preserving cue timestamps.
"""

from __future__ import annotations
import json
import logging
import re
import time
from typing import List, Optional, Callable, Any, Dict
import requests

from app.core.config import get_active_account_index, set_active_account_index
from app.core.credential_manager import CredentialManager
from app.core.types import SubtitleCue, SubtitleFile

logger = logging.getLogger("OnlineSubtitleGenerator.SubtitleRefiner")

CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4/accounts"
DEFAULT_REFINER_MODEL = "@cf/google/gemma-4-26b-a4b-it"

# Re-use quota cooldown tracking from provider level
_LLM_EXHAUSTED_UNTIL: Dict[int, float] = {}
_LLM_INVALID_ACCOUNTS: set[int] = set()


class SubtitleRefinerService:
    """Refines subtitle text using Cloudflare Workers AI LLMs (@cf/google/gemma-4-26b-a4b-it)."""

    def __init__(self, model_id: str = DEFAULT_REFINER_MODEL):
        self.model_id = model_id

    def get_active_engine_name(self) -> str:
        """Return the active AI proofreading engine."""
        return "Cloudflare Workers AI (Gemma 4 26B)"

    def _execute_llm_request(
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
                url = f"{CLOUDFLARE_API_BASE}/{acct_id}/ai/run/{self.model_id}"
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }

                try:
                    resp = requests.post(url, headers=headers, json=payload, timeout=120)
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

    def _build_system_prompt(self, language: str) -> str:
        lang_code = language.strip().lower()
        base_prompt = (
            "You are an expert subtitle proofreader and linguistic editor.\n"
            "Your task is to correct spelling errors, typos, wrong homophones, punctuation, and grammatical mistakes in the provided subtitle cues.\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. Output line-by-line using the exact format '[index] <text>'. Do NOT add, remove, or reorder any index.\n"
            "2. Only fix spelling, homophones, typos, and punctuation. Do NOT summarize or change the meaning.\n"
            "3. Directly output the corrected cues. Do NOT output internal thoughts, chain-of-thought, or markdown explanations."
        )

        if lang_code == "fa":
            return base_prompt + (
                "\n\nPersian Language Specific Rules:\n"
                "- Fix all homophone spelling mistakes (حروف هم‌صدا like گذاردن/گزاردن, راضی/رازی, تصویر/تصفیر, هاله/خاله, اعداد/عداد, ظهر/زهر, ص/س/ث, ز/ض/ظ/ذ, ق/غ, ه/ح).\n"
                "- Use correct half-space (نیم‌فاصله) where appropriate (e.g. می‌رود، کلمه‌ها، بی‌نقص، سال‌ها، لپ‌تاپ).\n"
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
        batch_size: int = 5,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        cancel_token: Optional[Any] = None
    ) -> List[SubtitleCue]:
        """
        Refine subtitle cues text using Gemma 4 LLM in batches.
        Strictly preserves original timestamps and cue counts.
        """
        if not cues:
            return cues

        total_cues = len(cues)
        system_prompt = self._build_system_prompt(language)
        batches = [cues[i:i + batch_size] for i in range(0, total_cues, batch_size)]
        total_batches = len(batches)

        logger.info(f"Refining {total_cues} subtitle cues with {self.model_id} across {total_batches} batches...")

        for b_idx, batch in enumerate(batches, 1):
            if cancel_token and getattr(cancel_token, "is_cancelled", False):
                raise RuntimeError("Operation cancelled by user.")

            pct = 85 + int((b_idx / total_batches) * 12)
            if progress_callback:
                progress_callback(
                    f"Refining subtitles with Gemma 4 26B [Batch {b_idx}/{total_batches}]...",
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
        """Parse '[index] text' response lines from LLM, tolerating markdown and notes."""
        if not output_text:
            return {}

        clean_text = output_text.strip()
        clean_text = re.sub(r"^```[a-zA-Z]*\n", "", clean_text)
        clean_text = re.sub(r"\n```$", "", clean_text)

        result: Dict[int, str] = {}
        for line in clean_text.splitlines():
            line = line.strip()
            if not line:
                continue

            # Match [1] text, **[1] text**, [1]: text, or 1. text
            m = re.search(r'\[?(\d+)\]?[:.]?\s*\**\s*([^*()\n]+?)\s*\**(?:\s*\(.*?\))?$', line)
            if m:
                idx = int(m.group(1))
                val = m.group(2).strip().strip('*').strip()
                if val:
                    result[idx] = val
        return result
