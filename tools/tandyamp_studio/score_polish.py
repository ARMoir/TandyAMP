"""Evidence-based cleanup for guide-free audio-to-MIDI, never MIDI-guided takes.

The three tiny rules are portable across styles:
1. Reject isolated, low-evidence *local register* outliers.
2. Merge adjacent same-pitch detector restarts, unless there is a credible
   new attack (accent, strength increase, or sufficiently separated onset).
3. Once a part commits to a note, do not shorten it for a later candidate.
No chord invention, quantization, genre labels or song-specific pitches.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, replace
from statistics import median
from typing import Iterable

from arranger import Note


@dataclass(frozen=True)
class PolishReport:
    source_notes: int = 0
    removed_register_spikes: int = 0
    merged_duplicate_attacks: int = 0
    declined_competing_attacks: int = 0

    def summary(self) -> str:
        return (
            "Guide-free, source-relative score cleanup\n"
            f"Source candidates examined: {self.source_notes}\n"
            f"Isolated register spikes removed: {self.removed_register_spikes}\n"
            f"Likely duplicate same-pitch attacks merged: {self.merged_duplicate_attacks}\n"
            f"Later competing notes declined (no partial note): {self.declined_competing_attacks}\n"
        )


def reject_register_spikes(notes: Iterable[Note]
                           ) -> tuple[list[Note], PolishReport]:
    """Filter extreme isolated notes only when contextual evidence agrees.

    Do not delete legitimate solo jumps, a track changing register, or
    repeated high/low melody figures. Requires local material before and
    after, no neighboring note near the alleged outlier, and low
    relative velocity or a very short glitch. The drum channel is not a
    pitched register and is never touched.
    """
    source=list(notes)
    by_part: dict[str,list[tuple[int,Note]]] = defaultdict(list)
    for i,n in enumerate(source):
        if n.part in ('bass','guitar','melody','harmony','accomp'):
            by_part[n.part].append((i,n))
    discard:set[int] = set()
    for _part, sequence in by_part.items():
        sequence.sort(key=lambda row:row[1].start)
        for j,(source_index,n) in enumerate(sequence):
            before=[other for _,other in sequence[max(0,j-14):j]
                    if 0 <= n.start-other.start <= .80]
            after=[other for _,other in sequence[j+1:j+15]
                   if 0 <= other.start-n.start <= .80]
            if len(before)<2 or len(after)<2:
                continue
            neighbors=before+after
            if abs(n.pitch-median(x.pitch for x in neighbors)) < 19:
                continue
            # An independent high or low passage is not a spurious spike.
            if any(abs(n.pitch-x.pitch)<=3 for x in neighbors):
                continue
            typical=median(x.velocity for x in neighbors)
            weak=n.velocity<max(66, typical*.83)
            if weak or n.end-n.start < .13:
                discard.add(source_index)
    result=[n for i,n in enumerate(source) if i not in discard]
    return result,PolishReport(source_notes=len(source),
                               removed_register_spikes=len(discard))


def merge_duplicate_attacks(notes: Iterable[Note], *,
                            groove: Iterable[float] = ()
                            ) -> tuple[list[Note], int]:
    """Merge probable detector restarts, not genuine new pick/syllable attacks.

    A note is only joined to its immediately preceding note in its part.
    Its original onset/velocity are preserved when the duplicate is joined;
    no newly invented note or pitch is introduced. Drum notes stay intact.
    """
    source=list(notes)
    strong_drums=sorted(n.start for n in source
                        if n.part=='drums' and n.pitch in (36,38))
    strong_drums.extend(float(t) for t in groove)
    strong_drums.sort()

    def near_accent(t:float) -> bool:
        j=bisect_left(strong_drums,t-.045)
        return j<len(strong_drums) and strong_drums[j]<=t+.045

    groups:dict[str,list[Note]]=defaultdict(list)
    for n in source:
        groups[n.part].append(n)
    result:list[Note]=[]
    merges=0
    max_spacing={'bass':.15,'guitar':.15,'melody':.19,
                 'harmony':.16,'accomp':.16}
    for part,track in groups.items():
        if part=='drums':
            result.extend(track)
            continue
        track.sort(key=lambda n:(n.start,n.pitch,-n.end))
        output:list[Note]=[]
        for n in track:
            if output:
                old=output[-1]
                gap=n.start-old.end
                onset_spacing=n.start-old.start
                accent=(near_accent(n.start) and
                        onset_spacing>=.10 and n.velocity>=74)
                strong=(n.velocity>=max(90,old.velocity+18))
                # Protect real rhythmic re-attacks even on the same pitch.
                if (old.pitch==n.pitch and -.035<=gap<=.055 and
                        not strong and not accent and
                        (onset_spacing<=max_spacing.get(part,.15) or
                         n.velocity<=old.velocity-17)):
                    output[-1]=replace(old,end=max(old.end,n.end))
                    merges+=1
                    continue
            output.append(n)
        result.extend(output)
    return sorted(result,key=lambda n:(n.start,n.end,n.part,n.pitch)),merges


def commit_role_notes(notes: Iterable[Note]) -> tuple[list[Note],int]:
    """Do not start a second different pitch before the first completes.

    Works on already selected monophonic musical roles, not raw
    polyphonic chords. Never chop, defer or retime a selected note:
    competing later proposals are declined whole. Real simultaneous
    near-onset alternatives are already resolved by the phrase engine.
    """
    source=list(notes)
    groups:dict[str,list[Note]]=defaultdict(list)
    for n in source:
        groups[n.part].append(n)
    retained:list[Note]=[]
    declined=0
    for part,track in groups.items():
        if part=='drums':
            retained.extend(track)
            continue
        track.sort(key=lambda n:(n.start,-(n.end-n.start)*n.velocity,
                                 n.pitch))
        accepted:list[Note]=[]
        for n in track:
            if accepted and n.start < accepted[-1].end-1e-7:
                # Commit the first audible note to its original note-off,
                # rather than creating a staccato fragment.
                declined+=1
                continue
            accepted.append(n)
        retained.extend(accepted)
    return sorted(retained,key=lambda n:(n.start,n.end,n.part,n.pitch)),declined
