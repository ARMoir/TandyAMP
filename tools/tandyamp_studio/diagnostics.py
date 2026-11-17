"""Reproducible stage snapshots. Density is a diagnostic, not an accuracy score."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from arranger import Note, voice_coverage
from preview import assign_preview_voices


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value) -> None:
    """Publish complete reports only; interrupted writes cannot become caches."""
    import os
    import tempfile
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def note_metrics(notes: list[Note], duration: float | None = None,
                 spk4: str = 'adapt', voice_selection: str = 'legacy') -> dict:
    """Count candidates separately from approximate *audible* voice occupancy.

    Include source leading/trailing silence. Role coverage is interval union,
    never the sum of overlapping note lengths. All times are seconds.
    """
    end = max((n.end for n in notes), default=0.0)
    duration = max(end, duration or 0.0)
    coverage = voice_coverage(notes)
    coverage['silent'] += max(0.0, duration - coverage['duration'])
    coverage['duration'] = duration
    events = [(0.0, 0, -1), (duration, 0, -1)]
    for i, n in enumerate(notes):
        if n.end > n.start:
            events.extend(((max(0.0, n.start), 1, i), (n.end, 0, i)))
    events.sort()
    active = set()
    audible = [0.0] * 5
    roles = Counter()
    audible_roles = Counter()
    previous_tones = []
    steals = 0
    longest_gap = gap = 0.0
    previous = 0.0
    for at, on, index in events:
        span = at - previous
        if span > 0:
            current = [notes[i] for i in active]
            tones, bass, _drum = assign_preview_voices(
                current, spk4, voice_selection=voice_selection,
                previous_tones=previous_tones, now=previous)
            steals += sum(n in current and n not in tones for n in previous_tones)
            previous_tones = tones
            audible[len(tones) + int(bass is not None)] += span
            for part in {n.part for n in tones + ([bass] if bass is not None else [])}:
                audible_roles[part] += span
            present = {n.part for n in current if n.part != 'drums'}
            for part in present:
                roles[part] += span
            if present:
                gap = 0.0
            else:
                gap += span
                longest_gap = max(longest_gap, gap)
        if index >= 0:
            if on:
                active.add(index)
            else:
                active.discard(index)
        previous = at
    return {'events': len(notes), 'events_by_role': dict(Counter(n.part for n in notes)),
            'candidate_seconds': coverage,
            'preview_voice_seconds': {str(i): v for i, v in enumerate(audible)},
            'role_active_seconds': dict(roles), 'longest_pitched_gap': longest_gap,
            'preview_role_seconds': dict(audible_roles),
            'preview_voice_steals': steals, 'voice_selection': voice_selection,
            'accuracy': 'Not measured without a reference transcription/listening review',
            'preview_scope': 'Approximate allocator, not cycle-accurate DOS playback'}


def save_stage(directory: Path, name: str, notes: list[Note],
               duration: float | None = None, spk4: str = 'adapt',
               voice_selection: str = 'legacy') -> dict:
    report = note_metrics(notes, duration, spk4, voice_selection)
    write_json(Path(directory) / (name + '.json'),
               {'metrics': report, 'notes': [asdict(n) for n in notes]})
    return report
