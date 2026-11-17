"""Evidence-gated accompaniment and six-stem guitar regression tests.

Lightweight CI tests do not download Demucs, YouTube audio, or Basic Pitch.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mido
from arranger import Note, load_midi, make_midi, prepare, voice_coverage
from accompaniment import (
    Chord, ChordSpan, infer_chord, chord_spans_from_chroma,
    build_accompaniment, stable_chord_spans
)
from transcribe import remove_guitar_bleed, transcribe_audio


class ChordInferenceTests(unittest.TestCase):
    def test_major_minor_power_and_ambiguous_audio(self):
        cmaj = [0.03] * 12
        cmaj[0], cmaj[4], cmaj[7] = 1.0, .75, .83
        chord = infer_chord(cmaj, bass_pc=0)
        self.assertIsNotNone(chord)
        self.assertEqual((chord.root, chord.quality), (0, 'major'))
        self.assertEqual(chord.pitch_classes, (0, 4, 7))

        amin = [0.04] * 12
        amin[9], amin[0], amin[4] = 1.0, .68, .81
        chord = infer_chord(amin, bass_pc=9)
        self.assertEqual((chord.root, chord.quality), (9, 'minor'))

        power = [0.03] * 12
        power[0], power[7] = 1.0, .81
        self.assertEqual(infer_chord(power).quality, 'power')
        self.assertIsNone(infer_chord([.8] * 12))
        self.assertIsNone(infer_chord([0] * 12))

    def test_only_consecutive_sustained_frames_count(self):
        chord = Chord(0, 'power', .89)
        frames = [(0.0, chord), (.3, chord), (.6, None),
                  (.9, chord), (1.2, None)]
        spans = stable_chord_spans(frames, .3, 'recover')
        self.assertEqual(len(spans), 1)
        self.assertAlmostEqual(spans[0].start, 0)
        self.assertAlmostEqual(spans[0].end, .6)
        self.assertEqual(stable_chord_spans(frames, .3, 'off'), [])

    def test_bass_hints_chord_but_does_not_invent_spectral_evidence(self):
        notes = [Note(0, 2, 36, 80, 'bass')]
        chroma = [(i*.3, [0.0]*12) for i in range(8)]
        self.assertEqual(chord_spans_from_chroma(chroma, notes), [])


class AccompanimentTests(unittest.TestCase):
    def setUp(self):
        self.power = ChordSpan(0.0, 1.0, Chord(0, 'power', .91))
        self.source = [
            Note(0, 1, 36, 110, 'bass'),
            Note(0, 1, 64, 95, 'melody'),
        ]

    def test_recover_adds_only_spectrally_observed_chord_tones(self):
        observed = {(0.0, 7): .82, (0.0, 0): .90}
        got = build_accompaniment([self.power], self.source,
                                  mode='recover', observed=observed)
        self.assertEqual(len(got), 2)
        self.assertEqual({n.pitch % 12 for n in got}, {0, 7})
        self.assertEqual({n.part for n in got}, {'accomp'})
        self.assertTrue(all(39 <= n.velocity <= 70 for n in got))
        self.assertEqual(build_accompaniment([self.power], self.source,
                          mode='recover', observed={(0.0, 7): .18}), [])

    def test_accompaniment_can_enable_real_four_voice_opportunity(self):
        added = build_accompaniment(
            [self.power], self.source, mode='recover',
            observed={(0.0, 7): .84, (0.0, 0): .81}
        )
        full = prepare(self.source+added, 'balanced', 'adapt', preserve=True)
        cov = voice_coverage(full)
        self.assertGreater(cov['four_plus'], .85)
        self.assertGreater(cov['four_candidate'], .85)
        self.assertEqual(len({n.pitch for n in full}), 4)

    def test_no_fabricated_support_without_stable_chord(self):
        self.assertEqual(build_accompaniment([], self.source, 'harmonize'), [])
        weak = ChordSpan(0, 1, Chord(0, 'major', .20))
        self.assertEqual(build_accompaniment([weak], self.source,
                                             'harmonize'), [])

    def test_harmonize_mode_can_support_quieter_detected_third(self):
        chord = ChordSpan(0, 1, Chord(0, 'major', .87))
        observed = {(0.0, 7): .9, (0.0, 4): .30, (0.0, 0): .9}
        bass_only = [Note(0, 1, 36, 94, 'bass')]
        recover = build_accompaniment([chord], bass_only, 'recover', observed)
        harmonize = build_accompaniment([chord], bass_only, 'harmonize',
                                        observed)
        self.assertNotIn(4, {n.pitch % 12 for n in recover})
        self.assertIn(4, {n.pitch % 12 for n in harmonize})

    def test_dense_real_triad_needs_no_accompaniment(self):
        full = self.source + [Note(0, 1, 60, 85, 'guitar'),
                              Note(0, 1, 67, 82, 'harmony')]
        self.assertEqual(build_accompaniment([self.power], full,
                                              'recover', {
                                                  (0.0, 7): .9,
                                                  (0.0, 0): .9}), [])

    def test_inferred_channel_survives_roundtrip_and_programs(self):
        notes = self.source + [
            Note(0, 1, 67, 60, 'accomp', 48),
            Note(0, 1, 60, 82, 'guitar', 30),
        ]
        data = make_midi(notes, 0.0, 1.0)
        midi = mido.MidiFile(file=BytesIO(data))
        on = {m.channel for m in midi.tracks[0]
              if m.type == 'note_on'}
        self.assertEqual(on, {0, 1, 3, 4})
        with tempfile.TemporaryDirectory() as td:
            filepath = Path(td) / 'CHECK.MID'
            filepath.write_bytes(data)
            recovered = load_midi(filepath)
        self.assertEqual({n.part for n in recovered},
                         {'melody', 'bass', 'guitar', 'accomp'})


class GuitarSeparationTests(unittest.TestCase):
    def test_remove_duplicate_guitar_bleed_but_retain_other_notes(self):
        guitar = [Note(.1, .6, 64, 90, 'guitar')]
        other = [Note(.11, .58, 64, 68, 'harmony'),
                 Note(.2, .7, 67, 75, 'harmony')]
        out = remove_guitar_bleed(guitar, other)
        self.assertEqual([n.pitch for n in out], [67])

    def test_guitar_separation_uses_six_stem_model_and_role(self):
        seen = {}
        def fake_run(cmd, check):
            self.assertTrue(check)
            seen['cmd'] = cmd
            model = cmd[cmd.index('-n')+1]
            root = Path(cmd[cmd.index('-o')+1]) / model / 'test'
            root.mkdir(parents=True, exist_ok=True)
            for stem in ('bass', 'vocals', 'guitar', 'other', 'drums'):
                (root / (stem+'.wav')).write_bytes(b'dummy')
        def fake_predict(path, part):
            return [Note(0, 1, {
                'bass': 36, 'melody': 69, 'guitar': 64, 'harmony': 55
            }[part], 90, part)]
        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / 'test.mp3'
            wav.write_bytes(b'dummy')
            with patch.dict(sys.modules, {'demucs': types.ModuleType('demucs')}):
                with patch('transcribe.subprocess.run', side_effect=fake_run):
                    with patch('transcribe._predict', side_effect=fake_predict):
                        with patch('transcribe._drum_onsets', return_value=[]):
                            with patch('accompaniment.analyze_accompaniment_audio',
                                       return_value=[
                                           Note(0,1,60,53,'accomp',48)
                                       ]) as analysis:
                                notes = transcribe_audio(
                                    wav, guitar_separation=True,
                                    accompaniment='recover'
                                )
        self.assertEqual(seen['cmd'][seen['cmd'].index('-n')+1],
                         'htdemucs_6s')
        self.assertEqual({n.part for n in notes},
                         {'bass','melody','guitar','harmony','accomp'})
        self.assertEqual(analysis.call_args.kwargs['mode'], 'recover')
        self.assertEqual(analysis.call_args.args[0].name, 'guitar.wav')

    def test_no_stems_for_accompaniment_fails_instead_of_guessing(self):
        with self.assertRaisesRegex(ValueError, 'requires --stems'):
            transcribe_audio(Path('test.mp3'), accompaniment='recover')


if __name__ == '__main__':
    unittest.main()
