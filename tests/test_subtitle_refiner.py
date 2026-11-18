"""
Tests for SubtitleRefinerService (Cloudflare Workers AI Llama 3.3 70B AI proofreader and spell-checker).
"""

from unittest.mock import patch, MagicMock
import pytest

from app.core.types import SubtitleCue
from app.services.subtitle_refiner_service import SubtitleRefinerService, _LLM_EXHAUSTED_UNTIL, _LLM_INVALID_ACCOUNTS


def setup_function():
    _LLM_EXHAUSTED_UNTIL.clear()
    _LLM_INVALID_ACCOUNTS.clear()


def test_parse_llm_output():
    refiner = SubtitleRefinerService()
    raw = """```text
[1] سلام حالتون چطوره؟
[2] امروز می‌خواهیم راجع‌به گزارش صحبت کنیم.
```"""
    parsed = refiner._parse_llm_output(raw)
    assert len(parsed) == 2
    assert parsed[1] == "سلام حالتون چطوره؟"
    assert parsed[2] == "امروز می‌خواهیم راجع‌به گزارش صحبت کنیم."


def test_parse_llm_output_with_markdown_and_notes():
    refiner = SubtitleRefinerService()
    raw = """Here are the corrected versions:
**[1] سلام چطورید؟**
*(Correction: Changed چهتورید to چطورید)*
**[2] بالاخره**
*(Correction: Changed بلاخره to بالاخره)*"""
    parsed = refiner._parse_llm_output(raw)
    assert len(parsed) == 2
    assert parsed[1] == "سلام چطورید؟"
    assert parsed[2] == "بالاخره"


@patch("requests.post")
def test_refine_cues_homophone_correction(mock_post):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "success": True,
        "result": {
            "choices": [
                {
                    "message": {
                        "content": "[1] حیاط خانه زیبا بود\n[2] راجع‌به این گزارش صحبت کردیم"
                    }
                }
            ]
        }
    }
    mock_post.return_value = resp

    cf_accounts = [{"index": 1, "account_id": "acct_test", "api_key": "tok_test", "configured": True}]

    with patch("app.core.credential_manager.CredentialManager.get_cloudflare_accounts", return_value=cf_accounts):
        refiner = SubtitleRefinerService()
        assert refiner.get_active_engine_name() == "Cloudflare Workers AI (Llama 3.3 70B)"
        cues = [
            SubtitleCue(index=1, start_ms=0, end_ms=2000, text="حیات خانه زیبا بود"),
            SubtitleCue(index=2, start_ms=2100, end_ms=4500, text="راجب این گذارش صحبت کردیم")
        ]

        refined = refiner.refine_cues(cues, language="fa")

        # Verify timestamps are 100% untouched
        assert refined[0].start_ms == 0
        assert refined[0].end_ms == 2000
        assert refined[1].start_ms == 2100
        assert refined[1].end_ms == 4500

        # Verify text was corrected
        assert refined[0].text == "حیاط خانه زیبا بود"
        assert refined[1].text == "راجع‌به این گزارش صحبت کردیم"


@patch("requests.post")
def test_refiner_fallback_on_network_failure(mock_post):
    mock_post.side_effect = RuntimeError("Network error")

    cf_accounts = [{"index": 1, "account_id": "acct_test", "api_key": "tok_test", "configured": True}]

    with patch("app.core.credential_manager.CredentialManager.get_cloudflare_accounts", return_value=cf_accounts):
        refiner = SubtitleRefinerService()
        cues = [
            SubtitleCue(index=1, start_ms=1000, end_ms=3000, text="Original Text")
        ]

        # Should not raise; graceful fallback to original cues
        refined = refiner.refine_cues(cues, language="en")
        assert len(refined) == 1
        assert refined[0].text == "Original Text"
