"""Aggressive yet musical guide-free stem cleanup, across multiple styles.

Only note evidence and musical-role timing; never hardcode a song/key.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from arranger import Note
from score_polish import (reject_register_spikes, stabilize_audio_candidates,
                          connect_legato_gaps)


def n(role, t, end, pitch, vel=90):
    return Note(t,end,pitch,vel,role,
                {'melody':80,'guitar':30,'bass':33,'drums':0,
                 'harmony':48,'accomp':48}[role])


class AggressivePhraseStabilizationTests(unittest.TestCase):
    def test_vocal_fragments_become_one_sustained_note(self):
        notes=[n('melody',0,.14,67,96),n('melody',.16,.32,67,78),
               n('melody',.34,.50,67,65)]
        out,rep=stabilize_audio_candidates(notes)
        self.assertEqual(len(out),1)
        self.assertEqual((out[0].start,out[0].end,out[0].pitch),
                         (0,.50,67))
        self.assertEqual(rep['merged_source_fragments'],2)

    def test_two_long_strong_repeated_vocal_syllables_survive(self):
        notes=[n('melody',0,.31,67,90),n('melody',.31,.62,67,92)]
        out,rep=stabilize_audio_candidates(notes)
        self.assertEqual(out,notes)
        self.assertEqual(rep['merged_source_fragments'],0)

    def test_strong_vocal_reattack_is_not_flattened(self):
        notes=[n('melody',0,.13,67,70),n('melody',.13,.28,67,104)]
        out,rep=stabilize_audio_candidates(notes)
        self.assertEqual(out,notes)
        self.assertEqual(rep['merged_source_fragments'],0)

    def test_guitar_duplicate_with_interleaved_overtone_merges(self):
        notes=[n('guitar',0,.12,52,95),n('guitar',.14,.18,76,36),
               n('guitar',.14,.28,52,72)]
        out,rep=stabilize_audio_candidates(notes)
        riffs=[v for v in out if v.pitch==52]
        self.assertEqual(len(riffs),1)
        self.assertAlmostEqual(riffs[0].end,.28)
        self.assertEqual(rep['merged_source_fragments'],1)

    def test_real_intervening_melodic_change_prevents_false_sustain(self):
        notes=[n('melody',0,.14,67,95),n('melody',.14,.22,69,92),
               n('melody',.22,.38,67,80)]
        out,rep=stabilize_audio_candidates(notes)
        self.assertEqual(out,notes)
        self.assertEqual(rep['merged_source_fragments'],0)

    def test_short_weak_pitch_jitter_inside_vocal_is_suppressed(self):
        notes=[n('melody',0,.15,67,99),n('melody',.15,.20,68,60),
               n('melody',.20,.38,67,90)]
        out,rep=stabilize_audio_candidates(notes)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0].pitch,67)
        self.assertAlmostEqual(out[0].end,.38)
        self.assertEqual(rep['removed_pitch_jitter'],1)

    def test_real_chromatic_ornament_is_protected(self):
        notes=[n('melody',0,.15,67,95),n('melody',.15,.22,68,94),
               n('melody',.22,.40,67,90)]
        out,rep=stabilize_audio_candidates(notes)
        self.assertEqual(out,notes)
        self.assertEqual(rep['removed_pitch_jitter'],0)

    def test_guitar_octave_beep_filtered_by_local_register(self):
        notes=[n('guitar',t,t+.16,52,88) for t in
               (0,.2,.4,.6,.8,1.0)]
        beep=n('guitar',.5,.58,76,111)
        out,rep=reject_register_spikes(notes+[beep])
        self.assertNotIn(beep,out)
        self.assertEqual(rep.removed_register_spikes,1)

    def test_repeated_high_guitar_solo_is_preserved(self):
        low=[n('guitar',t,t+.16,52,85) for t in (0,.2,.4)]
        high=[n('guitar',t,t+.15,79,99) for t in
              (.6,.8,1.,1.2,1.4)]
        back=[n('guitar',t,t+.16,52,85) for t in (1.6,1.8)]
        out,rep=reject_register_spikes(low+high+back)
        self.assertEqual(out,low+high+back)
        self.assertEqual(rep.removed_register_spikes,0)

    def test_drum_aligned_bass_repeated_attack_remains(self):
        notes=[n('bass',0,.17,40,90),n('bass',.17,.34,40,89),
               n('drums',.17,.23,36,97)]
        out,rep=stabilize_audio_candidates(notes)
        self.assertEqual(len([x for x in out if x.part=='bass']),2)
        self.assertEqual(rep['merged_source_fragments'],0)

    def test_classical_strings_repeated_detector_fragment_merges(self):
        notes=[n('harmony',0,.13,60,82),n('harmony',.14,.27,60,64)]
        out,rep=stabilize_audio_candidates(notes)
        self.assertEqual(len(out),1)
        self.assertAlmostEqual(out[0].end,.27)
        self.assertEqual(rep['merged_source_fragments'],1)

    def test_legato_links_short_vocal_gap_but_not_long_rest(self):
        notes=[n('melody',0,.20,67,90),n('melody',.25,.48,69,93),
               n('melody',.70,.90,72,95)]
        out,links=connect_legato_gaps(notes)
        self.assertAlmostEqual(out[0].end,.25)
        self.assertEqual(out[1:],notes[1:])
        self.assertEqual(links,1)

    def test_legato_leaves_bass_and_drum_timing_untouched(self):
        notes=[n('bass',0,.20,40,95),n('bass',.24,.4,43,95),
               n('drums',.22,.3,38,93)]
        out,links=connect_legato_gaps(notes)
        self.assertEqual(set(out),set(notes))
        self.assertEqual(links,0)

    def test_legato_preserves_all_original_onsets_pitches_velocities(self):
        notes=[n('melody',0,.20,67,93),n('melody',.26,.50,69,92),
               n('guitar',0,.22,52,88),n('guitar',.27,.52,55,84)]
        out,links=connect_legato_gaps(notes)
        self.assertEqual(links,2)
        self.assertEqual({(x.part,x.start,x.pitch,x.velocity) for x in out},
                         {(x.part,x.start,x.pitch,x.velocity) for x in notes})
        self.assertTrue(all(x.end>=note.end for x in out for note in notes
                            if x.start==note.start and x.part==note.part))

    def test_no_unwanted_invention_when_no_melody_or_drums(self):
        source=[n('harmony',0,.12,60,92),
                n('harmony',.14,.27,60,75)]
        out,_=stabilize_audio_candidates(source)
        joined,links=connect_legato_gaps(out)
        self.assertEqual(len(joined),1)
        self.assertEqual(links,0)
        self.assertFalse(any(x.part in ('drums','melody') for x in joined))


if __name__=="__main__":
    unittest.main()
