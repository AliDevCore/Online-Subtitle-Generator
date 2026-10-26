"""
Determine the release tag and title for GitHub Actions and local release tooling.
Supports automatic patch incrementing, manual workflow_dispatch overrides,
and tag push events.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent


def get_git_tags() -> List[str]:
    """Retrieve all local tags sorted by semver."""
    try:
        res = subprocess.run(
            ["git", "tag", "-l"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        if res.returncode == 0:
            return [t.strip() for t in res.stdout.splitlines() if t.strip()]
    except Exception:
        pass
    return []


def parse_version_tuple(tag: str) -> Tuple[int, ...]:
    """Extract numeric version tuple for sorting (e.g. 'v1.0.9' -> (1, 0, 9))."""
    nums = re.findall(r"\d+", tag)
    return tuple(map(int, nums)) if nums else (0,)


def get_base_version_from_pyproject() -> str:
    """Read version field from pyproject.toml."""
    pyproject = ROOT_DIR / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8")
            match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1).strip()
        except Exception:
            pass
    return "1.0.10"


def determine_tag_and_title() -> Tuple[str, str]:
    """Calculate the release tag and release title."""
    input_tag = os.environ.get("INPUT_TAG", "").strip()
    input_title = os.environ.get("INPUT_TITLE", "").strip()
    github_ref = os.environ.get("GITHUB_REF", "").strip()
    github_ref_name = os.environ.get("GITHUB_REF_NAME", "").strip()

    # 1. Explicit user tag input
    if input_tag:
        tag = input_tag if input_tag.startswith("v") else f"v{input_tag}"
    # 2. Triggered by a tag push (e.g. refs/tags/v1.0.10)
    elif github_ref.startswith("refs/tags/v"):
        tag = github_ref_name if github_ref_name.startswith("v") else f"v{github_ref_name}"
    # 3. Triggered by branch push (main/master) or automated detection
    else:
        tags = get_git_tags()
        base_ver = get_base_version_from_pyproject()
        candidate = f"v{base_ver}" if not base_ver.startswith("v") else base_ver

        if candidate in tags:
            # Candidate already published, increment patch version
            valid_tags = [t for t in tags if re.match(r"^v?\d+(\.\d+)*$", t)]
            if valid_tags:
                valid_tags.sort(key=parse_version_tuple)
                highest = valid_tags[-1]
                match = re.search(r"(\d+)$", highest)
                if match:
                    next_num = int(match.group(1)) + 1
                    prefix = highest[:match.start()]
                    tag = f"{prefix}{next_num}"
                else:
                    tag = f"{highest}.1"
            else:
                tag = f"{candidate}.1"
        else:
            tag = candidate

    if not tag.startswith("v"):
        tag = f"v{tag}"

    # Determine title
    if input_title:
        title = input_title
    else:
        title = f"Online Subtitle Generator {tag}"

    return tag, title


def main():
    tag, title = determine_tag_and_title()

    print(f"[RELEASE INFO] Tag:   {tag}")
    print(f"[RELEASE INFO] Title: {title}")

    # Write to GitHub Actions GITHUB_OUTPUT environment file if in CI
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        out_path = Path(gh_output)
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(f"tag={tag}\n")
            f.write(f"title={title}\n")
        print(f"[RELEASE INFO] Exported outputs to {gh_output}")


if __name__ == "__main__":
    main()
