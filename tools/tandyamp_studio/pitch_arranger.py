"""Pitch-correct a score and voice it for the Tandy's three PSG tones."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from math import floor, isfinite
from pathlib import Path
from statistics import median
from typing import Callable

from arranger import BASS_MAX, BASS_MIN, Note, _psg_pitch, load_midi, normalize
from phrase_score import Score, ScoreEvidence, _Groove, _line, arrange_score

MAX_CORRECTION = 2
ATTACK_TOLERANCE = .040
PARTS = ('guitar', 'bass', 'melody', 'drums')
# Weak passing tones and vocal slides can be ambiguous between these
# collections. Only apply a scale where the song provides enough evidence.
SCALES = {
    'major': (0, 2, 4, 5, 7, 9, 11),
    'minor': (0, 2, 3, 5, 7, 8, 10),
}
KEY_NAMES = ('C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B')


@dataclass(frozen=True)
class PitchReport:
    context: str
    corrected: dict[str, int]
    reference_mix: bool = False
    stem_offsets: dict[str, float] = field(default_factory=dict)
    stem_repairs: dict[str, int] = field(default_factory=dict)
    ensemble_repairs: dict[str, int] = field(default_factory=dict)

    def as_text(self) -> str:
        mode = 'aligned MIDI guide' if self.reference_mix else 'audio phrase score'
        stages = ''
        if not self.reference_mix:
            stages = (f'Pass 1 stem offsets in cents: {self.stem_offsets}\n'
                      f'Pass 1 stem repairs: {dict(sorted(self.stem_repairs.items()))}\n'
                      f'Pass 2 ensemble repairs: {dict(sorted(self.ensemble_repairs.items()))}\n')
        return (f'Pitch evidence: {self.context}\n'
                f'Arrangement source: {mode}\n'
                f'{stages}'
                f'Pitch corrections by role: {dict(sorted(self.corrected.items()))}\n')


@dataclass(frozen=True)
class BeatGrid:
    beats: tuple[float, ...]
    seconds: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.beats) < 2 or len(self.beats) != len(self.seconds):
            raise ValueError('A beat alignment needs at least two beat/time pairs')
        for column in (self.beats, self.seconds):
            if (not all(isfinite(value) and value >= 0 for value in column)
                    or any(b <= a for a, b in zip(column, column[1:]))):
                raise ValueError('Beat and time values must increase from zero or later')

    def time_at(self, beat: float) -> float:
        i = min(len(self.beats) - 2, max(0, bisect_right(self.beats, beat) - 1))
        slope = (self.seconds[i + 1] - self.seconds[i]) / (self.beats[i + 1] - self.beats[i])
        return self.seconds[i] + (beat - self.beats[i]) * slope

    @classmethod
    def parse(cls, text: str) -> BeatGrid:
        try:
            pairs = [entry.split('=') for entry in text.split(',')]
            if any(len(pair) != 2 for pair in pairs):
                raise ValueError
            beats, seconds = zip(*(tuple(float(v) for v in pair) for pair in pairs))
        except ValueError as exc:
            raise ValueError('Alignment must be beat=seconds pairs separated by commas') from exc
        return cls(beats, seconds)


@dataclass(frozen=True)
class Reference:
    notes: tuple[Note, ...]
    beat_grid: BeatGrid | None = None
    end: float | None = None

    @classmethod
    def load(cls, path: Path, channels: str | None = None,
             beat_grid: BeatGrid | None = None, end: float | None = None,
             *, beat_decoder: Callable[[float], float] | None = None) -> Reference:
        parts = None
        if channels:
            pairs = [entry.split('=') for entry in channels.split(',')]
            try:
                if any(len(p) != 2 or p[0] not in PARTS for p in pairs):
                    raise ValueError
                parts = {int(channel) - 1: part for part, channel in pairs}
                if (len(parts) != len(pairs) or len(set(parts.values())) != len(parts)
                        or any(not 0 <= channel < 16 for channel in parts)):
                    raise ValueError
            except ValueError as exc:
                raise ValueError('Use distinct MIDI channels 1-16 as role=channel '
                                 'pairs for guitar, bass, melody or drums') from exc
        decoder = beat_decoder
        if decoder is None and beat_grid is not None:
            decoder = lambda beat: beat
        notes = load_midi(path, channel_parts=parts, beat_to_time=decoder, min_duration=0.)
        if not any(n.part in PARTS for n in notes):
            raise ValueError('The MIDI guide has no notes on the selected channels')
        if end is not None and (not isfinite(end) or end <= 0):
            raise ValueError('Reference end time must be positive and finite')
        return cls(tuple(notes), beat_grid, end)

    def time_at(self, time: float) -> float:
        return self.beat_grid.time_at(time) if self.beat_grid else time

    def aligned_notes(self) -> list[Note]:
        return [replace(n, start=self.time_at(n.start), end=self.time_at(n.end))
                for n in self.notes if self.end is None or self.time_at(n.start) < self.end]


def _by_part(notes: list[Note]) -> dict[str, list[Note]]:
    groups = defaultdict(list)
    for n in notes:
        groups[n.part].append(n)
    return groups


def _near_note(notes: list[Note], starts: list[float], time: float) -> Note | None:
    """Find a note *still sounding*, not merely the latest note-on.

    Guitar and harmony estimates can overlap: a short decoration may end
    while an older root continues. Looking only at the last attack then
    misreports silence, causing the ensemble tuner/backing arranger to
    lose real harmonic context. Search backwards to the latest live note.
    On reconstructed phrase lines this is normally one or two notes.
    """
    i = bisect_right(starts, time) - 1
    while i >= 0:
        if notes[i].end > time:
            return notes[i]
        i -= 1
    return None


def _estimate_key(notes: list[Note]) -> tuple[str, set[int]] | None:
    weights: Counter[int] = Counter()
    for n in notes:
        if n.part in ('bass', 'guitar', 'melody', 'harmony') and n.velocity >= 54:
            weight = min(n.end - n.start, .45) * n.velocity
            weights[n.pitch % 12] += weight * (1.7 if n.part == 'bass' else 1.)
    if len(weights) < 4:
        return None
    ranked = []
    total = sum(weights.values())
    for root in range(12):
        for mode, intervals in SCALES.items():
            scale = {(root + interval) % 12 for interval in intervals}
            coverage = sum(weights[p] for p in scale) / total
            fit = coverage + .09 * (weights[root] + .4 * weights[(root + 7) % 12]) / total
            ranked.append((fit, coverage, root, mode, scale))
    ranked.sort(key=lambda x: x[0], reverse=True)
    best = ranked[0]
    alternative = next(row for row in ranked if row[4] != best[4])
    return ((f'{KEY_NAMES[best[2]]} {best[3]}', best[4])
            if best[1] >= .80 and best[0] - alternative[0] >= .033 else None)


def _stem_correction(score: Score) -> tuple[Score, Counter[str]]:
    """Pull weak one-note excursions back into an otherwise continuous line."""
    corrected = []
    counts: Counter[str] = Counter()
    for phrase in score.phrases:
        group = phrase.notes
        for i, n in enumerate(group):
            before = group[i - 1] if i else None
            after = group[i + 1] if i + 1 < len(group) else None
            if (before and after and before.pitch == after.pitch and
                    0 < abs(n.pitch - before.pitch) <= MAX_CORRECTION and
                    n.end - n.start <= .32 and n.start - before.end <= .09 and
                    after.start - n.end <= .09 and
                    n.velocity <= min(before.velocity, after.velocity) - 5):
                counts[n.part] += 1
                n = replace(n, pitch=before.pitch)
            corrected.append(n)
    return score.with_pitches(corrected), counts


def _ensemble_correction(score: Score, counts: Counter[str]) -> tuple[Score, PitchReport]:
    """Check small pitch errors against the key and the local bass/guitar."""
    notes = score.pitched_notes()
    global_key = _estimate_key(notes)
    groups = _by_part(sorted(notes, key=lambda n: n.start))
    sounding = {part: (groups[part], [n.start for n in groups[part]])
                for part in ('bass', 'guitar', 'melody', 'harmony')}
    by_passage = defaultdict(list)
    for n in notes:
        by_passage[floor(n.start / 8)].append(n)
    keys = {i: _estimate_key(by_passage.get(i - 1, []) + group +
                             by_passage.get(i + 1, [])) or global_key
            for i, group in by_passage.items()}
    corrected = []
    for n in notes:
        key = keys[floor(n.start / 8)]
        if n.part not in sounding or n.end - n.start > .33:
            corrected.append(n)
            continue
        middle = (n.start + n.end) / 2
        neighbors = [_near_note(*line, middle) for part, line in sounding.items()
                     if part != n.part]
        evidence = {m.pitch % 12 for m in neighbors if m and m.velocity >= 47}
        # Never tune a real blues/chromatic note to an *inferred* key,
        # or invent a fifth merely because a bass root suggests it.
        # A weak decoder error can be repaired only when another stem is
        # ACTUALLY sounding the target pitch class at this instant.
        # This also permits supported chromatic pitches outside the
        # estimated key: observed music outranks a global-scale guess.
        if n.pitch % 12 not in evidence and n.velocity < 80:
            candidates = [p for p in (n.pitch - 1, n.pitch + 1)
                          if 0 <= p <= 127 and p % 12 in evidence]
            if len(candidates) == 1 and n.part != 'bass':
                counts[n.part] += 1
                n = replace(n, pitch=candidates[0])
        corrected.append(n)
    label = 'stem continuity and observed cross-stem agreement'
    if global_key:
        label += f' ({global_key[0]})'
    return score.with_pitches(corrected), PitchReport(label, dict(counts))


def _guide_correction(notes: list[Note], aligned: list[Note]) -> tuple[list[Note], PitchReport]:
    guides = _by_part(sorted(aligned, key=lambda n: (n.start, n.pitch, n.end)))
    starts = {part: [n.start for n in group] for part, group in guides.items()}
    longest = {part: max(n.end - n.start for n in group) for part, group in guides.items()}
    result = []
    changes: Counter[str] = Counter()
    for n in notes:
        pitch = n.pitch
        if n.part in guides and n.part != 'drums':
            lo = bisect_left(starts[n.part], n.start - ATTACK_TOLERANCE - longest[n.part])
            hi = bisect_left(starts[n.part], n.end + ATTACK_TOLERANCE)
            matches = []
            for target in guides[n.part][lo:hi]:
                common = min(n.end + ATTACK_TOLERANCE, target.end) - max(
                    n.start - ATTACK_TOLERANCE, target.start)
                delta = (target.pitch - n.pitch + 6) % 12 - 6
                if common > .015 and abs(delta) <= MAX_CORRECTION:
                    matches.append((abs(delta), -common, delta))
            if matches:
                pitch += min(matches)[2]
        if pitch != n.pitch and 0 <= pitch <= 127:
            changes[n.part] += 1
            n = replace(n, pitch=pitch)
        result.append(n)
    return result, PitchReport('aligned MIDI guide', dict(changes))


def _monophonic(notes: list[Note], gap: float = .004) -> list[Note]:
    result: list[Note] = []
    for n in sorted(notes, key=lambda n: (n.start, -n.pitch)):
        if result and n.start < result[-1].end + gap:
            previous = result.pop()
            if n.start == previous.start:
                result.append(previous)
                continue
            if n.start - gap - previous.start >= .017:
                result.append(replace(previous, end=n.start - gap))
        result.append(n)
    return result



def _coherent_guitar_line(notes: list[Note], gap: float = .004) -> list[Note]:
    """Guard a guide-free guitar phrase against competing note fragments.

    Source-separated guitars can report an overtone over a still-ringing
    fundamental, or several pitches at precisely the same timestamp.
    The Tandy has one guitar *role* in this mix, not a polyphonic guitar
    instrument. Keep intentional strong attacks; do not give a weak
    transient priority just because it starts later.

    This helper is used only for guide-free automatic mixing. The proven
    PARATUNE MIDI-guide path keeps its historical voicing unchanged.
    """
    result: list[Note] = []

    def quality(n: Note) -> float:
        duration = n.end - n.start
        return (n.velocity + 28 * min(duration, .50)
                - .8 * max(0, n.pitch - 78))

    for n in sorted(notes, key=lambda n: (n.start, -quality(n), n.pitch)):
        if not result:
            result.append(n)
            continue
        old = result[-1]
        dt = n.start - old.start
        if abs(dt) <= .012:
            # Near-simultaneous pitch estimates are not two independent
            # guitar voices. Prefer stronger, sustained source evidence.
            if quality(n) > quality(old) + 4:
                result[-1] = n
            continue
        rest = n.start - old.end
        if rest <= .055 and n.pitch == old.pitch:
            # Quiet repeated fragments without a strong pick attack should
            # sound as one held tone. A strong re-attack remains a new note.
            if ((n.end - n.start <= .18 or
                     old.end - old.start <= .18) and
                    (n.velocity <= old.velocity - 8 or n.velocity < 65)):
                result[-1] = replace(old, end=max(old.end, n.end))
                continue
        if n.start < old.end + gap:
            duration = n.end - n.start
            # Very brief weak excursions should not steal the main riff.
            if (n.pitch != old.pitch and duration <= .13
                    and n.velocity <= old.velocity + 10
                    and old.end >= n.end + .055):
                continue
            if n.start <= old.end:
                # A legitimate new attack replaces the previous pitch,
                # with no artificial rest before the new note.
                clipped = n.start - old.start
                if clipped < .018:
                    if quality(n) > quality(old) + 6:
                        result[-1] = n
                    continue
                result[-1] = replace(old, end=n.start)
        result.append(n)
    return result


def _clip(notes: list[Note], duration: float | None) -> list[Note]:
    if duration is not None:
        notes = [replace(n, end=min(n.end, duration))
                 for n in notes if n.start < duration - .015]
    return sorted(notes, key=lambda n: (n.start, n.part, n.pitch))


def _vocal_level(n: Note) -> Note:
    return replace(n, velocity=min(113, max(70, round(12 + .94 * n.velocity))))


def _intro_counterline(guitar: list[Note], proposals: list[Note], low: list[Note],
                       root: int, end: float, period: float) -> tuple[list[Note], list[Note]]:
    """Recover a repeated midrange figure above recurring low guitar attacks."""
    if not isfinite(end):
        return guitar, []
    pedal = _monophonic([replace(n, part='harmony', velocity=66) for n in low
                         if n.pitch % 12 == root], .006)
    starts = [n.start for n in pedal]
    candidates = []
    for n in proposals:
        if (n.part == 'guitar' and 55 <= n.pitch <= 76 and n.pitch % 12 != root
                and n.velocity >= 29 and n.end - n.start >= .07 and n.end <= end
                and _near_note(pedal, starts, (n.start + n.end) / 2) is not None):
            candidates.append(n)
    repeat = Counter(n.pitch % 12 for n in candidates)
    candidates = [n for n in candidates if repeat[n.pitch % 12] >= 2]
    if len(candidates) < 4 or len({n.pitch % 12 for n in candidates}) < 2:
        return guitar, []
    chosen = _line([replace(n, velocity=max(57, n.velocity)) for n in candidates],
                   'guitar', _Groove((), (), tuple(starts), period))
    if not chosen:
        return guitar, []
    lead_starts = [n.start for n in chosen]
    riff = []
    for n in guitar:
        i = bisect_left(lead_starts, n.start - .045)
        overlaps = i < len(chosen) and chosen[i].start < n.end
        if n.start >= end or n.pitch % 12 != root or not overlaps:
            riff.append(n)
    lead_times = [n.start for n in guitar]
    for n in chosen:
        if n.start >= pedal[0].start - .24:
            i = bisect_left(lead_times, n.end)
            if i == 0 or guitar[i - 1].end <= n.start or guitar[i - 1].pitch % 12 == root:
                riff.append(replace(n, velocity=max(71, n.velocity)))
    # Where the guitar already carries the root itself it owns that pitch,
    # and there is no reason to duplicate it on another PSG voice.
    root_notes = sorted((n for n in riff if n.start < end and n.pitch % 12 == root),
                        key=lambda n: n.start)
    root_times = [n.start for n in root_notes]
    pedal = [n for n in pedal
             if _near_note(root_notes, root_times, (n.start + n.end) / 2) is None]
    return riff, pedal


def _reference_mix(notes: list[Note], reference: Reference,
                   aligned: list[Note]) -> list[Note]:
    """Use the guide for riff, floor and backbeat, with the recorded vocal attacks."""
    detected = _by_part(notes)
    parts = _by_part(aligned)
    bass_start = min((n.start for n in parts['bass']), default=float('inf'))
    vocal_start = min((n.start for n in parts['melody']), default=float('inf'))
    vocals = [_vocal_level(n) for n in detected['melody'] or parts['melody']]
    vocal_windows: list[tuple[float, float]] = []
    for n in sorted(parts['melody'], key=lambda n: n.start):
        if vocal_windows and n.start - vocal_windows[-1][1] <= .75:
            start, end = vocal_windows[-1]
            vocal_windows[-1] = (start, max(end, n.end))
        else:
            vocal_windows.append((n.start, n.end))
    window_starts = [a for a, b in vocal_windows]
    def sung(at: float) -> bool:
        i = bisect_right(window_starts, at) - 1
        return i >= 0 and at < vocal_windows[i][1]

    guitar_beats = [n for n in reference.notes if n.part == 'guitar']
    has_upper_guitar = any(n.pitch >= 55 for n in guitar_beats)
    if reference.beat_grid:
        units_per_beat = 1.
    else:
        attacks = sorted({n.start for n in reference.notes if n.part in ('bass', 'drums')})
        subdivisions = [b - a for a, b in zip(attacks, attacks[1:]) if .13 <= b - a <= .42]
        units_per_beat = 2 * median(subdivisions or [.25])
    guitar = []
    pedal = []
    roots: dict[int, int] = {}
    for n in guitar_beats:
        at, end = reference.time_at(n.start), reference.time_at(n.end)
        if reference.end is not None and at >= reference.end:
            continue
        # Keep the chord role through the following breath. A longer gap
        # marks an instrumental passage where the riff can come forward.
        if at >= vocal_start - .025 and (sung(at + .025) or sung(at - 1.0)):
            slot = round(n.start * 2 / units_per_beat)
            roots[slot] = min(roots.get(slot, n.pitch), n.pitch)
        elif n.pitch >= 55 or not has_upper_guitar:
            pitch = n.pitch
            while pitch > 92:
                pitch -= 12
            guitar.append(replace(n, start=at, end=end, pitch=pitch,
                                  velocity=90 if n.pitch >= 62 else 84))
        elif 45 <= n.pitch <= 54 and at < bass_start - .02:
            pedal.append(replace(n, start=at, end=min(end, bass_start),
                                 part='harmony', velocity=66))
    previous_root = None
    previous_slot = -2
    for slot, root in sorted(roots.items()):
        change = root != previous_root or slot - previous_slot > 2
        previous_slot, previous_root = slot, root
        if slot % 2 == 0 or change:
            start = reference.time_at(slot * units_per_beat / 2)
            end = reference.time_at((slot + 1.63) * units_per_beat / 2)
            fifth = 55 + (root + 7 - 55) % 12
            guitar.append(Note(start, end, fifth, 64 if change else 54, 'guitar', 30))

    bass = []
    drums: dict[int, Note] = {}
    for n in reference.notes:
        at = reference.time_at(n.start)
        if reference.end is not None and at >= reference.end:
            continue
        if n.part == 'bass':
            end = max(at + .105, reference.time_at(n.end) - .007)
            pitch = n.pitch
            while pitch < BASS_MIN:
                pitch += 12
            while pitch > BASS_MAX:
                pitch -= 12
            bass.append(Note(at, end, pitch,
                             66 if round(n.start * 2 / units_per_beat) % 2 else 79,
                             'bass', 33))
        if n.part == 'drums':
            if parts['bass'] and at < bass_start - .37:
                continue
            if n.pitch in (35, 36):
                pitch, length, velocity = 36, .072, 92
            elif n.pitch in (37, 38, 39, 40):
                pitch, length, velocity = 38, .059, 89
            elif n.pitch in (42, 44, 46, 49, 51, 57):
                pitch, length, velocity = 42, .046, 53
            else:
                continue
            slot = round(n.start * 2 / units_per_beat)
            if slot not in drums or velocity > drums[slot].velocity:
                drums[slot] = Note(at, at + length, pitch, velocity, 'drums', 0)
    foundation = _monophonic(bass or detected['bass'])
    intro = min(foundation[0].start if foundation else float('inf'),
                min((n.start for n in vocals), default=float('inf')))
    pedal = [replace(n, end=min(n.end, intro)) for n in pedal if n.start < intro - .017]
    return _clip(_monophonic(guitar or detected['guitar']) + _monophonic(pedal) +
                 foundation + vocals +
                 (list(drums.values()) or detected['drums']), reference.end)


def _automatic_mix(score: Score, notes: list[Note], proposals: list[Note],
                   preset: str, evidence: ScoreEvidence | None = None) -> list[Note]:
    """Give each part a register and keep guitar support under the vocal."""
    groups = _by_part(notes)
    bass, guitar, vocals = groups['bass'], groups['guitar'], groups['melody']
    bass_times = [n.start for n in bass]
    vocal_times = [n.start for n in vocals]
    other = sorted(groups['harmony'] + groups['accomp'], key=lambda n: n.start)
    other_times = [n.start for n in other]
    backing_attacks = {n.start for phrase in score.phrases
                       if phrase.part == 'guitar' and phrase.function == 'backing'
                       for n in phrase.notes}
    beats = score.beats
    period = median([b - a for a, b in zip(beats, beats[1:]) if .24 <= b - a <= 1.]
                    or [.5])
    supporting = []
    for n in guitar:
        if n.start in backing_attacks:
            bass_note = _near_note(bass, bass_times, (n.start + n.end) / 2)
            if bass_note and n.pitch % 12 == bass_note.pitch % 12:
                fifth = 55 + (bass_note.pitch + 7 - 55) % 12
                voice = _near_note(vocals, vocal_times, (n.start + n.end) / 2)
                if voice and fifth == _psg_pitch(voice):
                    fifth -= 12
                next_support = bisect_left(other_times, n.end)
                limit = other_times[next_support] if next_support < len(other) else float('inf')
                n = replace(n, pitch=fifth,
                            end=min(limit, max(n.end, n.start + .79 * period)),
                            velocity=max(44, min(64, n.velocity)))
        supporting.append(n)
    # A recurring low guitar pedal can be audible as its own tone in a bare
    # riff. Require stable, independent evidence and room before the band.
    first_bass = bass[0].start if bass else float('inf')
    first_vocal = vocals[0].start if vocals else float('inf')
    intro_end = min(first_bass, first_vocal)
    low = [n for n in proposals if n.part == 'guitar' and 28 <= n.pitch <= 52
           and n.velocity >= 58 and n.end - n.start >= .085 and n.end <= intro_end]
    counts = Counter(n.pitch % 12 for n in low)
    pedal = []
    if evidence is not None and evidence.guitar_support:
        pedal = [replace(n, end=min(n.end, intro_end)) for n in evidence.guitar_support
                 if n.start < intro_end - .045]
    elif counts and guitar:
        root, repeats = counts.most_common(1)[0]
        if repeats >= 3:
            supporting, pedal = _intro_counterline(supporting, proposals, low, root,
                                                  intro_end, period)
    for n in pedal:
        i = bisect_left(other_times, n.end)
        if i == 0 or other[i - 1].end <= n.start:
            groups['harmony'].append(n)
    groups['guitar'] = _coherent_guitar_line(supporting, .006)
    groups['melody'] = [_vocal_level(n) for n in vocals]
    groups['bass'] = [replace(n, velocity=min(86, max(56, n.velocity))) for n in bass]
    return normalize((n for group in groups.values() for n in group), preset, preserve=True)


def arrange_tuned(score: Score, proposals: list[Note], preset: str = 'balanced',
                  reference: Reference | None = None, *,
                  evidence: ScoreEvidence | None = None) -> tuple[list[Note], PitchReport]:
    """Apply small pitch repairs, then build a single hardware-ready mix."""
    if reference is not None:
        notes = sorted(arrange_score(score, preset), key=lambda n: (n.start, n.part, n.pitch))
        aligned = reference.aligned_notes()
        corrected, report = _guide_correction(notes, aligned)
        return _reference_mix(corrected, reference, aligned), replace(report, reference_mix=True)
    tuned, stem_repairs = _stem_correction(score)
    stem_offsets = {}
    if evidence is not None:
        stem_offsets = {role: round(track.cents, 1)
                        for role, track in sorted(evidence.pitches.items())}
        stem_repairs += evidence.pitch_corrections
    tuned, ensemble = _ensemble_correction(tuned, Counter())
    report = replace(ensemble, corrected=dict(stem_repairs + Counter(ensemble.corrected)),
                     stem_offsets=stem_offsets, stem_repairs=dict(stem_repairs),
                     ensemble_repairs=ensemble.corrected)
    return _automatic_mix(tuned, arrange_score(tuned, preset), proposals, preset,
                          evidence), report
