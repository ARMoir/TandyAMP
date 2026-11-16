"""Single-video YouTube -> MP3 input for TandyAMP Studio (optional dependency).

Downloads are used only on the user's computer. No API keys, cookie import,
playlist crawling or circumvention of paid/DRM-protected content.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import re
import shutil
import tempfile
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



def video_id_from_url(url: str) -> str:
    """Canonical video ID shared by watch, shorts, live and youtu.be URLs."""
    parsed = urlsplit(validate_video_url(url))
    host = (parsed.hostname or '').lower()
    if host in ('youtu.be', 'www.youtu.be'):
        return parsed.path.strip('/').split('/')[0]
    path = parsed.path.strip('/')
    if path == 'watch':
        return parse_qs(parsed.query)['v'][0]
    return path.split('/')[1]


def mp3_cache_directory() -> Path:
    """Stable user-specific temporary cache across separate Studio runs."""
    return Path(tempfile.gettempdir()) / 'tandyamp-youtube-cache'


def _cache_paths(video_id: str, quality: str, cache_dir: Path | None = None
                 ) -> tuple[Path, Path]:
    root = Path(cache_dir) if cache_dir is not None else mp3_cache_directory()
    name = f'{video_id}-{quality}'
    return root / (name + '.mp3'), root / (name + '.json')


def _valid_mp3(path: Path) -> bool:
    """Reject obviously truncated or non-MP3 cache entries without decoding.

    The expected FFmpeg output begins with ID3v2 or an MPEG audio frame.
    A full audio decode is deliberately not required on every cache hit.
    """
    try:
        if not path.is_file() or path.stat().st_size < 1024:
            return False
        with path.open('rb') as stream:
            header = stream.read(4)
        return (header[:3] == b'ID3' or
                (len(header) == 4 and header[0] == 0xff and
                 (header[1] & 0xe0) == 0xe0 and
                 (header[1] & 0x06) != 0))
    except OSError:
        return False


def cached_youtube_mp3(url: str, quality: str = '192',
                       cache_dir: Path | None = None) -> AudioDownload | None:
    """Return a validated cached MP3 without requiring yt-dlp or FFmpeg.

    Metadata is optional; a missing or damaged JSON title is safely replaced
    by a generic one. The validated URL ID and bitrate determine the match.
    """
    video_id = video_id_from_url(url)
    if quality not in ('128', '192', '256', '320'):
        raise ValueError('MP3 quality must be 128, 192, 256, or 320 kbps')
    mp3, metadata = _cache_paths(video_id, quality, cache_dir)
    if not _valid_mp3(mp3):
        return None
    title = 'YouTube'
    try:
        details = json.loads(metadata.read_text(encoding='utf-8'))
        if (isinstance(details, dict) and details.get('video_id') == video_id
                and details.get('quality') == quality
                and isinstance(details.get('title'), str)):
            title = details['title']
    except (OSError, ValueError, TypeError):
        pass
    return AudioDownload(mp3, title, video_id)


def _save_cache(downloaded: AudioDownload, quality: str,
                cache_dir: Path | None) -> AudioDownload:
    """Publish completed media using atomic rename; no partial cache hits."""
    mp3, meta = _cache_paths(downloaded.video_id, quality, cache_dir)
    mp3.parent.mkdir(parents=True, exist_ok=True)
    audio_tmp: Path | None = None
    metadata_tmp: Path | None = None
    try:
        # Separate unique files are important when two Studio processes
        # convert the same YouTube URL concurrently.
        with tempfile.NamedTemporaryFile(
            prefix='tandyamp-', suffix='.part', dir=mp3.parent, delete=False
        ) as temp:
            audio_tmp = Path(temp.name)
            with downloaded.audio_path.open('rb') as source:
                shutil.copyfileobj(source, temp)
        if not _valid_mp3(audio_tmp):
            raise RuntimeError('Extracted MP3 is not valid; refusing to cache it')
        os.replace(audio_tmp, mp3)
        audio_tmp = None
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', prefix='tandyamp-',
            suffix='.json.part', dir=meta.parent, delete=False
        ) as stream:
            metadata_tmp = Path(stream.name)
            json.dump({'video_id': downloaded.video_id, 'quality': quality,
                       'title': downloaded.title}, stream)
        os.replace(metadata_tmp, meta)
        metadata_tmp = None
        return AudioDownload(mp3, downloaded.title, downloaded.video_id)
    finally:
        for temporary in (audio_tmp, metadata_tmp):
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


def download_youtube_mp3(url: str, workspace: Path, quality: str = '192',
                         *, cache_dir: Path | None = None) -> AudioDownload:
    """Extract one MP3 with yt-dlp's embedded Python API + FFmpeg.

    The fixed source.%(ext)s template keeps arbitrary YouTube titles out
    of paths and prevents accidentally following playlists or overwriting user
    files; callers provide a fresh temporary directory.
    """
    url = validate_video_url(url)
    if quality not in ('128', '192', '256', '320'):
        raise ValueError('MP3 quality must be 128, 192, 256, or 320 kbps')
    video_id = video_id_from_url(url)
    cached = cached_youtube_mp3(url, quality, cache_dir)
    if cached is not None:
        print(f'Using cached YouTube MP3: {cached.audio_path}', flush=True)
        return cached
    cache_mp3, _ = _cache_paths(video_id, quality, cache_dir)
    if cache_mp3.exists():
        print(f'Invalid cached MP3; downloading fresh audio: {cache_mp3}', flush=True)
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
    if not _valid_mp3(destination):
        raise RuntimeError('yt-dlp did not produce a complete MP3. Check FFmpeg and download errors.')
    if info.get('id') != video_id:
        raise RuntimeError('YouTube returned a different video ID; refusing to cache unrelated audio.')
    downloaded = AudioDownload(destination, str(info.get('title') or 'YouTube'), video_id)
    try:
        cached = _save_cache(downloaded, quality, cache_dir)
    except OSError as exc:
        print(f'Could not store MP3 cache ({exc}); conversion will still continue.', flush=True)
        return downloaded
    print(f'Saved reusable MP3 in temporary cache: {cached.audio_path}', flush=True)
    return cached
