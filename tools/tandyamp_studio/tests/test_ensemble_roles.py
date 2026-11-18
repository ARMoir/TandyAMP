"""Genre-neutral role ensemble: no song-specific note list or genre classifier."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arranger import Note, _psg_pitch
from ensemble_roles import arrange_ensemble
from phrase_score import Phrase, Score
from pitch_arranger import arrange_tuned


def n(part, start, end, pitch, velocity=90):
    program={'bass':33,'guitar':30,'melody':80,'harmony':48,
             'accomp':48,'drums':0}[part]
    return Note(start,end,pitch,velocity,part,program)


def as_keys(notes):
    return {(x.part,x.start,x.end,x.pitch,x.velocity) for x in notes}


class EnsembleRoleTests(unittest.TestCase):
    def test_rock_four_roles_lead_riff_bass_drums_undisturbed(self):
        base=[n('bass',0,1.5,40),n('guitar',0,1.5,64),
              n('melody',.4,1.5,72),
              n('drums',0,.08,36),n('drums',.5,.58,38)]
        clutter=[n('harmony',.5,1.2,67,110),
                 n('harmony',.57,.66,79,119)]
        mixed,report=arrange_ensemble(base+clutter,spk4='off')
        self.assertEqual(as_keys(mixed),as_keys(base))
        self.assertEqual(report.protected_notes,5)
        self.assertEqual(report.rejected_competition,1)
        self.assertEqual(report.rejected_short_or_weak,1)

    def test_all_lead_and_bass_phrase_attacks_and_rests_are_preserved(self):
        bass=[n('bass',0,.40,40),n('bass',.51,.92,43)]
        riff=[n('guitar',0,.30,60),n('guitar',.44,.82,62),
              n('guitar',1.1,1.4,64)]
        vocals=[n('melody',.5,1.2,72)]
        notes=bass+riff+vocals+[n('harmony',.1,1.3,67)]
        out,_=arrange_ensemble(notes,spk4='off')
        self.assertTrue(as_keys(bass+riff+vocals).issubset(as_keys(out)))
        self.assertFalse(any(x.part=='harmony' for x in out))
        self.assertEqual(len([x for x in out if x.part=='guitar']),3)

    def test_classical_two_melodic_lines_and_inner_voice_without_drums(self):
        lead=n('melody',0,2,76)
        counter=n('guitar',0,2,67)
        inner=n('harmony',0,2,60,86)
        extra=n('harmony',.1,1.9,64,99)
        out,report=arrange_ensemble([lead,counter,inner,extra],spk4='off')
        self.assertEqual(as_keys(out),as_keys([lead,counter,inner]))
        self.assertEqual(report.accepted_support,1)
        self.assertFalse(any(x.part=='drums' for x in out))

    def test_synth_with_no_vocals_or_guitar_needs_not_invent_any(self):
        synth_bass=n('bass',0,2,36)
        synth_top=n('harmony',0,2,72)
        arp=n('accomp',.5,1.5,65,95)
        song=[synth_bass,synth_top,arp]
        out,_=arrange_ensemble(song,spk4='off')
        self.assertEqual(as_keys(out),as_keys(song))
        self.assertFalse(any(x.part=='melody' or x.part=='drums' for x in out))

    def test_original_sparse_three_voice_demo_is_unchanged(self):
        original=[n('bass',t,t+.50,40+int(t)%4,85)
                  for t in (0.,.5,1.,1.5)]
        original += [n('melody',t,t+.50,72+int(t*2),105)
                     for t in (0.,.5,1.,1.5)]
        original += [n('harmony',t,t+.50,60,70)
                     for t in (0.,.5,1.,1.5)]
        out,rep=arrange_ensemble(original,spk4='off')
        self.assertEqual(as_keys(out),as_keys(original))
        self.assertEqual(rep.accepted_support,4)

    def test_spk4_adapt_can_accept_fourth_real_voice(self):
        song=[n('bass',0,1,40,92),n('guitar',0,1,64,92),
              n('melody',0,1,72,92),n('harmony',0,1,67,91)]
        strict,_=arrange_ensemble(song,spk4='off')
        adaptive,_=arrange_ensemble(song,spk4='adapt')
        self.assertEqual(len(strict),3)
        self.assertEqual(len(adaptive),4)

    def test_speaker_does_not_force_low_part_to_play_when_unavailable(self):
        song=[n('bass',0,1,59,95),n('guitar',0,1,64),
              n('melody',0,1,72),n('harmony',0,1,67,100)]
        output,_=arrange_ensemble(song,spk4='adapt')
        self.assertEqual(len(output),3)
        self.assertIn(song[0],output)

    def test_whole_support_note_is_not_chopped_to_fit_a_gap(self):
        lead=n('melody',0,.50,72)
        guitar=n('guitar',0,.50,64)
        bass=n('bass',0,.50,40)
        cross=n('harmony',.25,.75,67,100)
        out,_=arrange_ensemble([lead,guitar,bass,cross],spk4='off')
        self.assertEqual(as_keys(out),as_keys([lead,guitar,bass]))

    def test_same_pitch_support_does_not_double_lead(self):
        lead=n('melody',0,1,72)
        double=n('harmony',0,1,72,111)
        out,_=arrange_ensemble([lead,double],spk4='off')
        self.assertEqual(out,[lead])

    def test_first_sustained_support_wins_against_late_note_steal(self):
        lead=n('melody',0,2,72)
        guitar=n('guitar',0,2,64)
        first=n('harmony',0,2,60,85)
        late=n('harmony',.5,1,67,120)
        out,_=arrange_ensemble([lead,guitar,first,late],spk4='off')
        self.assertEqual(as_keys(out),as_keys([lead,guitar,first]))

    def test_guitar_replaced_by_real_other_instrument_when_not_present(self):
        melody=n('melody',0,2,79)
        cello=n('bass',0,2,43)
        piano=n('harmony',0,2,60,86)
        out,_=arrange_ensemble([melody,cello,piano],spk4='off')
        self.assertEqual(as_keys(out),as_keys([melody,cello,piano]))

    def test_invalid_spk4_and_empty_input(self):
        self.assertEqual(arrange_ensemble([])[0],[])
        with self.assertRaises(ValueError):
            arrange_ensemble([],spk4='seven-channels')

    def test_tuned_automatic_reports_stable_support_without_changing_lead(self):
        bass=n('bass',0,1,40)
        lead=n('melody',0,1,72)
        guitar=n('guitar',0,1,64)
        pad=n('harmony',0,1,67,100)
        score=Score((),(),tuple(
            Phrase(x.part,x.part,(x,)) for x in (bass,lead,guitar,pad)))
        arranged,report=arrange_tuned(
            score,[bass,lead,guitar,pad],spk4='off')
        self.assertEqual({x.part for x in arranged},
                         {'bass','melody','guitar'})
        self.assertGreater(report.support_admission['offered'],0)
        self.assertGreater(report.support_admission['declined_competition'],0)
        self.assertIn('Pass 3 whole-note support',report.as_text())


if __name__=='__main__':
    unittest.main()
