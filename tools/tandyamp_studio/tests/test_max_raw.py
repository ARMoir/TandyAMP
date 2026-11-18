"""MAX RAW: audio note preservation and DOS split regression tests.

All tests are offline and use synthetic notes or mocked stem/model modules.
They do not fetch YouTube videos, FFmpeg, Demucs weights or music tracks.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mido
import studio
from arranger import Note, TEMPO, TICKS_PER_SECOND
from max_raw import RAW_PARTS, make_raw_midi, export_raw, raw_summary
from prediction_cache import decoder_settings
from transcribe import transcribe_audio


def midi_events(file: Path | bytes):
    midi = mido.MidiFile(file=BytesIO(file)) if isinstance(file, bytes) \
        else mido.MidiFile(str(file))
    total = 0
    result = []
    for msg in midi.tracks[0]:
        total += msg.time
        if msg.type in ('note_on', 'note_off'):
            result.append((total, msg.type, msg.channel, msg.note, msg.velocity))
    return midi, result


class MaxRawMidiTests(unittest.TestCase):
    def test_all_six_stems_keep_original_pitch_velocity_timing(self):
        notes = [
            Note(.003, .50, 127, 1, 'melody'),
            Note(.004, .71, 19, 2, 'bass'),
            Note(.01, .32, 66, 110, 'harmony'),
            Note(.05, .80, 95, 7, 'guitar'),
            Note(.00, .91, 24, 127, 'piano'),
            Note(.10, .11, 57, 91, 'drums'),
        ]
        data = make_raw_midi(notes, 0, 1)
        mid, events = midi_events(data)
        self.assertEqual(mid.type, 0)
        self.assertEqual(len(mid.tracks), 1)
        self.assertEqual(mid.tracks[0][0].tempo, TEMPO)
        starts = [(tick, channel, pitch, velocity)
                  for tick, kind, channel, pitch, velocity in events
                  if kind == 'note_on']
        self.assertEqual(len(starts), 6)
        for n in notes:
            channel, _program = RAW_PARTS[n.part]
            self.assertIn((round(n.start*TICKS_PER_SECOND), channel,
                           n.pitch, n.velocity), starts)
        self.assertIn((round(.11*TICKS_PER_SECOND), 'note_off',
                       9, 57, 0), events)
        self.assertNotIn((0, 9, 57, 0), events)

    def test_no_velocities_clamped_and_no_short_notes_discarded(self):
        notes = [Note(.1, .101, 109, 2, 'guitar'),
                 Note(.2, .21, 5, 120, 'bass'),
                 Note(.3, .35, 84, 3, 'piano')]
        mid, events = midi_events(make_raw_midi(notes, 0, 1))
        ons = [(channel, pitch, vel) for _, kind, channel, pitch, vel in events
               if kind == 'note_on']
        self.assertEqual(ons, [(4, 109, 2), (1, 5, 120), (5, 84, 3)])

    def test_no_arbitrary_time_split_for_long_sparse_song(self):
        notes = [Note(0, 220, 36, 80, 'bass'),
                 Note(215, 219, 64, 99, 'guitar')]
        with tempfile.TemporaryDirectory() as d:
            files = export_raw(notes, Path(d)/'A long name with spaces')
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].name, 'ALONGN01.MID')
            self.assertLess(files[0].stat().st_size, 42000)
            midi = mido.MidiFile(str(files[0]))
            self.assertAlmostEqual(midi.length, 220, delta=.01)

    def test_size_only_split_retains_each_note_start_and_channel(self):
        # All notes are separated, so a segment boundary cannot duplicate
        # a note-on. No event may be silently lost by the size splitter.
        notes = [Note(i*.035, i*.035+.012, 35+(i%65),
                      15+(i%110), ('guitar','melody','piano','bass',
                                  'harmony','drums')[i%6])
                 for i in range(180)]
        with tempfile.TemporaryDirectory() as d:
            files = export_raw(notes, Path(d)/'Many loud notes', max_bytes=360)
            self.assertGreater(len(files), 2)
            self.assertEqual([p.name for p in files],
                             [f'MANYLO{i:02d}.MID'
                              for i in range(1, len(files)+1)])
            self.assertTrue(all(p.stat().st_size <= 360 for p in files))
            all_ons = []
            position = 0
            for f in files:
                song, events = midi_events(f)
                self.assertEqual(song.type, 0)
                for tick, kind, ch, pitch, velocity in events:
                    if kind == 'note_on':
                        all_ons.append((round(position + tick/TICKS_PER_SECOND, 3),
                                        ch, pitch, velocity))
                position += song.length
            # A note held across a file boundary legitimately gets an
            # extra note_on in the next file. Every *original* attack must
            # nevertheless survive with its original channel/pitch/velocity.
            self.assertGreaterEqual(len(all_ons), len(notes))
            for n in notes:
                channel = RAW_PARTS[n.part][0]
                self.assertTrue(any(ch == channel and p == n.pitch and
                                    v == n.velocity and
                                    abs(at-n.start) <= .003
                                    for at, ch, p, v in all_ons),
                                f'Missing source attack: {n}')
            with self.assertRaises(FileExistsError):
                export_raw(notes, Path(d)/'Many loud notes', max_bytes=360)

    def test_held_notes_straddling_segments_remain_present(self):
        notes = [Note(0, 5, 36, 101, 'bass')]
        notes.extend(Note(i*.10, i*.10+.03, 60+i%5, 85, 'guitar')
                     for i in range(50))
        with tempfile.TemporaryDirectory() as d:
            files = export_raw(notes, Path(d)/'HOLD', max_bytes=300)
            self.assertGreater(len(files), 1)
            for f in files:
                _m, events = midi_events(f)
                self.assertIn((1, 36, 101),
                              [(ch,p,v) for t,k,ch,p,v in events
                               if k == 'note_on'])

    def test_invalid_notes_fail_instead_of_silent_removal(self):
        with self.assertRaisesRegex(ValueError, 'nonpositive'):
            export_raw([Note(1, 1, 60, 90, 'melody')], Path('unused'))
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            export_raw([Note(0, 1, 60, 90, 'unknown')], Path('unused'))

    def test_raw_summary_marks_source_as_estimates(self):
        report = raw_summary([Note(0, 1, 64, 105, 'guitar')])
        self.assertIn('ESTIMATES', report)
        self.assertIn('guitar', report)
        self.assertIn('Split boundaries', report)


class RawTranscriptionTests(unittest.TestCase):
    def test_decoder_is_highest_recall_profile(self):
        raw = decoder_settings('guitar', 'raw')
        standard = decoder_settings('guitar', 'standard')
        sensitive = decoder_settings('guitar', 'sensitive')
        self.assertLess(raw['onset_thresh'], sensitive['onset_thresh'])
        self.assertLess(raw['frame_thresh'], sensitive['frame_thresh'])
        self.assertLess(raw['min_note_len'], standard['min_note_len'])

    def test_demucs_six_stems_including_piano_and_no_cleanup(self):
        captured = {}
        def fake_run(cmd, check):
            captured['model'] = cmd[cmd.index('-n')+1]
            root = Path(cmd[cmd.index('-o')+1]) / captured['model'] / 'source'
            root.mkdir(parents=True, exist_ok=True)
            for stem in ('bass','vocals','guitar','other','piano','drums'):
                (root / (stem+'.wav')).write_bytes(b'dummy')
        def fake_predict(path, part, *, profile='standard', cache_dir=None):
            captured.setdefault('profiles', set()).add(profile)
            return [Note(0, .01, 90 if part != 'bass' else 20, 4,
                         part), Note(.2, .3, 63, 2, part)]
        with tempfile.TemporaryDirectory() as d:
            source = Path(d)/'source.mp3'
            source.write_bytes(b'mp3')
            with patch.dict(sys.modules, {'demucs': types.ModuleType('demucs')}):
                with patch('transcribe.subprocess.run', side_effect=fake_run):
                    with patch('transcribe._predict', side_effect=fake_predict):
                        with patch('transcribe._drum_onsets', return_value=[
                            Note(0, .03, 49, 44, 'drums')
                        ]) as drums:
                            with patch('postprocess.clean_stem_notes',
                                       side_effect=AssertionError(
                                           'RAW cannot run cleanup')):
                                with patch('transcribe.remove_guitar_bleed',
                                           side_effect=AssertionError(
                                               'RAW cannot discard bleed')):
                                    with patch('accompaniment.analyze_accompaniment_audio',
                                               side_effect=AssertionError(
                                                   'RAW cannot generate notes')):
                                        notes = transcribe_audio(
                                            source, raw_mode=True,
                                            accompaniment='harmonize',
                                            guitar_separation=False)
        self.assertEqual(captured['model'], 'htdemucs_6s')
        self.assertEqual(captured['profiles'], {'raw'})
        self.assertEqual(len(notes), 11)  # all five pitched sources + drums
        self.assertIn('piano', {n.part for n in notes})
        self.assertTrue(all(n.velocity == 4 for n in notes
                            if n.start == 0 and n.part != 'drums'))
        self.assertTrue(drums.call_args.kwargs['raw_mode'])

    def test_cli_flag_and_maxraw_only_audio(self):
        with patch('studio.convert', return_value=[Path('X.MID')]) as convert:
            rc = studio.main(['--cli',
                'https://www.youtube.com/watch?v=Uq42HUUJFzU',
                '--max-raw', '-o', 'out'])
        self.assertEqual(rc, 0)
        self.assertTrue(convert.call_args.kwargs['max_raw'])
        with tempfile.TemporaryDirectory() as d:
            original = Path(d)/'source.mid'
            original.write_bytes(make_raw_midi([
                Note(0, 1, 64, 80, 'guitar')], 0, 1))
            with self.assertRaisesRegex(ValueError, 'YouTube/audio'):
                studio._convert_local(original, Path(d), 'TEST',
                                      'balanced', 'adapt', False, False,
                                      max_raw=True)


if __name__ == '__main__':
    unittest.main()
