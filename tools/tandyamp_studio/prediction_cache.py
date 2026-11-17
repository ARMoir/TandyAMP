"""Optional Basic Pitch activation cache; never caches an arrangement decision."""
from __future__ import annotations

from importlib.metadata import version
import json
from pathlib import Path

from diagnostics import file_digest, write_json


def decoder_settings(part: str | None, profile: str) -> dict:
    if profile not in ('standard', 'sensitive'):
        raise ValueError('Transcription profile must be standard or sensitive')
    # Only separated guitar/other get the experimental decoder. Never lower
    # thresholds on a full mix or on vocals/bass just to increase density.
    if profile == 'sensitive' and part in ('guitar', 'harmony'):
        return dict(onset_thresh=.35, frame_thresh=.20, min_note_len=7)
    return dict(onset_thresh=.50, frame_thresh=.30, min_note_len=11)


def predict_cached(path: Path, model_path: Path, predict, directory: Path,
                   part: str | None, profile: str):
    import numpy as np
    from basic_pitch.note_creation import model_output_to_notes
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    identity = {'schema': 1, 'audio_sha256': file_digest(path),
                'basic_pitch': version('basic-pitch'),
                'model': str(model_path),
                'model_sha256': model_digest(Path(model_path))}
    import hashlib
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    artifact = directory / (key + '.npz')
    if artifact.exists():
        try:
            with np.load(artifact, allow_pickle=False) as stored:
                output = {k: stored[k] for k in ('note', 'onset', 'contour')}
            frames = output['note'].shape[0]
            if (output['note'].shape != (frames, 88) or
                    output['onset'].shape != (frames, 88) or
                    output['contour'].shape != (frames, 264) or
                    not all(np.isfinite(a).all() for a in output.values())):
                raise ValueError('Invalid activation cache shape or values')
            print(f'Reusing Basic Pitch activations: {path.name}', flush=True)
        except (OSError, ValueError, KeyError, EOFError) as exc:
            raise RuntimeError(f'Invalid prediction cache {artifact}; remove it and retry') from exc
    else:
        output, _midi, _events = predict(str(path), model_path)
        import os
        import tempfile
        fd, temporary = tempfile.mkstemp(dir=directory, suffix='.npz')
        try:
            with os.fdopen(fd, 'wb') as stream:
                np.savez_compressed(stream, **output)
            os.replace(temporary, artifact)
        finally:
            Path(temporary).unlink(missing_ok=True)
        write_json(directory / (key + '.json'), identity)
    midi, _events = model_output_to_notes(output, **decoder_settings(part, profile))
    return midi


def model_digest(path: Path) -> str:
    """Hash actual weights, including TensorFlow's directory-based model."""
    if path.is_file():
        return file_digest(path)
    import hashlib
    digest = hashlib.sha256()
    files = sorted(p for p in path.rglob('*') if p.is_file())
    if not files:
        raise FileNotFoundError(f'Basic Pitch model not found: {path}')
    for file in files:
        digest.update(file.relative_to(path).as_posix().encode())
        digest.update(file_digest(file).encode())
    return digest.hexdigest()
