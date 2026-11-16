"""Offline music cleanup regressions; no copyrighted audio or ML downloads."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import tempfile
import unittest
import wave
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mido
from arranger import Note, normalize, prepare, select_voices, make_midi
from postprocess import (classify_drum_bands, classify_drum_transient,
                         clean_stem_notes, drum_velocity, join_bass_fragments,
                         normalize_drum_fluxes, refine_drum_hits,
                         recover_high_hats, infer_snare_backbeat,
                         prune_weak_rock_kicks)
from preview import assign_preview_voices, preview_wav


class SpectralDrumTests(unittest.TestCase):
    def test_clear_spectral_classes_and_ambiguity(self):
        self.assertEqual(classify_drum_bands(12, 3, 1), 36)
        self.assertEqual(classify_drum_bands(1, 12, 4), 38)
        self.assertEqual(classify_drum_bands(.5, 2, 11), 42)
        self.assertIsNone(classify_drum_bands(5, 5, 5))
        self.assertIsNone(classify_drum_bands(0, 0, 0))

    def test_recording_relative_spectral_novelty_can_find_all_three_drums(self):
        # Synthesized BOOMY drum stem with strong bass in every transient.
        # Raw absolute low energy dominates, so calibration must preserve
        # unique broadband snare/hat attacks instead of all-kick output.
        bands = [
            (120, 5, 2), (110, 6, 3), (115, 5, 2),
            (88, 55, 30), (70, 10, 70),
        ]
        relative = normalize_drum_fluxes(bands)
        self.assertEqual(classify_drum_transient(*relative[0]), 36)
        self.assertEqual(classify_drum_transient(*relative[3]), 38)
        self.assertEqual(classify_drum_transient(*relative[4]), 42)

    def test_empty_and_ambiguous_drums_do_not_invent_notes(self):
        self.assertEqual(normalize_drum_fluxes([]), [])
        self.assertIsNone(classify_drum_transient(0, 0, 0))
        self.assertIsNone(classify_drum_transient(1, 1, 1))
        self.assertIsNone(classify_drum_transient(1, 1, 1, True))

    def test_percussion_velocity_uses_track_range_without_saturation(self):
        values = [drum_velocity(i, 1, 10) for i in (1, 4, 7, 10)]
        self.assertEqual(values[0], 56)
        self.assertEqual(values[-1], 110)
        self.assertEqual(len(set(values)), 4)

    def test_one_class_percussion_gets_sparser_not_fabricated_snares(self):
        hits = [Note(i*.15, i*.15+.07, 36, 90, 'drums')
                for i in range(60)]
        reduced = refine_drum_hits(hits)
        self.assertLess(len(reduced), 35)
        self.assertEqual({n.pitch for n in reduced}, {36})

    def test_louder_snare_can_displace_quieter_simultaneous_kick(self):
        hits = [Note(0, .07, 36, 62, 'drums'),
                Note(.025, .085, 38, 100, 'drums')]
        kept = prepare(hits, 'balanced')
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].pitch, 38)

    def test_independent_high_band_onses_recover_hats_without_a_beat_grid(self):
        existing = [Note(0.0, .07, 36, 90, 'drums')]
        attacks = [(.24, 4.0, .15, .25, 2.8),
                   (.49, 4.0, .17, .23, 2.7)]
        hats = recover_high_hats(attacks, existing, style='rock')
        self.assertEqual([n.pitch for n in hats], [42, 42])
        self.assertEqual([round(n.start, 2) for n in hats], [.24, .49])
        self.assertTrue(all(n.velocity < 90 for n in hats))

    def test_high_band_needs_actual_spectral_attack_evidence(self):
        # A kick with a bit of high-frequency energy is not a hat.
        lows = [(.25, 4.0, 4.0, 1.0, .25),
                (.50, 4.0, 5.0, 1.0, .30)]
        self.assertEqual(recover_high_hats(lows, [], style='rock'), [])
        self.assertEqual(recover_high_hats([], [], style='rock'), [])

    def test_hats_cannot_steal_single_noise_channel_from_snare(self):
        existing = [Note(.50, .57, 38, 95, 'drums')]
        attacks = [(.52, 3.0, .1, .2, 3.0)]
        self.assertEqual(recover_high_hats(attacks, existing, 'rock'), [])

    def test_backbeat_inferred_from_observed_snare_not_an_assumption(self):
        beats = [i*.36 for i in range(32)]
        snares = [Note(i*.36, i*.36+.06, 38, 95, 'drums')
                  for i in range(1, 24, 2)]
        self.assertEqual(infer_snare_backbeat(snares, beats), 1)
        self.assertIsNone(infer_snare_backbeat(snares[:2], beats))
        ambiguous = snares[:6] + [Note(i*.36, i*.36+.06, 38, 95, 'drums')
                                   for i in range(2, 14, 2)]
        self.assertIsNone(infer_snare_backbeat(ambiguous, beats))

    def test_rock_pulse_keeps_strong_kicks_and_reduces_weak_backbeats(self):
        beats = [i*.36 for i in range(48)]
        kicks = [Note(i*.36, i*.36+.07, 36,
                      98 if i % 2 == 0 else 55, 'drums')
                 for i in range(32)]
        snares = [Note(i*.36, i*.36+.065, 38, 85, 'drums')
                  for i in range(1, 32, 2)]
        result = prune_weak_rock_kicks(kicks+snares, beats)
        kick_result = [n for n in result if n.pitch == 36]
        self.assertLess(len(kick_result), len(kicks))
        self.assertTrue(all(n.velocity == 98 for n in kick_result
                            if n.start >= .5 and n.start < 10.5))
        self.assertEqual(len([n for n in result if n.pitch == 38]),
                         len(snares))

    def test_rock_pulse_does_not_remove_uniform_strength_kicks(self):
        kicks = [Note(i*.36, i*.36+.07, 36, 72, 'drums')
                 for i in range(32)]
        self.assertEqual(prune_weak_rock_kicks(kicks, []), kicks)

    def test_hats_can_replace_only_weak_kicks_with_clear_high_attack(self):
        kick = Note(.50, .57, 36, 56, 'drums')
        events = [(.52, 8.0, .1, .1, 8.0)]
        hats = recover_high_hats(events, [kick], style='rock')
        self.assertEqual(len(hats), 1)
        reduced = refine_drum_hits([kick] + hats, style='rock')
        self.assertEqual([n.pitch for n in reduced], [42])
        strong = Note(.50, .57, 36, 90, 'drums')
        self.assertEqual(recover_high_hats(events, [strong], 'rock'), [])

    def test_hats_do_not_replace_snare_backbeat(self):
        snare = Note(.5, .565, 38, 65, 'drums')
        events = [(.52, 9.0, .05, .1, 9.0)]
        self.assertEqual(recover_high_hats(events, [snare], 'rock'), [])

    def test_rock_mode_more_sparing_kicks_and_stronger_snares(self):
        dense = [Note(i*.21, i*.21+.07, 36, 80, 'drums')
                 for i in range(16)]
        regular = refine_drum_hits(dense, style='auto')
        rock = refine_drum_hits(dense, style='rock')
        self.assertGreater(len(regular), len(rock))
        kick = Note(0, .07, 36, 75, 'drums')
        snare = Note(.03, .10, 38, 88, 'drums')
        self.assertEqual(refine_drum_hits([kick, snare], style='rock')[0].pitch, 38)

    def test_snare_chatter_is_rejected(self):
        events = [
            Note(0.00, .08, 38, 90, 'drums'),
            Note(0.09, .17, 38, 91, 'drums'),
            Note(0.18, .26, 38, 80, 'drums'),
            Note(0.35, .43, 38, 92, 'drums'),
            Note(0.75, .83, 42, 85, 'drums')
        ]
        out = refine_drum_hits(events)
        self.assertEqual([n.pitch for n in out], [38, 38, 42])
        self.assertTrue(all(n.end - n.start <= .0751 for n in out))

    def test_both_balanced_and_quality_keep_short_hats(self):
        hit = Note(0.0, .048, 42, 90, 'drums')
        self.assertEqual(len(normalize([hit], 'balanced')), 1)
        self.assertEqual(len(normalize([hit], 'quality')), 1)


class StemCleanupTests(unittest.TestCase):
    def test_retains_riff_repeated_notes(self):
        riff = [
            Note(0, .19, 40, 70, 'bass'),
            Note(.24, .44, 40, 75, 'bass'),
            Note(.48, .70, 38, 72, 'bass'),
            Note(.72, .75, 52, 24, 'bass'),
        ]
        out = clean_stem_notes(riff, 'bass')
        self.assertEqual([n.pitch for n in out], [40, 40, 38])

    def test_bass_velocity_is_not_forced_to_107(self):
        notes = [Note(0, .2, 40, 68, 'bass'),
                 Note(.3, .5, 40, 97, 'bass'),
                 Note(.6, .8, 38, 110, 'bass')]
        out = normalize(notes, 'balanced')
        self.assertEqual([n.velocity for n in out], [68, 97, 110])

    def test_bass_fragment_joins_only_near_identical_weak_restarts(self):
        notes = [Note(0, .2, 40, 80, 'bass'),
                 Note(.222, .4, 40, 83, 'bass'),
                 Note(.46, .63, 40, 95, 'bass'),
                 Note(.67, .83, 38, 85, 'bass')]
        result = join_bass_fragments(notes)
        self.assertEqual(len(result), 3)
        self.assertAlmostEqual(result[0].end, .4)
        self.assertEqual([n.pitch for n in result], [40, 40, 38])

    def test_quiet_bass_velocities_no_longer_have_64_floor(self):
        notes = [Note(0, .2, 40, 50, 'bass'),
                 Note(.3, .5, 40, 55, 'bass'),
                 Note(.6, .8, 38, 62, 'bass')]
        normalized = normalize(notes, 'balanced')
        self.assertEqual([n.velocity for n in normalized], [50, 55, 62])
        self.assertEqual([n.pitch for n in normalized], [40, 40, 38])

    def test_removes_short_harmonic_artifact_without_losing_lead(self):
        melody = [
            Note(0, .3, 64, 80, 'melody'),
            Note(.35, .42, 83, 32, 'melody'),
            Note(.48, .82, 67, 72, 'melody'),
        ]
        out = clean_stem_notes(melody, 'melody')
        self.assertEqual([n.pitch for n in out], [64, 67])

    def test_harmony_polyphony_is_capped_but_bass_separate(self):
        harmony = [
            Note(0, .6, 60, 100, 'harmony'),
            Note(0, .6, 64, 90, 'harmony'),
            Note(0, .6, 67, 60, 'harmony'),
        ]
        out = clean_stem_notes(harmony, 'harmony')
        self.assertEqual(len(out), 2)
        self.assertEqual({n.pitch for n in out}, {60, 64})

    def test_no_cleanup_of_original_midi_during_arranging(self):
        # The stem cleanup is deliberately called only from transcribe_audio.
        notes = [Note(0, .20, 64, 33, 'melody')]
        self.assertEqual(len(prepare(notes)), 1)


class SpeakerPreviewTests(unittest.TestCase):
    def setUp(self):
        self.three = [
            Note(0, .5, 36, 100, 'bass'),
            Note(0, .5, 60, 105, 'melody'),
            Note(0, .5, 64, 100, 'harmony'),
        ]

    def test_adapt_uses_bass_plus_two_tones(self):
        tones, speaker, drum = assign_preview_voices(self.three, 'adapt')
        self.assertEqual({n.pitch for n in tones}, {60, 64})
        self.assertIsNotNone(speaker)
        self.assertEqual(speaker.pitch, 36)
        self.assertIsNone(drum)
        tones2, speaker2, _ = assign_preview_voices(self.three, 'bass')
        self.assertIsNone(speaker2)
        self.assertEqual(len(tones2), 3)
        self.assertEqual({n.pitch for n in select_voices(self.three, 'adapt')}, {36, 60, 64})

    def test_bass_and_fourth_tone_supported(self):
        four = self.three + [Note(0, .5, 67, 90, 'harmony')]
        tones, speaker, _ = assign_preview_voices(four, 'bass')
        self.assertIsNotNone(speaker)
        self.assertEqual(len(tones), 3)
        self.assertEqual({n.pitch for n in select_voices(four, 'bass')}, {36, 60, 64, 67})

    def test_valid_wav_and_different_speaker_modes(self):
        notes = self.three + [Note(.05, .12, 38, 90, 'drums')]
        with tempfile.TemporaryDirectory() as td:
            a = preview_wav(notes, Path(td) / 'a.wav', seconds=.45, spk4='off')
            b = preview_wav(notes, Path(td) / 'b.wav', seconds=.45, spk4='adapt')
            with wave.open(str(a)) as w:
                self.assertEqual(w.getnchannels(), 1)
                self.assertEqual(w.getsampwidth(), 2)
                self.assertEqual(w.getframerate(), 11025)
                self.assertEqual(w.getnframes(), int(.45*11025))
            self.assertNotEqual(a.read_bytes(), b.read_bytes())

    def test_export_stays_type0_and_small(self):
        notes = prepare(self.three, 'balanced', spk4='adapt')
        midi_data = make_midi(notes, 0, .5)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'A.MID'
            p.write_bytes(midi_data)
            parsed = mido.MidiFile(str(p))
            self.assertEqual(parsed.type, 0)
            self.assertLess(p.stat().st_size, 45056)


if __name__ == '__main__':
    unittest.main()
