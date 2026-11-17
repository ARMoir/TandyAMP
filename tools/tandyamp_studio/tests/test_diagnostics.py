from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arranger import Note
from diagnostics import note_metrics, file_digest, save_stage
from prediction_cache import decoder_settings
from transcribe import _predict


class DiagnosticsTests(unittest.TestCase):
    def test_metrics_follow_smart_mode_and_measure_audible_roles(self):
        notes = [Note(0, 1, p, 35, 'melody') for p in (84, 86, 88)]
        notes.append(Note(0, 1, 64, 95, 'guitar'))
        legacy = note_metrics(notes, spk4='off')
        smart = note_metrics(notes, spk4='off', voice_selection='smart')
        self.assertNotIn('guitar', legacy['preview_role_seconds'])
        self.assertEqual(smart['preview_role_seconds']['guitar'], 1)
        self.assertEqual(smart['voice_selection'], 'smart')
        self.assertEqual(smart['preview_voice_steals'], 0)

    def test_source_silence_and_overlapping_role_union(self):
        notes = [Note(1, 3, 60, 90, 'guitar'), Note(2, 4, 67, 90, 'guitar')]
        got = note_metrics(notes, duration=6)
        self.assertEqual(got['role_active_seconds']['guitar'], 3)
        self.assertEqual(got['candidate_seconds']['silent'], 3)
        self.assertEqual(got['longest_pitched_gap'], 2)
        self.assertEqual(sum(got['preview_voice_seconds'].values()), 6)

    def test_four_candidates_do_not_promise_four_audible_voices(self):
        notes = [Note(0, 1, 36, 40, 'bass')] + [
            Note(0, 1, p, 80, 'guitar') for p in (60, 64, 67)]
        got = note_metrics(notes)
        self.assertEqual(got['candidate_seconds']['four_candidate'], 1)
        self.assertEqual(got['preview_voice_seconds']['4'], 0)
        notes[0] = Note(0, 1, 36, 90, 'bass')
        self.assertEqual(note_metrics(notes)['preview_voice_seconds']['4'], 1)
        self.assertEqual(note_metrics(notes, spk4='off')['preview_voice_seconds']['4'], 0)

    def test_empty_audio_reports_duration(self):
        got = note_metrics([], 5)
        self.assertEqual(got['candidate_seconds']['silent'], 5)
        self.assertEqual(got['preview_voice_seconds']['0'], 5)

    def test_snapshots_and_digest_change_with_content(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'test.json'
            save_stage(Path(td), 'test', [], 3)
            first = file_digest(path)
            save_stage(Path(td), 'test', [], 4)
            self.assertNotEqual(first, file_digest(path))


class DecoderTests(unittest.TestCase):
    def test_sensitive_only_affects_separated_guitar_and_harmony(self):
        for part in (None, 'bass', 'melody'):
            self.assertEqual(decoder_settings(part, 'standard'),
                             decoder_settings(part, 'sensitive'))
        for part in ('guitar', 'harmony'):
            self.assertEqual(decoder_settings(part, 'sensitive')['min_note_len'], 7)
        with self.assertRaises(ValueError):
            decoder_settings('guitar', 'unknown')

    def test_sensitive_parameters_reach_basic_pitch(self):
        package = types.ModuleType('basic_pitch')
        package.ICASSP_2022_MODEL_PATH = 'model'
        inference = types.ModuleType('basic_pitch.inference')
        seen = {}
        def predict(audio, model, **settings):
            seen.update(settings)
            return {}, types.SimpleNamespace(instruments=[]), []
        inference.predict = predict
        with patch.dict(sys.modules, {'basic_pitch': package, 'basic_pitch.inference': inference}):
            _predict(Path('guitar.wav'), 'guitar', profile='sensitive')
        self.assertEqual(seen['onset_threshold'], .35)
        self.assertEqual(seen['frame_threshold'], .20)
        self.assertAlmostEqual(seen['minimum_note_length'], 81.26984127)


if __name__ == '__main__':
    unittest.main()
