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
    merged_source_fragments: int = 0
    removed_pitch_jitter: int = 0

    def summary(self) -> str:
        return (
            "Guide-free, source-relative score cleanup\n"
            f"Source candidates examined: {self.source_notes}\n"
            f"Isolated register spikes removed: {self.removed_register_spikes}\n"
            f"Same-pitch source fragments combined before arranging: {self.merged_source_fragments}\n"
            f"Weak pitch-jitter fragments removed before arranging: {self.removed_pitch_jitter}\n"
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
            local_register = median(x.pitch for x in neighbors)
            # Guitar beeps are often octave+ harmonics: a short lone
            # high note just 12 semitones above a stable guitar register
            # can be disruptive. Real solos form a recurring local line.
            threshold = (12 if _part == 'guitar' and
                         n.pitch > local_register else 19)
            if abs(n.pitch-local_register) < threshold:
                continue
            # An independent high or low passage is not a spurious spike.
            if any(abs(n.pitch-x.pitch)<=3 for x in neighbors):
                continue
            typical=median(x.velocity for x in neighbors)
            weak=n.velocity<max(66, typical*.83)
            if weak or n.end-n.start < (.16 if _part == 'guitar'
                                        else .13):
                discard.add(source_index)
    result=[n for i,n in enumerate(source) if i not in discard]
    return result,PolishReport(source_notes=len(source),
                               removed_register_spikes=len(discard))



def stabilize_audio_candidates(notes: Iterable[Note]
                               ) -> tuple[list[Note], dict[str, int]]:
    """Join unreliable stem restarts BEFORE the phrase finder picks notes.

    Work per part AND pitch so octave partials/chord notes between two
    same-pitch estimates cannot hide a repeated detector restart.
    Real new pick/syllable attacks and drum-aligned bass/riff attacks stay.
    This deliberately uses NO key, song title, genre or specific pitch.
    """
    source=list(notes)
    rhythmic = sorted(n.start for n in source if
                      n.part=='drums' and n.pitch in (36,38))
    pitched:dict[tuple[str,int,int],list[Note]]=defaultdict(list)
    by_role:dict[str,list[Note]]=defaultdict(list)
    for n in source:
        if n.part != 'drums':
            pitched[n.part,n.pitch,n.program].append(n)
            by_role[n.part].append(n)
    for role in by_role:
        by_role[role].sort(key=lambda n:n.start)
    role_times={role:[n.start for n in track] for role,track
                in by_role.items()}

    def on_beat(t:float) -> bool:
        i=bisect_left(rhythmic,t-.038)
        return i<len(rhythmic) and rhythmic[i]<=t+.038

    joins=0
    merged=[]
    for (role,_,_), track in pitched.items():
        track.sort(key=lambda n:(n.start,n.end))
        result:list[Note]=[]
        gap_limit={'melody':.095,'guitar':.075,'bass':.050,
                   'harmony':.060,'accomp':.060}.get(role,.055)
        close_attack={'melody':.290,'guitar':.240,'bass':.190,
                      'harmony':.215,'accomp':.215}.get(role,.200)
        for n in track:
            if result:
                old=result[-1]
                gap=n.start-old.end
                spacing=n.start-old.start
                new_strong=(n.velocity>=max(90,old.velocity+17))
                new_accent=(role in ('bass','guitar') and
                            spacing>=.10 and on_beat(n.start) and
                            n.velocity>=old.velocity-5)
                deliberate_long=(old.end-old.start>=.24 and
                                 n.end-n.start>=.22 and
                                 spacing>=.26 and n.velocity>=80)
                # Do not create a sustained same-pitch bridge across a
                # *credible* intervening change in the actual musical
                # line. Ignore weak fleeting chromatic pitch wobble.
                other_line=by_role.get(role, [])
                times=role_times.get(role, [])
                lo=bisect_left(times,old.end-.035)
                hi=bisect_left(times,n.start+.021)
                intervening=any(
                    x.pitch != n.pitch and
                    x.velocity >= min(old.velocity,n.velocity)-7 and
                    x.end-x.start >= .07
                    for x in other_line[lo:hi])
                if (-.10 <= gap <= gap_limit and
                        (spacing <= close_attack or
                         n.velocity<=old.velocity-12) and
                        not new_strong and not new_accent and
                        not deliberate_long and not intervening):
                    result[-1]=replace(old,end=max(old.end,n.end))
                    joins+=1
                    continue
            result.append(n)
        merged.extend(result)

    # One isolated weak short semitone/tone wobble inside a vocal
    # sustain is likely pitch-estimator jitter, not a performed melody
    # leap. A real strong ornament or new melodic phrase survives.
    by_role:dict[str,list[Note]]=defaultdict(list)
    for n in merged:
        by_role[n.part].append(n)
    output=[n for n in source if n.part=='drums']
    jitter=0
    for role,track in by_role.items():
        track.sort(key=lambda n:(n.start,n.end,n.pitch))
        if role not in ('melody','guitar'):
            output.extend(track)
            continue
        i=0
        while i<len(track):
            current=track[i]
            # After same-pitch joins, a faint semitone wobble may sit
            # entirely inside the now-held note. Remove only the short
            # weak outlier; leave legitimate ornaments and longer notes.
            if (current.end-current.start<=.095 and
                    any(anchor.pitch != current.pitch and
                        abs(anchor.pitch-current.pitch)<=2 and
                        anchor.start<=current.start+.001 and
                        anchor.end>=current.end-.001 and
                        anchor.velocity>=current.velocity+15
                        for anchor in track[max(0,i-6):i])):
                jitter+=1
                i+=1
                continue
            if i+2<len(track):
                a,b,c=track[i:i+3]
                if (a.pitch==c.pitch and
                        0<abs(b.pitch-a.pitch)<=2 and
                        b.end-b.start<=.095 and
                        b.velocity<=min(a.velocity,c.velocity)-11 and
                        a.end-a.start>=.075 and
                        c.end-c.start>=.075 and
                        -.025<=b.start-a.end<=.055 and
                        -.025<=c.start-b.end<=.055):
                    # Only bridge a detector blip when the surrounding
                    # note was clearly the same held phrase; never stretch
                    # beyond the next valid attack if it is independent.
                    output.append(replace(a,end=max(a.end,c.end)))
                    jitter+=1
                    joins+=1
                    i+=3
                    continue
            output.append(track[i])
            i+=1
    return sorted(output,key=lambda n:(n.start,n.end,n.part,n.pitch)),{
        'merged_source_fragments':joins,
        'removed_pitch_jitter':jitter,
    }


def connect_legato_gaps(notes: Iterable[Note]
                        ) -> tuple[list[Note], int]:
    """Smooth only unintentional micro-rests between committed long notes.

    This does not overlap notes, move any note-on, remove real rests,
    fabricate harmony or shorten a note that was already committed.
    Drum and bass timing is unchanged. Different-pitch transitions
    use PSG legato (not a crossfade, which PSG hardware cannot do).
    """
    source=list(notes)
    by_part:dict[str,list[Note]]=defaultdict(list)
    for n in source:
        by_part[n.part].append(n)
    output=[]
    links=0
    for role,track in by_part.items():
        track.sort(key=lambda n:(n.start,n.end,n.pitch))
        if role not in ('guitar','melody','harmony','accomp'):
            output.extend(track)
            continue
        allowed=.085 if role=='melody' else .065
        for i,n in enumerate(track):
            if i+1 < len(track):
                next_note=track[i+1]
                gap=next_note.start-n.end
                if (0 < gap<=allowed and
                        n.end-n.start>=.10 and
                        next_note.end-next_note.start>=.10 and
                        n.velocity>=56 and next_note.velocity>=56):
                    n=replace(n,end=next_note.start)
                    links+=1
            output.append(n)
    return sorted(output,key=lambda n:(n.start,n.end,n.part,n.pitch)),links


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
