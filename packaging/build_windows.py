import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
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
    _canonical_utility = Path(r"C:\Ali\Utility\Online Subtitle Generator")
    if _canonical_utility.parent.exists():
        UTILITY_DEST = _canonical_utility
    else:
        UTILITY_DEST = Path.home() / "Utility" / "Online Subtitle Generator"


def _download_and_extract_ffmpeg(target_dir: Path) -> bool:
    """Download official static FFmpeg binaries if not found on the host system."""
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    print(f"Downloading static FFmpeg bundle from: {url} ...")
    temp_zip = target_dir / "ffmpeg_temp.zip"
    try:
        urllib.request.urlretrieve(url, temp_zip)
        print("Extracting FFmpeg binaries...")
        with zipfile.ZipFile(temp_zip, 'r') as zf:
            for member in zf.namelist():
                name = Path(member).name.lower()
                if name in ("ffmpeg.exe", "ffprobe.exe"):
                    source = zf.open(member)
                    target = target_dir / name
                    with open(target, "wb") as f:
                        shutil.copyfileobj(source, f)
                    print(f"Extracted {name} to {target}")
        if temp_zip.exists():
            temp_zip.unlink()
        return (target_dir / "ffmpeg.exe").exists() and (target_dir / "ffprobe.exe").exists()
    except Exception as e:
        print(f"Warning: Failed to auto-download FFmpeg ({e}).")
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except Exception:
                pass
        return False


def create_portable_zip(app_dir: Path, output_zip: Path) -> Path:
    """Create a zip archive of the app directory and generate a SHA-256 hash file."""
    print(f"\nCompressing package to: {output_zip} ...")
    if output_zip.exists():
        output_zip.unlink()

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file_path in app_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(app_dir.parent)
                zf.write(file_path, arcname=str(rel_path))

    # Compute SHA-256
    sha256 = hashlib.sha256()
    with open(output_zip, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    hash_value = sha256.hexdigest()

    sha_file = output_zip.with_suffix(output_zip.suffix + ".sha256")
    sha_file.write_text(f"{hash_value}  {output_zip.name}\n", encoding="utf-8")

    size_mb = output_zip.stat().st_size / (1024 * 1024)
    print(f"Created portable zip ({size_mb:.1f} MB): {output_zip.name}")
    print(f"SHA-256: {hash_value}")
    return output_zip


def build(create_zip: bool = False, zip_tag: str = "") -> Path:
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

    if not (built_app_dir / "ffmpeg.exe").exists() or not (built_app_dir / "ffprobe.exe").exists():
        print("FFmpeg binaries missing in bundle, attempting automatic download...")
        _download_and_extract_ffmpeg(built_app_dir)

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

    # 4. Create Portable Zip if requested
    if create_zip or os.environ.get("CREATE_ZIP") == "1":
        tag_suffix = f"-{zip_tag}" if zip_tag else ""
        zip_path = DIST_DIR / f"Online-Subtitle-Generator{tag_suffix}-Windows-Portable.zip"
        create_portable_zip(built_app_dir, zip_path)
        # Also maintain generic zip name for convenience
        generic_zip = DIST_DIR / "Online-Subtitle-Generator-Portable.zip"
        if zip_path != generic_zip:
            shutil.copy2(zip_path, generic_zip)

    # 5. Deploy to local utility folder if not running in CI or skipped
    skip_deploy = os.environ.get("SKIP_UTILITY_DEPLOY") == "1" or os.environ.get("CI") == "true"
    if not skip_deploy:
        try:
            print(f"\nDeploying to User Utility directory: {UTILITY_DEST}...")
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
            print(f"Warning: Local utility deployment skipped or failed ({e}).")

    return built_app_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Online Subtitle Generator executable")
    parser.add_argument("--zip", action="store_true", help="Package into portable zip archive with checksum")
    parser.add_argument("--tag", type=str, default="", help="Tag suffix for zip filename (e.g. v1.0.10)")
    args = parser.parse_args()
    build(create_zip=args.zip, zip_tag=args.tag)

