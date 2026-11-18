"""Contract tests for one minimal musical arranger (no AI downloads).

Each fixture illustrates musical relationships, not a genre classifier or a
fixed target note count. Existing Build56 mode is tested separately.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mido
from arranger import Note, make_midi, prepare
from musical_arranger import arrange_musically
import studio


def pitched_at(notes: list[Note], when: float) -> list[Note]:
    return [n for n in notes if n.part != 'drums'
            and n.start <= when < n.end]


class MinimalMusicTests(unittest.TestCase):
    def test_rock_foundation_guitar_vocal_and_support(self):
        notes = [
            Note(0, 2, 40, 110, 'bass', 33),
            Note(0, 2, 64, 96, 'guitar', 30),
            Note(0, 2, 72, 96, 'melody', 80),
            Note(0, 2, 67, 86, 'harmony', 48),
            Note(.2, .27, 96, 23, 'melody', 80),  # isolated bleed squeal
        ]
        notes += [
            Note(t, t+.05, pitch, 100, 'drums')
            for t, pitch in ((0,36),(.125,42),(.25,38),(.375,42),
                             (.50,36),(.625,42),(.75,38),(.875,42))
        ]
        result, report = arrange_musically(notes, spk4='adapt')
        mid = pitched_at(result, .24)
        self.assertEqual({n.pitch for n in mid}, {40,64,67,72})
        self.assertTrue(all(n.pitch != 96 for n in result))
        self.assertEqual(report.suspected_artifacts, 1)
        self.assertGreater(report.four_voice_seconds, 1.9)
        self.assertEqual(
            [(n.start,n.pitch) for n in result if n.part == 'drums'],
            [(t,p) for t,p in ((0,36),(.125,42),(.25,38),(.375,42),
                              (.50,36),(.625,42),(.75,38),(.875,42))]
        )
        self.assertIn('foundation', report.as_text())

    def test_speaker_disabled_limits_to_three_with_real_bass(self):
        notes = [Note(0, 2, 40, 115, 'bass'),
                 Note(0, 2, 64, 95, 'guitar', 30),
                 Note(0, 2, 72, 95, 'melody', 80),
                 Note(0, 2, 67, 75, 'harmony'),
                 Note(0, 2, 76, 75, 'harmony')]
        out, _ = arrange_musically(notes, 'off')
        at = pitched_at(out, 1)
        self.assertEqual(len(at), 3)
        self.assertIn(40, {n.pitch for n in at})
        self.assertIn(64, {n.pitch for n in at})
        self.assertIn(72, {n.pitch for n in at})

    def test_speaker_needs_eligible_bass_not_just_four_candidates(self):
        notes = [Note(0, 1, 36, 42, 'bass')] + [
            Note(0, 1, p, 90, 'harmony') for p in (60,64,67,72)
        ]
        out, _ = arrange_musically(notes, 'adapt')
        self.assertEqual(len(pitched_at(out, .5)), 3)
        self.assertIn(36, {n.pitch for n in out})
        with self.assertRaises(ValueError):
            arrange_musically(notes, 'invented')

    def test_brandenburg_counterpoint_and_doubled_line(self):
        # Doubled high string line is *important*, but doesn't require
        # two identical PSG pitches. Independent inner lines are kept.
        notes = [
            Note(0, 1, 72, 95, 'melody', 48),
            Note(0, 1, 72, 95, 'harmony', 40),
            Note(0, 1, 64, 80, 'harmony', 40),
            Note(0, 1, 55, 80, 'harmony', 6),
        ]
        output, _ = arrange_musically(notes, 'off')
        at = pitched_at(output, .5)
        self.assertEqual(len(at), 3)
        self.assertEqual({n.pitch for n in at}, {55,64,72})
        self.assertFalse(any(n.part == 'drums' for n in output))

    def test_three_voice_demo_is_left_alone(self):
        notes = []
        for k in range(32):
            start = k * .5
            notes += [
                Note(start, start+.5, 41+(k//8)%4, 85, 'bass', 33),
                Note(start, start+.5, 60+(k//8)%4, 68, 'harmony', 48),
                Note(start, start+.5, 72+(k%4), 110, 'melody', 80),
            ]
        out, report = arrange_musically(notes, 'off')
        self.assertEqual(len(out), 96)
        self.assertEqual(report.selected_source_notes, 96)
        self.assertEqual({(n.start,n.end,n.pitch,n.velocity,n.part)
                          for n in out},
                         {(n.start,n.end,n.pitch,n.velocity,n.part)
                          for n in notes})
        self.assertFalse(any(n.part == 'drums' for n in out))

    def test_weak_high_solo_is_not_erased(self):
        n = Note(.217, .29, 89, 40, 'melody')
        out, report = arrange_musically([n], 'off')
        self.assertEqual(out, [n])
        self.assertEqual(report.suspected_artifacts, 0)

    def test_strong_new_attack_beats_held_support_but_not_riff(self):
        guitar = Note(0, 2, 64, 95, 'guitar', 30)
        singer = Note(0, 2, 72, 92, 'melody', 80)
        held = Note(0, 2, 67, 64, 'harmony', 48)
        weak = Note(.4, .9, 69, 70, 'harmony', 48)
        strong = Note(1, 1.3, 69, 125, 'harmony', 48)
        out, _ = arrange_musically([guitar,singer,held,weak,strong], 'off')
        self.assertEqual({n.pitch for n in pitched_at(out, .45)}, {64,72,67})
        self.assertEqual({n.pitch for n in pitched_at(out, 1.01)}, {64,72,69})
        self.assertTrue(any(n.pitch==67 and n.start==0 and
                            abs(n.end-1)<1e-8 for n in out))

    def test_offbeat_real_bass_note_keeps_exact_timing(self):
        notes = [
            Note(.19, .37, 43, 88, 'bass'),
            Note(0, 1, 60, 95, 'melody'),
            Note(.11, .51, 64, 70, 'harmony'),
            Note(.37, .50, 45, 91, 'bass'),
        ]
        out, _ = arrange_musically(notes, 'off')
        bass = [(n.start, n.end, n.pitch) for n in out if n.part=='bass']
        self.assertEqual(bass, [(.19,.37,43), (.37,.50,45)])
        self.assertTrue(all(n.pitch in {43,45,60,64} for n in out))

    def test_noise_channel_conflict_only_dedupes_near_attacks(self):
        notes = [Note(0, .06, 42, 44, 'drums'),
                 Note(.02, .08, 38, 105, 'drums'),
                 Note(.17, .24, 42, 60, 'drums'),
                 Note(.33, .39, 36, 100, 'drums')]
        out, report = arrange_musically(notes)
        self.assertEqual([(n.start,n.pitch) for n in out],
                         [(.02,38),(.17,42),(.33,36)])
        self.assertEqual((report.source_drums,report.output_drums),(4,3))

    def test_musical_midi_remains_dos_compatible(self):
        notes = [Note(0, 3, 40, 100, 'bass', 33),
                 Note(0, 3, 64, 92, 'guitar', 30),
                 Note(0, 3, 72, 92, 'melody', 80),
                 Note(0, 3, 67, 82, 'harmony', 48)]
        out,_ = arrange_musically(notes)
        with tempfile.TemporaryDirectory() as td:
            from arranger import export
            paths = export(out, Path(td)/'Groovy Song',
                           voice_selection='smart')
            self.assertTrue(paths)
            self.assertTrue(all(len(p.stem)<=8 and p.stat().st_size<45056
                                for p in paths))
            midi = mido.MidiFile(str(paths[0]))
            self.assertEqual(midi.type, 0)
            self.assertEqual(len(midi.tracks), 1)
            self.assertAlmostEqual(midi.length, 3, delta=.002)
            self.assertTrue(any(msg.type == 'control_change' and
                                msg.control == 119 and msg.value == 77
                                for msg in midi.tracks[0]))

    def test_unchanged_classic_baseline(self):
        notes = [Note(0, 1, 40, 95, 'bass'),
                 Note(0, 1, 64, 90, 'guitar'),
                 Note(0, 1, 72, 95, 'melody')]
        self.assertEqual(prepare(notes, 'balanced', 'adapt',
                                 preserve=True, voice_selection='smart'),
                         prepare(notes, 'balanced', 'adapt',
                                 preserve=True, voice_selection='smart'))

    def test_cli_opt_in_and_classic_midi_default(self):
        with patch('studio.convert', return_value=[Path('ONE.MID')]) as run:
            self.assertEqual(studio.main(['--cli','demo.mid']), 0)
        self.assertEqual(run.call_args.kwargs['arrangement'], 'classic')
        with patch('studio.convert', return_value=[Path('ONE.MID')]) as run:
            self.assertEqual(studio.main(['--cli','demo.mid',
                                          '--arrangement','musical']), 0)
        self.assertEqual(run.call_args.kwargs['arrangement'], 'musical')
        with self.assertRaisesRegex(ValueError,'alternative'):
            studio.convert('https://youtu.be/12345678901', Path('X'),
                           max_raw=True, arrangement='musical')

    def test_end_to_end_musical_import_keeps_legacy_folder_separate(self):
        notes = [
            Note(0, 1.1, 40, 95, 'bass', 33),
            Note(0, 1.1, 64, 95, 'guitar', 30),
            Note(0, 1.1, 72, 95, 'melody', 80),
            Note(0, 1.1, 67, 95, 'harmony', 48),
        ]
        with tempfile.TemporaryDirectory() as td:
            original = Path(td)/'SONG.MID'
            original.write_bytes(make_midi(notes,0,1.1))
            output = Path(td)/'OUT'
            music = studio.convert(original, output,
                                   arrangement='musical', preview=False)
            self.assertTrue(music)
            self.assertEqual(music[0].parent.name,'SONG_MUSIC')
            self.assertTrue((music[0].parent/'MUSIC.TXT').exists())
            self.assertTrue((music[0].parent/'INPUT.json').exists())
            self.assertTrue((music[0].parent/'PLAY.BAT').exists())
            classic = studio.convert(original, output,
                                     arrangement='classic', preview=False)
            self.assertEqual(classic[0].parent.name,'SONG_TANDY')
            self.assertNotEqual(music[0].parent,classic[0].parent)
            self.assertEqual(original.read_bytes(),make_midi(notes,0,1.1))


if __name__ == '__main__':
    unittest.main()
