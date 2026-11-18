"""Check the Tuned path with small MIDI and transcription fixtures."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arranger import Note, load_midi, make_midi, voice_coverage
from defaults import PARATUNE_REFERENCE_MIDI_SHA256, STUDIO_DEFAULTS
from phrase_score import Phrase, Score, arrange_score
from pitch_arranger import BeatGrid, Reference, arrange_tuned
import studio


class PitchArrangerTests(unittest.TestCase):
    def test_stems_and_shared_harmony_fix_only_small_errors(self):
        bass = [Note(0, .72, 40, 86, 'bass', 33)]
        guitar = [Note(0, .72, 59, 83, 'guitar', 30)]
        vocals = [
            Note(0, .15, 63, 89, 'melody', 80),  # Strong attacks may be intentional chromatic notes.
            Note(.18, .38, 67, 88, 'melody', 80),
            Note(.38, .52, 68, 67, 'melody', 80),
            Note(.53, .72, 67, 89, 'melody', 80),
        ]
        drums = (Note(.03, .09, 38, 89, 'drums', 0),)
        score = Score((), drums, tuple(Phrase(n[0].part, n[0].part, tuple(n))
                                       for n in (bass, guitar, vocals)))
        notes, report = arrange_tuned(score, bass + guitar + vocals)
        pitches = [n.pitch % 12 for n in notes if n.part == 'melody']
        # A repeated weak C/F/G pitch detector boundary may collapse
        # into a sustained note; the pitch contour must remain intact.
        self.assertEqual(pitches, [3, 7, 7])
        self.assertGreaterEqual(report.note_commit['duplicates_merged'],1)
        self.assertEqual(report.corrected, {'melody': 1})
        self.assertEqual(voice_coverage(notes)['four_plus'], 0)
        self.assertEqual([n for n in notes if n.part == 'drums'], list(drums))

    def test_shared_harmony_matches_a_supported_nearby_pitch(self):
        guitar = Note(0, .50, 60, 86, 'guitar', 30)
        vocal = Note(.1, .27, 61, 70, 'melody', 80)
        score = Score((), (), (Phrase('guitar', 'riff', (guitar,)),
                               Phrase('melody', 'vocal', (vocal,))))
        notes, report = arrange_tuned(score, [guitar, vocal])
        lead, = [n for n in notes if n.part == 'melody']
        self.assertEqual((lead.pitch % 12, lead.start, lead.end), (0, .1, .27))
        self.assertEqual(report.corrected, {'melody': 1})

    def test_guitar_hold_stops_before_the_next_support_line(self):
        guitar = Note(0, .10, 52, 70, 'guitar', 30)
        bass = Note(0, .6, 40, 80, 'bass', 33)
        vocal = Note(0, .6, 67, 96, 'melody', 80)
        harmony = Note(.14, .55, 65, 70, 'harmony', 48)
        score = Score((0., .5, 1.), (), tuple(
            Phrase(n.part, function, (n,)) for n, function in (
                (guitar, 'backing'), (bass, 'bass'), (vocal, 'vocal'), (harmony, 'harmony'))))
        notes, _ = arrange_tuned(score, [guitar, bass, vocal, harmony])
        self.assertEqual(voice_coverage(notes)['four_plus'], 0)
        arranged_guitar, = (n for n in notes if n.part == 'guitar')
        self.assertEqual(arranged_guitar.end, harmony.start)

    def test_midi_guide_matches_pitch_and_can_keep_sub_beat_drum_attacks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            guide = root / 'guide.mid'
            guide.write_bytes(make_midi([
                Note(0, .5, 67, 95, 'melody', 80),
                Note(0., .030, 38, 80, 'drums', 0),
            ], 0, .5))
            grid = BeatGrid.parse('0=.1,1=.6')
            reference = Reference.load(guide, 'melody=1,drums=10', grid, end=.6)
            score = Score((), (), (Phrase('melody', 'vocal',
                                          (Note(.1, .47, 68, 86, 'melody', 80),)),))
            notes, report = arrange_tuned(score, [], reference=reference)
        self.assertEqual(report.corrected, {'melody': 1})
        self.assertEqual([n.start for n in notes], [.1, .1])
        self.assertEqual({(n.part, n.pitch) for n in notes}, {('melody', 67), ('drums', 38)})

    def test_default_audio_writes_tuned_export_and_psg_playback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'test.wav'
            audio.touch()
            proposals = [Note(0, .5, 60, 89, 'guitar', 30),
                         Note(.11, .29, 61, 70, 'melody', 80)]
            with patch('transcribe.transcribe_audio', return_value=proposals):
                midi, = studio.convert(audio, root, preview=False)
            self.assertEqual(midi.parent.name, 'test_TUNED')
            self.assertIn('melody', (midi.parent / 'PITCH.TXT').read_text())
            self.assertEqual((midi.parent / 'PLAY.BAT').read_bytes(),
                             b'@ECHO OFF\r\nTANDYAMP /NOSPK4\r\n')
            self.assertEqual([n.pitch % 12 for n in load_midi(midi) if n.part == 'melody'], [0])

    def test_pinned_benchmark_settings(self):
        manifest = Path(__file__).resolve().parents[1] / 'benchmarks' / 'PARATUNE_reference.json'
        expected = json.loads(manifest.read_text())
        self.assertEqual(expected['midi_sha256'], PARATUNE_REFERENCE_MIDI_SHA256)
        for setting, value in expected['settings'].items():
            self.assertEqual(STUDIO_DEFAULTS[setting], value)


if __name__ == '__main__':
    unittest.main()
