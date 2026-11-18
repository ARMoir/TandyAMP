"""Reproduce the hardware-approved Paranoid excerpt using local source files."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arranger import Note, make_midi
from defaults import PARATUNE_REFERENCE_MIDI_SHA256
from phrase_score import ScoreEvidence, reconstruct_score
from pitch_arranger import BeatGrid, Reference, arrange_tuned

BASELINE = Path(__file__).with_name('PARATUNE_reference.json')


def reproduce(reference_midi: Path, transcription: Path) -> bytes:
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    guide = baseline['guide']
    expected = guide['sha256']
    if sha256(reference_midi.read_bytes()).hexdigest() != expected:
        raise ValueError('This benchmark requires the recorded reference MIDI edition')
    take = sha256(transcription.read_bytes()).hexdigest()
    if take != baseline['transcription_sha256']:
        raise ValueError('Use the archived transcription for an exact benchmark replay')
    source = json.loads(transcription.read_text(encoding='utf-8'))
    proposals = [Note(**row) for row in source['notes']]
    evidence = ScoreEvidence(**source['evidence'])
    grid = BeatGrid(tuple(guide['beats']), tuple(guide['seconds']))
    # Reproduce how the original sequencer-MIDI reader converted its
    # constant-tempo timestamps to beats. This matters at MIDI tick ties.
    seconds_per_beat = guide['midi_tempo_us'] / 1_000_000
    quarter_ticks = guide['midi_ticks_per_beat']

    def decode_beats(beat: float) -> float:
        return (round(beat * quarter_ticks) * (seconds_per_beat / quarter_ticks)
                / seconds_per_beat)

    reference = Reference.load(reference_midi, guide['channels'], grid,
                               baseline['seconds'], beat_decoder=decode_beats)
    score = reconstruct_score(proposals, evidence)
    notes, _ = arrange_tuned(score, proposals, reference=reference)
    data = make_midi(notes, 0., baseline['seconds'], voice_selection='smart')
    if sha256(data).hexdigest() != PARATUNE_REFERENCE_MIDI_SHA256:
        raise RuntimeError('Export differs from the hardware-approved PARATUNE.MID')
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference_midi', type=Path, help='Local sequencer MIDI')
    parser.add_argument('transcription', type=Path, help='Archived raw notes and stem evidence')
    parser.add_argument('-o', '--output', type=Path, default=Path('PARATUNE.MID'))
    args = parser.parse_args()
    data = reproduce(args.reference_midi, args.transcription)
    with args.output.open('xb') as stream:
        stream.write(data)
    print(f'{args.output} matches the hardware-approved take')


if __name__ == '__main__':
    main()
