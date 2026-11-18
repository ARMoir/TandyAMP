"""AutoTune harmonic-context regression checks.

A short estimated note can finish while a previously established bass/guitar
line continues. The harmony tuner must not interpret that overlap as silence.
No pretrained-model download or copyrighted audio is needed.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arranger import Note
from phrase_score import Phrase, Score
from pitch_arranger import _near_note, _ensemble_correction, arrange_tuned


def n(start, end, pitch, velocity=85, part='guitar'):
    return Note(start, end, pitch, velocity, part,
                {'guitar':30,'bass':33,'melody':80,'harmony':48}[part])


class AutoTuneContextBenchmarks(unittest.TestCase):
    def test_held_foundation_survives_ended_overlap(self):
        notes=[n(0,3,40,91,'bass'),
               n(1.0,1.12,52,70,'bass'),
               n(1.20,1.27,47,60,'bass')]
        self.assertEqual(_near_note(notes, [a.start for a in notes], 1.60),
                         notes[0])
        self.assertEqual(_near_note(notes,[a.start for a in notes],.7),
                         notes[0])
        self.assertEqual(_near_note(notes,[a.start for a in notes],3.2),
                         None)

    def test_ensemble_sees_ringing_chord_through_short_blip(self):
        held=n(0,2,60,96,'guitar')
        spur=n(1.0,1.11,67,60,'guitar')
        lead=n(1.30,1.46,61,69,'melody')
        score=Score((),(),(Phrase('guitar','riff',(held,spur)),
                            Phrase('melody','vocal',(lead,))))
        result,report=_ensemble_correction(score,Counter())
        self.assertEqual([x.pitch for p in result.phrases
                          if p.part=='melody' for x in p.notes],[60])
        self.assertEqual(report.corrected, {'melody':1})
        self.assertEqual([x.pitch for p in result.phrases
                          if p.part=='guitar' for x in p.notes], [60,67])

    def test_tuned_output_keeps_real_guitar_context(self):
        held=n(0,2,60,96,'guitar')
        spur=n(1.0,1.11,67,60,'guitar')
        lead=n(1.30,1.46,61,69,'melody')
        score=Score((),(),(Phrase('guitar','riff',(held,spur)),
                            Phrase('melody','vocal',(lead,))))
        arranged,report=arrange_tuned(score,[held,spur,lead])
        self.assertIn(60,[x.pitch for x in arranged if x.part=='melody'])
        self.assertEqual(report.ensemble_repairs, {'melody':1})

    def test_rests_and_strong_chromatic_notes_remain(self):
        held=n(0,.30,60,96,'guitar')
        after=n(1.0,1.11,67,60,'guitar')
        chromatic=n(1.3,1.46,61,104,'melody')
        score=Score((),(),(Phrase('guitar','riff',(held,after)),
                            Phrase('melody','vocal',(chromatic,))))
        tuned, report=_ensemble_correction(score,Counter())
        self.assertEqual(tuned.phrases[-1].notes,(chromatic,))
        self.assertFalse(report.corrected)

    def test_nearby_live_note_wins_over_older_held_note(self):
        notes=[n(0,3,40), n(1,2,45), n(1.5,1.55,50)]
        self.assertEqual(_near_note(notes,[a.start for a in notes],1.7),
                         notes[1])
        self.assertEqual(_near_note(notes,[a.start for a in notes],2.5),
                         notes[0])


if __name__ == '__main__':
    unittest.main()
