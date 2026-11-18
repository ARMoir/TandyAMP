"""MAX RAW: high-recall audio transcription -> unarranged, size-split DOS MIDI.

Unlike arranger.prepare(), this exporter NEVER:
* limits the number of candidate notes;
* changes pitch or note velocity;
* transposes bass/octave-folds treble;
* auto-levels parts;
* merges adjacent notes or removes simultaneous notes;
* simplifies drums.

These are estimates from the audio model, NOT an original studio MIDI score.
Every valid detected Note is represented. Splitting may retrigger notes held
across a segment boundary; this is unavoidable in independent DOS MIDI files.
"""
from __future__ import annotations

from collections import Counter
from io import BytesIO
from pathlib import Path
import re

import mido

from arranger import Note, MAX_FILE, PPQN, TEMPO, TICKS_PER_SECOND


RAW_PARTS = {
    # channel, GM program. Six separately decoded Demucs sources.
    'melody': (0, 80),   # vocals
    'bass': (1, 33),
    'harmony': (2, 48),  # other
    'guitar': (4, 30),
    'piano': (5, 0),
    'drums': (9, None),
}


def _valid_notes(notes: list[Note]) -> list[Note]:
    checked = []
    for n in notes:
        if n.part not in RAW_PARTS:
            raise ValueError(f'Unknown MAX RAW part: {n.part}')
        if not (0 <= n.pitch <= 127 and 0 <= n.velocity <= 127):
            raise ValueError('MAX RAW notes must have MIDI pitch/velocity 0..127')
        if n.start < 0 or n.end <= n.start:
            raise ValueError('MAX RAW note has negative start or nonpositive duration')
        checked.append(n)
    return checked


def make_raw_midi(notes: list[Note], start: float, end: float) -> bytes:
    """One compact type-0 MIDI segment, unchanged estimated notes.

    Preserve the source part's MIDI channel; per-note model output includes
    no continuous CC/pitch-bend data. Rearticulate notes across segment cuts.
    """
    if end <= start:
        raise ValueError('Invalid MAX RAW segment range')
    events = []
    for part, (channel, program) in RAW_PARTS.items():
        if program is not None:
            events.append((0, 0, mido.Message(
                'program_change', channel=channel, program=program)))
    # Maintain overlapping same-pitch MIDI notes and all distinct source
    # channels. Notes at or after 'end' are written to the next segment.
    for n in notes:
        if n.start >= end or n.end <= start:
            continue
        channel, _ = RAW_PARTS[n.part]
        begin_tick = max(0, round((max(start, n.start)-start) *
                                  TICKS_PER_SECOND))
        finish_tick = max(begin_tick+1, round((min(end, n.end)-start) *
                                              TICKS_PER_SECOND))
        events.append((begin_tick, 2, mido.Message(
            'note_on', channel=channel, note=n.pitch, velocity=n.velocity)))
        events.append((finish_tick, 1, mido.Message(
            'note_off', channel=channel, note=n.pitch, velocity=0)))
    events.sort(key=lambda e: (e[0], e[1]))
    track = mido.MidiTrack([mido.MetaMessage(
        'set_tempo', tempo=TEMPO, time=0)])
    last = 0
    for at, _, msg in events:
        track.append(msg.copy(time=at-last))
        last = at
    # The end-of-track marker retains the full source duration even where
    # the source has a silent tail before the next file boundary.
    finish = max(last, round((end-start) * TICKS_PER_SECOND))
    track.append(mido.MetaMessage('end_of_track', time=finish-last))
    midi = mido.MidiFile(type=0, ticks_per_beat=PPQN)
    midi.tracks.append(track)
    buffer = BytesIO()
    midi.save(file=buffer)
    return buffer.getvalue()


def export_raw(notes: list[Note], destination: Path, max_bytes: int = 42000
               ) -> list[Path]:
    """Preserve every note; split ONLY to satisfy DOS/TandyAMP file size.

    Avoid a gratuitous 180-second cut. The segment's last note carries
    forward on a fresh note-on in the next file when it straddles the split.
    Keep filenames in DOS 8.3 and SMF format 0 with six instrument parts.
    """
    if not 256 <= max_bytes < MAX_FILE:
        raise ValueError('max_bytes must be 256..45055')
    notes = _valid_notes(list(notes))
    if not notes:
        raise ValueError('MAX RAW detected no notes to export')
    notes.sort(key=lambda n: (n.start, n.end, n.pitch, n.part))
    duration = max(n.end for n in notes)
    dest = Path(destination)
    stem = re.sub(r'[^A-Z0-9]', '', dest.name.upper())[:6] or 'TANDY'
    pieces: list[bytes] = []
    start = 0.0
    tick_seconds = 1.0 / TICKS_PER_SECOND
    while start < duration - tick_seconds / 4:
        end = duration
        data = make_raw_midi(notes, start, end)
        if len(data) > max_bytes:
            # Binary-search the longest section that fits, including
            # sustained notes carried into this section.
            low, high = start, end
            for _ in range(34):
                middle = (low + high) / 2
                trial = make_raw_midi(notes, start, middle)
                if len(trial) <= max_bytes:
                    low = middle
                else:
                    high = middle
            # Don't advance by less than one MIDI tick or loop indefinitely.
            end = min(duration, round(low*TICKS_PER_SECOND) /
                      TICKS_PER_SECOND)
            if end <= start + tick_seconds / 2:
                raise ValueError(
                    'Too many simultaneous notes to fit a single DOS MIDI '
                    'segment even at the shortest supported time interval')
            data = make_raw_midi(notes, start, end)
            if len(data) > max_bytes:
                # Rounding up may have moved a boundary beyond capacity.
                end -= tick_seconds
                data = make_raw_midi(notes, start, end)
                if len(data) > max_bytes or end <= start:
                    raise ValueError('MAX RAW density exceeds MIDI size limit')
        pieces.append(data)
        if len(pieces) > 99:
            raise ValueError('MAX RAW requires over 99 DOS MIDI files; '
                             'reduce the source duration')
        start = end

    paths = [dest / f'{stem}{idx:02d}.MID'
             for idx in range(1, len(pieces)+1)]
    if any(p.exists() for p in paths):
        raise FileExistsError('Refusing to overwrite existing MAX RAW MIDI files')
    dest.mkdir(parents=True, exist_ok=True)
    for path, data in zip(paths, pieces):
        if len(data) > max_bytes:
            raise RuntimeError('MAX RAW size check failed before writing')
        path.write_bytes(data)
        # Final parse and physical limits check on the laptop.
        song = mido.MidiFile(str(path))
        if (song.type != 0 or len(song.tracks) != 1 or
                path.stat().st_size >= MAX_FILE or
                len(path.stem) > 8):
            raise RuntimeError(f'Invalid TandyAMP MAX RAW MIDI: {path}')
    return paths


def raw_summary(notes: list[Note]) -> str:
    counts = Counter(n.part for n in notes)
    return ('MAX RAW estimated audio-note transcription\n'
            'No note pruning, octave shifting, voice selection, velocity '
            'normalization or accompaniment generation.\n'
            'Six sources: vocals, bass, guitar, other, piano, drums.\n'
            'MIDI type 0; separate source channels 1,2,3,5,6 and 10.\n'
            'Model note pitches, starts, ends and velocities are ESTIMATES, '
            'not original studio MIDI data.\n'
            'DOS hardware still decides which notes are audible.\n'
            'Split boundaries re-trigger held notes; all notes survive.\n'
            'Events by part: ' + repr(dict(sorted(counts.items()))) + '\n')
