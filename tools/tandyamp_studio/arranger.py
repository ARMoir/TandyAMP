"""Offline, hardware-aware MIDI arranger for TandyAMP. Requires mido only."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, replace
from pathlib import Path
import re
from typing import Iterable

try:
    import mido
except ImportError as exc:
    raise SystemExit('Missing mido: python -m pip install -r requirements.txt') from exc

# These are constraints in TandyAMP src/midi.h and src/midi.c, not a generic GM synth.
MAX_FILE = 45056
MAX_TRACKS = 24
BASS_MIN, BASS_MAX = 24, 52
PPQN = 480
TEMPO = 500000
TICKS_PER_SECOND = PPQN * 1_000_000 / TEMPO
PART_CHANNEL = {'melody': 0, 'bass': 1, 'harmony': 2, 'drums': 9}
PRESETS = {
    'quality': {'high': 92, 'min_duration': 0.040, 'drum_gap': 0.055},
    'balanced': {'high': 86, 'min_duration': 0.065, 'drum_gap': 0.075},
    'performance': {'high': 81, 'min_duration': 0.090, 'drum_gap': 0.100},
}


@dataclass(frozen=True)
class Note:
    start: float
    end: float
    pitch: int
    velocity: int
    part: str = 'harmony'
    program: int = 48


def load_midi(path: Path) -> list[Note]:
    """Decode SMF 0/1 into time-in-seconds notes, honoring tempo and sustain."""
    midi = mido.MidiFile(str(path))
    if midi.type not in (0, 1):
        raise ValueError('Only MIDI type 0 or 1 is supported')
    tempo = TEMPO
    sec = 0.0
    programs = [None] * 16
    sustain = [False] * 16
    held = defaultdict(deque)
    deferred = defaultdict(list)
    result = []

    def finish(rec: tuple, end: float) -> None:
        start, pitch, velocity, chan, program = rec
        if end - start >= 0.012:
            if chan == 9:
                part = 'drums'
            elif program is not None and 32 <= program <= 39:
                part = 'bass'
            elif chan == 1 and pitch <= 60:
                part = 'bass'
            elif chan == 0 or (pitch >= 72 and chan not in (1, 2, 3)):
                part = 'melody'
            elif pitch <= 48:
                part = 'bass'
            else:
                part = 'harmony'
            result.append(Note(start, end, pitch, velocity, part, program if program is not None else (80 if part == 'melody' else 33 if part == 'bass' else 48)))

    for msg in mido.merge_tracks(midi.tracks):
        sec += mido.tick2second(msg.time, midi.ticks_per_beat, tempo)
        if msg.type == 'set_tempo':
            tempo = msg.tempo
        elif msg.type == 'program_change':
            programs[msg.channel] = msg.program
        elif msg.type == 'control_change' and msg.control == 64:
            old = sustain[msg.channel]
            sustain[msg.channel] = msg.value >= 64
            if old and not sustain[msg.channel]:
                for rec in deferred.pop(msg.channel, []):
                    finish(rec, sec)
        elif msg.type == 'note_on' and msg.velocity > 0:
            held[msg.channel, msg.note].append((sec, msg.note, msg.velocity, msg.channel, programs[msg.channel]))
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            key = (msg.channel, msg.note)
            if held[key]:
                rec = held[key].popleft()
                if sustain[msg.channel] and msg.channel != 9:
                    deferred[msg.channel].append(rec)
                else:
                    finish(rec, sec)
    for queue in held.values():
        for rec in queue:
            finish(rec, sec)
    for queue in deferred.values():
        for rec in queue:
            finish(rec, sec)
    return result


def normalize(notes: Iterable[Note], preset: str = 'balanced') -> list[Note]:
    config = PRESETS[preset]
    result = []
    for n in notes:
        # Noise hits are intentionally shorter than pitched notes. Preserve
        # hats across all presets instead of discarding them as tiny pitches.
        min_duration = .025 if n.part == 'drums' else config['min_duration']
        if n.end - n.start < min_duration or n.velocity < 12:
            continue
        p = n.pitch
        if n.part == 'drums':
            if p in (35, 36): p = 36
            elif p in (38, 40, 37, 39): p = 38
            elif p in (42, 44, 46, 49, 51, 57): p = 42
            else: continue
            result.append(replace(n, pitch=p, end=min(n.end, n.start + 0.08)))
            continue
        if n.part == 'bass':
            while p < BASS_MIN: p += 12
            while p > BASS_MAX: p -= 12
        else:
            # Fold notes to audible, practical PSG ranges before the V20 sees them.
            while p < 45: p += 12
            while p > config['high']: p -= 12
        velocity = max(24, min(127, n.velocity))
        if n.part == 'bass':
            velocity = max(107, velocity)  # pass the PIT2 audibility gate
        result.append(replace(n, pitch=p, velocity=velocity))
    return sorted(result, key=lambda n: (n.start, n.end, n.pitch))


def _priority(n: Note, previous: bool) -> int:
    part = {'melody': 1100, 'bass': 825, 'harmony': 370}.get(n.part, 0)
    return part + n.velocity * 3 + (200 if previous else 0) + (50 if n.pitch >= 60 else 0)


def _psg_pitch(n: Note) -> int:
    p = n.pitch
    while p < 45: p += 12
    return p


def select_voices(notes: Iterable[Note], spk4: bool = True) -> list[Note]:
    """Emit a bounded event arrangement: three distinct PSG pitches plus eligible PIT2 bass.

    Offline scoring applies at note boundaries, with a continuity bonus to
    reduce unnecessary voice switches. No real-time CPU cost on the Tandy.
    """
    source = [n for n in notes if n.part != 'drums']
    drums = [n for n in notes if n.part == 'drums']
    events = []
    for i, n in enumerate(source):
        if n.end > n.start:
            events.extend(((n.start, 1, i), (n.end, 0, i)))
    events.sort()  # note-off before note-on at the same timestamp
    active: set[int] = set()
    chosen: set[int] = set()
    opened: dict[int, float] = {}
    result: list[Note] = []
    pos = 0
    while pos < len(events):
        time = events[pos][0]
        while pos < len(events) and events[pos][0] == time:
            _, action, ident = events[pos]
            if action: active.add(ident)
            else: active.discard(ident)
            pos += 1
        ranked = sorted(active, key=lambda i: (-_priority(source[i], i in chosen), i))
        bass = None
        if spk4:
            for i in ranked:
                n = source[i]
                if n.part != 'bass' or not BASS_MIN <= n.pitch <= BASS_MAX:
                    continue
                distinct = {_psg_pitch(source[k]) for k in ranked if k != i and source[k].part != 'drums'}
                if len(distinct) >= 3:
                    bass = i
                    break
        selected = set()
        pitches = set()
        if bass is not None:
            selected.add(bass)  # PIT2; leave three separate notes for PSG
        for i in ranked:
            if len(selected) >= (4 if bass is not None else 3):
                break
            if i == bass:
                continue
            pitch = _psg_pitch(source[i])
            if pitch in pitches:
                continue
            selected.add(i)
            pitches.add(pitch)
        for i in chosen - selected:
            if time - opened[i] >= 0.012:
                result.append(replace(source[i], start=opened[i], end=time))
            opened.pop(i, None)
        for i in selected - chosen:
            opened[i] = time
        chosen = selected
    # Last timeline event closes all outstanding notes (normally none).
    for i in chosen:
        if events and events[-1][0] - opened[i] >= 0.012:
            result.append(replace(source[i], start=opened[i], end=events[-1][0]))
    return sorted(result + drums, key=lambda n: (n.start, n.part, n.pitch))


def reduce_drums(notes: Iterable[Note], preset: str = 'balanced') -> list[Note]:
    gap = PRESETS[preset]['drum_gap']
    drums = sorted((n for n in notes if n.part == 'drums'), key=lambda n: (n.start, {36: 0, 38: 1, 42: 2}.get(n.pitch, 3)))
    result = []
    for n in drums:
        if result and n.start - result[-1].start < gap:
            # Drums only have one PSG noise oscillator: prefer kick/snare.
            if {36: 3, 38: 2, 42: 1}.get(n.pitch, 0) > {36: 3, 38: 2, 42: 1}.get(result[-1].pitch, 0):
                result[-1] = n
        else:
            result.append(n)
    return result


def prepare(notes: Iterable[Note], preset: str = 'balanced', spk4: bool = True) -> list[Note]:
    normalized = normalize(notes, preset)
    arranged = select_voices(normalized, spk4)
    return sorted([n for n in arranged if n.part != 'drums'] + reduce_drums(arranged, preset), key=lambda n: (n.start, n.end, n.pitch))


def make_midi(notes: Iterable[Note], offset: float, until: float) -> bytes:
    """Render one fixed-tempo type-0 MIDI: small, simple parser budget for DOS."""
    events = []
    programs = {'melody': 80, 'bass': 33, 'harmony': 48}
    for part, prog in programs.items():
        events.append((0, 0, mido.Message('program_change', channel=PART_CHANNEL[part], program=prog, time=0)))
    for n in notes:
        if n.start >= until or n.end <= offset:
            continue
        start = max(offset, n.start)
        end = min(until, n.end)
        if end - start < 0.012: continue
        channel = PART_CHANNEL[n.part]
        a = max(0, round((start - offset) * TICKS_PER_SECOND))
        b = max(a + 1, round((end - offset) * TICKS_PER_SECOND))
        events.append((a, 2, mido.Message('note_on', channel=channel, note=n.pitch, velocity=n.velocity, time=0)))
        events.append((b, 1, mido.Message('note_off', channel=channel, note=n.pitch, velocity=0, time=0)))
    events.sort(key=lambda e: (e[0], e[1]))
    track = mido.MidiTrack([mido.MetaMessage('set_tempo', tempo=TEMPO, time=0)])
    prev = 0
    for at, _order, msg in events:
        track.append(msg.copy(time=at - prev))
        prev = at
    track.append(mido.MetaMessage('end_of_track', time=0))
    song = mido.MidiFile(type=0, ticks_per_beat=PPQN)
    song.tracks.append(track)
    from io import BytesIO
    buff = BytesIO()
    song.save(file=buff)
    return buff.getvalue()


def export(notes: Iterable[Note], destination: Path, max_bytes: int = 42000,
           max_seconds: float = 180.0) -> list[Path]:
    """Split automatically at note boundaries and enforce DOS 8.3 filenames."""
    if max_bytes < 256 or max_bytes >= MAX_FILE:
        raise ValueError('max_bytes must be 256..45055')
    if max_seconds <= 0:
        raise ValueError('max_seconds must be positive')
    notes = list(notes)
    if not notes:
        raise ValueError('No playable notes found; try a simpler song or different transcription')
    length = max(n.end for n in notes)
    if length <= 0:
        raise ValueError('Invalid song length')
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r'[^A-Z0-9]', '', dest.name.upper())[:6] or 'TANDY'
    chunks: list[bytes] = []
    start = 0.0
    while start < length - 0.0001:
        end = min(length, start + max_seconds)
        data = make_midi(notes, start, end)
        while len(data) > max_bytes:
            # Binary search end for the longest section that fits. Never
            # create a broken or over-limit MIDI and silently discard notes.
            lo, hi = start, end
            for _ in range(26):
                midpoint = (lo + hi) / 2
                trial = make_midi(notes, start, midpoint)
                if len(trial) <= max_bytes:
                    lo = midpoint
                else:
                    hi = midpoint
            end = lo
            if end - start < 0.25:
                raise ValueError('MIDI event density exceeds selected size limit')
            data = make_midi(notes, start, end)
        chunks.append(data)
        if len(chunks) > 64:
            raise ValueError('More than 64 chunks required; shorten input or raise max_bytes')
        start = end
    paths = []
    for idx, data in enumerate(chunks, 1):
        path = dest / f'{stem}{idx:02d}.MID'
        if path.exists():
            raise FileExistsError(f'Refusing to overwrite existing file: {path}')
        paths.append(path)
    for path, data in zip(paths, chunks):
        path.write_bytes(data)
        # Parse again so export errors are caught on the laptop.
        m = mido.MidiFile(str(path))
        if m.type != 0 or len(m.tracks) != 1 or path.stat().st_size >= MAX_FILE:
            raise RuntimeError(f'Output did not pass TandyAMP limits: {path}')
    return paths
