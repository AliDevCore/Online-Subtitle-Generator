"""
Test Cloudflare Workers AI WebVTT timestamp parsing.
"""

from app.providers.cloudflare_provider import _parse_cloudflare_vtt, _parse_vtt_timestamp


def test_vtt_timestamp_variations():
    assert _parse_vtt_timestamp("05.660") == 5660
    assert _parse_vtt_timestamp("05,660") == 5660
    assert _parse_vtt_timestamp("01:23.456") == 83456
    assert _parse_vtt_timestamp("00:01:23,456") == 83456
    assert _parse_vtt_timestamp("") == 0
    assert _parse_vtt_timestamp("   ") == 0


def test_cloudflare_vtt_parsing():
    sample_vtt = """WEBVTT

 --> 05.660
forever and ever. Amen. But

05.660 --> 06.580
why is it going to

06.580 --> 08.080
be so boring?
"""
    cues = _parse_cloudflare_vtt(sample_vtt)
    assert len(cues) == 3
    assert cues[0].start_ms == 0
    assert cues[0].end_ms == 5660
    assert cues[0].text == "forever and ever. Amen. But"

    assert cues[1].start_ms == 5660
    assert cues[1].end_ms == 6580
    assert cues[1].text == "why is it going to"

    assert cues[2].start_ms == 6580
    assert cues[2].end_ms == 8080
    assert cues[2].text == "be so boring?"
