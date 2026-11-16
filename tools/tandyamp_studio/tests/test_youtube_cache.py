"""Persistent YouTube MP3 cache regression tests; no network or FFmpeg required."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import studio
import youtube
from youtube import cached_youtube_mp3, download_youtube_mp3, mp3_cache_directory


VIDEO_ID = 'Uq42HUUJFzU'
WATCH = f'https://www.youtube.com/watch?v={VIDEO_ID}'
SHORT = f'https://youtu.be/{VIDEO_ID}?t=20'
AUDIO = b'ID3' + b'\0' * 2048


class FakeYoutubeDL:
    calls = []

    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download):
        self.calls.append((url, self.options['postprocessors'][0]['preferredquality']))
        Path(self.options['outtmpl'].replace('%(ext)s', 'mp3')).write_bytes(AUDIO)
        return {'title': 'Paranoid - Test', 'id': VIDEO_ID}


class YouTubeCacheTests(unittest.TestCase):
    def setUp(self):
        FakeYoutubeDL.calls.clear()

    def test_repeated_video_different_url_skips_yt_dlp_and_ffmpeg(self):
        fake = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            cache = base / 'persistent-cache'
            with patch.dict(sys.modules, {'yt_dlp': fake}):
                with patch('dependencies.shutil.which', return_value='/ffmpeg'):
                    with tempfile.TemporaryDirectory(dir=base) as work:
                        initial = download_youtube_mp3(WATCH, Path(work),
                                                      cache_dir=cache)
                        self.assertTrue(initial.audio_path.is_file())
                        self.assertEqual(initial.title, 'Paranoid - Test')
            self.assertTrue(initial.audio_path.is_file(),
                            'MP3 must remain after per-run workspace is deleted')
            with patch.dict(sys.modules, {'yt_dlp': None}):
                with patch('dependencies.require_ffmpeg',
                           side_effect=AssertionError('unwanted FFmpeg check')):
                    reused = download_youtube_mp3(SHORT, base / 'second',
                                                  cache_dir=cache)
            self.assertEqual(reused.audio_path, initial.audio_path)
            self.assertEqual(reused.audio_path.read_bytes(), AUDIO)
            self.assertEqual(reused.title, 'Paranoid - Test')
            self.assertEqual(len(FakeYoutubeDL.calls), 1)

    def test_bitrate_is_part_of_cache_key(self):
        fake = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with patch.dict(sys.modules, {'yt_dlp': fake}):
                with patch('dependencies.shutil.which', return_value='/ffmpeg'):
                    a = download_youtube_mp3(WATCH, base/'a', '192',
                                             cache_dir=base/'cache')
                    b = download_youtube_mp3(WATCH, base/'b', '256',
                                             cache_dir=base/'cache')
            self.assertNotEqual(a.audio_path, b.audio_path)
            self.assertEqual(len(FakeYoutubeDL.calls), 2)
            self.assertEqual([q for _, q in FakeYoutubeDL.calls], ['192', '256'])

    def test_corrupt_cache_is_not_reused_and_is_replaced(self):
        fake = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            cache = base/'cache'
            cache.mkdir()
            bad = cache / f'{VIDEO_ID}-192.mp3'
            bad.write_bytes(b'partial download')
            self.assertIsNone(cached_youtube_mp3(WATCH, cache_dir=cache))
            with patch.dict(sys.modules, {'yt_dlp': fake}):
                with patch('dependencies.shutil.which', return_value='/ffmpeg'):
                    out = download_youtube_mp3(WATCH, base/'workspace',
                                              cache_dir=cache)
            self.assertEqual(out.audio_path, bad)
            self.assertEqual(bad.read_bytes(), AUDIO)
            self.assertEqual(len(FakeYoutubeDL.calls), 1)

    def test_cache_missing_metadata_still_avoids_redownload(self):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            (cache / f'{VIDEO_ID}-192.mp3').write_bytes(AUDIO)
            cached = cached_youtube_mp3(WATCH, cache_dir=cache)
            self.assertIsNotNone(cached)
            self.assertEqual(cached.video_id, VIDEO_ID)
            self.assertEqual(cached.title, 'YouTube')

    def test_non_mp3_magic_is_rejected_even_if_large(self):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            (cache / f'{VIDEO_ID}-192.mp3').write_bytes(b'\0'*4096)
            self.assertIsNone(cached_youtube_mp3(WATCH, cache_dir=cache))

    def test_default_cache_is_under_system_temp(self):
        with patch('youtube.tempfile.gettempdir', return_value='/sample/Temp'):
            self.assertEqual(mp3_cache_directory(),
                             Path('/sample/Temp/tandyamp-youtube-cache'))

    def test_cached_mp3_still_supports_mp3_only_output(self):
        fake = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with patch('youtube.mp3_cache_directory', return_value=base/'cache'):
                with patch.dict(sys.modules, {'yt_dlp': fake}):
                    with patch('dependencies.shutil.which', return_value='/ffmpeg'):
                        first = studio.convert(WATCH, base/'out1', mp3_only=True)
                self.assertTrue(first[0].is_file())
                with patch.dict(sys.modules, {'yt_dlp': None}):
                    with patch('dependencies.require_ffmpeg',
                               side_effect=AssertionError('unwanted ffmpeg')):
                        second = studio.convert(SHORT, base/'out2', mp3_only=True)
                self.assertEqual(first[0].read_bytes(), second[0].read_bytes())
                self.assertEqual(len(FakeYoutubeDL.calls), 1)


if __name__ == '__main__':
    unittest.main()
