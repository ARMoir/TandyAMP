"""Minimal, musical-first offline arrangement for TandyAMP.

This is an opt-in *alternative* to the established Build56 Studio pipeline.
One shared engine selects foundation, identity and useful support regardless
of genre. It operates on actual transcribed notes and never invents material.

Output: at most three distinct PSG tones and, *if independently eligible*,
one low SPK4 bass, plus a single PSG-noise drum stream. Extra raw candidates
remain in Studio's INPUT diagnostics, not in the finished Tandy arrangement.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from typing import Iterable

from arranger import BASS_MIN, BASS_MAX, Note, _psg_pitch, voice_coverage


@dataclass(frozen=True)
class MusicReport:
    source_pitched: int
    selected_source_notes: int
    output_pitched_fragments: int
    source_drums: int
    output_drums: int
    suspected_artifacts: int
    four_voice_seconds: float
    role_counts: dict[str, int]

    def as_text(self) -> str:
        return (
            'TandyAMP Studio: optional MUSICAL arrangement\n'
            'Design: foundation + recognizable identity + useful support.\n'
            'Only real source note candidates are used; no filler or quantization.\n'
            'Hardware: up to three PSG tones and eligible independent SPK4 bass.\n'
            'Source pitched notes: {}\n'
            'Source notes heard at least once: {}\n'
            'Selected pitched fragments: {}\n'
            'Original drum hits: {}\n'
            'Retained drum hits: {}\n'
            'Suspected isolated high artifacts: {}\n'
            'Four-voice candidate seconds: {:.2f}\n'
            'Selected source notes by role: {}\n'
            'Note: counts and voice availability do not prove audible quality.\n'
        ).format(self.source_pitched, self.selected_source_notes,
                 self.output_pitched_fragments, self.source_drums,
                 self.output_drums, self.suspected_artifacts,
                 self.four_voice_seconds,
                 repr(dict(sorted(self.role_counts.items()))))


def _linked_phrases(source: list[Note]) -> set[int]:
    """Nearby pitches in the same instrument are evidence of a phrase.

    Do not link across part/program boundaries. This does *not* assume a
    fixed beat grid, a musical key or a single style of music.
    """
    grouped: dict[tuple[str, int], list[int]] = defaultdict(list)
    for i, n in enumerate(source):
        grouped[n.part, n.program].append(i)
    linked: set[int] = set()
    for indices in grouped.values():
        indices.sort(key=lambda i: (source[i].start, source[i].pitch))
        for j, i in enumerate(indices):
            note = source[i]
            for other_idx in (j - 1, j + 1):
                if not 0 <= other_idx < len(indices):
                    continue
                other = source[indices[other_idx]]
                # Distinct nearby attacks can be walking bass, trills,
                # classical passing tones or a riff, not random noise.
                if (abs(note.start - other.start) <= .55 and
                        abs(note.pitch - other.pitch) <= 12):
                    linked.add(i)
                    linked.add(indices[other_idx])
    return linked


def _suspect_high_note(n: Note, linked: bool) -> bool:
    """Only flag an extremely specific *candidate* artifact.

    Do not delete it unless a credible stronger note competes. Chromatic
    tones and high solos are protected when they form a phrase.
    """
    return (n.pitch >= 85 and n.velocity < 56 and
            n.end - n.start < .14 and not linked)


def _importance(n: Note, playing: bool, now: float, linked: bool) -> float:
    # Familiar distinct roles are hints; no mandatory genre assignment.
    roles = {'guitar': 660, 'melody': 630, 'bass': 500,
             'harmony': 220, 'accomp': 35}
    score = roles.get(n.part, 180) + n.velocity * 3.5
    score += min(.7, n.end - n.start) * 145
    if 40 <= n.program <= 47:  # orchestral string phrase/independent lead
        score += 160
    if linked:
        score += 130
    if playing:
        score += 340  # finish meaningful phrases rather than voice-hop
    elif now - n.start <= .045 and n.velocity >= 85:
        score += 360  # significant new attacks still enter
    if _suspect_high_note(n, linked):
        score -= 850
    return score


def _drum_groove(notes: list[Note]) -> list[Note]:
    """Select competing attacks for one PSG noise voice without a fake beat.

    Only simultaneous/near-simultaneous hits are reduced; offbeat kicks,
    hats, backbeats and syncopated spacing remain intact.
    """
    drums = sorted((n for n in notes if n.part == 'drums'),
                   key=lambda n: (n.start, n.pitch, -n.velocity))
    result: list[Note] = []
    for n in drums:
        if result and n.start - result[-1].start < .038:
            def score(hit: Note) -> int:
                return hit.velocity + {38: 10, 36: 8, 42: 0}.get(hit.pitch, 0)
            if score(n) > score(result[-1]):
                result[-1] = n
        else:
            result.append(n)
    return result


def arrange_musically(notes: Iterable[Note],
                      spk4: str = 'adapt') -> tuple[list[Note], MusicReport]:
    """Arrange by note boundaries for a simple, coherent hardware part set.

    Do *not* alter pitches/velocities, quantize starts, or synthesize notes.
    Bass is the foundation when present; otherwise a low continuing voice
    may serve as foundation. One or two leading melodic roles are protected,
    and remaining PSG slots carry the most useful genuine support.
    """
    if spk4 not in ('off', 'bass', 'adapt'):
        raise ValueError('SPK4 mode must be off, bass or adapt')
    all_notes = [n for n in notes if n.end > n.start]
    source = [n for n in all_notes if n.part != 'drums']
    drums = [n for n in all_notes if n.part == 'drums']
    linked = _linked_phrases(source)
    events: list[tuple[float, int, int]] = []
    for i, n in enumerate(source):
        events.append((n.start, 1, i))
        events.append((n.end, 0, i))
    events.sort(key=lambda x: (x[0], x[1], x[2]))  # note-off first

    active: set[int] = set()
    chosen: set[int] = set()
    opened: dict[int, float] = {}
    selected_ever: set[int] = set()
    suspect_seen: set[int] = set()
    result: list[Note] = []
    pos = 0
    while pos < len(events):
        now = events[pos][0]
        while pos < len(events) and events[pos][0] == now:
            _, on, i = events[pos]
            (active.add if on else active.discard)(i)
            pos += 1

        # Suspicious high note fragments are *only* suppressed if another
        # stronger meaningful tone is active. Never flatten a genuine solo.
        strong = any(source[i].velocity >= 68 and
                     not _suspect_high_note(source[i], i in linked)
                     for i in active)
        candidates = []
        for i in active:
            if strong and _suspect_high_note(source[i], i in linked):
                suspect_seen.add(i)
                continue
            candidates.append(i)
        def score(i: int) -> float:
            return _importance(source[i], i in chosen, now, i in linked)

        ranked = sorted(candidates, key=lambda i: (-score(i), i))
        played: set[int] = set()
        selected: set[int] = set()
        speaker = None

        # SPK4 can only carry *eligible* bass; never repurpose as a fourth
        # high voice. Require three other distinct tone candidates, and a
        # conservatively audible bass velocity.
        if spk4 != 'off':
            basses = [i for i in ranked if
                      source[i].part == 'bass' and
                      BASS_MIN <= source[i].pitch <= BASS_MAX and
                      source[i].velocity >= 58]
            for i in basses:
                other_pitches = {_psg_pitch(source[j]) for j in ranked
                                 if j != i and
                                 source[j].pitch != source[i].pitch}
                if len(other_pitches) >= 3:
                    speaker = i
                    selected.add(i)
                    break

        capacity = 3
        # If bass can't use speaker, carry the genuine bass line on PSG.
        if speaker is None:
            basses = [i for i in ranked if source[i].part == 'bass']
            if basses:
                bass_id = basses[0]
                selected.add(bass_id)
                played.add(_psg_pitch(source[bass_id]))
                capacity -= 1

        def pick(i: int) -> None:
            nonlocal capacity
            pitch = _psg_pitch(source[i])
            if capacity > 0 and i not in selected and pitch not in played:
                if speaker is None or source[i].pitch != source[speaker].pitch:
                    selected.add(i)
                    played.add(pitch)
                    capacity -= 1

        # Two different independent lead lines can matter more than two
        # arbitrary chord tones. String/violin melodies also qualify, but
        # don't presume all classical channels are permanent leads.
        leads = [i for i in ranked if
                 (source[i].part in ('guitar', 'melody') or
                  40 <= source[i].program <= 47)]
        for i in leads:
            pick(i)
            if capacity == 0:
                break

        # When no explicit bass exists, keep a real continuing lower line
        # as foundation *if* the passage has enough notes for a third part.
        if speaker is None and not any(source[i].part == 'bass'
                                       for i in selected):
            low = [i for i in ranked if source[i].pitch <= 64 and
                   source[i].velocity >= 48 and
                   source[i].end - source[i].start >= .11]
            if capacity > 0 and low and len(ranked) >= 2:
                # Do not force a second duplicate pitch or take a lead slot.
                for i in sorted(low, key=lambda i: (source[i].pitch, -score(i))):
                    if i not in selected:
                        pick(i)
                        break

        for i in ranked:
            if capacity == 0:
                break
            pick(i)

        for i in chosen - selected:
            duration = now - opened[i]
            if duration >= .012:
                result.append(replace(source[i], start=opened[i], end=now))
            opened.pop(i, None)
        for i in selected - chosen:
            opened[i] = now
        chosen = selected
        selected_ever.update(selected)

    # The last event normally closes all notes; defensive finalization.
    if events:
        end = events[-1][0]
        for i in chosen:
            if end - opened[i] >= .012:
                result.append(replace(source[i], start=opened[i], end=end))

    chosen_drums = _drum_groove(drums)
    output = sorted(result + chosen_drums,
                    key=lambda n: (n.start, n.end, n.part, n.pitch))
    coverage = voice_coverage(output)
    roles = Counter(source[i].part for i in selected_ever)
    report = MusicReport(
        source_pitched=len(source),
        selected_source_notes=len(selected_ever),
        output_pitched_fragments=len(result),
        source_drums=len(drums),
        output_drums=len(chosen_drums),
        suspected_artifacts=len(suspect_seen),
        four_voice_seconds=coverage['four_candidate'],
        role_counts=dict(roles),
    )
    return output, report
