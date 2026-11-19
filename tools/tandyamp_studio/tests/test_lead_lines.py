from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arranger import Note, voice_coverage
from lead_lines import instrumental_answers, measured_vocal_register, place_vocal_line
from phrase_score import Phrase, Score, ScoreEvidence, arrange_score, reconstruct_score
from pitch_arranger import arrange_tuned


def note(start, end, pitch, role, velocity=84):
    program = {'melody': 80, 'guitar': 30, 'bass': 33, 'harmony': 48}[role]
    return Note(start, end, pitch, velocity, role, program)


class MeasuredVoice:
    cents = 0.

    def __init__(self, strengths):
        self.strengths = strengths

    def sustain_strength(self, n):
        return self.strengths.get(n.pitch, 0.)


class LeadLineTests(unittest.TestCase):
    def test_guide_free_mix_uses_the_singers_measured_octave(self):
        voice = (note(0., .4, 55, 'melody'), note(.52, .8, 58, 'melody'))
        score = Score((), (), (Phrase('melody', 'vocal', voice),))
        evidence = ScoreEvidence()
        evidence.pitches['melody'] = MeasuredVoice({55: .88, 58: .95, 67: 1., 70: .90})
        arranged, _ = arrange_tuned(score, list(voice), evidence=evidence)
        self.assertEqual([(n.start, n.end, n.pitch) for n in arranged],
                         [(0., .4, 55), (.52, .8, 58)])

    def test_clear_octave_error_moves_the_whole_contour_and_weak_evidence_defers(self):
        phrase = (note(0., .4, 72, 'melody'), note(.4, .8, 74, 'melody'))
        signal = MeasuredVoice({60: .96, 62: .9, 72: .18, 74: .2})
        self.assertEqual(measured_vocal_register(phrase, signal),
                         tuple(replace(n, pitch=n.pitch - 12) for n in phrase))
        self.assertIsNone(measured_vocal_register(phrase, MeasuredVoice({72: .2})))

    def test_moving_a_lead_clear_of_guitar_cannot_cover_a_folded_bass_attack(self):
        sung = (note(0., .65, 55, 'melody'), note(.7, 1., 58, 'melody'))
        placed = [replace(n, pitch=n.pitch + 12) for n in sung]
        signal = MeasuredVoice({55: 1., 58: .9})
        bass = [note(.1, .6, 43, 'bass')]
        guitar = [note(.12, .55, 67, 'guitar')]
        self.assertEqual(place_vocal_line(sung, placed, signal, bass, guitar), placed)
        simultaneous = [replace(bass[0], start=sung[0].start)]
        self.assertEqual(place_vocal_line(sung, placed, signal, simultaneous, guitar), placed)
        self.assertEqual(place_vocal_line(sung, placed, signal, [], guitar), list(sung))

    def test_quiet_sung_turn_fits_between_accepted_notes(self):
        evidence = ScoreEvidence(beats=[0., .5, 1., 1.5])
        evidence.pitches['melody'] = MeasuredVoice({67: .9, 65: .85, 63: .88})
        source = [note(0., .33, 67, 'melody'), note(.30, .57, 65, 'melody', 24),
                  note(.70, 1.09, 63, 'melody'), note(1.2, 1.46, 76, 'melody', 24),
                  note(6., 6.35, 65, 'melody', 24)]
        score = reconstruct_score(source, evidence, recover_riff=True, finish_notes=True)
        arranged, _ = arrange_tuned(score, source, evidence=evidence)
        lead = [n for n in arranged if n.part == 'melody']
        self.assertEqual([(n.start, n.end, n.pitch) for n in lead],
                         [(0., .33, 67), (.33, .57, 65), (.70, 1.09, 63)])

    def test_measured_chromatic_turn_survives_both_tuning_passes(self):
        evidence = ScoreEvidence()
        evidence.pitches['melody'] = MeasuredVoice({65: .92, 64: .34})
        voice = tuple(note(s, e, p, 'melody', v) for s, e, p, v in
                      [(0., .28, 64, 90), (.29, .48, 65, 64), (.49, .81, 64, 90)])
        guitar = note(0., .81, 64, 'guitar')
        score = Score((), (), (Phrase('melody', 'vocal', voice),
                               Phrase('guitar', 'riff', (guitar,))))
        arranged, _ = arrange_tuned(score, list(voice) + [guitar], evidence=evidence)
        self.assertEqual([n.pitch % 12 for n in arranged if n.part == 'melody'], [4, 5, 4])

    def test_whole_instrumental_answer_between_vocal_sections(self):
        evidence = ScoreEvidence(beats=[i * .5 for i in range(11)])
        breath = [note(a, a + .18, p, 'harmony') for a, p in
                  ((.56, 67), (.81, 69), (1.02, 71))]
        answer = [note(a, a + .27, p, 'harmony') for a, p in
                  ((2., 62), (2.32, 64), (2.64, 65), (3.02, 62))]
        riff = [note(i * .5, i * .5 + .45, 55, 'guitar') for i in range(10)]
        source = breath + answer + riff + [note(0., 5., 40, 'bass')] + [
            note(a, b, 72, 'melody') for a, b in ((0., .5), (1.28, 1.56), (4.1, 4.45))]
        score = reconstruct_score(source, evidence, recover_riff=True, finish_notes=True)
        lead, = [p for p in score.phrases if p.function == 'instrumental lead']
        self.assertEqual([(n.start, n.end, n.pitch) for n in lead.notes],
                         [(n.start, n.end, n.pitch) for n in answer])
        arranged, _ = arrange_tuned(score, source, evidence=evidence)
        self.assertEqual([(n.start, n.end) for n in arranged if n.part == 'guitar'],
                         [(n.start, n.end) for n in riff])
        self.assertEqual([(n.start, n.end) for n in arranged
                          if n.part == 'melody' and 2. <= n.start < 4.],
                         [(n.start, n.end) for n in answer])
        self.assertFalse(any(.5 <= n.start < 1.28 for n in arranged if n.part == 'melody'))
        self.assertEqual(voice_coverage(arranged)['four_plus'], 0.)

    def test_only_an_independent_audible_line_gets_the_lead(self):
        line = [note(i * .5, i * .5 + .4, p, 'harmony') for i, p in enumerate((60, 62, 65))]
        doubled = [replace(n, part='guitar', pitch=n.pitch - 12) for n in line]
        self.assertEqual(instrumental_answers(line, [], [], doubled, .5, {}, None), [])
        levels = {'harmony': [.01] * 50, 'guitar': [.4] * 50}
        self.assertEqual(instrumental_answers(line, [], [], [], .5, levels, None), [])
        # Both instruments double the opening third of each lead note.
        partial = [replace(n, end=n.start + .13) for n in doubled]
        self.assertEqual(instrumental_answers(line, [], partial, partial, .5, {}, None), [line])

    def test_instrumental_piece_can_have_a_lead_without_a_guitar_or_vocal(self):
        source = [note(i * .42, i * .42 + .27, p, 'harmony')
                  for i, p in enumerate((60, 65, 63))]
        score = reconstruct_score(source, recover_riff=True, finish_notes=True)
        self.assertEqual([p.function for p in score.phrases], ['instrumental lead'])
        arranged, _ = arrange_tuned(score, source)
        self.assertEqual([n.pitch % 12 for n in arranged], [0, 5, 3])

    def test_guitar_level_follows_the_verse_and_returns_for_the_break(self):
        riff = tuple(note(a, a + .18, 57, 'guitar') for a in (.25, 1.1, 1.7, 2.6, 3.2, 4.1))
        sung = (Phrase('melody', 'vocal', (note(1., 1.5, 67, 'melody'),)),
                Phrase('melody', 'vocal', (note(2.4, 2.8, 69, 'melody'),)))
        score = Score(tuple(i * .5 for i in range(10)), (),
                      (Phrase('guitar', 'riff', riff, reconstructed=True), *sung))
        guitar = [n for n in arrange_score(score) if n.part == 'guitar']
        self.assertEqual([(n.start, n.end, n.pitch) for n in guitar],
                         [(n.start, n.end, n.pitch) for n in riff])
        loud, under_voice, breath, next_line, after, end = [n.velocity for n in guitar]
        self.assertEqual((under_voice, breath), (breath, next_line))
        self.assertEqual((loud, after), (after, end))
        self.assertLess(breath, after)


if __name__ == '__main__':
    unittest.main()
