"""Independent pitch evidence from a separated stem, before PSG voicing."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from arranger import Note

if TYPE_CHECKING:
    from numpy import ndarray

FRAME_SECONDS = 256 / 11025
HARMONIC_WEIGHTS = (1., .72, .32, .18, .12, .08)
RANGES = {
    'bass': (28, 66),
    'guitar': (45, 85),
    'melody': (44, 92),
    'harmony': (45, 90),
}


@dataclass(frozen=True)
class StemPitch:
    first: int
    strength: ndarray
    cents: float

    def retune(self, note: Note) -> Note:
        """Use the sustained part of an attack to reject scoops and blips."""
        import numpy as np
        from dataclasses import replace

        duration = note.end - note.start
        start = round((note.start + min(.055, duration * .20)) / FRAME_SECONDS)
        end = max(start + 2, round((note.end - duration * .18) / FRAME_SECONDS))
        frames = self.strength[max(0, start):end]
        old = note.pitch - self.first
        if len(frames) < 2 or not 0 <= old < frames.shape[1]:
            return note
        low, high = max(0, old - 2), min(frames.shape[1], old + 3)
        nearby = frames[:, low:high]
        candidates = nearby.mean(axis=0)
        pick = int(candidates.argmax()) + low
        # Require the new pitch in several frames. A decoder's short
        # consonant or guitar overtone can be stronger in a single frame.
        wins = np.count_nonzero(nearby.argmax(axis=1) == pick - low)
        if (pick != old and wins >= .55 * len(frames) and candidates[pick - low] > 0
                and candidates[pick - low] >= 1.21 * candidates[old - low]
                and candidates[pick - low] >= .32 * frames.mean(axis=0).max()):
            return replace(note, pitch=self.first + pick)
        return note

    def guitar_voices(self) -> tuple[list[Note], list[Note]]:
        """Read an upper riff and a real ringing lower tone independently."""
        import numpy as np
        from scipy.ndimage import median_filter

        signal = self.strength
        if not signal.size or not signal.max():
            return [], []
        notes = np.arange(self.first, self.first + signal.shape[1])
        peak = signal.max(axis=1)
        audible = peak > np.percentile(peak[peak > 0], 80) * .05
        lead = signal.copy()
        # A relatively strong upper fundamental can carry the riff over a
        # ringing chord root. Low notes still lead when played by themselves.
        lead[:, (notes >= 55) & (notes <= 76)] *= 1.57
        lead[:, notes > 77] *= .72
        lead_path = median_filter(lead.argmax(axis=1), size=3, mode='nearest')
        lead_indices = np.arange(len(signal))
        lead_path[~audible | (signal[lead_indices, lead_path] < .34 * peak)] = -1
        upper = self._segments(lead_path, peak, signal, 'guitar')

        # Only use a low note with audible energy of its own and a separate
        # guitar note above it. Remove adjacent bins and exact octave copies.
        distance = lead_path[:, None] + self.first - notes
        low = (notes <= 56) & (distance >= 4) & (distance <= 19) & (distance != 12)
        support = np.where(low, signal, 0.)
        pedal_path = median_filter(support.argmax(axis=1), size=3, mode='nearest')
        pedal_path[~audible | (support[lead_indices, pedal_path] < .34 * peak)] = -1
        lower = self._segments(pedal_path, peak, support, 'harmony')
        return upper, lower

    def _segments(self, path: ndarray, peak: ndarray, signal: ndarray,
                  role: str) -> list[Note]:
        start = 0
        result = []
        minimum = .077 if role == 'guitar' else .105
        for end in range(1, len(path) + 1):
            if end != len(path) and path[start] == path[end]:
                continue
            index = int(path[start])
            begin = max(0., (start - .5) * FRAME_SECONDS)
            finish = (end - .5) * FRAME_SECONDS
            if index >= 0 and finish - begin >= minimum:
                confidence = float(signal[start:end, index].mean() /
                                   max(1.e-8, peak[start:end].mean()))
                velocity = round(54 + min(1., confidence) * 34) if role == 'guitar' else 65
                result.append(Note(begin, finish, self.first + index, velocity,
                                   role, 30 if role == 'guitar' else 48))
            start = end
        return result


def measure_stem_pitch(path: Path, role: str) -> StemPitch:
    """Track fundamentals and their harmonics at the stem's measured tuning."""
    import numpy as np
    from numpy.lib.stride_tricks import sliding_window_view
    from scipy.fft import rfft
    from scipy.signal import resample_poly
    import soundfile as sf
    from math import gcd

    x, source_rate = sf.read(path, dtype='float32', always_2d=True)
    first, last = RANGES[role]
    if not len(x):
        return StemPitch(first, np.zeros((0, last - first), dtype=np.float32), 0.)
    factor = gcd(11025, source_rate)
    x = resample_poly(x.mean(axis=1), 11025 // factor, source_rate // factor)
    width = 1536 if role == 'bass' else 960
    fft_size = 8192
    width = min(width, max(2, len(x)))
    bin_hz = 11025 / fft_size
    window = np.hanning(width).astype(np.float32)
    frames = sliding_window_view(np.pad(x, (width // 2, width // 2)), width)[::256]

    # Measure the offset in cents from stable dominant spectral peaks. A
    # weak estimate falls back to concert pitch.
    sample = frames[::max(1, len(frames) // 560)]
    f = np.abs(rfft(sample * window, n=fft_size, axis=-1))
    lower = round(75 / bin_hz)
    upper = round(1600 / bin_hz)
    positions = f[:, lower:upper].argmax(axis=1) + lower
    rows = np.arange(len(f))
    weight = f[rows, positions]
    left, center, right = (np.log(f[rows, positions + d] + 1.e-9) for d in (-1, 0, 1))
    offset = .5 * (left - right) / np.minimum(-1.e-8, left - 2 * center + right)
    peak_pitch = 69 + 12 * np.log2((positions + offset.clip(-.5, .5)) * bin_hz / 440)
    phase = np.sum(np.exp(2j * np.pi * peak_pitch) * weight)
    tuning = float(np.angle(phase) / (2 * np.pi)) if abs(phase) > .22 * weight.sum() else 0.
    # A pitch near the halfway point between semitones is ambiguous. Favor
    # the corresponding decoder pitch where the global offset is unstable.
    tuning = min(.45, max(-.45, tuning))
    locations = (440 / bin_hz) * 2 ** ((np.arange(first, last) + tuning - 69) / 12)
    strength = np.empty((len(frames), last - first), dtype=np.float32)

    def sample_bins(spectrum, position):
        position = position.clip(0, spectrum.shape[1] - 1.00001)
        i = position.astype(int)
        return spectrum[:, i] * (1 - position + i) + spectrum[:, i + 1] * (position - i)

    for start in range(0, len(frames), 192):
        section = frames[start:start + 192]
        spectrum = np.abs(rfft(section * window, n=fft_size, axis=-1))
        partials = [sample_bins(spectrum, locations * k) for k in range(1, 7)]
        salience = np.zeros_like(partials[0])
        for k, (partial, gain) in enumerate(zip(partials, HARMONIC_WEIGHTS), 1):
            nearby = (sample_bins(spectrum, locations * k * 1.026) +
                      sample_bins(spectrum, locations * k / 1.026)) * .5
            salience += np.maximum(partial - .40 * nearby, 0) * gain
        strongest = np.maximum.reduce(partials)
        salience *= np.sqrt(.12 + .88 * partials[0] / strongest.clip(.0001))
        for interval, gain in ((12, .50), (19, .35), (24, .35)):
            salience[:, interval:] -= gain * salience[:, :-interval].clip(0)
        strength[start:start + len(section)] = salience.clip(0)
    return StemPitch(first, strength, tuning * 100)
