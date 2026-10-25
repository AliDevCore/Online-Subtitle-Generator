"""
Tests for Cloudflare ASR provider adapter with mocked network responses and multi-account rotation.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from app.core.types import SubtitleFile, SubtitleCue
from app.providers.cloudflare_provider import CloudflareASRProvider, _parse_vtt_timestamp


def test_cloudflare_credential_validation():
    with patch("app.core.credential_manager.CredentialManager.get_cloudflare_accounts", return_value=[]):
        p_invalid = CloudflareASRProvider(model_id="@cf/openai/whisper-large-v3-turbo", api_key="")
        valid, msg = p_invalid.validate_credentials()
        assert valid is False

    with patch("app.core.credential_manager.CredentialManager.get_cloudflare_accounts", return_value=[{"index": 1, "account_id": "12345678901234567890", "api_key": "token1234567890", "configured": True}]):
        p_valid = CloudflareASRProvider(model_id="@cf/openai/whisper-large-v3-turbo", api_key="valid")
        valid, msg = p_valid.validate_credentials()
        assert valid is True


@patch("requests.post")
def test_cloudflare_multi_account_failover_on_429(mock_post, tmp_path):
    mock_audio = tmp_path / "test.mp3"
    mock_audio.write_bytes(b"DUMMYAUDIOBYTES")

    # Account 1 returns 429 quota limit, Account 2 returns 200 with result
    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.text = '{"errors": [{"message": "AiError: daily free allocation of 10,000 neurons used up"}]}'

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {
        "success": True,
        "result": {
            "words": [
                {"word": "Hello", "start": 0.0, "end": 0.4},
                {"word": "world.", "start": 0.4, "end": 0.8}
            ]
        }
    }

    mock_post.side_effect = [resp_429, resp_200]

    accounts = [
        {"index": 1, "account_id": "acct1_1234567890", "api_key": "tok1_1234567890", "configured": True},
        {"index": 2, "account_id": "acct2_1234567890", "api_key": "tok2_1234567890", "configured": True}
    ]

    with patch("app.core.credential_manager.CredentialManager.get_cloudflare_accounts", return_value=accounts):
        provider = CloudflareASRProvider()
        sub = provider.transcribe(mock_audio, start_offset_seconds=0.0, duration_seconds=1.0)
        assert len(sub.cues) == 1
        assert sub.cues[0].text == "Hello world."
        # Verify 2 calls were made (Account 1, then Account 2)
        assert mock_post.call_count == 2
