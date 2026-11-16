"""YouTube URL handling, CLI mode and MP3 extraction tests; no network/audio models."""
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
from youtube import AudioDownload, download_youtube_mp3, is_youtube_url, safe_name, validate_video_url


class YouTubeUrlTests(unittest.TestCase):
    def test_single_video_forms(self):
        samples = [
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            'https://youtu.be/dQw4w9WgXcQ?t=3',
            'https://youtube.com/shorts/dQw4w9WgXcQ',
            'https://m.youtube.com/watch?v=dQw4w9WgXcQ&list=RD',
            'https://music.youtube.com/watch?v=dQw4w9WgXcQ',
        ]
        for url in samples:
            with self.subTest(url=url):
                self.assertTrue(is_youtube_url(url))
                self.assertEqual(validate_video_url(url), url)

    def test_reject_non_youtube_and_non_video(self):
        samples = [
            'https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ',
            'https://youtube.com/playlist?list=PL123456789',
            'https://www.youtube.com/watch?v=',
            'https://example.com/watch?v=dQw4w9WgXcQ',
            'file:///etc/passwd',
            'https://bad:pass@youtube.com/watch?v=dQw4w9WgXcQ',
            'https://youtube.com/@channelname',
        ]
        for url in samples:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_video_url(url)
        self.assertFalse(is_youtube_url('C:\\Music\\track.mid'))

    def test_filename_is_safe(self):
        name = safe_name('../evil:\\\\song / hello?', 'dQw4w9WgXcQ')
        self.assertNotIn('/', name)
        self.assertNotIn('\\', name)
        self.assertIn('dQw4w9WgXcQ', name)


class DownloaderTests(unittest.TestCase):
    def test_missing_ffmpeg_reports_installation(self):
        with tempfile.TemporaryDirectory() as td, patch('dependencies.shutil.which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'FFmpeg and ffprobe'):
                download_youtube_mp3('https://youtu.be/dQw4w9WgXcQ', Path(td), cache_dir=Path(td)/'cache')

    def test_downloader_uses_one_video_and_mp3_postprocess(self):
        captured = {}
        class FakeYoutubeDL:
            def __init__(self, opts):
                captured['opts'] = opts
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def extract_info(self, url, download):
                captured['url'] = url
                captured['download'] = download
                Path(captured['opts']['outtmpl'].replace('%(ext)s', 'mp3')).write_bytes(b'ID3' + b'\0'*2048)
                return {'title': 'Demo / Track', 'id': 'dQw4w9WgXcQ'}
        fake = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        with tempfile.TemporaryDirectory() as td, patch('dependencies.shutil.which', return_value='/usr/bin/ffmpeg'), patch.dict(sys.modules, {'yt_dlp': fake}):
            result = download_youtube_mp3('https://youtu.be/dQw4w9WgXcQ', Path(td), '256', cache_dir=Path(td)/'cache')
            self.assertTrue(result.audio_path.is_file())
            self.assertEqual(result.video_id, 'dQw4w9WgXcQ')
            self.assertTrue(captured['download'])
            self.assertTrue(captured['opts']['noplaylist'])
            pp = captured['opts']['postprocessors'][0]
            self.assertEqual(pp['key'], 'FFmpegExtractAudio')
            self.assertEqual(pp['preferredcodec'], 'mp3')
            self.assertEqual(pp['preferredquality'], '256')

    def test_missing_ytdlp_is_optional(self):
        # missing tools fail before importing yt-dlp; no import side-effects
        with tempfile.TemporaryDirectory() as td, patch('dependencies.shutil.which', return_value=None):
            with self.assertRaises(RuntimeError):
                download_youtube_mp3('https://youtu.be/dQw4w9WgXcQ', Path(td), cache_dir=Path(td)/'cache')


class CommandLineTests(unittest.TestCase):
    @staticmethod
    def fake_download(url, workspace, quality):
        assert quality == '192'
        audio = Path(workspace) / 'source.mp3'
        audio.write_bytes(b'ID3example')
        return AudioDownload(audio, 'My Song!', 'dQw4w9WgXcQ')

    def test_mp3_only_does_not_require_transcription(self):
        with tempfile.TemporaryDirectory() as td, patch('studio.download_youtube_mp3', side_effect=self.fake_download), patch('studio._convert_local', side_effect=AssertionError('transcription attempted')):
            paths = studio.convert('https://youtu.be/dQw4w9WgXcQ', Path(td), mp3_only=True)
            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0].suffix, '.mp3')
            self.assertEqual(paths[0].read_bytes(), b'ID3example')
            with self.assertRaises(FileExistsError):
                studio.convert('https://youtu.be/dQw4w9WgXcQ', Path(td), mp3_only=True)

    def test_url_conversion_uses_temporary_mp3(self):
        captured = {}
        def check_local(audio, output, name, preset, spk4, stems, preview, saved_mp3=None, drum_style='auto'):
            self.assertEqual(audio.read_bytes(), b'ID3example')
            self.assertTrue(name.startswith('My_Song'))
            self.assertEqual(spk4, 'adapt')
            self.assertEqual(saved_mp3, audio)
            captured['source'] = audio
            return [Path(output) / 'MYSONG01.MID']
        with tempfile.TemporaryDirectory() as td, patch('studio.download_youtube_mp3', side_effect=self.fake_download), patch('studio._convert_local', side_effect=check_local):
            result = studio.convert('https://youtu.be/dQw4w9WgXcQ', Path(td), spk4='adapt', keep_mp3=True)
            self.assertEqual(result[0].name, 'MYSONG01.MID')
            self.assertFalse(captured['source'].exists(), 'source MP3 should be cleaned from temp')

    def test_flags_are_fully_noninteractive(self):
        with patch('studio.convert', return_value=[Path('A.MID')]) as conv, patch('studio.gui', side_effect=AssertionError('GUI launched')):
            rc = studio.main([
                '--cli', 'https://youtu.be/dQw4w9WgXcQ',
                '-o', 'output', '--preset', 'performance', '--spk4', 'adapt',
                '--stems', '--drum-style', 'rock', '--preview', '--mp3-quality', '320', '--keep-mp3'
            ])
            self.assertEqual(rc, 0)
            self.assertEqual(conv.call_args.kwargs['mp3_quality'], '320')
            self.assertEqual(conv.call_args.kwargs['drum_style'], 'rock')
            self.assertTrue(conv.call_args.kwargs['keep_mp3'])
            self.assertEqual(conv.call_args.args[3], 'adapt')

    def test_cli_requires_input_and_does_not_open_gui(self):
        with patch('studio.gui', side_effect=AssertionError('GUI launched')):
            with self.assertRaises(SystemExit) as cm:
                studio.main(['--cli'])
            self.assertEqual(cm.exception.code, 2)

    def test_unknown_web_url_errors_noninteractive(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(studio.main(['--no-gui', 'https://example.com/audio', '-o', td]), 1)


if __name__ == '__main__':
    unittest.main()
