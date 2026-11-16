"""Optional laptop-only MP3/WAV transcription; never imported for MIDI-only use."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile

from arranger import Note


def _predict(path: Path, part: str | None) -> list[Note]:
    try:
        from basic_pitch import ICASSP_2022_MODEL_PATH
        from basic_pitch.inference import predict
    except ModuleNotFoundError as exc:
        # An ImportError *inside* installed Basic Pitch is not proof that Basic
        # Pitch is missing. Preserve the real missing module for diagnostics.
        if exc.name == 'basic_pitch':
            raise RuntimeError(
                'Basic Pitch is not installed. Run: '
                'py -3.11 -m pip install -r requirements-audio.txt'
            ) from exc
        if exc.name == 'pkg_resources':
            raise RuntimeError(
                'Basic Pitch dependency resampy cannot import pkg_resources. '
                'setuptools 82+ removed it. Run: '
                'py -3.11 -m pip install "setuptools>=70,<82"'
            ) from exc
        raise RuntimeError(
            'Basic Pitch could not load dependency {!r}: {}. '
            'See the Python traceback in the console.'.format(
                exc.name, exc
            )
        ) from exc
    except ImportError as exc:
        raise RuntimeError(
            'Basic Pitch initialization failed ({}): {}. '
            'See the Python traceback in the console.'.format(
                type(exc).__name__, exc
            )
        ) from exc
    # The public Basic Pitch predict() API requires the installed model path.
    _, midi, _ = predict(str(path), ICASSP_2022_MODEL_PATH)
    notes = []
    for instrument in midi.instruments:
        for n in instrument.notes:
            role = part or ('bass' if n.pitch <= 54 else 'melody' if n.pitch >= 68 else 'harmony')
            notes.append(Note(float(n.start), float(n.end), int(n.pitch), int(n.velocity), role,
                              33 if role == 'bass' else 80 if role == 'melody' else 48))
    return notes


def _drum_onsets(path: Path, style: str = 'auto') -> list[Note]:
    """Recover three rock drum classes without manufacturing rhythmic notes.

    Two onset detectors run on the *separated drum stem*:
    (1) full-spectrum onsets for kick/snare and
    (2) >6 kHz spectral novelty for hats/cymbals that a kick-led detector
        regularly misses. The Tandy's single noise oscillator is respected
        when deconflicting candidates.
    """
    if style not in ('auto', 'rock'):
        raise ValueError('Drum style must be auto or rock')
    try:
        import librosa
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            'Drum onset analysis requires librosa and numpy. '
            'Run: py -3.11 -m pip install -r requirements-audio.txt'
        ) from exc
    from bisect import bisect_left
    from collections import Counter
    from postprocess import (classify_drum_transient, drum_velocity,
                             normalize_drum_fluxes, recover_high_hats,
                             refine_drum_hits)

    samples, sr = librosa.load(str(path), sr=22050, mono=True)
    if len(samples) < 2048:
        return []
    hop = 256
    envelope = librosa.onset.onset_strength(y=samples, sr=sr, hop_length=hop)
    frames = librosa.onset.onset_detect(
        onset_envelope=envelope, sr=sr, hop_length=hop, backtrack=False
    )
    if not len(frames):
        return []

    strengths = np.asarray([envelope[min(int(i), len(envelope)-1)]
                            for i in frames], dtype=float)
    quiet, loud = np.percentile(strengths, [18, 90])

    beats = []
    try:
        _tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=envelope, sr=sr, hop_length=hop, trim=False
        )
        beats = list(librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop))
    except (ValueError, TypeError, RuntimeError):
        pass

    fft_size = 1024
    taper = np.hanning(fft_size)
    freqs = np.fft.rfftfreq(fft_size, 1.0/sr)
    bands = (
        (freqs >= 40) & (freqs < 270),
        (freqs >= 300) & (freqs < 4200),
        (freqs >= 4500) & (freqs < 10400),
    )

    def attack_at(frame: int):
        at = float(librosa.frames_to_time(frame, sr=sr, hop_length=hop))
        center = int(at*sr)
        before_end = center-int(.012*sr)
        before_start = before_end-fft_size
        after_start = center+int(.003*sr)
        if before_start < 0 or after_start+fft_size > len(samples):
            return None
        before = np.abs(np.fft.rfft(samples[before_start:before_end]*taper))
        after = np.abs(np.fft.rfft(samples[after_start:after_start+fft_size]*taper))
        novel = np.maximum(after-.88*before, 0)**2
        low, mid, high = [float(novel[mask].sum()) for mask in bands]
        return (at, low, mid, high)

    raw = []
    for idx, frame in enumerate(frames):
        attack = attack_at(int(frame))
        if attack is None:
            continue
        at, low, mid, high = attack
        backbeat_hint = False
        if len(beats) >= 4:
            j = bisect_left(beats, at)
            near = [k for k in (j-1, j) if 0 <= k < len(beats)]
            if near:
                closest = min(near, key=lambda k: abs(at-beats[k]))
                backbeat_hint = (abs(at-beats[closest]) <= .065 and
                                 closest % 2 == 1)
        raw.append((at, low, mid, high, backbeat_hint,
                    float(strengths[idx])))

    # Independent high-frequency onset envelope: don't infer hats merely
    # from the scarcity of MIDI note 42 in the classification results.
    spectrum = np.abs(librosa.stft(samples, n_fft=fft_size,
                                   hop_length=hop)).astype('float32')
    high_mask = (freqs >= 6000) & (freqs < 10400)
    high_envelope = np.zeros(spectrum.shape[1], dtype='float32')
    if high_mask.any() and spectrum.shape[1] > 1:
        high_envelope[1:] = np.maximum(
            np.diff(spectrum[high_mask, :], axis=1), 0
        ).sum(axis=0)
    del spectrum

    high_raw = []
    if high_envelope.max() > 0:
        high_frames = librosa.onset.onset_detect(
            onset_envelope=high_envelope, sr=sr, hop_length=hop,
            backtrack=False, wait=8, pre_max=3, post_max=3,
            pre_avg=8, post_avg=8, delta=.035
        )
        positive = high_envelope[high_envelope > 0]
        floor = max(float(np.percentile(positive, 52)),
                    float(high_envelope.max())*.035)
        for frame in high_frames:
            frame = int(frame)
            strength = float(high_envelope[min(frame, len(high_envelope)-1)])
            if strength < floor:
                continue
            attack = attack_at(frame)
            if attack is not None:
                high_raw.append((attack, strength))

    # Calibrate *all* attack spectra on the recording itself, not against
    # a hardcoded power level from some other song.
    all_bands = [(x[1], x[2], x[3]) for x in raw]
    all_bands.extend((x[0][1], x[0][2], x[0][3]) for x in high_raw)
    calibrated = normalize_drum_fluxes(all_bands)

    candidates = []
    for (at, _l, _m, _h, hint, strength), xyz in zip(raw, calibrated):
        category = classify_drum_transient(*xyz, backbeat_hint=hint)
        if category is not None:
            velocity = drum_velocity(strength, float(quiet), float(loud))
            candidates.append(Note(at, at+.07, category, velocity,
                                   'drums', 0))
    high_offset = len(raw)
    recovered = recover_high_hats(
        [(item[0][0], item[1], *xyz)
         for item, xyz in zip(high_raw, calibrated[high_offset:])],
        candidates, style=style
    )
    combined = candidates + recovered
    result = refine_drum_hits(combined, beats, style=style)
    before = dict(Counter(n.pitch for n in combined))
    after = dict(Counter(n.pitch for n in result))
    print('Drum analysis: {} broad onsets, {} independent high-band attacks, '
          '{} recovered hats; {} classified {}, {} retained {} '
          '(36=kick, 38=snare, 42=hat)'.format(
              len(frames), len(high_raw), len(recovered), len(combined),
              before, len(result), after), flush=True)
    return result


def transcribe_audio(path: Path, stems: bool = False,
                     drum_style: str = 'auto') -> list[Note]:
    """Transcribe and clean notes on the laptop; MIDI imports are unaffected."""
    from postprocess import clean_stem_notes

    if not stems:
        notes = _predict(path, None)
        cleaned = []
        for part in ('bass', 'melody', 'harmony'):
            group = [n for n in notes if n.part == part]
            cleaned.extend(clean_stem_notes(group, part))
        print(f'Cleaned direct transcription: {len(notes)} -> '
              f'{len(cleaned)} pitched events', flush=True)
        return cleaned
    try:
        import demucs  # noqa: F401; check before launching subprocess
    except ImportError as exc:
        raise RuntimeError('Stem separation needs Demucs. See requirements-audio.txt') from exc
    with tempfile.TemporaryDirectory(prefix='tandyamp-stems-') as temp:
        output = Path(temp)
        print('Separating bass, vocals, other and drums with Demucs (may take a while)...', flush=True)
        cmd = [sys.executable, '-m', 'demucs', '-n', 'htdemucs', '-o', str(output), str(path)]
        subprocess.run(cmd, check=True)
        root = output / 'htdemucs' / path.stem
        notes: list[Note] = []
        for name, part in [('bass', 'bass'), ('vocals', 'melody'), ('other', 'harmony')]:
            wav = root / (name + '.wav')
            if not wav.exists():
                raise RuntimeError(f'Demucs did not produce {wav}')
            print(f'Transcribing {name}...', flush=True)
            raw = _predict(wav, part)
            kept = clean_stem_notes(raw, part)
            print(f'  {name}: {len(raw)} -> {len(kept)} notes after cleanup', flush=True)
            notes.extend(kept)
        drums = root / 'drums.wav'
        if drums.exists():
            print('Estimating beat-aware kick/snare/hat onsets...', flush=True)
            notes.extend(_drum_onsets(drums, style=drum_style))
        return notes
