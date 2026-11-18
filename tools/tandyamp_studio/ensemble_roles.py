"""Conservative, genre-independent Tandy ensemble voice admission.

The upstream transcription reconstructs a few musical lines. This final
stage keeps those lines *whole* and admits optional supporting notes
only when the whole original note fits the available playback budget.

No automatic chord generation, instrument- or song-specific melody rules,
dynamic "winner each tick", pitch quantization or forced channel filling.
For the real Tandy SN76489, three simultaneous PSG pitches exist;
PIT2/SPK4 may carry a separate *eligible* bass in ADAPT/BASS modes.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from arranger import BASS_MIN, BASS_MAX, Note, _psg_pitch


@dataclass(frozen=True)
class EnsembleReport:
    protected_notes: int
    offered_support: int
    accepted_support: int
    rejected_short_or_weak: int
    rejected_competition: int

    def summary(self) -> str:
        return (
            "Stable ensemble, no new notes or channel filling\n"
            "Protected lead/foundation/companion: {}\n"
            "Proposed support: {}\n"
            "Whole support notes admitted: {}\n"
            "Weak/brief support declined: {}\n"
            "Support declined to avoid voice contention: {}\n"
        ).format(self.protected_notes, self.offered_support,
                 self.accepted_support, self.rejected_short_or_weak,
                 self.rejected_competition)


def _speaker_bass(played: list[Note], spk4: str) -> Note | None:
    """Potential low SPK4 role, never a guaranteed audible PIT2 voice."""
    if spk4 == 'off':
        return None
    bass = [n for n in played if n.part == 'bass' and
            BASS_MIN <= n.pitch <= BASS_MAX and n.velocity >= 58]
    if len(bass) != 1:
        return None
    others = {_psg_pitch(n) for n in played if n.part != 'bass'}
    required = 2 if spk4 == 'adapt' else 3
    return bass[0] if len(others) >= required else None


def _available(played: list[Note], spk4: str) -> bool:
    """Check the physical tone budget over one interval.

    SPK4 speaker eligibility depends on firmware, actual attenuation and
    volume; this is an upper-bound check, not a promise it will sound.
    """
    if not played:
        return True
    speaker = _speaker_bass(played, spk4)
    if speaker is not None:
        return len({_psg_pitch(n) for n in played
                    if n is not speaker}) <= 3
    return len({_psg_pitch(n) for n in played}) <= 3


def _fits_whole_note(note: Note, accepted: list[Note], spk4: str) -> bool:
    overlapping = [n for n in accepted if n.start < note.end
                   and n.end > note.start and n.part != 'drums']
    if not overlapping:
        return True

    boundaries = {note.start, note.end}
    for n in overlapping:
        boundaries.add(max(n.start, note.start))
        boundaries.add(min(n.end, note.end))
    points = sorted(boundaries)
    for start, end in zip(points, points[1:]):
        if end - start <= 1e-8:
            continue
        mid = (start + end) / 2
        live = [n for n in overlapping if n.start <= mid < n.end]
        # A simultaneous note with the same effective pitch merely
        # doubles the PSG voice and can make an unnecessary reattack.
        speaker = _speaker_bass(live + [note], spk4)
        if any(_psg_pitch(n) == _psg_pitch(note)
               for n in live if n is not speaker):
            return False
        if not _available(live + [note], spk4):
            return False
    return True


def arrange_ensemble(notes: Iterable[Note], *,
                     spk4: str = 'off') -> tuple[list[Note], EnsembleReport]:
    """Protect full source lines; add whole, non-competing accompaniment.

    'melody' is the identified lead, 'guitar' means the principal pitched
    companion (possibly synth, keyboard or plucked instrument), and 'bass'
    means the low harmonic foundation. Other parts are *optional support*.
    These are musical functions, not mandatory instrument timbres.
    If a piece has no singer, guitars or drums, don't invent any.
    """
    if spk4 not in ('off', 'bass', 'adapt'):
        raise ValueError('SPK4 must be off, bass, or adapt')

    source = [n for n in notes if n.end > n.start]
    anchors = [n for n in source if n.part in
               ('melody', 'guitar', 'bass', 'drums')]
    support = [n for n in source if n.part not in
               ('melody', 'guitar', 'bass', 'drums')]
    anchors.sort(key=lambda n: (n.start, n.end, n.part, n.pitch))

    # Complete note admission rather than frequent note-on/off chopping.
    # Sort simultaneous candidates by real duration and strength. Once a
    # phrase owns the spare PSG capacity, a new weak note cannot steal it.
    support.sort(key=lambda n: (n.start,
                                -(n.end-n.start) * n.velocity,
                                n.pitch, n.part))
    accepted: list[Note] = []
    too_short = 0
    contention = 0
    for note in support:
        # These are conservative evidence gates, not song-specific scales.
        if (note.end - note.start < .19 or note.velocity < 66 or
                note.part == 'accomp' and
                (note.end - note.start < .32 or note.velocity < 79)):
            too_short += 1
            continue
        if not _fits_whole_note(note, anchors + accepted, spk4):
            contention += 1
            continue
        accepted.append(note)

    output = sorted(anchors + accepted, key=lambda n:
                    (n.start, n.end, n.part, n.pitch))
    return output, EnsembleReport(
        protected_notes=len(anchors),
        offered_support=len(support),
        accepted_support=len(accepted),
        rejected_short_or_weak=too_short,
        rejected_competition=contention,
    )
