"""
Subtitle refinement and spelling correction service powered by Cloudflare Workers AI LLMs.
Uses @cf/meta/llama-3.3-70b-instruct-fp8-fast to fix spelling mistakes, homophone errors, grammar,
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
DEFAULT_REFINER_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"

# Re-use quota cooldown tracking from provider level
_LLM_EXHAUSTED_UNTIL: Dict[int, float] = {}
_LLM_INVALID_ACCOUNTS: set[int] = set()


class SubtitleRefinerService:
    """Refines subtitle text using Cloudflare Workers AI LLMs (@cf/meta/llama-3.3-70b-instruct-fp8-fast)."""

    def __init__(self, model_id: str = DEFAULT_REFINER_MODEL):
        self.model_id = model_id

    def get_active_engine_name(self) -> str:
        """Return the active AI proofreading engine."""
        return "Cloudflare Workers AI (Llama 3.3 70B)"

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

        if lang_code == "fa":
            return (
                "You are a professional subtitle editor and proofreader.\n"
                "Review and correct the provided subtitle text according to the following instructions:\n\n"
                "1. Spelling and Grammar: Fix all spelling mistakes, grammatical errors, incorrect word usage, and speech-to-text transcription errors (e.g. typos, and homophone errors like ص/س/ث, ز/ض/ظ/ذ, ق/غ, ه/ح).\n"
                "2. Natural Persian: Rewrite awkward, incomplete, or unnatural sentences into fluent, clear, and conversational Persian, while strictly preserving the original speaker's informal tone. Do NOT replace colloquial conversational words (like 'هیچی' or 'میخوایم') with unnatural phrases, and NEVER use non-Persian or foreign characters/words.\n"
                "3. Contextual Accuracy: Understand the overall subject and context before correcting sentences. Resolve mistranscribed words based on their meaning and context (e.g., کالابرگ, کد پستی, کمیته امداد), not just their raw sound.\n"
                "4. Content Correction & Fidelity: Identify and correct obvious transcription errors without inventing facts or details. If a phrase is genuinely unclear, use the safest interpretation.\n"
                "5. Subtitle Structure & Numbering: Strictly output line-by-line using the exact format '[index] <text>'. Preserve all subtitle indices exactly as provided. Do not merge, split, add, or remove subtitle entries.\n"
                "6. Subtitle Formatting: Keep each subtitle concise and readable. Maintain natural sentence flow across consecutive entries without making individual entries unnecessarily long.\n"
                "7. Writing Conventions: Use correct half-spaces (نیم‌فاصله), standard Persian punctuation (، ؟), numbers, and standard spelling conventions. Keep the language conversational rather than overly formal.\n\n"
                "Important requirements:\n"
                "- Preserve the original meaning and intended message.\n"
                "- Do not summarize or omit any information.\n"
                "- Do not translate the subtitles into another language.\n"
                "- Do not add explanations, comments, or editorial notes.\n"
                "- Directly output the corrected entries line-by-line using '[index] <text>'."
            )
        elif lang_code == "ar":
            return (
                "You are a professional subtitle editor and proofreader.\n"
                "Review and correct the provided subtitle text according to the following instructions:\n\n"
                "1. Spelling and Grammar: Fix all spelling errors, grammatical mistakes, hamza (أ/إ/آ/ا), and taa marbuta/ha (ة/ه).\n"
                "2. Natural Arabic: Ensure fluent, natural sentence structure while preserving natural conversational flow.\n"
                "3. Contextual Accuracy: Resolve mistranscribed words based on context and meaning.\n"
                "4. Subtitle Structure: Strictly output line-by-line using the exact format '[index] <text>'. Keep all original indices exactly as provided.\n"
                "5. Writing Conventions: Use accurate Arabic punctuation (، ؟) and standard conventions.\n\n"
                "Important requirements:\n"
                "- Do not summarize, add notes, or change the meaning.\n"
                "- Directly output the corrected entries line-by-line using '[index] <text>'."
            )
        else:
            return (
                "You are a professional subtitle editor and proofreader.\n"
                "Review and correct the provided subtitle text according to the following instructions:\n\n"
                "1. Spelling and Grammar: Fix all spelling mistakes, grammatical errors, and transcription typos.\n"
                "2. Natural Phrasing: Ensure fluent, clear, and natural sentence flow while preserving the speaker's tone.\n"
                "3. Contextual Accuracy: Resolve mistranscribed words based on context and meaning.\n"
                "4. Subtitle Structure: Strictly output line-by-line using the exact format '[index] <text>'. Keep all original indices exactly as provided. Do not merge or split entries.\n"
                "5. Formatting: Keep each subtitle concise and readable with standard punctuation and capitalization.\n\n"
                "Important requirements:\n"
                "- Do not summarize or omit information.\n"
                "- Do not add explanations, notes, or markdown formatting.\n"
                "- Directly output the corrected entries line-by-line using '[index] <text>'."
            )

    def refine_cues(
        self,
        cues: List[SubtitleCue],
        language: str = "en",
        batch_size: int = 200,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        cancel_token: Optional[Any] = None
    ) -> List[SubtitleCue]:
        """
        Refine subtitle cues text using Llama 3.3 70B LLM in batches.
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
                    f"Refining subtitles with Llama 3.3 70B [Batch {b_idx}/{total_batches}]...",
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
