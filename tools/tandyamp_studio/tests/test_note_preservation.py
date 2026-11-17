"""Full-vs-clean regression suite for lossless-first transcribed note selection."""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from arranger import Note, prepare, normalize, voice_coverage
from postprocess import clean_stem_notes
from transcribe import transcribe_audio


class PreservationTests(unittest.TestCase):
    def test_full_preserves_second_melodic_pitch(self):
        lead = [Note(0, 1, 60, 75, 'melody'),
                Note(0, 1, 64, 72, 'melody')]
        clean = clean_stem_notes(lead, 'melody', 'clean')
        full = clean_stem_notes(lead, 'melody', 'full')
        self.assertEqual(len(clean), 1)
        self.assertEqual(len(full), 2)
        self.assertEqual({n.pitch for n in full}, {60, 64})

    def test_all_credible_countermelodies_reach_final_psg_allocator(self):
        guitar = [Note(0, 1, p, 75, 'harmony')
                  for p in (48, 52, 55, 59, 64)]
        full = clean_stem_notes(guitar, 'harmony', 'full')
        clean = clean_stem_notes(guitar, 'harmony', 'clean')
        self.assertEqual(len(full), 5)
        self.assertEqual(len(clean), 2)
        # Hardware still cannot invent more than 3 PSG channels.
        rendered = prepare(full, preset='balanced', spk4='off',
                           preserve=True)
        self.assertEqual(len(rendered), 3)
        self.assertAlmostEqual(voice_coverage(rendered)['three_plus'], 1.0)

    def test_full_preserves_three_evidenced_harmony_tones(self):
        harmony = [Note(0, 1, p, 77, 'harmony') for p in (55, 59, 62)]
        clean = clean_stem_notes(harmony, 'harmony', 'clean')
        full = clean_stem_notes(harmony, 'harmony', 'full')
        self.assertEqual(len(clean), 2)
        self.assertEqual({n.pitch for n in full}, {55, 59, 62})

    def test_full_preserves_quieter_verse_note_and_short_attack(self):
        notes = [Note(0, .50, 60, 100, 'harmony'),
                 Note(.60, .67, 64, 40, 'harmony'),
                 Note(.90, 1.30, 62, 80, 'harmony')]
        clean = clean_stem_notes(notes, 'harmony', 'clean')
        full = clean_stem_notes(notes, 'harmony', 'full')
        self.assertEqual([n.pitch for n in clean], [60, 62])
        self.assertEqual([n.pitch for n in full], [60, 64, 62])

    def test_normalize_full_keeps_short_balanced_notes(self):
        notes = [Note(0, .052, 60, 85, 'melody')]
        self.assertEqual(len(normalize(notes, 'balanced')), 0)
        self.assertEqual(len(normalize(notes, 'balanced', preserve=True)), 1)

    def test_full_arrangement_has_more_active_voices_with_same_source(self):
        bass = [Note(0, 1, 40, 98, 'bass')]
        melody = [Note(0, 1, 60, 80, 'melody'),
                  Note(0, 1, 64, 78, 'melody')]
        a = bass + clean_stem_notes(melody, 'melody', 'clean')
        b = bass + clean_stem_notes(melody, 'melody', 'full')
        quiet = prepare(a, 'balanced', 'adapt', preserve=False)
        full = prepare(b, 'balanced', 'adapt', preserve=True)
        self.assertGreater(voice_coverage(full)['three_plus'],
                           voice_coverage(quiet)['three_plus'])
        self.assertEqual(voice_coverage(quiet)['three_plus'], 0)
        self.assertLessEqual(voice_coverage(full)['three_plus'], 1.0)

    def test_full_never_invents_untranscribed_notes(self):
        source = [Note(0, .50, 60, 80, 'melody'),
                  Note(.1, .40, 64, 65, 'melody')]
        full = clean_stem_notes(source, 'melody', 'full')
        self.assertTrue(full)
        for n in full:
            self.assertTrue(any(n.pitch == o.pitch and
                                o.start <= n.start and n.end <= o.end
                                for o in source))

    def test_legacy_defaults_still_clean(self):
        notes = [Note(0, 1, 60, 85, 'melody'),
                 Note(0, 1, 64, 75, 'melody')]
        self.assertEqual(clean_stem_notes(notes, 'melody'),
                         clean_stem_notes(notes, 'melody', 'clean'))
        self.assertEqual(prepare(notes), prepare(notes, preserve=False))
        with self.assertRaises(ValueError):
            clean_stem_notes(notes, 'melody', 'unrecognized')

    def test_coverage_reports_silence_one_two_three_and_bass_only(self):
        notes = [Note(.0, 2, 40, 90, 'bass'),
                 Note(.5, 1.5, 60, 90, 'melody'),
                 Note(1.0, 1.5, 64, 80, 'harmony')]
        stats = voice_coverage(notes)
        self.assertAlmostEqual(stats['duration'], 2)
        self.assertAlmostEqual(stats['silent'], 0)
        self.assertAlmostEqual(stats['one'], 1.0)
        self.assertAlmostEqual(stats['two'], .5)
        self.assertAlmostEqual(stats['three_plus'], .5)
        self.assertAlmostEqual(stats['bass_only'], 1.0)
        self.assertEqual(voice_coverage([])['duration'], 0)

    def test_direct_audio_uses_requested_mode_without_demucs(self):
        source = [Note(0, 1, 60, 80, 'melody'),
                  Note(0, 1, 64, 75, 'melody')]
        with patch('transcribe._predict', return_value=source):
            full = transcribe_audio(pathlib.Path('demo.wav'), stems=False,
                                    preservation='full')
            clean = transcribe_audio(pathlib.Path('demo.wav'), stems=False,
                                     preservation='clean')
        self.assertGreater(len(full), len(clean))


if __name__ == '__main__':
    unittest.main()
