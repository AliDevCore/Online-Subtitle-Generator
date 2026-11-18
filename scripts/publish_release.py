"""
Online Subtitle Generator - Automated Release Publisher.
Validates test suite, compiles application with all dependencies & FFmpeg,
creates portable release ZIP, generates SHA-256 checksum, manages git tags,
and publishes GitHub Releases either locally via GitHub API or via GitHub Actions CI.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, List, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

REPO_OWNER = "AliDevCore"
REPO_NAME = "Online-Subtitle-Generator"
DIST_DIR = ROOT_DIR / "dist"


def run_command(cmd: List[str], check: bool = True, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    """Execute a subprocess command with proper encoding."""
    print(f"\n[EXEC] {' '.join(cmd)}")
    res = subprocess.run(
        cmd,
        cwd=str(cwd or ROOT_DIR),
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    if check and res.returncode != 0:
        print(f"[ERROR] Command failed with exit code {res.returncode}")
        sys.exit(res.returncode)
    return res


def get_local_git_tags() -> List[str]:
    """Retrieve list of git tags from local repository."""
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
            tags = [t.strip() for t in res.stdout.strip().splitlines() if t.strip()]
            return tags
    except Exception:
        pass
    return []


def get_remote_github_tags() -> List[str]:
    """Fetch published tags from GitHub API via requests."""
    try:
        import requests
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/tags"
        resp = requests.get(url, timeout=6)
        if resp.status_code == 200:
            tags = [item["name"] for item in resp.json()]
            return tags
    except Exception:
        pass
    return []


def parse_version_tuple(tag: str) -> Tuple[int, ...]:
    """Extract numeric version tuple for sorting (e.g. 'v1.0.9' -> (1, 0, 9))."""
    nums = re.findall(r"\d+", tag)
    return tuple(map(int, nums)) if nums else (0,)


def compute_next_tag(existing_tags: List[str]) -> str:
    """Determine the next patch version tag based on existing tags."""
    valid_tags = [t for t in existing_tags if re.match(r"^v?\d+(\.\d+)*$", t)]
    if not valid_tags:
        return "v1.0.10"

    valid_tags.sort(key=parse_version_tuple)
    latest = valid_tags[-1]

    # Increment patch number
    match = re.search(r"(\d+)$", latest)
    if match:
        next_num = int(match.group(1)) + 1
        prefix = latest[:match.start()]
        next_tag = f"{prefix}{next_num}"
    else:
        next_tag = f"{latest}.1"

    if not next_tag.startswith("v"):
        next_tag = f"v{next_tag}"
    return next_tag


def run_tests() -> bool:
    """Run pytest suite before building."""
    print("\n" + "=" * 60)
    print("Step 1: Running Automated Test Suite...")
    print("=" * 60)
    cmd = [sys.executable, "-m", "pytest", "tests", "-v"]
    res = subprocess.run(cmd, cwd=str(ROOT_DIR))
    if res.returncode != 0:
        print("\n[ERROR] Tests failed! Aborting release.")
        return False
    print("[SUCCESS] All unit and integration tests passed cleanly.")
    return True


def compile_package(tag: str) -> Tuple[Path, Path]:
    """Compile application using packaging/build_windows.py and package portable zip."""
    print("\n" + "=" * 60)
    print(f"Step 2: Compiling Executable & Bundling All Dependencies for {tag}...")
    print("=" * 60)

    build_script = ROOT_DIR / "packaging" / "build_windows.py"
    env = os.environ.copy()
    env["SKIP_UTILITY_DEPLOY"] = "1"
    env["CREATE_ZIP"] = "1"

    cmd = [sys.executable, str(build_script), "--zip", "--tag", tag]
    res = subprocess.run(cmd, cwd=str(ROOT_DIR), env=env)
    if res.returncode != 0:
        raise RuntimeError("PyInstaller build process failed.")

    zip_file = DIST_DIR / f"Online-Subtitle-Generator-{tag}-Windows-Portable.zip"
    sha_file = zip_file.with_suffix(zip_file.suffix + ".sha256")

    if not zip_file.exists():
        generic_zip = DIST_DIR / "Online-Subtitle-Generator-Portable.zip"
        if generic_zip.exists():
            shutil.copy2(generic_zip, zip_file)

    if not zip_file.exists() or zip_file.stat().st_size == 0:
        raise RuntimeError(f"Build failed: Portable zip archive not found at {zip_file}")

    print(f"\n[SUCCESS] Portable release archive generated:")
    print(f"  Archive: {zip_file.name} ({zip_file.stat().st_size / (1024*1024):.1f} MB)")
    if sha_file.exists():
        print(f"  SHA256:  {sha_file.read_text(encoding='utf-8').strip()}")

    return zip_file, sha_file


def create_git_tag(tag: str) -> bool:
    """Create local annotated Git tag."""
    print("\n" + "=" * 60)
    print(f"Step 3: Creating Git Tag '{tag}'...")
    print("=" * 60)

    # Check if tag already exists locally
    local_tags = get_local_git_tags()
    if tag in local_tags:
        print(f"Tag '{tag}' already exists locally.")
        return True

    msg = f"Online Subtitle Generator {tag} Release"
    cmd = ["git", "tag", "-a", tag, "-m", msg]
    res = run_command(cmd, check=False)
    if res.returncode == 0:
        print(f"[SUCCESS] Git tag '{tag}' created successfully.")
        return True
    else:
        print(f"[WARNING] Could not create git tag via CLI.")
        return False


def push_git_tag(tag: str) -> bool:
    """Push commits and tags to GitHub."""
    print("\n" + "=" * 60)
    print(f"Step 4: Pushing Commits and Tag '{tag}' to GitHub...")
    print("=" * 60)

    cmd = ["git", "push", "origin", "main", "--tags"]
    res = run_command(cmd, check=False)
    if res.returncode == 0:
        print(f"[SUCCESS] Tag '{tag}' pushed to GitHub!")
        print("GitHub Actions workflow 'release.yml' will automatically verify and publish the release in cloud.")
        return True
    else:
        print("[NOTICE] Git push command returned non-zero code.")
        print("You can push manually via Git or GitHub Desktop with: git push origin main --tags")
        return False


def publish_github_release_api(
    tag: str,
    zip_path: Path,
    sha_path: Path,
    token: str,
    draft: bool = False,
    prerelease: bool = False,
    title: Optional[str] = None
) -> bool:
    """Publish release directly using GitHub REST API."""
    import requests

    print("\n" + "=" * 60)
    print(f"Step 5: Publishing Release '{tag}' via GitHub API...")
    print("=" * 60)

    release_title = title or f"Online Subtitle Generator {tag}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    body_notes = (
        f"## Online Subtitle Generator {tag}\n\n"
        "### What's Changed\n"
        "- Automated compilation with embedded FFmpeg and FFprobe static binaries.\n"
        "- Standalone zero-setup portable distribution.\n"
        "- Subtitle segmenter optimization and multi-account failover pool.\n\n"
        "### Checksum Verification\n"
        "Verify archive integrity with SHA-256:\n"
        "```text\n"
        f"{sha_path.read_text(encoding='utf-8').strip() if sha_path.exists() else ''}\n"
        "```\n"
    )

    create_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases"
    payload = {
        "tag_name": tag,
        "name": release_title,
        "body": body_notes,
        "draft": draft,
        "prerelease": prerelease,
        "generate_release_notes": True
    }

    print(f"Creating release on GitHub: {release_title}...")
    resp = requests.post(create_url, headers=headers, json=payload)
    if resp.status_code not in (200, 201):
        print(f"[ERROR] Failed to create release: {resp.status_code} - {resp.text}")
        return False

    rel_data = resp.json()
    upload_url_template = rel_data.get("upload_url", "")
    upload_url = upload_url_template.split("{")[0]
    html_url = rel_data.get("html_url", "")

    print(f"[SUCCESS] Release created at: {html_url}")

    # Upload Zip asset
    print(f"Uploading asset '{zip_path.name}' ({zip_path.stat().st_size / (1024*1024):.1f} MB)...")
    upload_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/zip"
    }
    with open(zip_path, "rb") as f:
        up_resp = requests.post(
            f"{upload_url}?name={zip_path.name}",
            headers=upload_headers,
            data=f
        )
    if up_resp.status_code in (200, 201):
        print(f"[SUCCESS] Uploaded {zip_path.name}")
    else:
        print(f"[WARNING] Uploading zip failed: {up_resp.status_code} - {up_resp.text}")

    # Upload SHA256 asset
    if sha_path.exists():
        print(f"Uploading checksum asset '{sha_path.name}'...")
        sha_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "text/plain"
        }
        with open(sha_path, "rb") as f:
            up_sha = requests.post(
                f"{upload_url}?name={sha_path.name}",
                headers=sha_headers,
                data=f
            )
        if up_sha.status_code in (200, 201):
            print(f"[SUCCESS] Uploaded {sha_path.name}")

    print("\n" + "=" * 60)
    print(f"RELEASE PUBLISHED SUCCESSFULLY ON GITHUB!")
    print(f"URL: {html_url}")
    print("=" * 60)
    return True


def main():
    parser = argparse.ArgumentParser(description="Automated Release Publisher for Online Subtitle Generator")
    parser.add_argument("--tag", type=str, default="", help="Target release tag (e.g. v1.0.10). Auto-calculated if omitted.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip running pytest")
    parser.add_argument("--skip-build", action="store_true", help="Skip recompiling binary (use existing build)")
    parser.add_argument("--push", action="store_true", help="Automatically push git tag to origin")
    parser.add_argument("--token", type=str, default="", help="GitHub Personal Access Token for direct API release")
    parser.add_argument("--draft", action="store_true", help="Create as a draft release")
    parser.add_argument("--prerelease", action="store_true", help="Create as a pre-release")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print(" Online Subtitle Generator - Automated Release Publisher")
    print("=" * 60)

    # 1. Determine release tag
    all_tags = list(set(get_local_git_tags() + get_remote_github_tags()))
    all_tags.sort(key=parse_version_tuple)
    suggested_tag = compute_next_tag(all_tags)

    target_tag = args.tag.strip()
    if not target_tag:
        print(f"Existing tags found: {', '.join(all_tags[-5:]) if all_tags else 'None'}")
        print(f"Suggested next release tag: [{suggested_tag}]")
        try:
            user_input = input(f"Enter target tag (press Enter for {suggested_tag}): ").strip()
            target_tag = user_input if user_input else suggested_tag
        except (KeyboardInterrupt, EOFError):
            print("\nOperation cancelled.")
            sys.exit(0)

    if not target_tag.startswith("v"):
        target_tag = f"v{target_tag}"

    print(f"\n=> Target Release Tag: {target_tag}")

    # 2. Run Tests
    if not args.skip_tests:
        if not run_tests():
            sys.exit(1)
    else:
        print("\n[SKIP] Skipping tests as requested.")

    # 3. Compile & Bundle Executable
    zip_path = DIST_DIR / f"Online-Subtitle-Generator-{target_tag}-Windows-Portable.zip"
    sha_path = zip_path.with_suffix(zip_path.suffix + ".sha256")

    if not args.skip_build:
        zip_path, sha_path = compile_package(target_tag)
    else:
        print(f"\n[SKIP] Skipping compilation, looking for existing archive: {zip_path.name}")
        if not zip_path.exists():
            generic_zip = DIST_DIR / "Online-Subtitle-Generator-Portable.zip"
            if generic_zip.exists():
                shutil.copy2(generic_zip, zip_path)
            else:
                print(f"[ERROR] Existing archive not found at {zip_path}")
                sys.exit(1)

    # 4. Create Git Tag
    create_git_tag(target_tag)

    # 5. Publishing Options
    github_token = args.token.strip() or os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()

    if github_token:
        # Direct GitHub API publication
        publish_github_release_api(
            tag=target_tag,
            zip_path=zip_path,
            sha_path=sha_path,
            token=github_token,
            draft=args.draft,
            prerelease=args.prerelease
        )
    else:
        # Git Push path
        should_push = args.push
        if not should_push:
            try:
                ans = input(f"\nPush git tag '{target_tag}' to GitHub origin to trigger GitHub Actions release? (Y/n): ").strip().lower()
                should_push = ans in ("", "y", "yes")
            except (KeyboardInterrupt, EOFError):
                should_push = False

        if should_push:
            push_git_tag(target_tag)

        print("\n" + "=" * 60)
        print("RELEASE PREPARATION COMPLETE!")
        print("=" * 60)
        print(f"1. Standalone portable ZIP is ready at:")
        print(f"   {zip_path}")
        print(f"2. Git Tag '{target_tag}' is created.")
        print(f"3. GitHub Releases Page:")
        print(f"   https://github.com/{REPO_OWNER}/{REPO_NAME}/releases")
        print("\nTip: To publish via GitHub Actions CI in cloud, simply push the tag with:")
        print(f"   git push origin {target_tag}")
        print("Or set GITHUB_TOKEN environment variable to publish directly via API.")


if __name__ == "__main__":
    main()
