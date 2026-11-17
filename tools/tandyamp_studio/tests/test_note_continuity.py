"""Protect real chords and sustain while removing transcription duplicates."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arranger import Note
from postprocess import clean_stem_notes
from transcribe import remove_guitar_bleed


class ContinuityTests(unittest.TestCase):
    def test_overlapping_quiet_octave_is_not_a_sequential_glitch(self):
        notes = [Note(0, .5, 60, 90, 'guitar'),
                 Note(.10, .22, 72, 60, 'guitar'),
                 Note(.25, .75, 60, 90, 'guitar')]
        self.assertIn(notes[1], clean_stem_notes(notes, 'guitar', 'full'))

    def test_sequential_short_weak_octave_glitch_is_still_removed(self):
        notes = [Note(0, .2, 60, 90, 'melody'),
                 Note(.2, .32, 72, 60, 'melody'),
                 Note(.32, .6, 60, 90, 'melody')]
        self.assertNotIn(notes[1], clean_stem_notes(notes, 'melody', 'full'))

    def test_legitimate_non_octave_leap_is_preserved(self):
        notes = [Note(0, .2, 60, 90, 'melody'),
                 Note(.2, .32, 71, 60, 'melody'),
                 Note(.32, .6, 60, 90, 'melody')]
        self.assertIn(notes[1], clean_stem_notes(notes, 'melody', 'full'))

    def test_short_guitar_does_not_delete_long_harmony_tail(self):
        guitar = [Note(0, .3, 64, 90, 'guitar')]
        other = [Note(.01, 1.5, 64, 65, 'harmony')]
        kept = remove_guitar_bleed(guitar, other)
        self.assertEqual(kept, [Note(.3, 1.5, 64, 65, 'harmony')])

    def test_exact_duplicate_and_tiny_tail_disappear(self):
        guitar = [Note(0, 1, 64, 90, 'guitar')]
        for end in (1, 1.02):
            self.assertEqual(remove_guitar_bleed(guitar,
                             [Note(.01, end, 64, 65, 'harmony')]), [])

    def test_unrelated_pitch_or_later_attack_is_preserved(self):
        guitar = [Note(0, 1, 64, 90, 'guitar')]
        other = [Note(.01, 1.5, 67, 65, 'harmony'),
                 Note(.5, 1.5, 64, 65, 'harmony')]
        self.assertEqual(remove_guitar_bleed(guitar, other), other)

    def test_multiple_overlaps_never_extend_or_duplicate_support(self):
        guitar = [Note(0, .4, 64, 90, 'guitar'),
                  Note(.1, .7, 64, 80, 'guitar')]
        other = [Note(0, 1, 64, 65, 'harmony')]
        self.assertEqual(remove_guitar_bleed(guitar, other),
                         [Note(.7, 1, 64, 65, 'harmony')])


if __name__ == '__main__':
    unittest.main()
