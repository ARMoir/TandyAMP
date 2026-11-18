"""Recover a repeating instrumental line from competing stem detections."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, replace
from statistics import median
from typing import TYPE_CHECKING

from arranger import Note

if TYPE_CHECKING:
    from stem_pitch import StemPitch


@dataclass
class RiffCandidates:
    weights: dict[Note, float]
    repeated: set[float]


def _attacks(weights: dict[Note, float], spacing: float) -> list[Note]:
    """Keep a small set of alternatives at each attack for matching phrases."""
    buckets: dict[int, dict[int, Note]] = defaultdict(dict)
    for n, weight in weights.items():
        group = buckets[round(n.start / spacing)]
        if n.pitch not in group or weight > weights[group[n.pitch]]:
            group[n.pitch] = n
    return sorted((n for group in buckets.values()
                   for n in sorted(group.values(), key=weights.__getitem__, reverse=True)[:3]),
                  key=lambda n: n.start)


def _fundamental_weights(notes: list[Note], signal: StemPitch | None,
                         beat: float) -> dict[Note, float]:
    starts = [n.start for n in notes]
    strength = {n: signal.sustain_strength(n) for n in notes} if signal else {}
    weights = {}
    for n in notes:
        duration = n.end - n.start
        heard = strength.get(n)
        weight = (n.velocity - 48) / 64 + .64 * min(duration, .38)
        if heard is not None:
            weight += .92 * heard - .27
        neighbors = notes[bisect_left(starts, n.start - .20):
                          bisect_right(starts, n.start + .038)]
        # A partial of another sounding note brings no new attack. A
        # fifth can be played independently, so give it a smaller penalty.
        harmonic = max((
            (.68 if n.pitch - lo.pitch in (12, 24, 36) else .32)
            for lo in neighbors
            if n.pitch - lo.pitch in (12, 19, 24, 28, 31, 36)
            and lo.end >= n.start + min(.052, duration * .75)
            and (lo.velocity >= n.velocity - 16 or
                 heard is not None and (strength[lo] or 0.) >= heard * .65)
            and (heard is None or heard < .83 or strength[lo] is None
                 or n.pitch - lo.pitch in (12, 24, 36) and abs(lo.start - n.start) <= .045)
        ), default=0.)
        weights[n] = weight - harmonic

    anchors = _attacks(weights, min(.18, beat * .33))
    anchor_times = [n.start for n in anchors]
    for n in notes:
        if n.end - n.start > min(.22, beat * .54):
            continue
        i = bisect_left(anchor_times, n.start - .12)
        j = bisect_right(anchor_times, n.start + .12)
        span = min(1.0, 2 * beat)
        before = [x for x in anchors[max(0, i - 9):i]
                  if x.start >= n.start - span and weights[x] > .20]
        after = [x for x in anchors[j:j + 9]
                 if x.start <= n.end + span and weights[x] > .20]
        local = before + after
        if (before and after and len(local) >= 4
                and n.pitch - median(x.pitch for x in local) >= 12
                and not any(abs(n.pitch - x.pitch) <= 4 for x in local)):
            weights[n] -= .72
    return weights


def _match_repeats(weights: dict[Note, float], beat: float
                   ) -> dict[Note, float]:
    """Find the same contour and attack spacing in separate performances.

    A matching anchor pitch provides a time offset. Look for corroborating
    pitches at that offset among the alternatives, before choosing a line.
    """
    width = max(.035, min(.065, beat * .13))
    span = min(1.60, beat * 3.5)
    minimum_lag = max(.48, span * .84)
    maximum_lag = max(9., beat * 24)
    attacks = _attacks({n: w for n, w in weights.items() if w >= .35},
                       max(.063, beat * .15))
    starts = [n.start for n in attacks]
    tracks: dict[int, list[Note]] = defaultdict(list)
    for n in attacks:
        tracks[n.pitch].append(n)
    times = {pitch: [n.start for n in track] for pitch, track in tracks.items()}
    support: dict[Note, float] = {}
    for i, first in enumerate(attacks):
        onsets = times[first.pitch]
        start = bisect_left(onsets, first.start + minimum_lag)
        stop = bisect_right(onsets, first.start + maximum_lag)
        for second in tracks[first.pitch][start:stop]:
            lag = second.start - first.start
            end = bisect_right(starts, first.start + min(span, lag - .12), i + 1)
            pairs = [(first, second)]
            for a in attacks[i + 1:end]:
                a_time = a.start + lag
                candidates = tracks[a.pitch]
                onsets_a = times[a.pitch]
                lo = bisect_left(onsets_a, a_time - width)
                hi = bisect_right(onsets_a, a_time + width)
                b = max(candidates[lo:hi],
                        key=lambda n: weights[n] - 4 * abs(n.start - a_time),
                        default=None)
                if (b is not None and a.start - pairs[-1][0].start >= .068
                        and b.start - pairs[-1][1].start >= .068):
                    pairs.append((a, b))
            if (len(pairs) < 3 or pairs[-1][0].start - first.start < .28
                    or len({a.pitch for a, _ in pairs}) < 2):
                continue
            # A strong, longer match outranks several weak two-pitch
            # coincidences. Limit the bonus so solos can take over.
            fit = median(min(weights[a], weights[b]) for a, b in pairs)
            bonus = min(.75, .095 * len(pairs) + .29 * fit)
            for a, b in pairs:
                support[a] = max(support.get(a, 0.), bonus)
                support[b] = max(support.get(b, 0.), bonus)
    return support


def _join_fragments(weights: dict[Note, float], repeated: dict[Note, float],
                    beat: float, signal: StemPitch | None) -> dict[Note, float]:
    tracks: dict[int, list[Note]] = defaultdict(list)
    for n in weights:
        tracks[n.pitch].append(n)
    onsets = list(weights)
    starts = [n.start for n in onsets]
    joined = {}
    for track in tracks.values():
        chain: list[Note] = []
        for n in sorted(track, key=lambda x: (x.start, -weights[x], -x.end)):
            if chain:
                old = chain[-1]
                gap = n.start - old.end
                spacing = n.start - old.start
                duplicate = spacing <= .035
                continuation = (
                    -.085 <= gap <= min(.063, beat * .14)
                    and n.velocity <= old.velocity - 8
                    and n.end - n.start <= min(.24, beat * .60))
                if continuation:
                    reattack = signal.has_reattack(n) if signal is not None else None
                    continuation = reattack is False or (reattack is None and n not in repeated)
                if continuation and gap > 0.:
                    left = bisect_left(starts, old.end - .015)
                    right = bisect_left(starts, n.start)
                    continuation = not any(
                        0 < abs(x.pitch - old.pitch) < 12
                        and weights[x] >= max(.40, weights[n])
                        for x in onsets[left:right])
                if duplicate or continuation:
                    merged = replace(old, end=max(old.end, n.end))
                    weights[merged] = max(weights[old], weights[n])
                    bonus = max(repeated.get(old, 0.), repeated.get(n, 0.))
                    if bonus:
                        repeated[merged] = bonus
                    chain[-1] = merged
                    continue
            chain.append(n)
        joined.update((n, weights[n]) for n in chain)
    return joined


def reconstruct_riff(notes: list[Note], beat: float,
                     signal: StemPitch | None = None) -> RiffCandidates:
    """Score one instrumental stem before any PSG parts are allocated."""
    if not notes:
        return RiffCandidates({}, set())

    notes = sorted(notes, key=lambda n: (n.start, n.pitch, n.end))
    weights = _fundamental_weights(notes, signal, beat)
    repeated = _match_repeats(weights, beat)
    candidates = _join_fragments(weights, repeated, beat, signal)
    confirmed = sorted((n for n in candidates if repeated.get(n, 0.) >= .50),
                       key=lambda n: n.start)
    starts = [n.start for n in confirmed]
    attacks = sorted(set(starts))
    choices = {}
    for n, weight in candidates.items():
        bonus = repeated.get(n, 0.)
        quality = weight + bonus
        duration = n.end - n.start
        if duration >= beat:
            lo = bisect_left(starts, n.start - .025)
            hi = bisect_left(starts, n.end - .075)
            upper = [m for m in confirmed[lo:hi]
                     if 4 <= m.pitch - n.pitch <= 14 and m.pitch - n.pitch != 12
                     and candidates[m] >= .57]
            # A long pedal that rings under several independent attacks
            # supports the riff without taking the melodic lane from it.
            if (len({m.pitch for m in upper}) >= 2
                    and upper[-1].start - upper[0].start >= .11):
                quality -= .48
        if quality <= .32:
            continue
        # Rank the amount of credible music covered by an interval.
        # Rewarding note count would favor chopping a held tone into
        # however many tiny detections happened to run across it.
        choices[n] = (quality - .16) * min(duration, .90)
        if bonus < .50:
            continue
        # The tail of a ringing string may extend past the next supported
        # pick. Offer that release as an alternative before selecting full
        # notes. Competing pitches never cut a note after selection.
        first = max(n.start + .080, n.end - min(.16, .34 * beat))
        for attack in attacks[bisect_left(attacks, first):bisect_left(attacks, n.end - 1e-7)]:
            cost = .16 if n.end - attack < .010 else .19
            choices[replace(n, end=attack)] = (quality - cost) * min(attack - n.start, .90)
    return RiffCandidates(choices, set(attacks))
