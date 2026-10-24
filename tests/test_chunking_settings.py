"""
Tests for Cloudflare audio chunking settings and duration controls.
"""

from app.core.types import ChunkingSettings
from app.core.config import load_chunking_settings, save_chunking_settings


def test_chunking_settings_defaults():
    cfg = ChunkingSettings()
    assert cfg.enabled is True
    assert cfg.cloudflare_minutes == 5.0
    assert cfg.get_chunk_duration_seconds("cloudflare") == 300.0


def test_chunking_disabled_returns_none():
    cfg = ChunkingSettings(enabled=False)
    assert cfg.get_chunk_duration_seconds("cloudflare") is None


def test_chunking_custom_minutes():
    cfg = ChunkingSettings(enabled=True, cloudflare_minutes=7.5)
    assert cfg.get_chunk_duration_seconds("cloudflare") == 450.0


def test_chunking_serialization_roundtrip():
    original = ChunkingSettings(enabled=False, cloudflare_minutes=4.0)
    d = original.to_dict()
    restored = ChunkingSettings.from_dict(d)
    assert restored.enabled is False
    assert restored.cloudflare_minutes == 4.0
