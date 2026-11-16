"""Lightweight *approximation* of a TandyAMP PSG + PIT2 mix.

No hardware ports are used. Quantizes PSG pitch to SN76489 10-bit periods,
models three pitched voices, one gated noise voice, envelopes, and the
separate 1-bit PC speaker. It is NOT cycle-accurate hardware emulation.
"""
from __future__ import annotations

from pathlib import Path
import math
import random
import struct
import wave

from arranger import BASS_MIN, BASS_MAX, Note

PSG_CLOCK = 3579545.0 / 32.0
PIT_CLOCK = 1193182.0
RATE = 11025


def _freq(note: int, speaker: bool = False) -> float:
    # TandyAMP raises low notes for the 10-bit PSG, but not for PIT2.
    while note < 45 and not speaker:
        note += 12
    ideal = 440.0 * 2.0 ** ((note - 69) / 12.0)
    clock = PIT_CLOCK if speaker else PSG_CLOCK
    div = min(65535 if speaker else 1023, max(1, round(clock / ideal)))
    return clock / div


def assign_preview_voices(active: list[Note], spk4: str = 'bass') -> tuple[list[Note], Note | None, Note | None]:
    """Match the Tandy constraints without pretending preview == DOS engine."""
    if spk4 not in ('off', 'bass', 'adapt'):
        raise ValueError('Unknown SPK4 mode')
    pitched = [n for n in active if n.part != 'drums']
    drums = [n for n in active if n.part == 'drums']
    order = {'melody': 0, 'bass': 1, 'harmony': 2}
    pitched.sort(key=lambda n: (order.get(n.part, 3), -n.velocity, n.start))
    bass = None
    if spk4 != 'off':
        required = 2 if spk4 == 'adapt' else 3
        for n in pitched:
            if (n.part != 'bass' or not BASS_MIN <= n.pitch <= BASS_MAX
                    or n.velocity < 65):
                continue
            others = {_freq(k.pitch) for k in pitched if k is not n and k.pitch != n.pitch}
            if len(others) >= required:
                bass = n
                break
    tones = []
    played = set()
    for n in pitched:
        if n is bass:
            continue
        pitch = _freq(n.pitch)
        if pitch in played:
            continue
        played.add(pitch)
        tones.append(n)
        if len(tones) == 3:
            break
    drum = max(drums, key=lambda n: (n.velocity, -n.start), default=None)
    return tones, bass, drum


def preview_wav(notes: list[Note], output: Path, seconds: float = 30.0,
                spk4: str = 'bass') -> Path:
    if not notes:
        raise ValueError('Cannot preview an empty arrangement')
    seconds = min(seconds, max(n.end for n in notes))
    if seconds <= 0:
        raise ValueError('Invalid preview length')
    count = int(seconds * RATE)
    events: list[tuple[int, int, int]] = []
    for idx, n in enumerate(notes):
        if n.start >= seconds or n.end <= n.start:
            continue
        # process note-off before note-on at the same sample
        events.extend(((max(0, int(n.start * RATE)), 1, idx),
                       (min(count, int(n.end * RATE)), 0, idx)))
    events.sort()
    active: set[int] = set()
    tones: list[Note] = []
    speaker: Note | None = None
    drum: Note | None = None
    pos = 0
    rng = random.Random(1234)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        buffer = bytearray()
        for tick in range(count):
            updated = False
            while pos < len(events) and events[pos][0] <= tick:
                _, on, idx = events[pos]
                (active.add if on else active.discard)(idx)
                pos += 1
                updated = True
            if updated:
                tones, speaker, drum = assign_preview_voices(
                    [notes[i] for i in sorted(active)], spk4)
            t = tick / RATE
            mix = 0.0
            for n in tones:
                age = max(0.0, t - n.start)
                # A few milliseconds of attack/release avoid hard clicks.
                attack = min(1.0, age/.009)
                release = min(1.0, max(0.0, n.end-t)/.012)
                # Harsh treble softening; long plucks decay gently.
                fade = math.exp(-age/1.3) if n.part == 'harmony' else 1.0
                amp = .145 * (n.velocity/127.0) * attack * release * fade
                f = _freq(n.pitch)
                if f > 1500:
                    amp *= .75
                mix += amp * (1.0 if (t*f)%1.0 < .5 else -1.0)
            if speaker is not None:
                n = speaker
                age = max(0.0, t-n.start)
                gate = min(1.0, age/.012, max(0.0, n.end-t)/.012)
                raised = (spk4 == 'adapt' and n.pitch < 44 and n.pitch <= 35)
                f = _freq(n.pitch + (12 if raised else 0), speaker=True)
                # Actual PIT2 is one-bit and has no volume register.
                mix += .105 * gate * (1.0 if (t*f)%1.0 < .5 else -1.0)
            if drum is not None:
                age = max(0.0, t-drum.start)
                decay = {36: .048, 38: .032, 42: .014}.get(drum.pitch, .027)
                level = .21 * (drum.velocity/127.0) * math.exp(-age/decay)
                noise = rng.uniform(-1.0, 1.0)
                if drum.pitch == 36:
                    noise = .55*noise + .45*math.sin(2*math.pi*75*t)
                mix += level*noise
            # Fixed headroom rather than a hard digital clip on every chord.
            mix = max(-.94, min(.94, mix))
            buffer.extend(struct.pack('<h', int(mix*32767)))
            if len(buffer) >= 16384:
                wav.writeframesraw(buffer)
                buffer.clear()
        if buffer:
            wav.writeframesraw(buffer)
    return output
