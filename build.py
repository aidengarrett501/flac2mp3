"""Builds FLAC2MP3.exe. Installs its own build dependencies and bundles ffmpeg.

Run it through build.bat, or directly with a real Python: py -3 build.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
# When launched from a self-extracting bundle, artifacts and the ffmpeg
# cache live next to the bundle instead of in the throwaway work folder.
HOME = Path(os.environ.get("FLAC2MP3_HOME") or HERE).resolve()
APP_NAME = "FLAC2MP3"
SCRIPT = HERE / "flac2mp3_gui.py"
ICON = HERE / "flac2mp3.ico"
ISS = HERE / "installer.iss"
FFMPEG = HOME / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")

FFMPEG_URLS = [
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
]

INNO_PATHS = [
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    Path.home() / r"AppData\Local\Programs\Inno Setup 6\ISCC.exe",
]


def step(text):
    print(f"\n=== {text}")


def run(cmd):
    print("  > " + " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True)


def ensure_pip():
    try:
        import pip  # noqa: F401
    except ImportError:
        step("Bootstrapping pip")
        run([sys.executable, "-m", "ensurepip", "--upgrade"])


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        print("  PyInstaller already installed.")
    except ImportError:
        step("Installing PyInstaller")
        run([sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", "pyinstaller"])


def progress(count, block, total):
    if total <= 0:
        return
    done = min(count * block, total)
    pct = done * 100 // total
    print(f"\r  {pct:3d}%  ({done // 1048576} of {total // 1048576} MB)", end="", flush=True)


def extract_ffmpeg(archive, target):
    with zipfile.ZipFile(archive) as zf:
        member = next(
            (n for n in zf.namelist() if n.lower().endswith("bin/ffmpeg.exe")), None
        )
        if member is None:
            return False
        with zf.open(member) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
    return True


def ensure_ffmpeg():
    if FFMPEG.is_file():
        print(f"  Using existing {FFMPEG.name}.")
        return True
    if sys.platform != "win32":
        print("  Not on Windows, skipping ffmpeg bundling.")
        return False

    step("Downloading ffmpeg (about 100 MB, one time only)")
    for url in FFMPEG_URLS:
        print(f"  Source: {url}")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / "ffmpeg.zip"
                urllib.request.urlretrieve(url, archive, reporthook=progress)
                print()
                if extract_ffmpeg(archive, FFMPEG):
                    print(f"  Extracted {FFMPEG.name}.")
                    return True
                print("  No ffmpeg.exe inside that archive, trying the next source.")
        except Exception as exc:
            print(f"\n  Download failed: {exc}")
    print("  Could not fetch ffmpeg. The app will fall back to ffmpeg on PATH.")
    return False


def build_exe(bundled):
    step("Building the executable")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--windowed", "--clean", "--noconfirm",
        "--name", APP_NAME,
    ]
    if ICON.is_file():
        cmd += ["--icon", str(ICON)]
    if bundled:
        cmd += ["--add-binary", f"{FFMPEG};."]
    cmd.append(str(SCRIPT))
    run(cmd)


def find_inno():
    found = shutil.which("ISCC")
    if found:
        return Path(found)
    hit = next((p for p in INNO_PATHS if p.is_file()), None)
    if hit:
        return hit
    # winget's install location can vary, so sweep the usual roots.
    roots = [
        Path(r"C:\Program Files (x86)"),
        Path(r"C:\Program Files"),
        Path.home() / r"AppData\Local\Programs",
    ]
    for root in roots:
        if root.is_dir():
            for candidate in root.glob("Inno Setup*/ISCC.exe"):
                return candidate
    return None


def install_inno():
    if sys.platform != "win32" or shutil.which("winget") is None:
        return False
    step("Installing Inno Setup (needed to build the installer)")
    print("  Windows may show a UAC prompt. Approve it.")
    try:
        run([
            "winget", "install", "-e", "--id", "JRSoftware.InnoSetup",
            "--accept-package-agreements", "--accept-source-agreements",
        ])
    except subprocess.CalledProcessError as exc:
        print(f"  winget exited with code {exc.returncode}.")
        return False
    return True


def build_installer():
    if not ISS.is_file():
        return None

    iscc = find_inno()
    if iscc is None and install_inno():
        iscc = find_inno()

    if iscc is None:
        print("\n  Could not set up Inno Setup, skipping the installer.")
        print("  The portable exe in dist\\ still works on its own.")
        return None

    step("Building the installer")
    run([str(iscc), str(ISS)])
    return HERE / "dist" / f"{APP_NAME}-Setup.exe"


def deliver(paths):
    """Copy finished artifacts out of a temporary work folder."""
    if HOME == HERE:
        return paths
    out = HOME / "dist"
    out.mkdir(parents=True, exist_ok=True)
    delivered = []
    for path in paths:
        if path and path.is_file():
            target = out / path.name
            shutil.copy2(path, target)
            delivered.append(target)
        else:
            delivered.append(path)
    return delivered


def main():
    if not SCRIPT.is_file():
        print(f"Cannot find {SCRIPT.name} next to this script.")
        return 1

    print(f"Python: {sys.version.split()[0]} at {sys.executable}")
    ensure_pip()
    ensure_pyinstaller()
    bundled = ensure_ffmpeg()
    build_exe(bundled)
    installer = build_installer()

    exe = HERE / "dist" / f"{APP_NAME}.exe"
    exe, installer = deliver([exe, installer])

    step("Done")
    if exe and exe.is_file():
        print(f"  App:       {exe}  ({exe.stat().st_size // 1048576} MB)")
    if installer and installer.is_file():
        print(f"  Installer: {installer}")
        print("  Hand out the installer. It needs nothing on the target machine.")
    if bundled:
        print("  ffmpeg is bundled inside. No dependencies on the target machine.")
    else:
        print("  ffmpeg is NOT bundled. Target machines need ffmpeg on PATH.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        print(f"\nA build command failed with exit code {exc.returncode}.")
        sys.exit(1)
