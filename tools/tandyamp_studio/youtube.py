"""Single-video YouTube -> MP3 input for TandyAMP Studio (optional dependency).

Downloads are used only on the user's computer. No API keys, cookie import,
playlist crawling or circumvention of paid/DRM-protected content.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit


_ALLOWED_HOSTS = frozenset((
    'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com',
    'youtu.be', 'www.youtu.be', 'www.youtube-nocookie.com',
))


def is_youtube_url(value: str) -> bool:
    """Recognize full http(s) YouTube video URLs; don't treat file paths as URLs."""
    try:
        url = urlsplit(str(value).strip())
        return (url.scheme in ('http', 'https') and
                (url.hostname or '').lower() in _ALLOWED_HOSTS and
                url.username is None and url.password is None)
    except ValueError:
        return False


def validate_video_url(value: str) -> str:
    """Only one video, not search pages/channels/playlist-only links."""
    text = str(value).strip()
    if not is_youtube_url(text):
        raise ValueError('Use a full https://www.youtube.com/watch?v=... or https://youtu.be/... link')
    url = urlsplit(text)
    host = (url.hostname or '').lower()
    path = url.path.strip('/')
    if host in ('youtu.be', 'www.youtu.be'):
        video_id = path.split('/')[0]
    elif path == 'watch':
        video_id = parse_qs(url.query).get('v', [''])[0]
    elif path.startswith(('shorts/', 'live/', 'embed/')):
        video_id = path.split('/')[1]
    else:
        video_id = ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{6,32}', video_id):
        raise ValueError('A single YouTube video URL is required (playlist-only links are not supported)')
    return text


def safe_name(title: str, video_id: str) -> str:
    """Keep host filenames portable, short, and resistant to path traversal."""
    clean_id = re.sub(r'[^A-Za-z0-9_-]', '', str(video_id))[:32]
    if not clean_id:
        raise ValueError('YouTube video identifier missing')
    clean_title = re.sub(r'[^A-Za-z0-9 _-]', '', str(title))
    clean_title = re.sub(r'\s+', '_', clean_title.strip())[:56].strip('._-')
    return f'{clean_title or "YouTube"}_{clean_id}'


@dataclass(frozen=True)
class AudioDownload:
    audio_path: Path
    title: str
    video_id: str


def download_youtube_mp3(url: str, workspace: Path, quality: str = '192') -> AudioDownload:
    """Extract one MP3 with yt-dlp's embedded Python API + FFmpeg.

    The fixed source.%(ext)s template keeps arbitrary YouTube titles out
    of paths and prevents accidentally following playlists or overwriting user
    files; callers provide a fresh temporary directory.
    """
    url = validate_video_url(url)
    if quality not in ('128', '192', '256', '320'):
        raise ValueError('MP3 quality must be 128, 192, 256, or 320 kbps')
    from dependencies import require_ffmpeg
    require_ffmpeg()
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError('YouTube support is optional. Install: '
                           'py -3.11 -m pip install -r requirements-youtube.txt') from exc

    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    destination = workspace / 'source.mp3'
    if destination.exists():
        raise FileExistsError(f'Refusing to overwrite {destination}')
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(workspace / 'source.%(ext)s'),
        'noplaylist': True,
        'restrictfilenames': True,
        'overwrites': False,
        'nooverwrites': True,
        'retries': 3,
        'fragment_retries': 3,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': quality,
        }],
    }
    print('Downloading single YouTube video audio and extracting MP3...', flush=True)
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:
        # Keep provider-specific diagnostics visible without a false claim of
        # success. The provider can change or block playback/download.
        raise RuntimeError(f'YouTube audio download failed: {exc}') from exc
    if not isinstance(info, dict) or info.get('_type') in ('playlist', 'multi_video'):
        raise RuntimeError('Expected one YouTube video; received a playlist or invalid response')
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError('yt-dlp did not produce an MP3. Check FFmpeg and the download errors.')
    return AudioDownload(destination, str(info.get('title') or 'YouTube'),
                         str(info.get('id') or ''))
