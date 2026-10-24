"""
Pytest configuration and shared fixtures for OnlineSub.
"""

import sys
from pathlib import Path
import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def sample_srt_text():
    return (
        "1\n"
        "00:00:01,000 --> 00:00:04,500\n"
        "Hello and welcome to the tutorial.\n\n"
        "2\n"
        "00:00:05,000 --> 00:00:08,200\n"
        "Today we are going to learn about speech recognition.\n\n"
        "3\n"
        "00:00:09,000 --> 00:00:12,000\n"
        "Let's get started right away.\n"
    )


@pytest.fixture
def temp_database(tmp_path):
    from app.core.database import Database
    db_file = tmp_path / "test_onlinesub.db"
    return Database(db_file)
