"""
Provider factory and registry for Online Subtitle Generator.
"""

from __future__ import annotations
from typing import Optional, Any
from app.core.credential_manager import CredentialManager
from app.providers.base import BaseASRProvider
from app.providers.cloudflare_provider import CloudflareASRProvider


def get_asr_provider(
    provider_id: str = "cloudflare",
    model_id: str = "@cf/openai/whisper",
    api_key: Optional[str] = None,
    **kwargs: Any
) -> BaseASRProvider:
    """Instantiate the Cloudflare ASR provider adapter with secure credentials."""
    return CloudflareASRProvider(model_id=model_id, api_key=api_key, **kwargs)
