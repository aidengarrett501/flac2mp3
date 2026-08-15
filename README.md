# FLAC2MP3

A small Windows app that converts FLAC files to MP3 using ffmpeg. Pick a source
folder, pick a destination, hit Convert.

ffmpeg is bundled inside the installer, so there is nothing else to install.

## Install

Download FLAC2MP3-Setup.exe from the Releases page and run it.

### Windows will warn you

The installer is not code signed, so Windows SmartScreen shows a blue
"Windows protected your PC" box on first run. Click More info, then Run anyway.

Some antivirus tools also flag apps built with PyInstaller. It is a known
false positive with this kind of packaging.

If you would rather not deal with an installer, FLAC2MP3.exe on the same
Releases page is a portable single file. Put it anywhere and run it.

## Using it

- Source folder is searched recursively, so subfolders are included.
- Destination folder receives all the MP3s in one flat directory.
- Bitrate defaults to 320k.
- Delete originals is off by default and asks for confirmation before it
  starts. FLAC files are only deleted after a conversion succeeds.

Files that already exist in the destination are skipped rather than
overwritten, and a skipped file never has its source deleted.

Folder paths and settings are saved to %USERPROFILE%\.flac2mp3_gui.json

## Building from source

You need Windows. Everything else is handled for you.

Run build.bat in this folder. It will find Python or install it with winget,
download ffmpeg, install PyInstaller and Inno Setup, then build
dist\FLAC2MP3.exe and dist\FLAC2MP3-Setup.exe.

Expect a UAC prompt during the winget steps. First build takes a few minutes,
mostly the ffmpeg download.

To run the GUI without building anything, you need Python and ffmpeg on PATH:

    py -3 flac2mp3_gui.py

## License

MIT for this project own code. See LICENSE.

The bundled ffmpeg binary is licensed separately. See NOTICE.md.
