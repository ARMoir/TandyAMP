"""Conservative laptop-side cleanup for imperfect Basic Pitch/Demucs notes.

Never applied to user-supplied MIDI; preserve their intentional arrangement.
'velocity' here is a useful confidence proxy, NOT an ML probability score.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from statistics import median

from arranger import Note


def _limit_polyphony(notes: list[Note], voices: int) -> list[Note]:
    """Select stable stronger notes at boundaries without losing quick riff attacks."""
    if not notes:
        return []
    events = []
    for i, n in enumerate(notes):
        events.extend(((n.start, 1, i), (n.end, 0, i)))
    events.sort()
    active = set()
    chosen = set()
    opened: dict[int, float] = {}
    result = []
    pos = 0
    while pos < len(events):
        at = events[pos][0]
        while pos < len(events) and events[pos][0] == at:
            _, on, idx = events[pos]
            if on:
                active.add(idx)
            else:
                active.discard(idx)
            pos += 1
        ranked = sorted(active, key=lambda i: (
            -(notes[i].velocity + min(.5, notes[i].end-notes[i].start)*40
              + (15 if i in chosen else 0)), i
        ))
        selected = set()
        used = set()
        for i in ranked:
            if notes[i].pitch in used:
                continue
            selected.add(i)
            used.add(notes[i].pitch)
            if len(selected) >= voices:
                break
        for i in chosen - selected:
            if at-opened[i] >= .050:
                result.append(replace(notes[i], start=opened[i], end=at))
            opened.pop(i, None)
        for i in selected - chosen:
            opened[i] = at
        chosen = selected
    return sorted(result, key=lambda n: (n.start, n.pitch, n.end))


def clean_stem_notes(notes: list[Note], part: str) -> list[Note]:
    """Remove low-strength/short pitched artifacts; bass and voice stay monophonic.

    Do not gate all quiet vocals: the cut scales with this stem's median
    velocity, and 'other' is cleaned more strictly than melodic material.
    """
    if not notes:
        return []
    floor = {'bass': 30, 'melody': 31, 'harmony': 42}.get(part, 35)
    shortest = {'bass': .090, 'melody': .085, 'harmony': .115}.get(part, .100)
    typical = median(n.velocity for n in notes)
    threshold = max(floor, min(67, int(typical * .62)))
    valid = [
        replace(n, part=part)
        for n in notes
        if n.velocity >= threshold and n.end - n.start >= shortest
        and 0 <= n.pitch <= 127
    ]
    if not valid:
        return []
    # Spurious octave jumps of very short duration usually arise from
    # distorted guitar harmonics or vocal doubling, not a new phrase.
    valid.sort(key=lambda n: (n.start, n.end, n.pitch))
    filtered = []
    for i, n in enumerate(valid):
        if .085 <= n.end - n.start < .15 and 0 < i < len(valid)-1:
            before, after = valid[i-1], valid[i+1]
            near = (n.start - before.end <= .10 and
                    after.start - n.end <= .10)
            if (near and before.pitch == after.pitch and
                    abs(before.pitch-n.pitch) >= 11 and
                    n.velocity < min(before.velocity, after.velocity)):
                continue
        filtered.append(n)
    return _limit_polyphony(filtered, 2 if part == 'harmony' else 1)


def classify_drum_bands(low: float, mid: float, high: float) -> int | None:
    """Conservative drum-stem spectral classifier: 36 kick, 38 snare, 42 hat.

    Unlike the previous centroid-only classifier, ambiguous transients are
    discarded rather than being turned into an endless stream of snares.
    """
    total = max(0.0, low) + max(0.0, mid) + max(0.0, high)
    if total <= 0.0:
        return None
    l, m, h = low / total, mid / total, high / total
    if l >= .44 and low >= 1.3 * mid:
        return 36
    if h >= .52 and high >= 1.3 * mid:
        return 42
    if m >= .47 and mid >= 1.35 * low and mid >= .80 * high:
        return 38
    return None


def refine_drum_hits(notes: list[Note], beats: list[float] | None = None) -> list[Note]:
    """Beat-aware debounce for the Tandy's *one* noise channel.

    Align hits only when very near a reliable tracked beat, keeping guitar
    riffs off the drum channel. Prevent sub-100 ms snare chatter and avoid
    masking kicks with frequent snare triggers.
    """
    if not notes:
        return []
    from bisect import bisect_left
    beats = sorted(beats or [])
    minimum = {36: .18, 38: .28, 42: .105}
    last_type: dict[int, float] = {}
    result: list[Note] = []
    typical = median(n.velocity for n in notes)
    for n in sorted(notes, key=lambda x: (x.start, {36: 0, 38: 1, 42: 2}.get(x.pitch, 3))):
        if n.pitch not in minimum or n.velocity < max(38, .48 * typical):
            continue
        t = n.start
        if beats:
            j = bisect_left(beats, t)
            nearby = [beats[k] for k in (j-1, j) if 0 <= k < len(beats)]
            if nearby:
                closest = min(nearby, key=lambda b: abs(b-t))
                diff = abs(closest-t)
                if diff <= .035:
                    t = closest
                # Weak, off-grid snares are more often bleed or transients.
                elif n.pitch == 38 and diff > .13 and n.velocity < typical:
                    continue
        if t - last_type.get(n.pitch, -100) < minimum[n.pitch]:
            continue
        if result and t - result[-1].start < .085:
            old = result[-1]
            importance = {36: 3, 38: 2, 42: 1}
            if importance[n.pitch] <= importance[old.pitch]:
                continue
            result.pop()
        end = t + {36: .075, 38: .060, 42: .048}[n.pitch]
        result.append(replace(n, start=t, end=end))
        last_type[n.pitch] = t
    return result
