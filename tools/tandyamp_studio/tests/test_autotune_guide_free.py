"""Guide-free AutoTune regression tests: coherent riff and evidenced tuning.

The reference-MIDI PARATUNE path is intentionally untouched.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arranger import Note
from phrase_score import Phrase, Score
from pitch_arranger import (
    _coherent_guitar_line, _ensemble_correction, arrange_tuned,
)


def n(at: float, end: float, pitch: int, velocity: int,
      role: str = 'guitar') -> Note:
    program = {'guitar':30, 'bass':33, 'melody':80, 'harmony':48}[role]
    return Note(at, end, pitch, velocity, role, program)


class GuideFreeAutoTuneTests(unittest.TestCase):
    def test_weak_stem_overtone_cannot_cut_off_ringing_guitar(self):
        source = [
            n(0, .95, 52, 95),
            n(.34, .40, 76, 51),
            n(.5, .58, 52, 55),
            n(.98, 1.45, 57, 96),
        ]
        cleaned = _coherent_guitar_line(source)
        self.assertEqual([(x.start, x.end, x.pitch) for x in cleaned],
                         [(0, .95, 52), (.98, 1.45, 57)])
        self.assertEqual(cleaned[0].velocity, 95)

    def test_near_simultaneous_guitar_chord_keeps_one_source_voice(self):
        source = [
            n(0, .7, 52, 95),
            n(0, .35, 64, 62),
            n(.005, .23, 76, 40),
        ]
        out = _coherent_guitar_line(source)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].pitch, 52)

    def test_real_strong_riff_attack_is_not_dropped(self):
        source = [n(0,.75,52,87), n(.45, .93, 57, 106)]
        out = _coherent_guitar_line(source)
        self.assertEqual([(x.start,x.end,x.pitch) for x in out],
                         [(0,.45,52),(.45,.93,57)])

    def test_strong_repeat_keeps_two_attack_events(self):
        source = [n(0,.30,52,95),n(.30,.60,52,95)]
        out = _coherent_guitar_line(source)
        self.assertEqual(out, source)

    def test_weak_same_pitch_glitch_is_held_without_new_attack(self):
        source = [n(0,.60,52,95),n(.43,.51,52,60)]
        out = _coherent_guitar_line(source)
        self.assertEqual(out, source[:1])

    def test_bass_inferred_fifth_does_not_move_real_blues_note(self):
        bass = n(0,2,48,97,'bass')   # C3 root: implied G would be MIDI67.
        chromatic = n(.5,.70,66,63,'guitar')  # F# is not automatically wrong.
        score = Score((),(),(Phrase('bass','bass',(bass,)),
                              Phrase('guitar','riff',(chromatic,))))
        with patch('pitch_arranger._estimate_key',
                   return_value=('C major',{0,2,4,5,7,9,11})):
            corrected, report = _ensemble_correction(score,Counter())
        self.assertEqual(corrected.phrases[1].notes,(chromatic,))
        self.assertEqual(report.corrected,{})

    def test_observed_chromatic_pitch_outweighs_estimated_key(self):
        guitar = n(0,1,61,97,'guitar')  # C# supported in the guitar stem
        vocal = n(.25,.44,60,69,'melody')
        score = Score((),(),(Phrase('guitar','riff',(guitar,)),
                              Phrase('melody','vocal',(vocal,))))
        with patch('pitch_arranger._estimate_key',
                   return_value=('C major',{0,2,4,5,7,9,11})):
            corrected, report = _ensemble_correction(score,Counter())
        self.assertEqual(corrected.phrases[1].notes[0].pitch,61)
        self.assertEqual(report.corrected,{'melody':1})

    def test_ambiguous_two_stem_semitones_cannot_force_choice(self):
        guitar = n(0,1,60,94,'guitar')
        harmony = n(0,1,62,94,'harmony')
        singer = n(.2,.4,61,65,'melody')
        score = Score((),(),(Phrase('guitar','riff',(guitar,)),
                              Phrase('harmony','support',(harmony,)),
                              Phrase('melody','vocal',(singer,))))
        corrected, report = _ensemble_correction(score, Counter())
        self.assertEqual(corrected.phrases[2].notes[0],singer)
        self.assertFalse(report.corrected)

    def test_midi_guide_not_rerouted_to_automatic_guitar_helper(self):
        import inspect
        from pitch_arranger import _automatic_mix, _reference_mix
        self.assertIn('_coherent_guitar_line',inspect.getsource(_automatic_mix))
        self.assertNotIn('_coherent_guitar_line',inspect.getsource(_reference_mix))

    def test_end_to_end_guide_free_tuned_preserves_riff_and_vocal(self):
        held = n(0,1,52,95)
        weak = n(.3,.37,76,45)
        next_attack = n(1.02,1.5,57,94)
        lead = n(.6,.92,67,93,'melody')
        bass = n(0,1.5,40,95,'bass')
        score=Score((),(),(Phrase('bass','bass',(bass,)),
                           Phrase('guitar','riff',(held,weak,next_attack)),
                           Phrase('melody','vocal',(lead,))))
        arranged,_=arrange_tuned(score,[bass,held,weak,next_attack,lead])
        guitar=[x for x in arranged if x.part=='guitar']
        # AutoTune may transpose the complete phrase by an octave to
        # make it audible beside bass/vocals. Preserve contour and timing.
        self.assertEqual([(x.pitch % 12,x.start) for x in guitar],
                         [(52 % 12,0),(57 % 12,1.02)])
        self.assertEqual(guitar[1].pitch - guitar[0].pitch,5)
        self.assertGreaterEqual(guitar[0].end,.98)
        self.assertEqual([x.pitch for x in arranged if x.part=='melody'],[67])
        self.assertTrue(any(x.part=='bass' for x in arranged))


if __name__=='__main__':
    unittest.main()
