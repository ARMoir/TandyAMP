"""Guide-free phrase reconstruction before the Tandy voice mix."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arranger import Note, voice_coverage
from phrase_score import ScoreEvidence, reconstruct_score
from pitch_arranger import arrange_tuned
from stem_pitch import FRAME_SECONDS, StemPitch
from studio import _stabilize_tuned


def note(start, end, pitch, velocity=85, part='guitar', program=30):
    return Note(start, end, pitch, velocity, part, program)


def motif(start, part='guitar', program=30):
    return [note(start + offset, start + offset + .15, pitch, velocity, part, program)
            for offset, pitch, velocity in ((0., 57, 69), (.19, 59, 74),
                                            (.38, 62, 78), (.57, 59, 75))]


def reconstructed(source):
    cleaned, _ = _stabilize_tuned(source)
    evidence = ScoreEvidence(beats=[i * .38 for i in range(12)])
    score = reconstruct_score(cleaned, evidence, recover_riff=True, finish_notes=True)
    arranged, _ = arrange_tuned(score, cleaned, evidence=evidence)
    return score, arranged


class RiffReconstructionTests(unittest.TestCase):
    def test_repeat_repairs_the_guitar_line_and_continues_under_the_vocal(self):
        riff = motif(0.) + motif(1.52)
        candidates = riff + [
            note(.19, .32, 71, 89),
            note(.29, .37, 86, 103),
            note(1.73, 1.86, 66, 96),
            note(1.90, 2.04, 74, 91),
        ]
        bass = note(1.50, 2.36, 40, 90, 'bass', 33)
        vocal = note(1.57, 2.36, 67, 93, 'melody', 80)
        drum = note(1.52, 1.57, 36, 90, 'drums', 0)
        score, arranged = reconstructed(candidates + [bass, vocal, drum])
        guitar_phrases = [p for p in score.phrases if p.part == 'guitar']
        self.assertTrue(all(p.reconstructed and p.function == 'riff'
                            for p in guitar_phrases))
        kept = [n for n in arranged if n.part == 'guitar']
        self.assertEqual([(n.start, n.end, n.pitch) for n in kept],
                         [(n.start, n.end, n.pitch) for n in riff])
        self.assertEqual([(n.start, n.end) for n in arranged if n.part == 'melody'],
                         [(vocal.start, vocal.end)])
        self.assertEqual(voice_coverage(arranged)['four_plus'], 0)

    def test_fragments_merge_and_real_reattacks_keep_their_complete_length(self):
        held = note(0., .19, 57, 97)
        tail = note(.22, .41, 57, 54)
        beep = note(.30, .37, 81, 76)
        strike = note(.42, .64, 57, 97)
        end = note(.65, .91, 62, 95)
        _, arranged = reconstructed([held, tail, beep, strike, end])
        guitar = [n for n in arranged if n.part == 'guitar']
        self.assertEqual([(n.start, n.end, n.pitch) for n in guitar],
                         [(0., .41, 57), (.42, .64, 57), (.65, .91, 62)])

    def test_local_register_moves_with_an_independent_high_phrase(self):
        low = [note(t, t + .17, p) for t, p in ((0., 52), (.22, 55), (.44, 57))]
        high = [note(t, t + .17, p) for t, p in
                ((1.2, 86), (1.42, 89), (1.64, 88), (1.86, 86))]
        score, arranged = reconstructed(low + high)
        self.assertEqual([n.pitch for n in score.pitched_notes()],
                         [n.pitch for n in low + high])
        highs = [n for n in arranged if n.start >= high[0].start]
        self.assertEqual([n.pitch - highs[0].pitch for n in highs], [0, 3, 2, 0])

    def test_keyboard_or_synth_can_supply_the_companion_riff(self):
        for program in (0, 81):
            with self.subTest(program=program):
                riff = motif(0., 'harmony', program) + motif(1.52, 'harmony', program)
                _, arranged = reconstructed(riff)
                self.assertEqual([(n.start, n.end, n.pitch) for n in arranged],
                                 [(n.start, n.end, n.pitch) for n in riff])
                self.assertTrue(all(n.part == 'guitar' for n in arranged))

    def test_measured_stem_recovers_a_pitch_missing_from_the_decoder(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('NumPy is required for stem pitch measurements')

        intended = motif(0.) + motif(1.52)
        first = 52
        strength = np.zeros((120, 16), dtype=np.float32)
        for n in intended:
            start = round(n.start / FRAME_SECONDS)
            end = round(n.end / FRAME_SECONDS)
            strength[start:end, n.pitch - first] = 1.
        evidence = ScoreEvidence(beats=[i * .38 for i in range(12)])
        evidence.pitches['guitar'] = StemPitch(first, strength, 0.)
        source = intended[:6] + intended[7:]
        score = reconstruct_score(source, evidence, recover_riff=True, finish_notes=True)
        out, _ = arrange_tuned(score, source, evidence=evidence)
        guitar = [n for n in out if n.part == 'guitar']
        self.assertEqual([n.pitch for n in guitar], [n.pitch for n in intended])
        self.assertAlmostEqual(guitar[6].start, intended[6].start, delta=.04)


if __name__ == '__main__':
    unittest.main()
