"""KISS TandyAMP arrangement: rhythm foundation + guitar + vocal.

One genuinely simple *offline* selection pass. Unlike the more generous
MUSICAL arranger, CORE deliberately writes no more than three distinct
pitched notes at a time (bass, riff and vocal where available) plus a
single PSG noise/drum stream. It never creates extra harmony for density
or to force PC-speaker activation. The source can contain many more notes.

The Tandy player itself is unchanged. SPK4 remains optional; with only
three total pitched notes its existing four-voice gate often leaves bass
on the PSG, which is the correct trade-off for a sparse arrangement.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from typing import Iterable

from arranger import Note, _psg_pitch, voice_coverage
from musical_arranger import _drum_groove, _linked_phrases


@dataclass(frozen=True)
class CoreReport:
    source_pitched: int
    chosen_pitched: int
    retained_source_notes: int
    source_drums: int
    chosen_drums: int
    role_counts: dict[str, int]

    def as_text(self) -> str:
        return (
            'TandyAMP Studio CORE - KISS hardware arrangement\n'
            'Bass + drums provide the groove; guitar connects to vocals.\n'
            'At most THREE distinct pitched PSG parts plus ONE PSG noise part.\n'
            'No invented chords, beat grid, velocity compression or extra notes.\n'
            'SPK4 is optional, never forced by adding unwanted harmony.\n'
            'Original pitched notes: {}\n'
            'Unique source pitched notes used: {}\n'
            'Output pitched note fragments: {}\n'
            'Source drum hits: {}\n'
            'Output drum hits: {}\n'
            'Retained pitched source roles: {}\n'
            'Musical quality still requires physical Tandy listening.\n'
        ).format(self.source_pitched, self.retained_source_notes,
                 self.chosen_pitched, self.source_drums, self.chosen_drums,
                 repr(dict(sorted(self.role_counts.items()))))


def _select_one(ids: list[int], notes: list[Note], chosen: set[int],
                linked: set[int], now: float) -> int | None:
    """Choose one continuous, credible note for a single musical function."""
    if not ids:
        return None

    def quality(i: int) -> tuple[float, float, int]:
        n = notes[i]
        duration = n.end - n.start
        score = 4.0 * n.velocity + 90.0 * min(duration, .55)
        if i in linked:
            score += 110
        if i in chosen:
            score += 195   # hold a meaningful phrase rather than flicker
        elif now - n.start <= .035 and n.velocity >= 85:
            score += 235   # allow a strong new riff/vocal attack
        if n.pitch >= 84 and n.velocity < 62 and duration < .14:
            score -= 480  # short, quiet high harmonics often are bleed
        if n.velocity < 42 and duration < .09:
            score -= 210
        # Prefer a clear lower guitar fundamental to a near-tied harmonic.
        if n.part == 'guitar' and n.pitch > 80:
            score -= min(120, (n.pitch-80)*12)
        return score, -n.start, -i

    return max(ids, key=quality)


def _drums_core(notes: list[Note]) -> list[Note]:
    """Keep kick/snare groove and useful hats, not every transient in a cloud.

    No quantizing or invented beats. A hat under 100ms after the preceding
    hat is optional detail; removing it frees the shared noise generator.
    """
    reduced = _drum_groove(notes)
    result = []
    last_hat = -1e6
    for n in reduced:
        if n.pitch == 42:
            if n.start - last_hat < .10:
                continue
            last_hat = n.start
        result.append(n)
    return result


def arrange_core(notes: Iterable[Note],
                 spk4: str = 'adapt') -> tuple[list[Note], CoreReport]:
    """Keep real bass/riff/vocal voices; admit support only in their gaps.

    The source role labels are transcription estimates. An existing MIDI
    with no dedicated guitar stem still retains one meaningful harmony
    line in the available role, without pretending to identify a guitarist.
    Every selected note retains its original pitch/velocity/timing, except
    where a competing note interrupts its duration.
    """
    if spk4 not in ('off', 'bass', 'adapt'):
        raise ValueError('SPK4 must be off, bass, or adapt')
    source_all = [n for n in notes if n.end > n.start]
    notes = [n for n in source_all if n.part != 'drums']
    drums = [n for n in source_all if n.part == 'drums']
    linked = _linked_phrases(notes)
    events: list[tuple[float,int,int]] = []
    for i,n in enumerate(notes):
        events.extend(((n.start,1,i),(n.end,0,i)))
    events.sort(key=lambda x:(x[0],x[1],x[2])) # offs before ons

    active: set[int] = set()
    chosen: set[int] = set()
    chosen_ever: set[int] = set()
    opened: dict[int,float] = {}
    emitted: list[Note] = []
    idx = 0

    while idx < len(events):
        at = events[idx][0]
        while idx < len(events) and events[idx][0] == at:
            _, on, i = events[idx]
            (active.add if on else active.discard)(i)
            idx += 1

        def part(part_name: str) -> list[int]:
            return [i for i in active if notes[i].part == part_name]

        # A weak isolated upper harmonic is not a lead while stronger
        # musical material plays. Do not remove a genuine solo note.
        strong_other = any(notes[i].velocity >= 75 and
                           notes[i].pitch <= 83 for i in active)
        def clean_role(role: str) -> list[int]:
            ids = part(role)
            if not strong_other:
                return ids
            return [i for i in ids
                    if not (notes[i].pitch >= 84 and
                            notes[i].velocity < 58 and
                            notes[i].end-notes[i].start < .14 and
                            i not in linked)]

        # One voice per core musical job: prevents a guitar chord, vocal
        # harmonic cloud or multiple concurrent bass fundamentals from
        # monopolizing the entire PSG.
        selected: set[int] = set()
        pitched: set[int] = set()
        def add(i: int | None) -> None:
            if i is None or len(selected) >= 3:
                return
            pitch = _psg_pitch(notes[i])
            if pitch not in pitched:
                selected.add(i)
                pitched.add(pitch)

        add(_select_one(clean_role('bass'),notes,chosen,linked,at))
        add(_select_one(clean_role('guitar'),notes,chosen,linked,at))
        add(_select_one(clean_role('melody'),notes,chosen,linked,at))

        # If lead/guitar has a duplicate PSG pitch, give the freed slot to
        # a real continuing independent line rather than duplicating it.
        # Only stable support from the source is admitted. No manufactured
        # accompaniment and no obligatory third PSG note.
        room = 3 - len(selected)
        if room:
            # If a real bass and lead already sound, any optional
            # background note must be exceptionally clear and sustained.
            # A guitar-led band should not be buried under keyboards.
            # But a simple three-part melody (DEMO) must *keep* its quiet,
            # consistently repeated middle harmony. Phrase evidence wins
            # over a blanket minimum velocity.
            busy_guitar = bool(part('bass') and part('guitar'))
            def meaningful_support(i: int) -> bool:
                n = notes[i]
                duration = n.end - n.start
                if n.part == 'accomp':
                    return (duration >= .40 and n.velocity >= 98)
                if busy_guitar:
                    return (duration >= .38 and n.velocity >= 102)
                if part('bass') and part('melody'):
                    return ((i in linked and duration >= .25 and
                             n.velocity >= 62) or
                            (duration >= .36 and n.velocity >= 92))
                return duration >= .19 and n.velocity >= 78

            support = [i for i in active if notes[i].part in
                       ('harmony','accomp') and
                       meaningful_support(i) and
                       _psg_pitch(notes[i]) not in pitched]
            # Prefer independently moving lower voice in bassless music.
            # When there is a bass+riff+vocal trio, there is no slot for
            # accompaniment. This is intentional, not a missing note.
            support.sort(key=lambda i: (
                -int(i in chosen), -int(i in linked),
                notes[i].pitch if not part('bass') else 0,
                -notes[i].velocity, i))
            # Bass-led songs allow at most one extra background line.
            # Counterpoint without a recognized bass/riff/vocal can still
            # need two independent parts, as in the Brandenburg benchmark.
            allowed_support = 1 if part('bass') else 2
            included_support = 0
            for i in support:
                old_count = len(selected)
                add(i)
                included_support += len(selected)-old_count
                if len(selected) == 3 or included_support >= allowed_support:
                    break

        for i in chosen-selected:
            if at-opened[i] >= .012:
                emitted.append(replace(notes[i],start=opened[i],end=at))
            opened.pop(i,None)
        for i in selected-chosen:
            opened[i] = at
        chosen = selected
        chosen_ever.update(selected)

    # Last event is a note-off; defensive finalization for edge cases.
    if events:
        end = events[-1][0]
        for i in chosen:
            if end-opened[i] >= .012:
                emitted.append(replace(notes[i],start=opened[i],end=end))

    drum_out = _drums_core(drums)
    output = sorted(emitted+drum_out,
                    key=lambda n:(n.start,n.end,n.part,n.pitch))
    report = CoreReport(
        source_pitched=len(notes),chosen_pitched=len(emitted),
        retained_source_notes=len(chosen_ever),source_drums=len(drums),
        chosen_drums=len(drum_out),
        role_counts=dict(Counter(notes[i].part for i in chosen_ever)))
    return output, report
