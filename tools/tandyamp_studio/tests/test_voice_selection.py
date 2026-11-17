"""Opt-in role-aware voice allocation; legacy song output remains byte-stable."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mido
from arranger import (Note, _smart_candidate_priority, make_midi,
                      prepare, export, select_candidates)
from preview import assign_preview_voices


class SmartSelectionTests(unittest.TestCase):
    def test_guitar_chord_leaves_space_for_strong_vocal(self):
        guitar = [Note(0, 1, p, 95, 'guitar') for p in (60, 64, 67)]
        vocal = Note(0, 1, 72, 95, 'melody')
        tones, _, _ = assign_preview_voices(
            guitar + [vocal], 'off', voice_selection='smart', now=.2)
        self.assertIn(vocal, tones)
        self.assertTrue(any(n.part == 'guitar' for n in tones))
        alone, _, _ = assign_preview_voices(guitar, 'off', voice_selection='smart')
        self.assertEqual(len(alone), 3)

    def test_bass_foundation_survives_when_speaker_is_off(self):
        notes = [Note(0, 1, p, 95, 'guitar') for p in (60, 64, 67)]
        vocal = Note(0, 1, 72, 95, 'melody')
        bass = Note(0, 1, 36, 120, 'bass')
        tones, speaker, _ = assign_preview_voices(
            notes + [vocal, bass], 'off', voice_selection='smart', now=.2)
        self.assertIsNone(speaker)
        self.assertIn(bass, tones)
        self.assertEqual({n.part for n in tones}, {'bass', 'guitar', 'melody'})

    def test_strong_new_attack_can_replace_a_held_support_note(self):
        guitar = Note(0, 2, 64, 95, 'guitar')
        vocal = Note(0, 2, 72, 95, 'melody')
        old = Note(0, 2, 67, 60, 'harmony')
        new = Note(.3, 1, 69, 100, 'harmony')
        tones, _, _ = assign_preview_voices(
            [guitar, vocal, old, new], 'off', voice_selection='smart',
            previous_tones=[guitar, vocal, old], now=.3)
        self.assertIn(new, tones)
        self.assertNotIn(old, tones)

    def test_quieter_vocal_survives_loud_guitar_chord(self):
        guitar = [Note(0, 2, p, 110, 'guitar') for p in (60, 64, 67)]
        vocal = Note(0, 2, 74, 50, 'melody')
        tones, _, _ = assign_preview_voices(
            guitar + [vocal], 'off', voice_selection='smart',
            previous_tones=guitar, now=.5)
        self.assertIn(vocal, tones)
        self.assertTrue(any(n.part == 'guitar' for n in tones))

    def test_moderate_bass_falls_back_without_displacing_either_lead(self):
        notes = [Note(0, 2, p, 110, 'guitar') for p in (60, 64, 67)]
        notes += [Note(0, 2, 74, 50, 'melody'), Note(0, 2, 40, 70, 'bass')]
        tones, _, _ = assign_preview_voices(notes, 'off', voice_selection='smart', now=.5)
        self.assertEqual({n.part for n in tones}, {'guitar', 'melody', 'bass'})

    def test_candidate_pool_preserves_quiet_lead_amid_dense_chord(self):
        chord = [Note(0, 2, p, 110, 'guitar') for p in (48, 52, 55, 60, 64, 67, 72)]
        vocal = Note(0, 2, 74, 50, 'melody')
        notes = select_candidates(chord + [vocal], voice_selection='smart')
        self.assertIn(vocal, notes)
        self.assertLessEqual(len(notes), 6)

    def test_quiet_transcribed_leads_gain_dynamics_without_pitch_or_time_changes(self):
        from postprocess import calibrate_lead_dynamics
        notes = [Note(i, i+.2, 60+i, v, 'guitar')
                 for i, v in enumerate((25, 30, 32, 35, 40, 45, 50, 60, 90, 100))]
        result = calibrate_lead_dynamics(notes, 'guitar')
        self.assertGreater(result[3].velocity, notes[3].velocity)
        self.assertEqual([(n.start, n.end, n.pitch) for n in result],
                         [(n.start, n.end, n.pitch) for n in notes])
        self.assertEqual(sorted(n.velocity for n in result), [n.velocity for n in result])
        self.assertTrue(all(a.velocity <= round(b.velocity*1.6) for a,b in zip(result,notes)))
        self.assertEqual(calibrate_lead_dynamics(notes, 'harmony'), notes)
        strong = [Note(i, i+.2, 60, 100, 'melody') for i in range(10)]
        self.assertEqual(calibrate_lead_dynamics(strong, 'melody'), strong)

    def test_full_leads_keep_their_original_high_register(self):
        from arranger import normalize
        notes = [Note(0, 1, 89, 90, 'guitar'), Note(0, 1, 91, 90, 'melody')]
        self.assertEqual([n.pitch for n in normalize(notes, preserve=True)], [89, 91])
        self.assertEqual([n.pitch for n in normalize(notes)], [77, 79])

    def test_smart_protects_strong_guitar_from_weak_vocal_harmonic(self):
        notes = [
            Note(0, 1, 40, 95, 'bass'),
            Note(0, 1, 64, 96, 'guitar'),
            Note(0, 1, 72, 100, 'melody'),
            Note(0, 1, 96, 28, 'melody'),  # likely vocal harmonic
            Note(0, 1, 60, 85, 'harmony'),
            Note(0, 1, 67, 73, 'harmony'),
            Note(0, 1, 76, 71, 'harmony'),
            Note(0, 1, 79, 63, 'harmony'),
            Note(0, 1, 69, 56, 'accomp')
        ]
        smart = select_candidates(notes, spk4='adapt',
                                  voice_selection='smart')
        legacy = select_candidates(notes, spk4='adapt',
                                   voice_selection='legacy')
        self.assertEqual(len(smart), 6)
        self.assertEqual(len(legacy), 6)
        self.assertIn(64, {n.pitch for n in smart})
        self.assertIn(40, {n.pitch for n in smart})
        self.assertNotIn(96, {n.pitch for n in smart})
        self.assertEqual({n.part for n in smart if n.pitch == 64}, {'guitar'})

    def test_hold_continuity_does_not_suppress_a_strong_new_guitar_attack(self):
        old = Note(0, .8, 64, 95, 'guitar')
        new = Note(.25, .9, 69, 117, 'guitar')
        weak = Note(.25, .9, 71, 65, 'guitar')
        self.assertGreater(_smart_candidate_priority(new, False, .25),
                           _smart_candidate_priority(old, True, .25))
        self.assertGreater(_smart_candidate_priority(old, True, .25),
                           _smart_candidate_priority(weak, False, .25))

    def test_preview_keeps_existing_support_until_stronger_change(self):
        guitar = Note(0, 1, 64, 95, 'guitar')
        vocal = Note(0, 1, 72, 95, 'melody')
        support = Note(0, 1, 67, 64, 'harmony')
        new_weak = Note(.2, 1, 69, 67, 'harmony')
        notes, speaker, _ = assign_preview_voices(
            [guitar, vocal, support], 'off', voice_selection='smart',
            now=.15)
        self.assertEqual({n.pitch for n in notes}, {64, 72, 67})
        after, _, _ = assign_preview_voices(
            [guitar, vocal, support, new_weak], 'off',
            voice_selection='smart', previous_tones=notes, now=.21)
        self.assertEqual({n.pitch for n in after}, {64, 72, 67})
        self.assertIsNone(speaker)

    def test_accompaniment_uses_open_slot_not_guitar_voice(self):
        notes = [
            Note(0, 1, 64, 94, 'guitar'),
            Note(0, 1, 72, 90, 'melody'),
            Note(0, 1, 67, 50, 'accomp')
        ]
        tones, _, _ = assign_preview_voices(
            notes, 'off', voice_selection='smart', now=.20)
        self.assertEqual({n.pitch for n in tones}, {64, 72, 67})
        competing = notes + [Note(.1, 1, 60, 92, 'harmony')]
        tones, _, _ = assign_preview_voices(
            competing, 'off', voice_selection='smart', now=.20)
        self.assertEqual({n.pitch for n in tones}, {64, 72, 60})
        self.assertNotIn(67, {n.pitch for n in tones})

    def test_fourth_speaker_still_reserved_for_real_bass(self):
        notes = [
            Note(0, 1, 36, 115, 'bass'),
            Note(0, 1, 64, 95, 'guitar'),
            Note(0, 1, 72, 95, 'melody'),
            Note(0, 1, 67, 70, 'harmony'),
            Note(0, 1, 96, 30, 'melody')
        ]
        voices, speaker, _ = assign_preview_voices(
            notes, 'adapt', voice_selection='smart', now=.2)
        self.assertIsNotNone(speaker)
        self.assertEqual(speaker.pitch, 36)
        self.assertEqual({n.pitch for n in voices}, {64, 72, 67})

    def test_smart_midi_marker_is_explicit_and_does_not_change_timing(self):
        notes = [Note(.2, 1.50, 64, 100, 'guitar'),
                 Note(.2, 1.25, 36, 115, 'bass')]
        legacy = mido.MidiFile(file=BytesIO(make_midi(notes, 0, 2)))
        smart = mido.MidiFile(file=BytesIO(
            make_midi(notes, 0, 2, voice_selection='smart')))
        self.assertFalse(any(m.type == 'control_change' and m.control == 119
                             for m in legacy.tracks[0]))
        markers = [m for m in smart.tracks[0] if m.type == 'control_change'
                   and m.control == 119]
        self.assertEqual(len(markers), 1)
        self.assertEqual((markers[0].channel, markers[0].value), (0, 77))
        self.assertAlmostEqual(smart.length, legacy.length, delta=.000001)
        self.assertEqual(
            [(m.type, m.note, m.velocity) for m in smart.tracks[0]
             if m.type in ('note_on', 'note_off')],
            [(m.type, m.note, m.velocity) for m in legacy.tracks[0]
             if m.type in ('note_on', 'note_off')]
        )

    def test_smart_marker_in_every_split_segment(self):
        notes = [Note(.0, 2.4, 64, 100, 'guitar')]
        with tempfile.TemporaryDirectory() as td:
            files = export(notes, Path(td)/'Smart', max_seconds=1.0,
                           voice_selection='smart')
            self.assertEqual(len(files), 3)
            for file in files:
                song = mido.MidiFile(str(file))
                self.assertEqual(song.type, 0)
                self.assertTrue(any(m.type == 'control_change'
                                    and m.control == 119 and m.value == 77
                                    for m in song.tracks[0]))
                self.assertLess(file.stat().st_size, 45056)

    def test_legacy_prepare_unchanged(self):
        notes = [Note(0, 1, 64, 91, 'guitar'),
                 Note(0, 1, 60, 80, 'harmony')]
        self.assertEqual(prepare(notes),
                         prepare(notes, voice_selection='legacy'))
        with self.assertRaises(ValueError):
            prepare(notes, voice_selection='unknown')


if __name__ == '__main__':
    unittest.main()
