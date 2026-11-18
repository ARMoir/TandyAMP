"""Reconstruct musical lines from audio evidence before mapping to PSG."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from heapq import heappop, heappush
from math import floor, isfinite
from statistics import median

from arranger import Note, _psg_pitch, normalize
from core_arranger import _drums_core


@dataclass
class ScoreEvidence:
    """Optional timing and signal levels measured on the separated audio."""

    beats: list[float] = field(default_factory=list)
    # RMS in consecutive 50 ms windows, before Basic Pitch normalizes audio.
    levels: dict[str, list[float]] = field(default_factory=dict)


@dataclass(frozen=True)
class Phrase:
    part: str
    function: str
    notes: tuple[Note, ...]

    @property
    def start(self) -> float:
        return self.notes[0].start

    @property
    def end(self) -> float:
        return self.notes[-1].end


@dataclass(frozen=True)
class Score:
    beats: tuple[float, ...]
    drums: tuple[Note, ...]
    phrases: tuple[Phrase, ...]

    def summary(self) -> str:
        counts = Counter(p.function for p in self.phrases)
        return (
            'TandyAMP Studio CORE - audio phrase score\n'
            'Each phrase is a single musical line with its own attacks and rests.\n'
            f'Drum hits: {len(self.drums)}\n'
            f'Tracked beats: {len(self.beats)}\n'
            f'Phrases: {dict(sorted(counts.items()))}\n'
            f'Pitched notes: {sum(len(p.notes) for p in self.phrases)}\n'
        )


@dataclass(frozen=True)
class _Groove:
    beats: tuple[float, ...]
    subdivisions: tuple[float, ...]
    accents: tuple[float, ...]
    period: float


def _groove(drums: list[Note], evidence: ScoreEvidence) -> _Groove:
    beats = tuple(sorted({t for t in evidence.beats if isfinite(t) and t >= 0}))
    steps = [b - a for a, b in zip(beats, beats[1:]) if .24 <= b - a <= 1.0]
    if len(steps) < 2:
        beats = ()
    period = median(steps) if beats else .50
    subdivisions = {a + (b - a) * i / 4
                    for a, b in zip(beats, beats[1:]) if .24 <= b - a <= 1.0
                    for i in range(4)}
    accents = tuple(n.start for n in drums if n.pitch in (36, 38))
    return _Groove(beats, tuple(sorted(subdivisions)), accents, period)


def _near(points: tuple[float, ...], when: float, width: float) -> bool:
    idx = bisect_left(points, when - width)
    return idx < len(points) and points[idx] <= when + width


def _has_signal(notes: list[Note], role: str,
                evidence: ScoreEvidence) -> list[Note]:
    levels = evidence.levels.get(role)
    if not levels:
        return notes
    typical_peak = sorted(levels)[int(.95 * (len(levels) - 1))]
    noise_floor = max(1e-7, typical_peak * .035)
    others = [evidence.levels[p] for p in ('bass', 'guitar', 'melody')
              if p != role and p in evidence.levels]
    result = []
    for n in notes:
        first = int(n.start / .05)
        last = max(first + 1, int(min(n.end, n.start + .25) / .05 + .5))
        own = max(levels[first:last], default=0.)
        other = max((max(row[first:last], default=0.) for row in others),
                    default=0.)
        # A high decoder velocity on an almost silent stem can be bleed.
        if own >= max(noise_floor, other * .10):
            result.append(n)
    return result


def _line(notes: list[Note], role: str, groove: _Groove) -> list[Note]:
    """Find a maximum-scoring attack path through complete note proposals.

    Each edge considers the gap, interval, and overlap with the previous
    attack. Long rests end that continuity so unrelated phrases can restart.
    The sweep retains only the part of the graph still close enough to link.
    """
    notes = sorted(notes, key=lambda n: (n.start, n.pitch, -n.end, -n.velocity))
    starts = [n.start for n in notes]
    floor = {'bass': 49, 'guitar': 43, 'melody': 47,
             'harmony': 52, 'accomp': 58}[role]
    link = max(.28, .9 * groove.period)
    minimum_spacing = min(.095, .21 * groove.period)
    endings: list[tuple[float, int]] = []
    open_paths: dict[int, None] = {}
    scores: list[float] = []
    predecessors: list[int] = []
    closed = -1
    best = -1
    for i, n in enumerate(notes):
        duration = n.end - n.start
        weight = (n.velocity - floor) / 42 + 1.2 * min(duration, .45) - .20
        if role == 'bass':
            weight -= min(.90, .075 * max(0, n.pitch - 52))
        elif role == 'guitar':
            weight -= min(.85, .045 * max(0, n.pitch - 76))
        if role != 'melody':
            if _near(groove.subdivisions, n.start, .032):
                weight += .11
            if _near(groove.accents, n.start, .044):
                weight += .13
        # Octave and overtone duplicates near an onset need independent
        # evidence to beat the lower fundamental of the same attack.
        if any(n.pitch - m.pitch in (12, 19, 24, 28, 31, 36)
               and m.velocity >= n.velocity - 7 and m.end > n.start + .05
               for m in notes[bisect_left(starts, n.start - .056):
                              bisect_right(starts, n.start + .042)]):
            weight -= .62
        while endings and endings[0][0] < n.start - link:
            _, j = heappop(endings)
            del open_paths[j]
            if closed == -1 or scores[j] > scores[closed]:
                closed = j
        previous = closed
        subtotal = scores[closed] if closed != -1 else 0.
        if weight > -.20:
            for j in open_paths:
                old = notes[j]
                gap = n.start - old.end
                # Model note tails can overlap slightly at a real new attack.
                # Never interrupt a sustained candidate just to resume it.
                interval = abs(n.pitch - old.pitch)
                played = n.start - old.start
                tail = min(.060, (old.end - old.start) * .32)
                if (role == 'guitar' and 0 < interval <= 7 and
                        n.velocity >= max(54, .86 * old.velocity) and
                        played >= .105 and n.end > old.end - .08):
                    # Successive attacks can overlap as strings ring out.
                    # A credible change with enough time on the old pitch
                    # can finish that note once, at the new attack.
                    tail = .28
                if played < minimum_spacing or gap < -tail:
                    continue
                motion = (.15 - .052 * min(16, max(0, interval - 4)))
                continuity = motion * (1 - max(0., gap) / link)
                overlap_cost = 1.3 * max(0., -gap) + .10 * (gap < -.060)
                branch = scores[j] + continuity - overlap_cost
                if branch > subtotal:
                    subtotal, previous = branch, j
        scores.append(subtotal + weight)
        predecessors.append(previous)
        if weight > -.20 and scores[i] > 0:
            heappush(endings, (n.end, i))
            open_paths[i] = None
            if best == -1 or scores[i] > scores[best]:
                best = i
    result = []
    while best != -1:
        n = notes[best]
        if result and n.end > result[-1].start:
            n = replace(n, end=result[-1].start)
        result.append(n)
        best = predecessors[best]
    return list(reversed(result))


def _group(notes: list[Note], gap: float) -> list[list[Note]]:
    groups: list[list[Note]] = []
    for n in notes:
        if (not groups or n.part != groups[-1][-1].part or
                n.start - groups[-1][-1].end >= gap):
            groups.append([])
        groups[-1].append(n)
    return groups


def _connect(notes: list[Note], groove: _Groove) -> list[Note]:
    """Join weak tails and bridge decoder-sized gaps inside a chosen line."""
    result: list[Note] = []
    for n in notes:
        if result:
            old = result[-1]
            gap = n.start - old.end
            if (n.pitch == old.pitch and gap <= .043 and
                    n.end - n.start <= .15 and n.velocity <= .77 * old.velocity
                    and not _near(groove.accents, n.start, .042)
                    and not _near(groove.subdivisions, n.start, .032)):
                result[-1] = replace(old, end=n.end)
                continue
            if (n.part != 'bass' and n.pitch != old.pitch and
                    0 < gap <= .029 and min(n.velocity, old.velocity) >= 50):
                result[-1] = replace(old, end=n.start)
        result.append(n)
    return result


def _recurring_attacks(line: list[Note], period: float) -> set[float]:
    """Find repeated four-attack contours at a comparable pulse or transposition."""
    seen: dict[tuple[int, ...], list[tuple[tuple[Note, ...], tuple[float, ...]]]]
    seen = defaultdict(list)
    repeated = set()
    for i in range(len(line) - 3):
        figure = tuple(line[i:i + 4])
        contour = tuple((n.pitch - figure[0].pitch) % 12 for n in figure[1:])
        rhythm = tuple(b.start - a.start for a, b in zip(figure, figure[1:]))
        if not any(contour) or max(rhythm) > 1.32 * period:
            continue
        for old, times in seen[contour]:
            if not all(abs(a - b) <= max(.050, .23 * a)
                       for a, b in zip(times, rhythm)):
                continue
            if old[-1].start < figure[0].start:
                repeated.update(n.start for n in old + figure)
            break
        else:
            seen[contour].append((figure, rhythm))
    return repeated


def _guitar_bed(notes: list[Note], vocal: Phrase, groove: _Groove,
                bass_attacks: tuple[float, ...]) -> list[Note]:
    """Use observed guitar accents at beat scale under this vocal phrase."""
    beats = groove.beats
    cells: dict[int, list[Note]] = defaultdict(list)
    for n in notes:
        time = n.start + .035
        if not beats:
            cell = floor((time - vocal.start) / groove.period)
        elif time < beats[0]:
            cell = floor((time - beats[0]) / groove.period)
        elif time > beats[-1]:
            cell = len(beats) - 1 + floor((time - beats[-1]) / groove.period)
        else:
            cell = bisect_right(beats, time) - 1
        cells[cell].append(n)
    return [
        max(cell, key=lambda n: (
            n.velocity + 76 * min(groove.period, n.end - n.start)
            + 12 * _near(bass_attacks, n.start, .055)
            + 9 * _near(beats, n.start, .055), -n.start))
        for cell in cells.values()
    ]


def reconstruct_score(notes: list[Note], evidence: ScoreEvidence | None = None,
                      *, connect: bool = True) -> Score:
    """Write the rhythm section, vocal and riff as independent musical lines."""
    evidence = evidence or ScoreEvidence()
    source: dict[str, list[Note]] = defaultdict(list)
    for n in notes:
        if not (isfinite(n.start) and isfinite(n.end) and 0 <= n.pitch <= 127):
            continue
        start = max(0., n.start)
        if n.end - start >= .040 and n.velocity > 0:
            source[n.part].append(n if start == n.start else replace(n, start=start))
    drums = _drums_core(source['drums'])
    for i in range(len(drums) - 1):
        if drums[i].end > drums[i + 1].start:
            drums[i] = replace(drums[i], end=drums[i + 1].start)
    groove = _groove(drums, evidence)
    rest = max(.34, 1.06 * groove.period)

    def line(role: str) -> list[Note]:
        chosen = _line(_has_signal(source[role], role, evidence), role, groove)
        return _connect(chosen, groove) if connect else chosen

    bass = line('bass')
    bass_attacks = tuple(n.start for n in bass)
    phrases = [Phrase('bass', 'bass', tuple(group))
               for group in _group(bass, rest)]
    vocals = [Phrase('melody', 'vocal', tuple(group))
              for group in _group(line('melody'), rest)]
    phrases.extend(vocals)

    guitar = line('guitar')
    repeats = _recurring_attacks(guitar, groove.period)
    vocal_starts = [p.start for p in vocals]
    slots: dict[tuple[int, bool], list[Note]] = defaultdict(list)
    for n in guitar:
        i = bisect_right(vocal_starts, n.start) - 1
        sung = i >= 0 and n.start < vocals[i].end
        slots[i, sung].append(n)
    guitar_phrases = []
    for (i, sung), group in slots.items():
        for phrase in _group(group, rest):
            recurring = sum(n.start in repeats for n in phrase)
            keep_riff = not sung or recurring >= max(3, len(phrase) * .6)
            if not keep_riff:
                phrase = _guitar_bed(phrase, vocals[i], groove, bass_attacks)
            guitar_phrases.append(Phrase('guitar', 'riff' if keep_riff else 'backing',
                                         tuple(phrase)))
    phrases.extend(guitar_phrases)

    # One fallback line is useful when the harmonic stem is the only backing
    # (including four-stem audio). Do not fill holes between riff attacks.
    backing = sorted(line('harmony') + line('accomp'), key=lambda n: n.start)
    occupied = sorted((p.start, p.end) for p in guitar_phrases)
    occupied_ends = [b for _, b in occupied]
    last_end = 0.
    support = []
    for n in backing:
        next_guitar = bisect_right(occupied_ends, n.start)
        if (n.start >= last_end and (next_guitar == len(occupied) or
                                    n.end <= occupied[next_guitar][0])):
            support.append(n)
            last_end = n.end
    phrases.extend(Phrase(group[0].part, 'harmony', tuple(group))
                   for group in _group(support, rest))
    return Score(groove.beats, tuple(drums),
                 tuple(sorted(phrases, key=lambda p: (p.start, p.part))))


def _overlap(line: list[Note], phrase: Phrase) -> list[Note]:
    start = bisect_right(line, phrase.start, key=lambda n: n.end)
    end = bisect_left(line, phrase.end, key=lambda n: n.start)
    return line[start:end]


def _register(notes: tuple[Note, ...], others: list[Note], center: int,
              velocity: float = 1.) -> list[Note]:
    """Choose one octave for the phrase to retain its contour and avoid unisons."""
    ordered = sorted(others, key=lambda n: n.start)
    octaves = range(-72, 73, 12)
    inside = [shift for shift in octaves
              if all(45 <= n.pitch + shift <= 92 for n in notes)]

    def fold(pitch: int) -> int:
        if pitch < 45:
            return 45 + (pitch - 45) % 12
        if pitch > 92:
            return 92 - (92 - pitch) % 12
        return pitch

    def cost(shift: int) -> float:
        seconds = 0.
        first = 0
        for n in notes:
            raw = n.pitch + shift
            pitch = fold(raw)
            duration = n.end - n.start
            seconds += duration * (abs(pitch - center) + 2 * max(0, pitch - 79)
                                   + abs(raw - pitch))
            while first < len(ordered) and ordered[first].end <= n.start:
                first += 1
            for i in range(first, len(ordered)):
                other = ordered[i]
                if other.start >= n.end:
                    break
                if _psg_pitch(other) == pitch:
                    seconds += 36 * max(0., min(n.end, other.end) -
                                         max(n.start, other.start))
        return seconds

    shift = min(inside or octaves, key=lambda value: (cost(value), abs(value)))
    return [replace(n, pitch=fold(n.pitch + shift), velocity=round(n.velocity * velocity))
            for n in notes]


def arrange_score(score: Score, preset: str = 'balanced') -> list[Note]:
    """Map the finished score to bass, lead, one backing tone, and PSG noise."""
    bass = normalize((n for p in score.phrases if p.part == 'bass'
                      for n in p.notes), preset, preserve=True)
    vocals: list[Note] = []
    for phrase in score.phrases:
        if phrase.part == 'melody':
            vocals.extend(_register(phrase.notes, _overlap(bass, phrase), 67))
    backing: list[Note] = []
    for phrase in score.phrases:
        if phrase.part in ('bass', 'melody'):
            continue
        vocal_overlap = _overlap(vocals, phrase)
        gain = .72 if phrase.function == 'backing' else .86 if vocal_overlap else 1.
        neighbors = _overlap(bass, phrase) + vocal_overlap
        backing.extend(_register(phrase.notes, neighbors,
                                 62 if vocal_overlap else 64, gain))
    return normalize(bass + vocals + backing + list(score.drums), preset, preserve=True)
