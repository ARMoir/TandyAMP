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
    """Experimental spectral-centroid kick/snare/hat approximation (not a drum transcription model)."""
    try:
        import librosa
        import numpy as np
    except ImportError:
        return []
    samples, sr = librosa.load(str(path), sr=22050, mono=True)
    if not len(samples):
        return []
    hop = 256
    onset_env = librosa.onset.onset_strength(y=samples, sr=sr, hop_length=hop)
    frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, hop_length=hop, backtrack=False)
    result = []
    for frame in frames:
        t = float(librosa.frames_to_time(frame, sr=sr, hop_length=hop))
        i = int(t * sr)
        window = samples[i:min(i + int(.08 * sr), len(samples))]
        if len(window) < 256: continue
        spectrum = np.abs(np.fft.rfft(window))
        freqs = np.fft.rfftfreq(len(window), 1.0 / sr)
        centroid = float((spectrum * freqs).sum() / max(float(spectrum.sum()), 1e-8))
        pitch = 36 if centroid < 900 else 42 if centroid > 3400 else 38
        velocity = 104 if pitch == 36 else 87
        result.append(Note(t, t + .09, pitch, velocity, 'drums', 0))
    return result


def transcribe_audio(path: Path, stems: bool = False) -> list[Note]:
    """Direct transcription is fast to set up; optional Demucs stems improve source separation."""
    if not stems:
        return _predict(path, None)
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
            notes.extend(_predict(wav, part))
        drums = root / 'drums.wav'
        if drums.exists():
            print('Estimating drum onsets...', flush=True)
            notes.extend(_drum_onsets(drums))
        return notes
