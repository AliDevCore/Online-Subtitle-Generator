"""
Application configuration, verified provider metadata, and constants.
"""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
from app.core.types import ProviderInfo, PerformanceSettings, ChunkingSettings


APP_NAME = "Online Subtitle Generator"
APP_VERSION = "1.0.10"
APP_AUTHOR = "OnlineSub"

# Determine base paths and portable mode
IS_FROZEN = getattr(sys, "frozen", False)
if IS_FROZEN:
    APP_DIR = Path(sys.executable).parent.resolve()
else:
    APP_DIR = Path(__file__).resolve().parent.parent.parent

# Check for portable mode indicator (presence of portable.txt or data directory beside exe)
PORTABLE_FLAG_FILE = APP_DIR / "portable.txt"
PORTABLE_DATA_DIR = APP_DIR / "data"

# Determine user data directory with robust write-permission fallback
if PORTABLE_FLAG_FILE.exists() or PORTABLE_DATA_DIR.exists():
    IS_PORTABLE = True
    USER_DATA_DIR = PORTABLE_DATA_DIR
else:
    IS_PORTABLE = False
    appdata = os.environ.get("APPDATA")
    if appdata:
        USER_DATA_DIR = Path(appdata) / "OnlineSubtitleGenerator"
    else:
        USER_DATA_DIR = Path.home() / ".onlinesubtitlegenerator"

try:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    _test = USER_DATA_DIR / ".write_test"
    _test.touch()
    _test.unlink()
except (PermissionError, OSError):
    # Directory beside executable is write-protected (e.g. Program Files); fallback gracefully to %APPDATA%
    IS_PORTABLE = False
    appdata = os.environ.get("APPDATA")
    if appdata:
        USER_DATA_DIR = Path(appdata) / "OnlineSubtitleGenerator"
    else:
        USER_DATA_DIR = Path.home() / ".onlinesubtitlegenerator"
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE = USER_DATA_DIR / "settings.json"
DATABASE_FILE = USER_DATA_DIR / "onlinesubtitlegenerator.db"
LOGS_DIR = USER_DATA_DIR / "logs"
CACHE_DIR = USER_DATA_DIR / "temp"

try:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

# Default performance settings
DEFAULT_PERFORMANCE_SETTINGS = PerformanceSettings(
    cpu_usage_target=100,
    process_priority="Normal",
    cpu_threads="Automatic",
    ram_limit="Automatic",
    affinity_cpus=None
)

# Default audio chunking settings
DEFAULT_CHUNKING_SETTINGS = ChunkingSettings(
    enabled=True,
    cloudflare_minutes=5.0,
)


def get_app_icon():
    """Find and return the application icon across all deployment environments."""
    from PySide6.QtGui import QIcon
    candidates = [
        APP_DIR / "assets" / "app_icon.ico",
        APP_DIR / "assets" / "app_icon.png",
        APP_DIR / "_internal" / "assets" / "app_icon.ico",
        APP_DIR / "_internal" / "assets" / "app_icon.png",
        Path(__file__).resolve().parent.parent.parent / "assets" / "app_icon.ico",
        Path(__file__).resolve().parent.parent.parent / "assets" / "app_icon.png",
    ]
    if hasattr(sys, "_MEIPASS"):
        candidates.insert(0, Path(sys._MEIPASS) / "assets" / "app_icon.ico")
        candidates.insert(1, Path(sys._MEIPASS) / "assets" / "app_icon.png")

    for p in candidates:
        if p.exists():
            icon = QIcon(str(p))
            if not icon.isNull():
                return icon
    return QIcon()


def load_chunking_settings() -> ChunkingSettings:
    """Load persisted audio chunking preferences or return defaults."""
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if "chunking" in data:
                return ChunkingSettings.from_dict(data["chunking"])
        except Exception:
            pass
    return ChunkingSettings()


def save_chunking_settings(settings: ChunkingSettings) -> None:
    """Persist audio chunking preferences to settings.json."""
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if SETTINGS_FILE.exists():
            try:
                existing = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing["chunking"] = settings.to_dict()
        SETTINGS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_active_account_index() -> int:
    """Retrieve the last successful active Cloudflare account index (1 to 10)."""
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return int(data.get("active_account_index", 1))
        except Exception:
            pass
    return 1


def set_active_account_index(index: int) -> None:
    """Persist the active Cloudflare account index for sticky failover across sessions."""
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if SETTINGS_FILE.exists():
            try:
                existing = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing["active_account_index"] = int(index)
        SETTINGS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception:
        pass


# ============================================================================
# Verified AI Providers & Model Registry
# Date of verification: October 2026
# Official documentation links and verified capabilities
# ============================================================================

# Pipeline A: Speech Recognition (Cloudflare Workers AI dedicated engine)
VERIFIED_ASR_PROVIDERS: List[ProviderInfo] = [
    ProviderInfo(
        provider_id="cloudflare",
        display_name="Cloudflare Workers AI",
        model_id="@cf/openai/whisper-large-v3-turbo",
        model_display_name="OpenAI Whisper Large v3 Turbo (@cf/openai/whisper-large-v3-turbo)",
        pipeline="ASR",
        is_free=True,
        pricing_desc="10,000 Neurons/day free; Paid: $0.0005 per audio minute (46.6 Neurons/min)",
        free_tier_desc="Free tier offers 10,000 Neurons daily (~214 minutes / 3.5+ hours of audio daily per account)",
        supports_timestamps=True,
        max_duration_sec=300,  # 5-minute chunks default
        requires_key=True,
        doc_url="https://developers.cloudflare.com/workers-ai/models/whisper-large-v3-turbo/",
        verification_date="2026-10"
    ),
]

# Online Subtitle Generator is focused exclusively on Speech Recognition (ASR)
VERIFIED_TRANSLATION_PROVIDERS: List[ProviderInfo] = []
