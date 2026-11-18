"""Check the GUI, CLI and Python defaults against the PARATUNE settings."""
from __future__ import annotations

import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import studio
from defaults import BUILD56_DEFAULTS, BUILD56_REFERENCE_MIDI_SHA256, STUDIO_DEFAULTS


EXPECTED = {
    'preset': 'balanced',
    'spk4': 'off',
    'stems': False,  # guitar separation implicitly enables six-stem
    'preview': True,
    'drum_style': 'rock',
    'note_preservation': 'full',
    'guitar_separation': True,
    'accompaniment': 'off',
    'transcription': 'sensitive',
    'voice_selection': 'smart',
    'max_raw': False,
    'mp3_quality': '192',
    'arrangement': 'tuned',
    'core_smoothing': 'auto',
}


class StudioDefaultTests(unittest.TestCase):
    def test_approved_profile_and_legacy_reference(self):
        self.assertEqual(dict(STUDIO_DEFAULTS), EXPECTED)
        self.assertEqual(BUILD56_DEFAULTS['spk4'], 'adapt')
        self.assertEqual(
            BUILD56_REFERENCE_MIDI_SHA256,
            'c8f9c342a7632ac50df52f8eb6f4c26e0dc56e42c001ef52a5b7b9a1a606ad5f'
        )

    def test_python_convert_defaults_match_paratune(self):
        signature = inspect.signature(studio.convert)
        for key, value in EXPECTED.items():
            with self.subTest(option=key):
                self.assertEqual(signature.parameters[key].default, value)

    def test_cli_with_no_conversion_options_uses_paratune_profile(self):
        with patch('studio.convert', return_value=[Path('A.MID')]) as convert:
            rc = studio.main(['--cli', 'https://youtu.be/Uq42HUUJFzU'])
        self.assertEqual(rc, 0)
        args = convert.call_args.args
        kwargs = convert.call_args.kwargs
        self.assertEqual(args[2:6],
                         (EXPECTED['preset'], EXPECTED['spk4'],
                          EXPECTED['stems'], EXPECTED['preview']))
        for key in ('mp3_quality', 'drum_style', 'note_preservation',
                    'guitar_separation', 'accompaniment', 'transcription',
                    'voice_selection', 'max_raw', 'arrangement'):
            with self.subTest(key=key):
                self.assertEqual(kwargs[key], EXPECTED[key])

    def test_manual_overrides_can_disable_new_default_modes(self):
        cli = [
            '--cli', 'https://youtu.be/Uq42HUUJFzU',
            '--preset', 'performance', '--spk4', 'off',
            '--drum-style', 'auto', '--note-preservation', 'clean',
            '--no-guitar-separation', '--accompaniment', 'recover',
            '--transcription', 'standard', '--voice-selection', 'legacy',
            '--no-preview',
        ]
        with patch('studio.convert', return_value=[Path('B.MID')]) as convert:
            self.assertEqual(studio.main(cli), 0)
        a = convert.call_args.args
        k = convert.call_args.kwargs
        self.assertEqual(a[2], 'performance')
        self.assertEqual(a[3], 'off')
        self.assertFalse(a[5])
        self.assertEqual(k['drum_style'], 'auto')
        self.assertEqual(k['note_preservation'], 'clean')
        self.assertFalse(k['guitar_separation'])
        self.assertEqual(k['accompaniment'], 'recover')
        self.assertEqual(k['transcription'], 'standard')
        self.assertEqual(k['voice_selection'], 'legacy')
        self.assertFalse(k['max_raw'])

    def test_max_raw_is_still_opt_in(self):
        with patch('studio.convert', return_value=[Path('RAW.MID')]) as convert:
            self.assertEqual(studio.main([
                '--cli', 'https://youtu.be/Uq42HUUJFzU', '--max-raw'
            ]), 0)
        self.assertTrue(convert.call_args.kwargs['max_raw'])

    def test_gui_gets_defaults_from_same_profile(self):
        gui_source = inspect.getsource(studio.gui)
        for variable in ('preset', 'spk4', 'drum_style', 'note_preservation',
                         'guitar_separation', 'accompaniment',
                         'transcription', 'voice_selection', 'preview',
                         'max_raw', 'arrangement', 'core_smoothing'):
            with self.subTest(gui_variable=variable):
                self.assertIn(
                    f"{variable} = tk.", gui_source
                )
                self.assertIn(
                    f"value=DEFAULTS['{variable}']", gui_source
                )


if __name__ == '__main__':
    unittest.main()
