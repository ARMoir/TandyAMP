"""Audio phrase selection and its Studio export, without model downloads."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arranger import Note, load_midi, voice_coverage
from phrase_score import ScoreEvidence, arrange_score, reconstruct_score
import studio


def note(part, start, end, pitch, velocity=80):
    return Note(start, end, pitch, velocity, part)


def line(score, part):
    return [n for phrase in score.phrases if phrase.part == part for n in phrase.notes]


class PhraseScoreTests(unittest.TestCase):
    def test_silent_stem_bleed_cannot_enter_guitar_intro(self):
        notes = [note('guitar', 0, .30, 52), note('guitar', .38, .65, 57),
                 note('bass', 0, .30, 40, 120), note('melody', 0, .30, 64, 120),
                 note('bass', 1, 1.5, 40), note('melody', 1, 1.5, 67),
                 note('drums', 1, 1.07, 36)]
        evidence = ScoreEvidence(levels={
            'bass': [.00001] * 20 + [.12] * 12,
            'melody': [.00001] * 20 + [.10] * 12,
            'guitar': [.10] * 33,
        })
        score = reconstruct_score(notes, evidence)
        self.assertEqual([n.start for n in line(score, 'bass')], [1])
        self.assertEqual([n.start for n in line(score, 'melody')], [1])
        self.assertEqual([n.pitch for n in line(score, 'guitar')], [52, 57])
        self.assertEqual(list(score.drums), notes[-1:])

    def test_a_loud_overtone_cannot_punch_a_hole_in_a_sustain(self):
        riff = [note('guitar', 0, .48, 52), note('guitar', .50, .71, 52, 86),
                note('guitar', .75, .99, 57)]
        unrelated = note('guitar', .18, .28, 76, 115)
        score = reconstruct_score([unrelated, *riff], connect=False)
        self.assertEqual(line(score, 'guitar'), riff)

    def test_intentional_pick_attack_can_follow_a_ringing_string(self):
        first = note('guitar', .30, .73, 62, 54)
        attack = note('guitar', .47, .68, 64, 84)
        finish = note('guitar', .71, .90, 57, 81)
        notes = line(reconstruct_score([first, attack, finish], connect=False), 'guitar')
        self.assertEqual([(n.start, n.pitch) for n in notes], [(n.start, n.pitch)
                                                               for n in (first, attack, finish)])
        self.assertEqual(notes[0].end, attack.start)

    def test_sparse_guitar_backing_is_a_phrase_decision(self):
        bass = [note('bass', i * .5, i * .5 + .45, 40) for i in range(4)]
        drums = [note('drums', i * .5, i * .5 + .07, 36) for i in range(4)]
        vocals = [note('melody', .05, .6, 67), note('melody', .65, 1.1, 69),
                  note('melody', 1.2, 2, 67)]
        pitches = [55, 58, 56, 63, 60, 55, 59, 52]
        guitar = [note('guitar', .1 + .25 * i, .29 + .25 * i, p)
                  for i, p in enumerate(pitches)]
        harmony = [note('harmony', .30, .37, 65, 118)]
        score = reconstruct_score(bass + drums + vocals + guitar + harmony,
                                  ScoreEvidence(beats=[0, .5, 1, 1.5, 2]))
        self.assertEqual([p.function for p in score.phrases if p.part == 'guitar'],
                         ['backing'])
        self.assertEqual(len(line(score, 'guitar')), 4)
        self.assertEqual(len(line(score, 'melody')), len(vocals))
        self.assertFalse(line(score, 'harmony'))
        self.assertEqual(voice_coverage(arrange_score(score))['four_plus'], 0)
        self.assertEqual(sorted(n.start for n in score.drums), [n.start for n in drums])

    def test_recurring_riff_continues_under_the_vocal_phrase(self):
        pitches = [55, 57, 60, 57]
        guitar = [note('guitar', offset + .24 * i, offset + .24 * i + .20, p)
                  for offset in (0, 2) for i, p in enumerate(pitches)]
        vocals = [note('melody', 1.95, 2.35, 67),
                  note('melody', 2.49, 2.94, 69)]
        score = reconstruct_score(guitar + vocals, connect=False)
        parts = [p for p in score.phrases if p.part == 'guitar']
        self.assertEqual([p.function for p in parts], ['riff', 'riff'])
        self.assertEqual(line(score, 'guitar'), guitar)

    def test_studio_writes_score_and_progressive_previews(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / 'input.wav'
            source.touch()
            notes = [note('bass', 0, .5, 40), note('guitar', 0, .4, 57),
                     note('melody', .08, .5, 67), note('drums', .05, .12, 36)]
            with patch('transcribe.transcribe_audio', return_value=notes) as transcribe:
                mid, = studio.convert(source, work / 'out', arrangement='core',
                                      spk4='off')
            self.assertIsInstance(transcribe.call_args.kwargs['score_evidence'],
                                  ScoreEvidence)
            score = json.loads((mid.parent / 'SCORE.json').read_text())
            self.assertEqual({p['part'] for p in score['phrases']},
                             {'bass', 'guitar', 'melody'})
            self.assertEqual(len(load_midi(mid)), 4)
            for path in ('PREVIEW.WAV', 'AUDITION/RHYTHM.WAV', 'AUDITION/RIFF.WAV'):
                self.assertTrue((mid.parent / path).is_file())


if __name__ == '__main__':
    unittest.main()
