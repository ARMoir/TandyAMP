"""Dependency checks and opt-in FFmpeg installation on Windows."""
from __future__ import annotations
import shutil
import subprocess
import sys

FFMPEG_COMMAND = 'winget install --id Gyan.FFmpeg --exact'


class MissingFFmpegError(RuntimeError):
    """FFmpeg CLI tools are absent."""


def missing_ffmpeg() -> list[str]:
    return [name for name in ('ffmpeg', 'ffprobe') if shutil.which(name) is None]


def ffmpeg_help(missing: list[str] | None = None) -> str:
    if missing is None:
        missing = missing_ffmpeg()
    return (
        'YouTube MP3 conversion requires FFmpeg and ffprobe. '
        'Missing from PATH: {}.\n'
        'On Windows install with: {}\n'
        'Then close and reopen TandyAMP Studio (or the terminal) '
        'and check: ffmpeg -version and ffprobe -version.\n'
        'Manual installation: https://ffmpeg.org/download.html'
    ).format(', '.join(missing) if missing else 'none', FFMPEG_COMMAND)


def require_ffmpeg() -> None:
    missing = missing_ffmpeg()
    if missing:
        raise MissingFFmpegError(ffmpeg_help(missing))


def install_ffmpeg_windows() -> str:
    """Run only when a user explicitly approves the winget command in the GUI."""
    if sys.platform != 'win32':
        raise RuntimeError('Automatic installation is Windows-only. '
                           'Install manually from https://ffmpeg.org/download.html')
    winget = shutil.which('winget')
    if winget is None:
        raise RuntimeError('winget is unavailable. '
                           'Install manually from https://ffmpeg.org/download.html')
    cmd = [winget, 'install', '--id', 'Gyan.FFmpeg', '--exact',
           '--accept-package-agreements', '--accept-source-agreements']
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f'FFmpeg install could not finish: {exc}') from exc
    if result.returncode:
        details = (result.stderr or result.stdout or 'No details provided').strip()[-1200:]
        raise RuntimeError(f'winget returned {result.returncode}: {details}\n'
                           'Manual installation: https://ffmpeg.org/download.html')
    return ('FFmpeg installer finished. Close and reopen Studio to refresh PATH, '
            'then run ffmpeg -version and ffprobe -version.')
