"""Optional crude square-wave preview, deliberately NOT an SN76489 hardware emulator."""
from __future__ import annotations

from pathlib import Path
import math
import random
import struct
import wave
from arranger import Note


def preview_wav(notes: list[Note], output: Path, seconds: float = 30.0) -> Path:
    samplerate = 11025
    seconds = min(max(n.end for n in notes), seconds)
    if seconds <= 0:
        raise ValueError('No audible events to preview')
    events = []
    for i, n in enumerate(notes):
        if n.start < seconds:
            events.extend(((max(0, int(n.start * samplerate)), 1, i),
                           (min(int(seconds * samplerate), int(n.end * samplerate)), 0, i)))
    events.sort()
    active = set()
    pos = 0
    rng = random.Random(0)
    with wave.open(str(output), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(samplerate)
        buffer = bytearray()
        for t in range(int(seconds * samplerate)):
            while pos < len(events) and events[pos][0] <= t:
                _, on, ident = events[pos]
                (active.add if on else active.discard)(ident)
                pos += 1
            sample = 0.0
            for i in active:
                n = notes[i]
                amp = (n.velocity / 127) * (0.19 if n.part == 'bass' else 0.16)
                if n.part == 'drums':
                    sample += rng.uniform(-1, 1) * amp
                else:
                    freq = 440.0 * (2.0 ** ((n.pitch - 69) / 12.0))
                    sample += (1 if (t * freq / samplerate) % 1 < .5 else -1) * amp
            sample = max(-0.95, min(0.95, sample))
            buffer.extend(struct.pack('<h', round(sample * 32767)))
            if len(buffer) >= 8192:
                wav.writeframesraw(buffer)
                buffer.clear()
        if buffer:
            wav.writeframesraw(buffer)
    return output
