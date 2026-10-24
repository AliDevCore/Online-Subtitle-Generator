"""
Network resilience, exponential backoff, rate-limit detection, and auto-retry handling.
Provides unattended overnight fault tolerance for AI API providers (Cloudflare, Gemini, etc.).
"""

from __future__ import annotations
import logging
import time
from typing import Optional, Callable, Any
import requests
from app.core.credential_manager import CredentialManager

logger = logging.getLogger("OnlineSub.Resilience")


def execute_with_resilience(
    request_func: Callable[[], requests.Response],
    provider_name: str,
    cancel_token: Optional[Any] = None,
    base_delay_seconds: int = 60,
    max_delay_seconds: int = 600,
    max_retries: int = 999999
) -> requests.Response:
    """
    Execute an HTTP request with continuous resilience against rate limits (HTTP 429),
    server overloads (HTTP 503), and transient network errors.
    
    If rate limit is hit:
    - Notifies cancel_token via notify_rate_limit(provider_name, remaining_sec, attempt, reason) every second.
    - Checks cancel_token.is_cancelled every second so cancellation remains instantaneous.
    - Clears rate limit banner via cancel_token.notify_rate_limit_cleared(provider_name) on success.
    """
    attempt = 0
    current_delay = base_delay_seconds

    while attempt < max_retries:
        if cancel_token and getattr(cancel_token, "is_cancelled", False):
            raise RuntimeError("Operation cancelled by user.")

        try:
            resp = request_func()

            # Success
            if resp.status_code == 200:
                if cancel_token and hasattr(cancel_token, "notify_rate_limit_cleared"):
                    try:
                        cancel_token.notify_rate_limit_cleared(provider_name)
                    except Exception:
                        pass
                return resp

            # Rate Limit (429) or Server Unavailable (503)
            is_rate_limited = (resp.status_code in (429, 503))
            resp_lower = resp.text.lower()
            if not is_rate_limited and ("rate limit" in resp_lower or "quota" in resp_lower):
                is_rate_limited = True

            if is_rate_limited:
                attempt += 1
                # Check for Retry-After header
                retry_after = resp.headers.get("Retry-After")
                wait_sec = current_delay
                if retry_after:
                    try:
                        wait_sec = int(float(retry_after))
                    except (ValueError, TypeError):
                        pass

                wait_sec = max(15, min(wait_sec, max_delay_seconds))

                sanitized_msg = CredentialManager.sanitize_text(resp.text)
                clean_reason = f"سهمیه یا محدودیت نرخ سرویس {provider_name} فعال شد (کد {resp.status_code})"
                if "quota" in resp_lower:
                    clean_reason = f"سهمیه موقت سرویس {provider_name} پر شده است. در حال انتظار برای آزادسازی..."

                logger.warning(
                    f"[{provider_name}] Rate limited ({resp.status_code}, attempt {attempt}). "
                    f"Waiting {wait_sec}s before next retry. Raw: {sanitized_msg[:120]}"
                )

                # Second-by-second countdown with instantaneous cancel check
                for rem in range(wait_sec, 0, -1):
                    if cancel_token and getattr(cancel_token, "is_cancelled", False):
                        raise RuntimeError("Operation cancelled by user.")

                    if cancel_token and hasattr(cancel_token, "notify_rate_limit"):
                        try:
                            cancel_token.notify_rate_limit(provider_name, rem, attempt, clean_reason)
                        except Exception:
                            pass

                    time.sleep(1)

                # Increase delay exponentially for subsequent attempts (up to max_delay)
                current_delay = min(current_delay * 2, max_delay_seconds)
                continue

            # Non-recoverable fatal errors (e.g. 400 Bad Request, 401 Unauthorized, 403 Forbidden)
            sanitized = CredentialManager.sanitize_text(resp.text)
            raise RuntimeError(f"{provider_name} API error ({resp.status_code}): {sanitized}")

        except requests.exceptions.RequestException as e:
            # Network drops, DNS issues, or connection timeouts
            attempt += 1
            wait_sec = 20
            clean_reason = f"خطای ارتباط با سرور {provider_name}. تلاش مجدد تا برقراری اینترنت..."
            logger.warning(f"[{provider_name}] Network error: {e}. Retrying in {wait_sec}s...")

            for rem in range(wait_sec, 0, -1):
                if cancel_token and getattr(cancel_token, "is_cancelled", False):
                    raise RuntimeError("Operation cancelled by user.")

                if cancel_token and hasattr(cancel_token, "notify_rate_limit"):
                    try:
                        cancel_token.notify_rate_limit(provider_name, rem, attempt, clean_reason)
                    except Exception:
                        pass

                time.sleep(1)
            continue

    raise RuntimeError(f"{provider_name} request exceeded maximum retry limits.")
