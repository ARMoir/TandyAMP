"""Host regression tests; no AI downloads and no Tandy hardware required."""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import mido
from arranger import Note, export, load_midi, make_midi, normalize, prepare, select_voices


class ArrangerTests(unittest.TestCase):
    def test_spk4_uses_exactly_three_psg_and_low_bass(self):
        notes = [Note(0, 1, 36, 115, 'bass'), Note(0, 1, 60, 90, 'melody'),
                 Note(0, 1, 64, 90, 'harmony'), Note(0, 1, 67, 90, 'harmony')]
        selected = select_voices(notes)
        self.assertEqual({n.pitch for n in selected}, {36, 60, 64, 67})
        self.assertEqual(len(select_voices(notes, spk4=False)), 3)
        self.assertEqual(len(select_voices(notes[:-1], spk4=True)), 3)

    def test_spk4_cannot_take_high_overflow(self):
        notes = [Note(0, 1, n, 100, 'melody' if n == 72 else 'harmony') for n in (60, 64, 67, 72)]
        self.assertEqual(len(select_voices(notes)), 3)

    def test_bass_transposed_into_range_and_treble_soft(self):
        notes = normalize([Note(0, 1, 19, 85, 'bass'), Note(0, 1, 110, 85, 'melody')])
        self.assertTrue(24 <= notes[0].pitch <= 52 or 24 <= notes[1].pitch <= 52)
        self.assertTrue(all(n.pitch <= 86 for n in notes if n.part != 'bass'))

    def test_type0_small_and_dos_filenames(self):
        notes = [Note(0, 2, 36, 120, 'bass'), Note(0, 2, 60, 110, 'melody'),
                 Note(0, 2, 64, 90), Note(0, 2, 67, 90),
                 Note(0.1, 0.18, 36, 120, 'drums')]
        with tempfile.TemporaryDirectory() as td:
            paths = export(prepare(notes), pathlib.Path(td) / 'Long Fancy Song')
            self.assertEqual(paths[0].name, 'LONGFA01.MID')
            self.assertTrue(paths[0].stat().st_size < 45056)
            midi = mido.MidiFile(str(paths[0]))
            self.assertEqual(midi.type, 0)
            self.assertEqual(len(midi.tracks), 1)
            self.assertEqual({m.channel for m in midi.tracks[0] if m.type == 'note_on'}, {0, 1, 2, 9})
            parsed = load_midi(paths[0])
            self.assertTrue(parsed)
            self.assertGreaterEqual(max(n.end for n in parsed), 1.98)

    def test_chop_at_time_limit_keeps_sustained_notes(self):
        notes = [Note(0.0, 5.0, 36, 110, 'bass'), Note(0.0, 5.0, 60, 90, 'melody')]
        with tempfile.TemporaryDirectory() as td:
            paths = export(notes, pathlib.Path(td) / 't', max_seconds=2)
            self.assertEqual(len(paths), 3)
            durations = [max(n.end for n in load_midi(f)) for f in paths]
            self.assertEqual([round(x, 1) for x in durations], [2, 2, 1])

    def test_file_size_split_and_reject_overwrite(self):
        notes = [Note(k / 20, k / 20 + .045, 60 + k % 8, 100, 'melody') for k in range(500)]
        with tempfile.TemporaryDirectory() as td:
            dst = pathlib.Path(td) / 'burst'
            paths = export(notes, dst, max_bytes=650, max_seconds=150)
            self.assertGreater(len(paths), 1)
            self.assertTrue(all(f.stat().st_size <= 650 for f in paths))
            with self.assertRaises(FileExistsError):
                export(notes, dst, max_bytes=650, max_seconds=150)

    def test_export_invalid_size(self):
        with self.assertRaises(ValueError):
            export([Note(0, 1, 60, 100)], pathlib.Path('unused'), max_bytes=45056)


if __name__ == '__main__':
    unittest.main()
