# Third-party components

## ffmpeg

FLAC2MP3 does not implement audio encoding. It calls ffmpeg, which is bundled
inside the released executable.

The build downloads a prebuilt Windows binary from gyan.dev:

https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip

That build is distributed under the GNU General Public License v3. Because the
binary ships inside the installer, releases of this project carry the GPL
obligations that come with redistributing it, including making the
corresponding source available.

ffmpeg source and license text:

- https://ffmpeg.org/download.html
- https://www.ffmpeg.org/legal.html
- https://git.ffmpeg.org/ffmpeg.git

If you fork this and would rather avoid GPL redistribution, swap the download
URL in build.py for an LGPL build. BtbN publishes them alongside the GPL ones:

https://github.com/BtbN/FFmpeg-Builds/releases

FLAC2MP3 runs ffmpeg as a separate process rather than linking against it, so
an LGPL build carries lighter obligations.

None of this is legal advice. If you plan to distribute widely, read the
licenses yourself.
