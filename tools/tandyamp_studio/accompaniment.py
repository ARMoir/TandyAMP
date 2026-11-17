"""Optional chord-guided PSG accompaniment for TandyAMP Studio.

Generated notes are explicitly marked with part='accomp' / MIDI channel 3.
'Recover' requires a sustained spectral chord AND a strong spectral peak for
each inferred tone. 'Harmonize' may also use chord-template tones not
independently prominent; it is an artistic reconstruction, not transcription.

All CPU-intensive audio processing runs on the user's modern computer.
No Demucs/Basic Pitch or librosa imports are needed for MIDI-only operation.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Iterable

from arranger import Note


@dataclass(frozen=True)
class Chord:
    root: int
    quality: str  # power, major, minor
    confidence: float

    @property
    def pitch_classes(self) -> tuple[int, ...]:
        intervals = {'power': (0, 7), 'major': (0, 4, 7),
                     'minor': (0, 3, 7)}[self.quality]
        return tuple((self.root + interval) % 12 for interval in intervals)


@dataclass(frozen=True)
class ChordSpan:
    start: float
    end: float
    chord: Chord


def infer_chord(chroma: Iterable[float], bass_pc: int | None = None
                ) -> Chord | None:
    """Conservative template inference on 12-bin relative pitch energy.

    Strong root and fifth are required; unsupported major/minor thirds are
    *not* forced. Bass is a soft hint, not proof of a chord's root.
    """
    values = [max(0.0, float(x)) for x in chroma]
    if len(values) != 12:
        raise ValueError('Chroma must have 12 pitch classes')
    maximum = max(values)
    if maximum <= 1e-8:
        return None
    v = [x / maximum for x in values]
    contrast = max(v) - min(v)
    if contrast < .28:
        return None

    candidates: list[tuple[float, Chord]] = []
    for root in range(12):
        one = v[root]
        fifth = v[(root + 7) % 12]
        major = v[(root + 4) % 12]
        minor = v[(root + 3) % 12]
        if one < .47 or fifth < .32:
            continue
        if major >= .48 and major >= minor * 1.18:
            quality = 'major'
            third = major
        elif minor >= .48 and minor >= major * 1.18:
            quality = 'minor'
            third = minor
        else:
            quality = 'power'
            third = 0.0
        chord = Chord(root, quality, round((one + fifth + third) /
                                           (3 if third else 2), 3))
        # Bass pitch supports, but never overrides, a weak spectral chord.
        score = one + .78 * fifth + .30 * third
        if bass_pc is not None and root == (bass_pc % 12):
            score += .22
        candidates.append((score, chord))

    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[0], x[1].root, x[1].quality))
    top_score, top = candidates[0]
    # Ambiguous templates should not be used to manufacture chord tones.
    if len(candidates) > 1:
        other_score = max(score for score, chord in candidates[1:]
                          if chord.root != top.root) if any(
                              chord.root != top.root for _, chord in candidates[1:]
                          ) else -999
        if top_score - other_score < .09:
            return None
    return top


def stable_chord_spans(frames: list[tuple[float, Chord | None]],
                       hop: float, mode: str = 'recover'
                       ) -> list[ChordSpan]:
    """Only extend the harmony through *consecutive observed* chord frames."""
    if mode not in ('off', 'recover', 'harmonize'):
        raise ValueError('Accompaniment mode must be off, recover or harmonize')
    if not frames or mode == 'off':
        return []
    minimum = .55 if mode == 'recover' else .40
    spans: list[ChordSpan] = []
    first = frames[0][0]
    current = frames[0][1]
    previous = first
    for at, chord in frames[1:] + [(frames[-1][0] + hop, None)]:
        contiguous = at - previous <= 1.6 * hop
        same = (current is not None and chord is not None and
                current.root == chord.root and current.quality == chord.quality)
        if not contiguous or not same:
            if current is not None:
                end = previous + hop
                if end - first >= minimum:
                    spans.append(ChordSpan(first, end, current))
            first = at
            current = chord
        previous = at
    return spans


def _bass_root(notes: list[Note], at: float) -> int | None:
    active = [n for n in notes if n.part == 'bass' and
              n.start <= at < n.end]
    if not active:
        return None
    bass = max(active, key=lambda n: n.velocity)
    return bass.pitch % 12


def chord_spans_from_chroma(chroma: list[tuple[float, list[float]]],
                            notes: list[Note],
                            hop: float = .30, mode: str = 'recover'
                            ) -> list[ChordSpan]:
    frames = [
        (at, infer_chord(energy, _bass_root(notes, at + hop * .5)))
        for at, energy in chroma
    ]
    return stable_chord_spans(frames, hop=hop, mode=mode)


def _choose_pitch(pc: int, existing: set[int],
                  center: float = 60.0) -> int | None:
    choices = [n for n in range(49, 74) if n % 12 == pc and n not in existing]
    return min(choices, key=lambda n: (abs(n-center), n)) if choices else None


def build_accompaniment(spans: list[ChordSpan], source: list[Note],
                        mode: str = 'recover',
                        observed: dict[tuple[float, int], float] | None = None
                        ) -> list[Note]:
    """Build *distinct, provenance-marked* support notes for sparse chords.

    Only adds a tone when there is a sustained inferred chord and an unused
    real PSG channel opportunity. Bass and melody aren't shifted or replaced.
    'observed' is per-chord spectral pitch-class strength (0..1) keyed by
    (span-start, pitch-class). Recover never inserts a weakly observed tone.
    Harmonize can infer a quieter third/fifth with an explicit provenance.
    """
    if mode not in ('off', 'recover', 'harmonize'):
        raise ValueError('Accompaniment mode must be off, recover or harmonize')
    if mode == 'off':
        return []
    observed = observed or {}
    added: list[Note] = []
    for span in spans:
        start, end = span.start, span.end
        if end - start < (.55 if mode == 'recover' else .40):
            continue
        if span.chord.confidence < (.62 if mode == 'recover' else .54):
            continue
        # Count notes that are audible at the center of this chord,
        # plus true sustained tones. Don't count four *sequential* guitar
        # riff notes as a simultaneous four-note chord.
        middle = .5 * (start+end)
        existing = [
            n for n in source if n.part not in ('drums', 'accomp')
            and ((n.start <= middle < n.end) or
                 max(0.0, min(n.end,end)-max(n.start,start)) >=
                    .65 * (end-start))
        ]
        sounding = {n.pitch for n in existing if n.part != 'bass'}
        classes = {p % 12 for p in sounding}
        # A low PIT2 bass root and a higher PSG chord root are genuinely
        # distinct octave voices, so intentional octave support is allowed.

        # One PSG lead and two PSG harmony parts are enough with optional
        # PIT2 bass. Don't create chord padding when already complete.
        wanted = max(0, min(2, 3 - len(sounding)))
        if wanted == 0:
            continue
        # Put the fifth first for power chords; thirds are less reliable
        # in distorted recordings, and are never invented in recover mode.
        root = span.chord.root
        ordered = ((root+7) % 12, (root+4 if span.chord.quality == 'major'
                    else root+3) % 12, root)
        if span.chord.quality == 'power':
            ordered = ((root+7) % 12, root)
        used = set(sounding)
        for pc in ordered:
            if wanted <= 0:
                break
            if pc in classes:
                continue
            strength = observed.get((start, pc), 0.0)
            if mode == 'recover' and strength < .52:
                continue
            if mode == 'harmonize' and strength < .18 and pc != root:
                # In artistic mode the quality-inferred third may be weak
                # but don't invent a silent band out of nothing.
                continue
            pitch = _choose_pitch(pc, used)
            if pitch is None:
                continue
            strength = max(0.0, min(1.0, strength))
            velocity = max(39, min(70, round(43 + 26 * strength)))
            if mode == 'harmonize':
                velocity = max(38, velocity - 7)
            # Slight release gap between independently detected chords,
            # not fake strumming or synthetic repeated attacks.
            tone_start = start + .015
            tone_end = end - .025
            if tone_end - tone_start < .30:
                continue
            added.append(Note(tone_start, tone_end, pitch, velocity,
                              'accomp', 48))
            used.add(pitch)
            classes.add(pc)
            wanted -= 1
    return sorted(added, key=lambda n: (n.start, n.pitch))


def analyze_accompaniment_audio(path: Path, existing: list[Note],
                                mode: str = 'recover') -> list[Note]:
    """Analyze *separated* harmonic audio with librosa on the laptop only.

    No accompaniment is added without stable spectral evidence. This is not
    guaranteed chord recognition; validate by ear, especially on distorted
    electric guitars. Source WAV is never modified.
    """
    if mode == 'off':
        return []
    try:
        import librosa
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            'Accompaniment analysis needs librosa and numpy; install '
            'requirements-audio.txt') from exc
    sr = 11025
    samples, _ = librosa.load(str(path), sr=sr, mono=True)
    if samples.size < sr // 2:
        return []
    hop = 512
    # Harmonic separation reduces sharp pick attacks leaking into chroma.
    harmonic = librosa.effects.harmonic(samples, margin=2.0)
    chroma = librosa.feature.chroma_stft(
        y=harmonic, sr=sr, n_fft=4096, hop_length=hop, tuning=0.0
    )
    rms = librosa.feature.rms(y=harmonic, frame_length=4096,
                             hop_length=hop)[0]
    window_frames = max(1, round(.30 * sr / hop))
    max_rms = float(np.percentile(rms, 90))
    if max_rms < 1e-6:
        return []
    # Avoid treating near silence as a power chord.
    threshold = max_rms * .075
    profiles: list[tuple[float, list[float]]] = []
    profiles_by_start: dict[float, list[float]] = {}
    for a in range(0, chroma.shape[1], window_frames):
        b = min(a + window_frames, chroma.shape[1])
        at = a * hop / sr
        if float(np.median(rms[a:b])) < threshold:
            profile = [0.0] * 12
        else:
            profile = [float(v) for v in
                       np.median(chroma[:, a:b], axis=1)]
        if max(profile) > 0:
            peak = max(profile)
            profile = [v/peak for v in profile]
        profiles.append((at, profile))
        profiles_by_start[at] = profile

    step = window_frames * hop / sr
    spans = chord_spans_from_chroma(profiles, existing, hop=step, mode=mode)
    observed: dict[tuple[float, int], float] = {}
    for span in spans:
        matching = [profile for at, profile in profiles
                    if span.start <= at < span.end]
        if matching:
            for pc in range(12):
                observed[span.start, pc] = median(p[pc] for p in matching)
    result = build_accompaniment(spans, existing, mode=mode, observed=observed)
    print('Chord-guided {} accompaniment: {} stable spectral regions, '
          '{} explicitly inferred MIDI notes (channel 4)'.format(
              mode, len(spans), len(result)), flush=True)
    return result
