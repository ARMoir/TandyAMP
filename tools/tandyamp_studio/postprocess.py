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


def clean_stem_notes(notes: list[Note], part: str,
                     preservation: str = 'clean') -> list[Note]:
    """Remove weak artifacts while optionally preserving original polyphony.

    Full mode retains every credible lead/guitar pitch until the *final*
    hardware-aware allocator chooses the available PSG/SPK4 voices. Clean
    mode reproduces V5's per-stem monophonic melody / two-note guitar cap.
    """
    if preservation not in ('clean', 'full'):
        raise ValueError('Note preservation must be clean or full')
    if not notes:
        return []
    if preservation == 'full':
        # Lightly de-noise but keep the candidate counter-melodies and short
        # guitar attacks. Final PSG/PIT2 hardware limits are applied later.
        floor = {'bass': 22, 'melody': 24, 'harmony': 28}.get(part, 24)
        shortest = {'bass': .055, 'melody': .050, 'harmony': .060}.get(part, .055)
        fraction, ceiling = .46, 55
    else:
        # Legacy V5 cleanup for a reproducible A/B control.
        floor = {'bass': 30, 'melody': 31, 'harmony': 42}.get(part, 35)
        shortest = {'bass': .090, 'melody': .085, 'harmony': .115}.get(part, .100)
        fraction, ceiling = .62, 67
    typical = median(n.velocity for n in notes)
    threshold = max(floor, min(ceiling, int(typical*fraction)))
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
            # This heuristic describes a *sequence*, not three overlapping
            # chord tones. Negative gaps used to count as "near" and could
            # delete a legitimate quiet upper chord voice in Full mode.
            near = (-.010 <= n.start - before.end <= .10 and
                    -.010 <= after.start - n.end <= .10)
            if (near and before.pitch == after.pitch and
                    abs(before.pitch-n.pitch) in (12, 24) and
                    n.velocity < min(before.velocity, after.velocity)):
                continue
        filtered.append(n)
    if preservation == 'full' and part != 'bass':
        # Avoid destructively capping either vocals or guitar here. We will
        # only retain a maximum of three PSG tones (+ optional PIT2 bass)
        # when the offline arranger scores all pitches together.
        selected = filtered
    else:
        cap = 2 if part == 'harmony' else 1
        selected = _limit_polyphony(filtered, cap)
    if part == 'bass':
        selected = join_bass_fragments(selected)
    if preservation == 'full':
        selected = calibrate_lead_dynamics(selected, part)
    return selected



def calibrate_lead_dynamics(notes: list[Note], part: str) -> list[Note]:
    """Map unusually weak model velocities to usable lead dynamics.

    Basic Pitch velocity is not a calibrated stem loudness measurement.
    A robust 90th-percentile reference raises quiet lead stems by at most
    1.6x, retaining their ordering and leaving already strong tracks alone.
    Apply only to full audio transcription, never imported MIDI or backing.
    """
    if part not in ('guitar', 'melody') or len(notes) < 8:
        return notes
    levels = sorted(n.velocity for n in notes)
    reference = levels[int((len(levels)-1)*.90)]
    gain = min(1.6, max(1.0, 96 / max(1, reference)))
    if gain == 1.0:
        return notes
    return [replace(n, velocity=min(127, round(n.velocity*gain))) for n in notes]


def join_bass_fragments(notes: list[Note], gap: float = .027) -> list[Note]:
    """Join same-pitch fragments caused by transcription, not articulated riffs.

    Distinct repeated notes with a clear gap or new strong attack remain
    separate, preserving the famous guitar/bass riff's articulation.
    """
    result: list[Note] = []
    for n in sorted(notes, key=lambda n: (n.start, n.end)):
        if result:
            prev = result[-1]
            delta = n.start-prev.end
            if (prev.pitch == n.pitch and 0 <= delta <= gap
                    and abs(prev.velocity - n.velocity) <= 12
                    and prev.end-prev.start >= .085):
                result[-1] = replace(prev, end=max(prev.end, n.end),
                                     velocity=round((prev.velocity+n.velocity)/2))
                continue
        result.append(n)
    return result


def normalize_drum_fluxes(rows: list[tuple[float, float, float]]
                         ) -> list[tuple[float, float, float]]:
    """Calibrate low/mid/high spectral novelty to this track.

    Distorted/boomy recordings may have >20x more low-band power than
    mid/high content. Compare attacks against each band's 80th-percentile
    activity, with a floor so silent bands are not amplified from noise.
    """
    if not rows:
        return []
    columns = list(zip(*rows))
    levels = []
    for col in columns:
        values = sorted(max(0.0, float(v)) for v in col)
        levels.append(values[int((len(values)-1)*.80)])
    floor = max(levels)*.025
    scales = [max(v, floor, 1e-9) for v in levels]
    return [
        (max(0.0, row[0])/scales[0],
         max(0.0, row[1])/scales[1],
         max(0.0, row[2])/scales[2])
        for row in rows
    ]


def classify_drum_transient(low_flux: float, mid_flux: float, high_flux: float,
                            backbeat_hint: bool = False) -> int | None:
    """Classify *new* spectral energy, not bass-heavy absolute stem energy.

    Demucs separated drum stems frequently contain sustained low-end bleed.
    Compare attack spectrum against preceding audio first. If no distinctive
    transient exists, do not invent a drum. Beat position is a *small* hint,
    never a mandatory or exclusive drum-class rule.
    """
    l = max(0.0, low_flux)
    m = max(0.0, mid_flux)
    h = max(0.0, high_flux)
    total = l + m + h
    if total <= 0:
        return None
    l, m, h = l/total, m/total, h/total
    if l >= .49 and l >= 1.35*m and h <= .37:
        return 36
    if h >= .56 and h >= 1.20*m:
        return 42
    if m >= .37 and m+h >= .60 and l <= .40 and (h >= .10 or m >= .60):
        return 38
    # Weak musical-time hint for an otherwise plausible broadband snare.
    if backbeat_hint and m >= .34 and m+h >= .75 and l <= .25:
        return 38
    return None


def drum_velocity(strength: float, quiet: float, loud: float) -> int:
    """Stable stem-relative dynamic scaling without 118-velocity saturation."""
    if loud <= quiet + 1e-6:
        return 80
    fraction = max(0.0, min(1.0, (strength-quiet)/(loud-quiet)))
    return max(48, min(110, round(56+54*fraction)))

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



def recover_high_hats(events: list[tuple[float, float, float, float, float]],
                      existing: list[Note], style: str = 'auto') -> list[Note]:
    """Recover real *independent* cymbal attacks from high-band onset evidence.

    Event format: (time_sec, high-band onset strength, calibrated low,
    calibrated mid, calibrated high). Never create a regular beat grid or
    fill in hats where the isolated drum stem shows no detected attack.
    Distinct high-band onsets matter because full-spectrum onset tracking
    is often dominated by kick/snare energy.
    """
    if style not in ('auto', 'rock'):
        raise ValueError('Drum style must be auto or rock')
    if not events:
        return []
    strengths = sorted(max(0.0, e[1]) for e in events)
    floor = strengths[int((len(strengths)-1) * (.55 if style == 'rock' else .65))]
    floor = max(floor, strengths[-1] * .045, 1e-10)
    result: list[Note] = []
    minimum_gap = .115 if style == 'rock' else .14
    high_fraction = .42 if style == 'rock' else .49
    for at, strength, low, mid, high in sorted(events):
        if strength < floor:
            continue
        energy = max(0.0, low) + max(0.0, mid) + max(0.0, high)
        if energy <= 0:
            continue
        # A real high-frequency transient must dominate its local spectrum;
        # a little presence above 6 kHz in a kick is not a hi-hat.
        if high/energy < high_fraction or high < .78*max(low, mid):
            continue
        if result and at-result[-1].start < minimum_gap:
            continue
        # Tandy has only ONE noise oscillator: don't add an inaudible hat
        # on top of a kick/snare with a nearly simultaneous attack.
        near = [n for n in existing if abs(n.start-at) < .085]
        if near:
            # Only an unmistakable high-band transient may displace a
            # *weak* kick. Never sacrifice a genuine snare backbeat for hats.
            if (style != 'rock' or
                any(n.pitch != 36 or n.velocity > 64 for n in near) or
                strength < .73*strengths[-1]):
                continue
        if any(abs(n.start-at) < .090 for n in result):
            continue
        relative = min(1.0, max(0.0, strength / max(strengths[-1], 1e-10)))
        velocity = round(52 + 28*relative)
        result.append(Note(at, at+.045, 42, velocity, 'drums', 0))
    return result



def infer_snare_backbeat(snare: list[Note], beats: list[float]) -> int | None:
    """Find a plausible alternating backbeat from *actual* snare evidence.

    Avoid assuming beat phase when tempo is half/double or detection is weak.
    The result is only a bias for pruning weak kicks, never a reason to
    invent snare notes.
    """
    if len(beats) < 8 or len(snare) < 6:
        return None
    from bisect import bisect_left
    weights = [0.0, 0.0]
    hits = [0, 0]
    for n in snare:
        at = bisect_left(beats, n.start)
        options = [i for i in (at - 1, at) if 0 <= i < len(beats)]
        if not options:
            continue
        idx = min(options, key=lambda i: abs(n.start - beats[i]))
        if abs(n.start - beats[idx]) > .11:
            continue
        phase = idx % 2
        weights[phase] += n.velocity
        hits[phase] += 1
    total = sum(weights)
    winner = 0 if weights[0] >= weights[1] else 1
    if hits[winner] < 5 or total <= 0 or weights[winner] / total < .72:
        return None
    return winner


def prune_weak_rock_kicks(notes: list[Note], beats: list[float]) -> list[Note]:
    """Keep accents and the authentic pulse; remove weak repetitive attacks.

    Works only on detected kick *candidates*. A strong neighboring kick and
    significant dynamics are required before suppressing one. Clear on-beat
    kicks not occupying the snare's backbeat are protected when a reliable
    alternating snare phase exists.
    """
    kicks = sorted((n for n in notes if n.pitch == 36), key=lambda n: n.start)
    if len(kicks) < 12:
        return notes
    velocities = sorted(n.velocity for n in kicks)
    p20 = velocities[int((len(velocities)-1)*.20)]
    p40 = velocities[int((len(velocities)-1)*.40)]
    p80 = velocities[int((len(velocities)-1)*.80)]
    if p80 - p20 < 12:
        return notes  # no reliable strength contrast: preserve the groove
    threshold = p40 + .30*(p80-p40)
    snare_phase = infer_snare_backbeat(
        [n for n in notes if n.pitch == 38], beats
    )
    from bisect import bisect_left
    kept: list[Note] = []
    rejected: set[int] = set()
    for n in kicks:
        if n.velocity >= threshold:
            kept.append(n)
            continue
        stronger = any(
            0 < abs(other.start-n.start) <= .52
            and other.velocity >= n.velocity + 16
            for other in kicks
        )
        if not stronger or (kept and n.start-kept[-1].start > .65):
            kept.append(n)
            continue
        if beats and snare_phase is not None:
            j = bisect_left(beats, n.start)
            options = [i for i in (j - 1, j) if 0 <= i < len(beats)]
            if options:
                idx = min(options, key=lambda i: abs(n.start-beats[i]))
                if abs(n.start-beats[idx]) <= .08:
                    if idx % 2 != snare_phase:
                        kept.append(n)  # protect an actual kick-phase beat
                        continue
        # If snare phase isn't reliable, require a larger difference before
        # suppressing a kick; don't assume an alternating metronome.
        if snare_phase is None and not any(
            0 < abs(other.start-n.start) <= .52
            and other.velocity >= n.velocity + 21
            for other in kicks
        ):
            kept.append(n)
            continue
        rejected.add(id(n))
    if rejected:
        print('Rock rhythm: suppressed {} weaker repeated kick candidates'.format(
            len(rejected)), flush=True)
    return [n for n in notes if n.pitch != 36 or id(n) not in rejected]


def refine_drum_hits(notes: list[Note], beats: list[float] | None = None,
                     style: str = 'auto') -> list[Note]:
    """Beat-aware debounce for the Tandy's *one* noise channel.

    Align hits only when very near a reliable tracked beat, keeping guitar
    riffs off the drum channel. Prevent sub-100 ms snare chatter and avoid
    masking kicks with frequent snare triggers.
    """
    if style not in ('auto', 'rock'):
        raise ValueError('Drum style must be auto or rock')
    if not notes:
        return []
    from bisect import bisect_left
    beats = sorted(beats or [])
    # Rock mode deliberately reduces dense kick chatter, but retains actual
    # backbeats and cymbal attacks (no invented quarter/eighth-note hats).
    minimum = ({36: .28, 38: .25, 42: .11} if style == 'rock'
               else {36: .20, 38: .28, 42: .105})
    if style == 'rock':
        notes = prune_weak_rock_kicks(notes, beats)
    last_type: dict[int, float] = {}
    result: list[Note] = []
    typical = median(n.velocity for n in notes)
    from collections import Counter
    distribution = Counter(n.pitch for n in notes)
    dominant, dominant_count = distribution.most_common(1)[0]
    collapsed = len(notes) >= 30 and dominant_count/len(notes) >= .88
    if collapsed:
        # A track full of one drum voice is more likely bleed / a weak
        # classifier than a real 8th-note kick for three minutes.
        minimum[dominant] = max(minimum[dominant], .38 if dominant == 36 else .32)
        print('WARNING: drum analysis heavily favors MIDI note {} ({} of {}). '
              'Reducing repetitions, not inventing other drums.'.format(
                  dominant, dominant_count, len(notes)), flush=True)
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
            # Previous fixed ordering made *every* kick trump a snare, even
            # when the snare transient was much louder. A single noise voice
            # must choose the stronger event, with only a modest tie-break.
            bonus = ({36: 3, 38: 9, 42: 0} if style == 'rock'
                     else {36: 5, 38: 4, 42: 0})
            score = lambda hit: hit.velocity + bonus[hit.pitch]
            if score(n) <= score(old):
                continue
            result.pop()
        end = t + {36: .075, 38: .060, 42: .048}[n.pitch]
        result.append(replace(n, start=t, end=end))
        last_type[n.pitch] = t
    return result
