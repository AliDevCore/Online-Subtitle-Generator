"""
Secure API credential storage using Windows Credential Manager (via keyring).
API keys and secrets are never stored in plaintext settings, SQLite databases, or logs.
Supports up to 10 Cloudflare accounts for automatic rotation upon quota exhaustion.
"""

from __future__ import annotations
import logging
from typing import Optional, Dict, List, Any
import keyring

logger = logging.getLogger("OnlineSubtitleGenerator.Security")

SERVICE_NAME_PREFIX = "OnlineSubtitleGenerator"


class CredentialManager:
    """Manages secure persistence and retrieval of API credentials."""

    # In-memory cache to prevent repeated blocking OS keyring / DPAPI queries during logging
    _CREDENTIALS_CACHE: Dict[str, Optional[str]] = {}
    _ACCOUNTS_CACHE: Optional[List[Dict[str, Any]]] = None

    @classmethod
    def invalidate_cache(cls):
        """Clear memory cache when credentials are updated."""
        cls._CREDENTIALS_CACHE.clear()
        cls._ACCOUNTS_CACHE = None

    @staticmethod
    def _service_key(provider_id: str, field_name: str = "api_key") -> str:
        return f"{SERVICE_NAME_PREFIX}_{provider_id}_{field_name}"

    @classmethod
    def get_credential(cls, provider_id: str, field_name: str = "api_key") -> Optional[str]:
        """Retrieve credential securely from Windows Credential Manager with caching."""
        service = cls._service_key(provider_id, field_name)
        if service in cls._CREDENTIALS_CACHE:
            return cls._CREDENTIALS_CACHE[service]

        try:
            val = keyring.get_password(service, "OnlineSubUser")
            if not val and SERVICE_NAME_PREFIX != "OnlineSub":
                # Fallback to legacy OnlineSub prefix for smooth migration
                legacy_service = f"OnlineSub_{provider_id}_{field_name}"
                val = keyring.get_password(legacy_service, "OnlineSubUser")
            res = val if val else None
            cls._CREDENTIALS_CACHE[service] = res
            return res
        except Exception as e:
            logger.warning(f"Failed to read credential for {provider_id}/{field_name}: {e}")
            cls._CREDENTIALS_CACHE[service] = None
            return None

    @classmethod
    def set_credential(cls, provider_id: str, secret_value: str, field_name: str = "api_key") -> bool:
        """Store credential securely in Windows Credential Manager."""
        cls.invalidate_cache()
        service = cls._service_key(provider_id, field_name)
        try:
            if not secret_value:
                return cls.delete_credential(provider_id, field_name)
            keyring.set_password(service, "OnlineSubUser", secret_value.strip())
            logger.info(f"Credential updated for {provider_id}/{field_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to store credential for {provider_id}/{field_name}: {e}")
            return False

    @classmethod
    def delete_credential(cls, provider_id: str, field_name: str = "api_key") -> bool:
        """Remove credential from Windows Credential Manager."""
        cls.invalidate_cache()
        service = cls._service_key(provider_id, field_name)
        try:
            keyring.delete_password(service, "OnlineSubUser")
            logger.info(f"Credential removed for {provider_id}/{field_name}")
            return True
        except keyring.errors.PasswordDeleteError:
            return True
        except Exception as e:
            logger.warning(f"Failed to delete credential for {provider_id}/{field_name}: {e}")
            return False

    @classmethod
    def get_cloudflare_accounts(cls, max_accounts: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieve all configured Cloudflare accounts (up to max_accounts).
        Cached in-memory to prevent hundreds of OS DPAPI calls per minute.
        """
        if cls._ACCOUNTS_CACHE is not None:
            return cls._ACCOUNTS_CACHE

        accounts = []
        for idx in range(1, max_accounts + 1):
            if idx == 1:
                acct = cls.get_credential("cloudflare", "account_id_1") or cls.get_credential("cloudflare", "account_id")
                key = cls.get_credential("cloudflare", "api_key_1") or cls.get_credential("cloudflare", "api_key")
            else:
                acct = cls.get_credential("cloudflare", f"account_id_{idx}")
                key = cls.get_credential("cloudflare", f"api_key_{idx}")

            is_configured = bool(acct and key and len(acct.strip()) > 5 and len(key.strip()) > 5)
            accounts.append({
                "index": idx,
                "account_id": (acct or "").strip(),
                "api_key": (key or "").strip(),
                "configured": is_configured
            })
        cls._ACCOUNTS_CACHE = accounts
        return accounts

    @classmethod
    def set_cloudflare_account(cls, index: int, account_id: str, api_key: str) -> bool:
        """Save a specific Cloudflare account slot (1 to 10)."""
        if index < 1 or index > 10:
            return False

        ok1 = cls.set_credential("cloudflare", account_id, f"account_id_{index}")
        ok2 = cls.set_credential("cloudflare", api_key, f"api_key_{index}")

        # Keep slot 1 mirrored to default account_id and api_key
        if index == 1:
            cls.set_credential("cloudflare", account_id, "account_id")
            cls.set_credential("cloudflare", api_key, "api_key")

        cls.invalidate_cache()
        return ok1 and ok2

    @classmethod
    def delete_cloudflare_account(cls, index: int) -> bool:
        """Delete a specific Cloudflare account slot."""
        cls.delete_credential("cloudflare", f"account_id_{index}")
        cls.delete_credential("cloudflare", f"api_key_{index}")
        if index == 1:
            cls.delete_credential("cloudflare", "account_id")
            cls.delete_credential("cloudflare", "api_key")
        cls.invalidate_cache()
        return True

    @classmethod
    def mask_key(cls, key: Optional[str]) -> str:
        """Return masked representation of a secret (e.g. 1234...XYZ or (Not configured))."""
        if not key or len(key.strip()) == 0:
            return "(Not configured)"
        stripped = key.strip()
        if len(stripped) <= 8:
            return "********"
        return f"{stripped[:4]}...{stripped[-4:]}"

    @classmethod
    def sanitize_text(cls, text: str, known_secrets: Optional[list[str]] = None) -> str:
        """Redact sensitive keys from exception strings, URLs, and log messages."""
        if not text:
            return ""
        sanitized = text

        if known_secrets:
            for s in known_secrets:
                if s and len(s) > 4:
                    sanitized = sanitized.replace(s, "[REDACTED_API_KEY]")

        for acct in cls.get_cloudflare_accounts():
            for secret in (acct.get("api_key"), acct.get("account_id")):
                if secret and len(secret) > 6:
                    sanitized = sanitized.replace(secret, "[REDACTED]")

        import re
        sanitized = re.sub(r'(key=)[^&\s]+', r'\1[REDACTED]', sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r'(Bearer\s+)[a-zA-Z0-9_\-\.]{10,}', r'\1[REDACTED]', sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r'(/accounts/)[a-zA-Z0-9_\-\.]{10,}(/)', r'\1[REDACTED_ACCOUNT]\2', sanitized, flags=re.IGNORECASE)
        return sanitized
