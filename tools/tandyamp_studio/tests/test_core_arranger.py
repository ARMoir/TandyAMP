"""KISS CORE mode tests: groove first, guitar bridges to vocal.

No model downloads, invented music, genre classifier, or DOS executable edits.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mido

import studio
from arranger import Note, _psg_pitch, make_midi
from core_arranger import arrange_core


def sounding(notes: list[Note], when: float) -> list[Note]:
    return [n for n in notes if n.part != 'drums'
            and n.start <= when < n.end]


class CoreMusicTests(unittest.TestCase):
    def test_bass_drums_guitar_vocal_only_no_unnecessary_harmony(self):
        notes = [Note(0, 1, 40, 105, 'bass'),
                 Note(0, 1, 64, 99, 'guitar', 30),
                 Note(0, 1, 72, 95, 'melody', 80)]
        notes += [Note(0, 1, p, 125, 'harmony')
                  for p in (48, 55, 60, 67, 76, 79)]
        notes += [Note(t, t+.05, p, 100, 'drums')
                  for t,p in ((0,36),(.14,42),(.29,38),(.44,42))]
        output, report = arrange_core(notes)
        self.assertEqual({n.pitch for n in sounding(output,.5)},
                         {40,64,72})
        self.assertFalse(any(n.part == 'harmony' for n in output))
        self.assertEqual([n.pitch for n in output if n.part == 'drums'],
                         [36,42,38,42])
        self.assertEqual(report.retained_source_notes,3)
        self.assertEqual(report.chosen_drums,4)
        self.assertIn('CORE',report.as_text())

    def test_guitar_chord_does_not_fill_three_channels(self):
        notes = [Note(0, 1, 38, 108, 'bass'),
                 Note(0, 1, 72, 90, 'melody')]
        notes.extend(Note(0, 1, p, 110, 'guitar', 30)
                     for p in (60, 64, 67, 76))
        out, _ = arrange_core(notes)
        at = sounding(out,.5)
        self.assertEqual(len(at),3)
        self.assertEqual(sum(n.part=='guitar' for n in at),1)
        self.assertEqual({n.part for n in at},
                         {'bass','guitar','melody'})

    def test_no_new_notes_added_and_source_timing_is_preserved(self):
        notes = [Note(.17, .42, 41, 92, 'bass'),
                 Note(.06, .60, 64, 99, 'guitar',30),
                 Note(.12, .52, 72, 100, 'melody',80)]
        out,_ = arrange_core(notes)
        self.assertEqual({(n.start,n.end,n.pitch,n.velocity,n.part)
                          for n in out},
                         {(n.start,n.end,n.pitch,n.velocity,n.part)
                          for n in notes})

    def test_weak_high_vocal_artifact_ignored_but_solo_survives(self):
        notes = [Note(0, 1, 40, 100, 'bass'),
                 Note(0, 1, 64, 100, 'guitar',30),
                 Note(.2, .25, 99, 30, 'melody')]
        out,_ = arrange_core(notes)
        self.assertNotIn(99,{n.pitch for n in out})
        solo = [Note(.2, .25, 99, 30, 'melody')]
        out,_ = arrange_core(solo)
        self.assertEqual(out,solo)

    def test_real_repeated_riff_attack_can_retrigger(self):
        notes = [Note(0, .45, 64, 100, 'guitar',30),
                 Note(.30, .78, 64, 105, 'guitar',30),
                 Note(0, .8, 40, 100, 'bass')]
        out,_ = arrange_core(notes)
        riffs = [n for n in out if n.part == 'guitar']
        self.assertEqual(len(riffs),2)
        self.assertAlmostEqual(riffs[0].end,.30)
        self.assertAlmostEqual(riffs[1].start,.30)

    def test_vocal_entrance_over_guitar_riff(self):
        notes = [Note(0,2,40,100,'bass'),
                 Note(0,2,64,100,'guitar',30),
                 Note(1,2,72,90,'melody'),
                 Note(0,2,55,70,'harmony')]
        out,_ = arrange_core(notes)
        self.assertEqual({n.pitch for n in sounding(out,.5)},{40,64})
        self.assertEqual({n.pitch for n in sounding(out,1.5)},
                         {40,64,72})

    def test_only_credible_support_while_guitar_is_playing(self):
        notes = [Note(0,2,40,100,'bass'),
                 Note(0,2,64,100,'guitar',30),
                 Note(0,2,67,75,'harmony'),
                 Note(0,2,71,108,'harmony')]
        out,_ = arrange_core(notes)
        self.assertEqual({n.pitch for n in sounding(out,1)},
                         {40,64,71})
        self.assertNotIn(67,{n.pitch for n in out})

    def test_drums_keep_offbeat_pocket_but_drop_repeated_hat_noise(self):
        notes = [Note(0,.05,36,110,'drums'),
                 Note(.12,.16,42,80,'drums'),
                 Note(.16,.2,42,72,'drums'),
                 Note(.26,.31,38,110,'drums'),
                 Note(.4,.45,42,80,'drums'),
                 Note(.64,.69,36,110,'drums')]
        out,report = arrange_core(notes)
        self.assertEqual([(n.start,n.pitch) for n in out],
                         [(0,36),(.12,42),(.26,38),(.4,42),(.64,36)])
        self.assertEqual((report.source_drums,report.chosen_drums),(6,5))

    def test_classical_doubling_does_not_waste_a_voice(self):
        notes = [Note(0,1,72,96,'melody',48),
                 Note(0,1,72,96,'harmony',40),
                 Note(0,1,64,90,'harmony',40),
                 Note(0,1,55,85,'harmony',6)]
        out,_ = arrange_core(notes,'off')
        self.assertEqual({n.pitch for n in sounding(out,.5)},
                         {55,64,72})
        self.assertEqual(len(sounding(out,.5)),3)

    def test_demo_three_voice_harmony_not_deleted_for_quiet_velocity(self):
        notes = []
        for i in range(32):
            at = i * .5
            notes += [Note(at,at+.5,41+i//8,85,'bass'),
                      Note(at,at+.5,60+i//8,68,'harmony'),
                      Note(at,at+.5,72+i%4,110,'melody')]
        out,report=arrange_core(notes,'off')
        self.assertEqual(len(out),96)
        self.assertEqual(report.retained_source_notes,96)
        self.assertEqual({(n.start,n.end,n.pitch,n.part) for n in out},
                         {(n.start,n.end,n.pitch,n.part) for n in notes})

    def test_three_distinct_pitches_max_regardless_of_spk4(self):
        notes = [Note(0,1,36,125,'bass')]
        notes += [Note(0,1,p,125,'guitar',30)
                  for p in (60,64,67,71,74)]
        notes += [Note(0,1,p,125,'melody')
                  for p in (72,76,79)]
        for spk4 in ('off','bass','adapt'):
            out,_ = arrange_core(notes,spk4)
            self.assertLessEqual(
                len({_psg_pitch(n) for n in sounding(out,.5)}),3)
            self.assertTrue(any(n.part=='bass' for n in out))
        with self.assertRaises(ValueError):
            arrange_core(notes,'unknown')

    def test_empty_and_drums_only_valid(self):
        out,report=arrange_core([])
        self.assertEqual(out,[])
        self.assertEqual(report.source_pitched,0)
        drum=Note(0,.1,38,100,'drums')
        out,_=arrange_core([drum])
        self.assertEqual(out,[drum])

    def test_dos_export_and_cli_flag(self):
        with patch('studio.convert',return_value=[Path('TEST.MID')]) as f:
            self.assertEqual(studio.main(['--cli','song.mid',
                                          '--arrangement','core']),0)
        self.assertEqual(f.call_args.kwargs['arrangement'],'core')
        with patch('studio.convert',return_value=[Path('TEST.MID')]) as f:
            self.assertEqual(studio.main(['--cli','song.mid']),0)
        self.assertEqual(f.call_args.kwargs['arrangement'],'classic')
        with self.assertRaisesRegex(ValueError,'alternative'):
            studio.convert('https://youtu.be/Uq42HUUJFzU',Path('X'),
                           arrangement='core',max_raw=True)

    def test_end_to_end_core_midi_not_overwrite_music_or_classic(self):
        src=[Note(0,1.1,40,100,'bass',33),
             Note(0,1.1,64,100,'guitar',30),
             Note(0,1.1,72,100,'melody',80),
             Note(0,1.1,67,100,'harmony',48),
             Note(0,.05,36,100,'drums')]
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'MYSONG.MID'
            before=make_midi(src,0,1.1)
            source.write_bytes(before)
            target=Path(td)/'OUT'
            paths=studio.convert(source,target,arrangement='core',
                                 preview=False)
            self.assertTrue(paths)
            self.assertEqual(paths[0].parent.name,'MYSONG_CORE')
            self.assertTrue((paths[0].parent/'CORE.TXT').exists())
            self.assertTrue((paths[0].parent/'INPUT.json').exists())
            self.assertTrue((paths[0].parent/'PLAY.BAT').exists())
            midi=mido.MidiFile(str(paths[0]))
            self.assertEqual(midi.type,0)
            self.assertLess(paths[0].stat().st_size,45056)
            self.assertLessEqual(len(paths[0].stem),8)
            midnotes=[m.note for m in midi.tracks[0]
                      if m.type=='note_on' and m.channel!=9]
            self.assertNotIn(67,midnotes)
            self.assertEqual(source.read_bytes(),before)
            classic=studio.convert(source,target,arrangement='classic',
                                   preview=False)
            self.assertEqual(classic[0].parent.name,'MYSONG_TANDY')
            assert paths[0].parent != classic[0].parent


if __name__ == '__main__':
    unittest.main()
