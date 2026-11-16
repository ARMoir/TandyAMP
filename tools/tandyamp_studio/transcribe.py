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


def _drum_onsets(path: Path) -> list[Note]:
    """Conservative beat-aware kick/snare/hat detection on Demucs' DRUM stem.

    Band energy and onset strength are more useful than centroid alone:
    ambiguous events are not automatically assigned to the snare.
    """
    try:
        import librosa
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            'Drum onset analysis requires librosa and numpy. '
            'Run: py -3.11 -m pip install -r requirements-audio.txt'
        ) from exc
    from postprocess import classify_drum_bands, refine_drum_hits

    samples, sr = librosa.load(str(path), sr=22050, mono=True)
    if len(samples) < 512:
        return []
    hop = 256
    envelope = librosa.onset.onset_strength(y=samples, sr=sr, hop_length=hop)
    frames = librosa.onset.onset_detect(
        onset_envelope=envelope, sr=sr, hop_length=hop, backtrack=False
    )
    if not len(frames):
        return []

    candidates = []
    positive = envelope[envelope > 0]
    typical_strength = float(np.median(positive)) if len(positive) else 1.0
    for frame in frames:
        at = float(librosa.frames_to_time(frame, sr=sr, hop_length=hop))
        i = int(at * sr)
        lo = max(0, i-int(.010*sr))
        hi = min(len(samples), i+int(.080*sr))
        window = samples[lo:hi]
        if len(window) < 512:
            continue
        window = window * np.hanning(len(window))
        power = np.abs(np.fft.rfft(window)) ** 2
        freq = np.fft.rfftfreq(len(window), 1.0/sr)
        low = float(power[(freq >= 40) & (freq < 250)].sum())
        mid = float(power[(freq >= 350) & (freq < 3800)].sum())
        high = float(power[(freq >= 4700) & (freq < 10000)].sum())
        category = classify_drum_bands(low, mid, high)
        if category is None:
            continue
        strength = float(envelope[min(int(frame), len(envelope)-1)])
        velocity = int(max(48, min(118, 65 + 22 * strength /
                                   max(.01, typical_strength))))
        candidates.append(Note(at, at+.08, category, velocity, 'drums', 0))

    beats = []
    try:
        _tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=envelope, sr=sr, hop_length=hop, trim=False
        )
        beats = list(librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop))
    except (ValueError, TypeError, RuntimeError):
        # Beat estimation is best-effort; onset classification still works.
        pass
    result = refine_drum_hits(candidates, beats)
    print(f'Drum onsets: {len(frames)} detected, {len(candidates)} '
          f'classified, {len(result)} retained for PSG noise', flush=True)
    return result


def transcribe_audio(path: Path, stems: bool = False) -> list[Note]:
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
            notes.extend(_drum_onsets(drums))
        return notes
