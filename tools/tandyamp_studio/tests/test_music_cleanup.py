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
from postprocess import classify_drum_bands, clean_stem_notes, refine_drum_hits
from preview import assign_preview_voices, preview_wav


class SpectralDrumTests(unittest.TestCase):
    def test_clear_spectral_classes_and_ambiguity(self):
        self.assertEqual(classify_drum_bands(12, 3, 1), 36)
        self.assertEqual(classify_drum_bands(1, 12, 4), 38)
        self.assertEqual(classify_drum_bands(.5, 2, 11), 42)
        self.assertIsNone(classify_drum_bands(5, 5, 5))
        self.assertIsNone(classify_drum_bands(0, 0, 0))

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
