"""CORE audio-transcription phrase smoothing (HOLD / CONNECT / REMOVE).

Testing deliberately separate from imported, hand-arranged MIDI; no Demucs
or Basic Pitch downloads. Preserve the Tandy PSG 3-pitch upper bound.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arranger import Note, make_midi, _psg_pitch
from core_arranger import arrange_core, smooth_core_fragments
import studio


def note(start, end, pitch=52, velocity=80, part='guitar'):
    program = {'guitar': 30, 'bass': 33, 'melody': 80,
               'harmony': 48, 'drums': 0}[part]
    return Note(start, end, pitch, velocity, part, program)


class CoreSmoothingTests(unittest.TestCase):
    def test_opening_e3_fragments_become_two_phrases_not_six(self):
        notes = [
            note(1.057, 1.126, 52, 75),
            note(1.126, 1.289, 52, 97),
            note(1.289, 1.474, 52, 77),
            note(1.474, 1.544, 52, 60),
            note(1.544, 1.625, 52, 62),
            note(1.625, 1.649, 52, 86),
            note(1.103, 1.178, 36, 80, 'drums')
        ]
        out, stats = smooth_core_fragments(notes)
        guitar = [n for n in out if n.part == 'guitar']
        self.assertEqual(len(guitar), 2)
        self.assertAlmostEqual(guitar[0].start, 1.057)
        self.assertAlmostEqual(guitar[0].end, 1.126)
        self.assertAlmostEqual(guitar[1].start, 1.126)
        self.assertAlmostEqual(guitar[1].end, 1.649)
        self.assertEqual(stats['held_joins'], 4)
        self.assertEqual(len([n for n in out if n.part=='drums']),1)

    def test_same_pitch_fragment_without_new_attack_is_held(self):
        notes = [note(0, .11, 52, 91),
                 note(.115, .21, 52, 70),
                 note(.21, .30, 52, 69)]
        out, stats = smooth_core_fragments(notes)
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0].end, .30)
        self.assertEqual(out[0].velocity, 91)
        self.assertEqual(stats['held_joins'], 2)

    def test_strong_restrike_keeps_distinct_attack(self):
        n = [note(0,.12,52,70),note(.12,.28,52,106)]
        out,stats = smooth_core_fragments(n)
        self.assertEqual(out,n)
        self.assertEqual(stats['held_joins'],0)

    def test_kick_reinforced_attack_keeps_restrike(self):
        n = [note(0,.12,52,70),note(.12,.28,52,88),
             note(.14,.22,36,95,'drums')]
        out,stats = smooth_core_fragments(n)
        self.assertEqual(len([x for x in out if x.part=='guitar']),2)
        self.assertEqual(stats['held_joins'],0)

    def test_different_pitch_micropause_becomes_legato(self):
        n = [note(0,.15,57,91),note(.178,.38,59,92)]
        out,stats = smooth_core_fragments(n)
        self.assertEqual(len(out),2)
        self.assertAlmostEqual(out[0].end,.178)
        self.assertAlmostEqual(out[1].start,.178)
        self.assertEqual(stats['connected_gaps'],1)
        self.assertEqual([x.pitch for x in out],[57,59])

    def test_weak_pitch_blip_between_two_identical_notes_is_removed(self):
        n = [note(0,.12,52,98),note(.12,.153,59,42),
             note(.153,.35,52,92)]
        out,stats = smooth_core_fragments(n)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0].pitch,52)
        self.assertAlmostEqual(out[0].end,.35)
        self.assertEqual(stats['removed_blips'],1)
        self.assertEqual(stats['held_joins'],1)

    def test_legitimate_short_chromatic_note_not_deleted(self):
        n = [note(0,.16,52,95),note(.16,.205,59,105),
             note(.205,.40,52,90)]
        out,stats = smooth_core_fragments(n)
        self.assertEqual(len(out),3)
        self.assertEqual(stats['removed_blips'],0)

    def test_intentional_half_second_demo_rearticulation_kept(self):
        n = [note(i*.5,(i+1)*.5,52,95) for i in range(4)]
        out,stats = smooth_core_fragments(n)
        self.assertEqual(out,n)
        self.assertEqual(stats['held_joins'],0)

    def test_bass_is_not_connected_across_a_real_rest(self):
        n=[note(0,.12,40,92,'bass'),note(.16,.30,45,92,'bass')]
        out,stats=smooth_core_fragments(n)
        self.assertEqual(out,n)
        self.assertEqual(stats['connected_gaps'],0)

    def test_no_fourth_pitch_created_by_legato_extension(self):
        n = [
            note(0,.150,57,90,'guitar'),
            note(.180,.400,59,90,'guitar'),
            note(0,.400,40,100,'bass'),
            note(0,.400,72,95,'melody'),
            note(.155,.178,67,95,'harmony')]
        out,stats=smooth_core_fragments(n)
        guitar=[x for x in out if x.part=='guitar']
        self.assertAlmostEqual(guitar[0].end,.150)
        self.assertEqual(stats['connected_gaps'],0)
        # At every note boundary, up to three *effective* PSG pitches.
        bounds=sorted({t for x in out for t in (x.start,x.end)})
        for a,b in zip(bounds,bounds[1:]):
            if b>a:
                pitched={_psg_pitch(x) for x in out
                         if x.part!='drums' and x.start <= (a+b)/2 < x.end}
                self.assertLessEqual(len(pitched),3)

    def test_select_actual_stronger_lower_fundamental_at_opening(self):
        n=[note(.302,.406,69,43),note(.313,.45,52,75)]
        out,_=arrange_core(n, smooth=False)
        chosen=[x for x in out if x.pitch==52]
        self.assertTrue(chosen)
        self.assertTrue(all(x.pitch!=69 for x in out))

    def test_core_reports_smoothing_stats(self):
        n=[note(0,.1,52,80),note(.1,.2,52,75)]
        out,report=arrange_core(n,smooth=True)
        self.assertEqual(len(out),1)
        self.assertEqual(report.held_joins,1)
        self.assertIn('Held/merged',report.as_text())
        plain,_=arrange_core(n,smooth=False)
        self.assertEqual(len(plain),2)

    def test_auto_only_smoothes_audio_but_manual_midi_opt_in_works(self):
        # Studio's CORE default should respect deliberately composed MIDI.
        n=[note(0,.1,52,80),note(.1,.2,52,75)]
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'GUITAR.MID'
            src.write_bytes(make_midi(n,0,.2))
            auto=studio.convert(src, Path(td)/'DEFAULT', arrangement='core',
                                preview=False)
            on=studio.convert(src, Path(td)/'SMOOTH', arrangement='core',
                              preview=False, core_smoothing='on')
            default_txt=(auto[0].parent/'CORE.TXT').read_text()
            on_txt=(on[0].parent/'CORE.TXT').read_text()
            self.assertIn('Held/merged same-pitch fragments: 0',default_txt)
            self.assertIn('Held/merged same-pitch fragments: 1',on_txt)

    def test_core_smoothing_cli_override_is_forwarded(self):
        with patch('studio.convert',return_value=[Path('TEST.MID')]) as run:
            self.assertEqual(studio.main(['--cli','input.mid',
                         '--arrangement','core',
                         '--core-smoothing','on']),0)
        self.assertEqual(run.call_args.kwargs['core_smoothing'],'on')
        with self.assertRaisesRegex(ValueError,'CORE smoothing'):
            studio.convert('example.mid',Path('X'),
                           arrangement='core',core_smoothing='unknown')

    def test_classic_build56_still_default_and_does_not_require_smoothing(self):
        with patch('studio.convert',return_value=[Path('TEST.MID')]) as run:
            self.assertEqual(studio.main(['--cli','input.mid']),0)
        self.assertEqual(run.call_args.kwargs['arrangement'],'classic')
        self.assertNotIn('core_smoothing',run.call_args.kwargs)


if __name__ == '__main__':
    unittest.main()
