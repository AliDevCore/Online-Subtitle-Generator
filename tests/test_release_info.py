import os
import pytest
from scripts.determine_release_info import (
    parse_version_tuple,
    determine_tag_and_title,
    get_base_version_from_pyproject
)


def test_parse_version_tuple():
    assert parse_version_tuple("v1.0.9") == (1, 0, 9)
    assert parse_version_tuple("v1.0.10") == (1, 0, 10)
    assert parse_version_tuple("2.3.4") == (2, 3, 4)
    assert parse_version_tuple("invalid") == (0,)


def test_determine_tag_with_env_override(monkeypatch):
    monkeypatch.setenv("INPUT_TAG", "v2.5.0")
    monkeypatch.setenv("INPUT_TITLE", "Custom Release 2.5")
    tag, title = determine_tag_and_title()
    assert tag == "v2.5.0"
    assert title == "Custom Release 2.5"


def test_determine_tag_from_tag_ref(monkeypatch):
    monkeypatch.delenv("INPUT_TAG", raising=False)
    monkeypatch.setenv("GITHUB_REF", "refs/tags/v1.5.0")
    monkeypatch.setenv("GITHUB_REF_NAME", "v1.5.0")
    tag, title = determine_tag_and_title()
    assert tag == "v1.5.0"
    assert "v1.5.0" in title


def test_get_base_version_from_pyproject():
    version = get_base_version_from_pyproject()
    assert bool(version and version[0].isdigit())
