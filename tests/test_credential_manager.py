"""
Tests for credential security, masking, and automatic secret redaction.
"""

from app.core.credential_manager import CredentialManager


def test_mask_key():
    assert CredentialManager.mask_key(None) == "(Not configured)"
    assert CredentialManager.mask_key("") == "(Not configured)"
    assert CredentialManager.mask_key("1234") == "********"
    assert CredentialManager.mask_key("AIzaSyB1234567890XYZ") == "AIza...0XYZ"


def test_sanitize_text_url_and_bearer():
    raw_error = "Failed to connect to https://generativelanguage.googleapis.com/v1beta/models?key=AIzaSySecretKey123 with error 403"
    sanitized = CredentialManager.sanitize_text(raw_error)
    assert "AIzaSySecretKey123" not in sanitized
    assert "key=[REDACTED]" in sanitized

    raw_header = "Authorization: Bearer my_secret_token_abcdef12345"
    sanitized2 = CredentialManager.sanitize_text(raw_header)
    assert "my_secret_token" not in sanitized2
    assert "Bearer [REDACTED]" in sanitized2


def test_sanitize_known_secret():
    secret = "hf_CustomVerySecretToken999"
    text = f"An exception occurred with token {secret} in worker"
    sanitized = CredentialManager.sanitize_text(text, known_secrets=[secret])
    assert secret not in sanitized
    assert "[REDACTED_API_KEY]" in sanitized
