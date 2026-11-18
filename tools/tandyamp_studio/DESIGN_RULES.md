# TandyAMP Studio — musical arrangement design rules

**Status:** Design specification for future Studio changes. It does **not** claim these rules are implemented, alter the DOS player, or change current Studio conversion defaults.

## The goal: the best *Tandy* MIDI, not the most complete MIDI

> **The ideal TandyAMP Studio output should have the musical organization of Seventh Son, the voice-leading awareness of Brandenburg, and the hardware discipline of DEMO.MID.**

A transcription containing *every* note in a recording is useful **source material**, but is not automatically good music on the Tandy. The finished MIDI should be **deliberately simple and musically complete**: fewer carefully chosen notes that preserve the core sounds, timing and relationships of the piece.

A 7 MHz Tandy 1000 EX has **three pitched PSG voices, one PSG noise channel, and an optional independent PC-speaker/SPK4 bass voice**. More MIDI events can be available as candidates than the hardware can sound. A good arrangement does **not** try to play all of them.

**Primary success test:** Could a listener recognize the song, feel the rhythm/phrasing, and understand the important melodic/harmonic movement on the *actual Tandy*?

## One small arranger, not one engine per genre

Every passage goes through the **same three musical questions**:

| Musical job | Decision | Rock / metal example | Classical example | Native three-voice example |
| --- | --- | --- | --- | --- |
| **Foundation** | What holds the passage together? | Interlocking drums + bass | Bass motion, repeated accompaniment or lower counterline | Coherent low harmonic part |
| **Identity** | What makes it recognizable? | Riff, sung melody, strong guitar attacks | Leading phrase and its independent answering voice | Clear upper melody |
| **Support** | Which additional line gives the most value? | Chord movement, guitar–vocal link | Essential inner voice, suspension or counterpoint | Middle harmony or rhythmic response |

These are *musical roles*, **not permanently assigned PSG channels**. The bass may use SPK4 when possible; two concurrent melodic lines may both deserve PSG tones; a sparse passage may need only two voices. Don't create a note merely to keep all channels busy.

**Style should influence priorities, not trigger a complicated genre classifier.** Judge local musical relationships. Progressive rock can be rhythm-driven in one section and contrapuntal in another. When uncertain, use a conservative arrangement and retain the original candidates for comparison. No hardcoded genre-specific quotas or separate sprawling rule engines.

### Five steps, in order

1. **Detect the foundation.** Preserve natural rhythm, bass movement or lower harmonic line. Drums and bass belong together *when they are the rhythm section*. Classical without drums gets no invented drums.
2. **Protect the identity.** Preserve a recognizable lead, recurring riff, motif, and significant phrase attacks/ends. A weak high harmonic should not steal a strong midrange riff; a real solo entrance can still take priority.
3. **Pick only useful support.** Favor chord-defining movement, answering lines, counterpoint, or accents that complement the first two roles. Purposeful rests are allowed. Don't add generic filler just because a PSG channel is free.
4. **Fit the actual hardware.** Up to three distinct PSG pitches, one noise voice, and *eligible* SPK4 bass. Avoid redundant same-pitch oscillator assignments and rapid weak-note switching. Don't equate “four MIDI candidates” with “four audible notes.”
5. **Listen, compare, simplify again.** The answer is the version that sounds best on the Tandy—not the one that retains most notes, gets the highest density score or removes the most events.

## Required musical safeguards

**Keep these:** timing/syncopation, beat accents, riff outline, strong attacks, meaningful repeated notes, bass–chord movement, recognizable melodic contour, classical suspensions and counterpoint, true chromatic/blues notes, expressive rests, phrase continuity.

**Remove or de-prioritize only with evidence:** isolated pitch spikes, erroneous high harmonics, cross-stem leakage, false drum onsets, pointless same-pitch duplication in **final hardware allocation**, and weak transient notes that interrupt more important voices.

**Do not:**

- Turn a fluid performance into a strict beat grid or force every bass note onto a kick.
- Delete “out-of-key” pitches automatically; chromatic notes and dissonances can be intentional.
- Pad every quiet gap with inferred harmony or invented hi-hats, or insist on four tones throughout a song.
- Treat intentional part-doubling as a transcription error. Two instrument tracks agreeing on one line is *evidence of its importance*, even though one PSG voice may carry it.
- Flatten velocities or alter pitches as an unannounced side effect of a cleanup mode.
- Optimize only for MIDI file size, note count, 4+ candidate coverage, waveform loudness, or low voice-switch counts.

**Simplicity means simple *audible arrangement*, not mandatory removal of source evidence.** Preserve a full source candidate inventory and clearly separate it from the smaller hardware-ready arrangement. MAX RAW is an opt-in source/candidate diagnostic, *not* the intended best-sounding final product.

## The three reference pieces and what each actually establishes

### 1. SEVENT01.MID — musical organization / groove

[Verified reference and onset measurements](benchmarks/SEVENT01_MUSICAL_BENCHMARK.md) · [data](benchmarks/SEVENT01_reference.json)

This pre-arranged MIDI has 3,810 note pairs across 180 seconds; **89.5% of bass onsets** are within 50 ms of a drum hit and **97.6%** within 50 ms of the harmony part. That is evidence of coordinated musical parts, *not* a requirement that other songs have those percentages. Its 87.1% 4+-candidate occupancy is **not** an output-density target. Main principle: **drums and bass make the funk; guitar builds the riffs and connects to the vocals**. In this file the guitar isn't separately performed on a dedicated guitar channel; that bridging relationship is a design objective rather than an independently measured guitar track.

### 2. Brandenburg Concerto No. 6 — independent lines / voice-leading

[Verified reference](benchmarks/BRANDENBURG_CLASSICAL_BENCHMARK.md)

This MIDI contains deliberately interlocking string-ensemble, violin and harpsichord roles without drums. Every one of its 396 violin notes is exactly doubled in the string ensemble. **Do not waste two final PSG tone channels on an identical pitch, but also do not delete the important doubled melodic line when analyzing importance.** Protect counter-melody, bass motion, entrances, suspensions and note duration. Do not apply rock-style kick/bass rules where there is no drum kit.

### 3. DEMO.MID — clarity / economy / hardware discipline

[Verified reference](benchmarks/DEMO_HARDWARE_BENCHMARK.md)

Only 96 notes in 16 seconds, with three coordinated pitched roles and no drums. It is intentionally simple and directly suited to the SN76489's three tones. It demonstrates that an effective Tandy arrangement need not be dense or use every optional hardware feature. **Don't copy DEMO's fixed half-second rhythm and constant velocities into real compositions**; those are demo-specific simplifications.

### Stable listening baseline: Paranoid SPK4 Build56

The current [Build56 Studio recipe](README.md#default-sound-paranoid-spk4-build56-best-mix) remains the **default**. Its settings represent the preferred *audio-to-MIDI conversion sound*; SEVENT01, Brandenburg and DEMO represent the *arranging philosophy*. These are complementary, not interchangeable. Neither documentation nor benchmark scores should silently replace user-preferred defaults.

## Future Studio workflow — intentionally small

```text
Source audio / MIDI
    |
    v
All estimated notes + source roles (keep as evidence)
    |
    v
Recognize foundation, identity, useful support
    |
    v
Remove only demonstrable noise; protect important phrases
    |
    v
Choose coherent PSG roles; optional real SPK4 bass / noise percussion
    |
    v
8.3-safe, size-limited Tandy MIDI + comparison report
```

Avoid a huge rules-and-exceptions system. A few explainable priorities should guide selection: **importance to the song, continuity of the line, genuine rhythmic/harmonic support, and confidence that a note is real**. Select a strong new attack when it matters, but do not endlessly switch voices because a weak note briefly appears.

A future optional **Groove Clean** stage may apply this logic at light/balanced/aggressive strengths, but **does not exist merely because these documents were committed**. Its job is to *remove noise while preserving the core*, not to maximize the fidelity of a giant GM note stream. Keep the original, cleaned and final arranged files available for A/B tests; record why candidate notes were suppressed.

## Implementation and regression gates

**Hard requirements for each proposed change:** standard compatible type-0 MIDI output, DOS 8.3 filenames, under 45,056 bytes per TandyAMP input (Studio normally targets 42,000 bytes), correct tick-time/duration encoding, preserved channel/role provenance, valid note-off behavior across split files, correct three-PSG-plus-eligible-SPK4 limitations, no nonoptional DOS/player changes, and MAX RAW remaining an independent override.

**Musical A/B requirements before promoting a new default:**

- **Rock:** Is drums+bass alone a convincing rhythm section? Does guitar retain the riff and move with the bass? Do vocals connect to that phrase rather than crowd it?
- **Classical:** Can you hear a continuous leading line and meaningful responding parts? Do doubling/counterpoint and expressive timing survive?
- **Hardware-native:** Are all audible voices useful, with few unnecessary steals, and no effort to manufacture extra instruments?
- **Every style:** Are the important notes recognizable? Did a deleted note remove a riff onset, essential harmony, passing note or accent? Is a newly added note supported by the source? Do the original and new versions stay the same length?
- **Actual Tandy:** Listen at the same player volume, SPK4 and treble settings; laptop preview is approximate. Do not promote from metrics alone.

Document the input/source SHA-256, command/options, Studio commit, model versions, note-count/role changes, salient omissions/insertions, PSG/SPK4 eligibility, MIDI files produced, listening notes and physical EX results. For source-audio comparisons, the *same* original track must be used; an unrelated benchmark song is **not** acoustic ground truth.

**Reject** a change that produces a fuller-looking score but loses the signature riff, destroys bass/drum pocket, interrupts a classical phrase, invents unwanted notes, or changes tempo.

## Current status

- This file and [machine-readable design constraints](benchmarks/design_rules.json) are **documentation and prospective evaluation contracts**, not implemented audio algorithms.
- The Build56 Studio defaults, DOS player, current arrangement code and MAX RAW remain untouched.
- User-supplied reference MIDI files are **not committed**. Store only measurements and methods.
- Changes to processing should be separate, opt-in, testable and reversible until hardware listening establishes an improvement.

**In one sentence: _Make the simplest MIDI that still sounds like the song on the Tandy._**
