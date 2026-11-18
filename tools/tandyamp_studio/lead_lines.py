"""Recover sung pitches and instrumental responses in the lead voice."""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import replace
from statistics import median
from typing import TYPE_CHECKING

from arranger import Note

if TYPE_CHECKING:
    from stem_pitch import StemPitch


def vocal_candidates(source: list[Note], sung: list[Note], signal: StemPitch,
                     beat: float) -> dict[Note, float]:
    """Recover quiet notes supported by both the decoder and the vocal stem."""
    starts = [n.start for n in sung]
    proposals = {}
    for n in source:
        midpoint = (n.start + n.end) / 2
        i = bisect_right(starts, midpoint)
        left = sung[i - 1] if i else None
        right = sung[i] if i < len(sung) else None
        start = max(n.start, left.end) if left else n.start
        end = min(n.end, right.start) if right else n.end
        duration = end - start
        # Decoder release tails can overlap a real new syllable by a
        # few frames. Keep the boundaries of the accepted lead intact.
        if duration < max(.095, min(.17, beat * .28), .70 * (n.end - n.start)):
            continue
        note = replace(n, start=start, end=end)
        heard = signal.sustain_strength(note)
        if heard is None or heard < .65:
            continue
        context = [a.pitch for a in (left, right) if a is not None and
                   max(a.start - end, start - a.end) <= max(1.1, 3.5 * beat)]
        if not context:
            continue
        # A singing voice can produce a stronger second harmonic than
        # its fundamental. Follow the surrounding register only when the
        # lower fundamental is also present in this very note.
        center = median(context)
        if note.pitch - center >= 9:
            lower = replace(note, pitch=note.pitch - 12)
            low_strength = signal.sustain_strength(lower)
            if low_strength is not None and low_strength >= .25:
                note = lower
            elif duration < .24 and all(abs(note.pitch - p) >= 9 for p in context):
                continue
        proposals[note] = duration * (.5 + heard)
    return proposals


def vocal_sections(spans: list[tuple[float, float]], beat: float
                   ) -> list[tuple[float, float]]:
    """Keep the vocal in front across the spaces between syllables."""
    sections: list[tuple[float, float]] = []
    for start, end in sorted(spans):
        if sections and start - sections[-1][1] <= max(.65, 2 * beat):
            sections[-1] = (sections[-1][0], max(end, sections[-1][1]))
        else:
            sections.append((start, end))
    return sections


def instrumental_answers(line: list[Note], sections: list[tuple[float, float]],
                         bass: list[Note], guitar: list[Note], beat: float,
                         levels: dict[str, list[float]], signal: StemPitch | None
                         ) -> list[list[Note]]:
    """Admit an audible, independently moving phrase while the singer rests."""
    section_ends = [end for _, end in sections]
    foundation = [(track, [n.end for n in track]) for track in (bass, guitar)]
    own_levels = levels.get('harmony', [])
    competing = [levels[role] for role in ('bass', 'guitar', 'melody') if role in levels]
    groups: list[list[Note]] = []
    previous_section = -1
    for n in line:
        i = bisect_right(section_ends, n.start)
        if i < len(sections) and sections[i][0] < n.end:
            continue
        if own_levels:
            lo = int(n.start / .05)
            hi = max(lo + 1, int(n.end / .05))
            own = max(own_levels[lo:hi], default=0.)
            other = max((max(row[lo:hi], default=0.) for row in competing), default=0.)
            if own < max(.0001, other * .22):
                continue
        heard = signal.sustain_strength(n) if signal is not None else None
        if (heard is not None and heard < .42) or (heard is None and n.velocity < 66):
            continue
        if (not groups or i != previous_section
                or n.start - groups[-1][-1].end > max(.36, 1.25 * beat)):
            groups.append([])
        groups[-1].append(n)
        previous_section = i

    answers = []
    for group in groups:
        if len(group) < 3 or group[-1].end - group[0].start < 1.5 * beat:
            continue
        independent = set()
        for n in group:
            overlaps = []
            for track, ends in foundation:
                i = bisect_right(ends, n.start)
                while i < len(track) and track[i].start < n.end:
                    other = track[i]
                    if n.pitch % 12 == other.pitch % 12:
                        overlaps.append((max(n.start, other.start), min(n.end, other.end)))
                    i += 1
            # Count a shared bass/guitar unison once on the time axis.
            end = n.start
            doubled = 0.
            for a, b in sorted(overlaps):
                doubled += max(0., b - max(a, end))
                end = max(b, end)
            if doubled < .5 * (n.end - n.start):
                independent.add(n.pitch % 12)
        if len(independent) >= 2:
            answers.append(group)
    return answers
