"""Guide-free Tandy note cleanup: real whole notes, not note stealing.

Exercises musical roles independent of song, genre, key, exact BPM or
instrument names. No AI model downloads, source recording, or DOS code.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import studio
from arranger import Note
from phrase_score import ScoreEvidence, reconstruct_score
from pitch_arranger import _coherent_guitar_line
from score_polish import (reject_register_spikes, merge_duplicate_attacks,
                          commit_role_notes)


def n(role, at, end, pitch, vel=86):
    return Note(at,end,pitch,vel,role,
                {'bass':33,'guitar':30,'melody':80,'harmony':48,
                 'drums':0,'accomp':48}[role])


class ReusableNotePolishTests(unittest.TestCase):
    def test_isolated_weak_extreme_bass_note_removed_by_context(self):
        source=[n('bass',t,t+.15,40,86) for t in (0,.2,.4,.6,.8,1.)]
        source += [n('bass',.5,.74,71,50)]
        filtered,report=reject_register_spikes(source)
        self.assertEqual(report.removed_register_spikes,1)
        self.assertNotIn(71,[x.pitch for x in filtered])
        self.assertEqual(len(filtered),6)

    def test_real_solo_register_change_is_preserved(self):
        base=[n('guitar',t,t+.16,52,86) for t in (0,.2,.4)]
        high=[n('guitar',t,t+.16,85,91) for t in (.6,.8,1.,1.2)]
        tail=[n('guitar',t,t+.16,52,86) for t in (1.4,1.6,1.8)]
        out,report=reject_register_spikes(base+high+tail)
        self.assertEqual(out,base+high+tail)
        self.assertEqual(report.removed_register_spikes,0)

    def test_strong_single_leap_and_bass_octave_survive(self):
        notes=[n('melody',i*.17,i*.17+.15,64,90)
               for i in range(6)]
        leap=n('melody',.42,.60,88,112)
        out,report=reject_register_spikes(notes+[leap])
        self.assertIn(leap,out)
        self.assertEqual(report.removed_register_spikes,0)

    def test_no_register_filter_for_drums_or_empty(self):
        hits=[n('drums',0,.1,36),n('drums',.2,.3,98)]
        out,report=reject_register_spikes(hits)
        self.assertEqual(out,hits)
        self.assertEqual(report.removed_register_spikes,0)
        self.assertEqual(reject_register_spikes([])[0],[])

    def test_same_pitch_weak_decoder_restart_is_held(self):
        notes=[n('guitar',0,.09,52,88),n('guitar',.09,.20,52,64)]
        out,merged=merge_duplicate_attacks(notes)
        self.assertEqual(len(out),1)
        self.assertEqual((out[0].start,out[0].end,out[0].velocity),
                         (0,.20,88))
        self.assertEqual(merged,1)

    def test_same_pitch_strong_restrike_is_separate(self):
        notes=[n('guitar',0,.12,52,80),
               n('guitar',.12,.31,52,110)]
        out,merged=merge_duplicate_attacks(notes)
        self.assertEqual(out,notes)
        self.assertEqual(merged,0)

    def test_drum_accent_preserves_rhythmic_bass_restart(self):
        notes=[n('bass',0,.16,40,85),
               n('bass',.16,.34,40,84),
               n('drums',.16,.22,36,95)]
        out,merged=merge_duplicate_attacks(notes)
        self.assertEqual(merged,0)
        self.assertEqual(len([x for x in out if x.part=='bass']),2)

    def test_sustained_vocal_restarts_merge_without_new_syllable(self):
        notes=[n('melody',0,.13,67,91),
               n('melody',.13,.26,67,76),
               n('melody',.26,.40,67,65)]
        out,merged=merge_duplicate_attacks(notes)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0].end,.40)
        self.assertEqual(merged,2)

    def test_note_commit_declines_entire_competing_note_no_shortening(self):
        original=n('guitar',0,.75,52,89)
        competing=n('guitar',.44,1.0,57,110)
        next_valid=n('guitar',.80,1.15,62,85)
        out,declined=commit_role_notes([original,competing,next_valid])
        self.assertEqual(out,[original,next_valid])
        self.assertEqual(declined,1)
        self.assertEqual(original.end,.75)

    def test_different_roles_can_sustain_together(self):
        notes=[n('bass',0,1,40),n('melody',0,1,72),
               n('guitar',0,1,64),n('drums',0,.07,36)]
        out,declined=commit_role_notes(notes)
        self.assertEqual(out,notes)
        self.assertEqual(declined,0)

    def test_guitar_helper_can_require_note_completion(self):
        first=n('guitar',0,.80,52,90)
        cut=n('guitar',.45,.95,57,109)
        # Historical gate still available for explicit comparisons.
        old=_coherent_guitar_line([first,cut])
        self.assertAlmostEqual(old[0].end,.45)
        committed=_coherent_guitar_line([first,cut],commit_full=True)
        self.assertEqual(committed,[first])

    def test_phrase_graph_in_completion_mode_never_truncates_selected(self):
        candidates=[n('guitar',0,.75,52,100),
                    n('guitar',.46,.91,57,107),
                    n('guitar',.93,1.30,60,90)]
        score=reconstruct_score(candidates,ScoreEvidence(),
                                connect=False,finish_notes=True)
        chosen=[n for p in score.phrases if p.part=='guitar'
                for n in p.notes]
        self.assertTrue(chosen)
        self.assertTrue(all(n in candidates for n in chosen))
        self.assertTrue(all(a.end <= b.start for a,b in
                            zip(chosen,chosen[1:])))

    def test_gui_cli_default_and_guided_path_are_still_separate(self):
        with patch('studio.convert',return_value=[Path('A.MID')]) as call:
            self.assertEqual(studio.main(['--cli','source.mid']),0)
        self.assertEqual(call.call_args.kwargs['arrangement'],'classic')
        with patch('studio.convert',return_value=[Path('A.MID')]) as call:
            self.assertEqual(studio.main(['--cli','source.mp3',
                                          '--arrangement','tuned']),0)
        self.assertEqual(call.call_args.kwargs['arrangement'],'tuned')

    def test_studio_audio_saves_raw_and_cleaned_candidates(self):
        raw=[n('bass',t,t+.17,40,88) for t in (0,.2,.4,.6,.8,1.)]
        raw.append(n('bass',.5,.72,71,50))
        raw.extend([n('guitar',0,.9,52),
                    n('melody',.1,.9,67),
                    n('drums',0,.07,36)])
        with tempfile.TemporaryDirectory() as td:
            wav=Path(td)/'synthetic.wav'
            wav.touch()
            with patch('transcribe.transcribe_audio',return_value=raw):
                files=studio.convert(wav,Path(td)/'out',
                                     arrangement='tuned',preview=False)
            self.assertTrue(files)
            target=files[0].parent
            source=json.loads((target/'INPUT.json').read_text())['notes']
            cleaned=json.loads((target/'CLEAN.json').read_text())['notes']
            self.assertEqual(len(source),len(raw))
            self.assertEqual(len(cleaned),len(raw)-1)
            report=(target/'POLISH.TXT').read_text()
            self.assertIn('register spikes removed: 1',report)
            pitch=(target/'PITCH.TXT').read_text()
            self.assertIn('note completion/duplicate merging',pitch)


if __name__=='__main__':
    unittest.main()
