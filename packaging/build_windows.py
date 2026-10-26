"""
Automated Windows build script for Online Subtitle Generator.
Builds the PyInstaller distribution, bundles FFmpeg binaries, and deploys to Utility directory.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"
SPEC_FILE = ROOT_DIR / "packaging" / "OnlineSubtitleGenerator.spec"
_deploy_override = os.environ.get("DEPLOY_DIR")
if _deploy_override:
    UTILITY_DEST = Path(_deploy_override)
else:
    # Explicit user path: C:\Ali\Utility\Online Subtitle Generator
    _canonical_utility = Path(r"C:\Ali\Utility\Online Subtitle Generator")
    if _canonical_utility.parent.exists():
        UTILITY_DEST = _canonical_utility
    else:
        UTILITY_DEST = Path.home() / "Utility" / "Online Subtitle Generator"


def build():
    print("=" * 60)
    print("Building Online Subtitle Generator Windows Executable...")
    print("=" * 60)

    # 1. Clean previous build artifacts
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)

    # 2. Run PyInstaller
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        str(SPEC_FILE)
    ]
    print(f"Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(ROOT_DIR))
    if res.returncode != 0:
        print("PyInstaller build failed!")
        sys.exit(1)

    built_app_dir = DIST_DIR / "Online Subtitle Generator"
    if not built_app_dir.exists():
        print(f"Build output not found at: {built_app_dir}")
        sys.exit(1)

    print(f"Build succeeded at: {built_app_dir}")

    # 3. Bundle FFmpeg and FFprobe binaries
    from app.services.ffmpeg_service import find_media_tool
    ffmpeg_exe = find_media_tool("ffmpeg")
    ffprobe_exe = find_media_tool("ffprobe")
    if ffmpeg_exe and Path(ffmpeg_exe).is_file():
        shutil.copy2(ffmpeg_exe, built_app_dir / "ffmpeg.exe")
        print(f"Copied FFmpeg ({Path(ffmpeg_exe).stat().st_size / (1024*1024):.1f} MB): {ffmpeg_exe}")
    if ffprobe_exe and Path(ffprobe_exe).is_file():
        shutil.copy2(ffprobe_exe, built_app_dir / "ffprobe.exe")
        print(f"Copied FFprobe ({Path(ffprobe_exe).stat().st_size / (1024*1024):.1f} MB): {ffprobe_exe}")

    # Add portable flag and assets
    (built_app_dir / "portable.txt").write_text("Online Subtitle Generator Portable Mode Enabled\n", encoding="utf-8")
    assets_src = ROOT_DIR / "assets"
    if assets_src.exists():
        dest_assets = built_app_dir / "assets"
        if dest_assets.exists():
            shutil.rmtree(dest_assets)
        shutil.copytree(assets_src, dest_assets)

    for doc in ["README.md", "LICENSE"]:
        src = ROOT_DIR / doc
        if src.exists():
            shutil.copy2(src, built_app_dir / doc)

    # 4. Deploy to local utility folder if configured / present
    try:
        print(f"\nDeploying to User Utility directory: {UTILITY_DEST}...")
        # Gracefully terminate any running instances of the app to prevent Windows file locking
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] and 'Online Subtitle Generator' in proc.info['name']:
                    proc.kill()
                    print(f"Terminated running process: {proc.info['name']}")
        except Exception:
            pass

        UTILITY_DEST.mkdir(parents=True, exist_ok=True)
        for item in built_app_dir.iterdir():
            dest = UTILITY_DEST / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        print(f"Deployment complete! Executable is ready at:\n{UTILITY_DEST / 'Online Subtitle Generator.exe'}")
    except Exception as e:
        print(f"ERROR: Local utility deployment failed ({e}). Check if application is running!")
        raise


if __name__ == "__main__":
    build()
