# SEVENT01.MID — musical-quality benchmark

**Status:** Reference established November 2026.  
**Subject:** User-supplied DOS-friendly MIDI conversion of *Seventh Son of a Seventh Son*.  
**Benchmark role:** A positive example of a *musically coordinated arrangement*, **not** a template whose exact note counts, tempo, or chord density must be copied into other songs.  
**Related reference:** The user-preferred `Paranoid_SPK4_Build56.zip` is the current audio-to-MIDI *sound/recipe* baseline. These references serve different purposes.

## Central arranging principle: groove first, lead connection second

> **Drums and bass together create the groove. Guitar builds the riffs and harmonic structure on top of that rhythm section, then provides the musical connection to the vocals.**

This is the primary design requirement for future TandyAMP Studio cleanup and audio-to-MIDI work:

1. **Drums and bass = one rhythm section.** Preserve kick/bass accents, backbeat/snare response, hi-hat subdivisions, intentional offbeats, rests, and repeated-note articulation **as an interacting groove**. Neither stem is simply a standalone note-count quota.
2. **Guitar = the riff and harmonic bridge.** Protect recurring motifs and essential attacks. Maintain guitar/bass agreement on harmonic movement without automatically merging guitar into bass. In guitar-led music, guitar connects a stable rhythm section to the melodic phrases the singer uses.
3. **Vocals = intelligible lead phrasing.** Preserve the recognizable sung line when present; maintain its entrances and breaks against the guitar riff. Weak vocal harmonics must not steal the guitar's central phrase or obscure the pulse.
4. **Supporting harmony = fill the real gaps.** Only retain or infer chord tones that reinforce the established groove/riff/lead relationship, and mark inferred tones explicitly. A sustained chord or higher note is not automatically desirable.
5. **Tandy constraint applies *last*.** Three distinct SN76489 PSG pitches, PSG noise, and eligible independent SPK4 bass are playback constraints—not reasons to destroy musical structure before the player gets the candidate notes.

**Practical rule:** *Keep the funk; lose the noise.* Do not define quality as “fewest notes” or “maximum 4-note density.” A good arrangement contains silence, offbeat accents, repeated attacks, bent/blues/chromatic notes, and occasional dissonance when musically intentional.

## Verified MIDI reference data

File: `SEVENT01.MID` (user-supplied; **not committed** to this repository).  
File size: **28,829 bytes**.  
SHA-256: `82c53291a4918ea1c62191b9a702ca02fee43aa073b8d8208f79e8efb04f0303`.  
MIDI format: **0**, one track, **480 PPQN**, encoded 120 BPM tempo (500,000 microseconds per quarter); **180.00 seconds**. This tempo meta-event is an encoding of performance time, not proof the musical beat is 120 BPM.  
Total note-on/note-off pairs: **3,810**.

| MIDI role / source channel | Note pairs | Observation |
| --- | ---: | --- |
| Melody, channel 1 (zero-based 0) | 216 | Lead line; fixed source velocity 126 |
| Bass, channel 2 (zero-based 1) | 1,150 | Active moving bass, fixed velocity 110 |
| Harmony/chord layer, channel 3 (zero-based 2) | 1,497 | Frequent synchronized multiple-note attacks, fixed velocity 110 |
| Drums, channel 10 (zero-based 9) | 947 | Three relevant GM drum classes, fixed velocity 110 |
| **Total** | **3,810** | All note events counted once |

Percussion note distribution: **475 closed hats** (GM 42), **281 snares** (GM 38), **191 kicks** (GM 36). There are **no CC119=77 Smart Voice Selection markers**. Program-change messages may initialize other channels, but **there are no separately performed guitar notes on channel 5** in this reference. Thus “guitar connects to vocals” is an *arranging principle* to apply to new transcriptions, not a verified track separation in this MIDI.

**Measured pitched-note availability** (drums excluded; distinct simultaneously held MIDI channel/pitch pairs):

| Simultaneous pitched notes | Seconds | Approx. share of 180 s |
| --- | ---: | ---: |
| None | 8.89 | 4.9% |
| One | 7.84 | 4.4% |
| Two | 3.05 | 1.7% |
| Three | 3.45 | 1.9% |
| Four or more | **156.76** | **87.1%** |

These are **MIDI candidates**, **not** a measurement that the Tandy audibly played four notes for that much time. PSG/SPK4 eligibility and real-time voice selection impose stricter limits.

### Evidence that the rhythm, bass, and harmony function together

Measurements use note **onset timestamps** and count a match when a second source attacks within **±50 milliseconds**; events are not quantized to a guessed beat grid.

| Relationship | Matched bass attacks | Share of 1,150 bass attacks |
| --- | ---: | ---: |
| Bass near **any drum** attack (kick, snare, or hat) | 1,029 | **89.5%** |
| Bass near **any chord/harmony** attack | 1,122 | **97.6%** |
| Bass near **kick** attack | 232 | 20.2% |
| Bass near **snare** attack | 325 | 28.3% |
| Bass near **hat** attack | 472 | 41.0% |

These figures reveal **coordination**, not a rule that all bass notes must land on a kick. The bass aligns with many different drum accents and with chord movement; that is why the groove feels connected. A future converter that quantizes every bass onset to a kick would destroy the character we want to preserve.

The harmony layer has **961 distinct onset times**: **420** of these contain at least two notes attacked together (including **116** three-note groups). The chord movement is organized, not merely a cloud of random transcribed overtones.

Across the percussion events, common adjacent hi-hat intervals include **~0.15 seconds** and **~0.30 seconds**. The individual drum parts contribute distinct roles; the total number of kicks is not the measure of whether the rhythm works.

### Interpretation, not proven by the MIDI data alone

- The source is an existing arranged MIDI, so chord relationships and timings were deliberately available **before** TandyAMP optimization. Reconstructing this from a finished YouTube mix is much harder and inherently uncertain.
- Consistent velocities do **not** mean the musical rhythm is flat. Accents also arise from pitch choice, note duration, onset alignment, rests, chord attacks, and which notes the player actually sounds.
- Four-or-more candidate-note coverage is one symptom of completeness, **not** a minimum required percentage. A correct sparse verse or solo should not be padded to 87%.
- MIDI alone cannot confirm the guitarist/vocalist's intended roles or whether a particular chromatic pitch is musically wrong without hearing the corresponding source.

## How Studio should use this benchmark

| Stage | Preserve / evaluate | Do **not** do |
| --- | --- | --- |
| **Groove construction** | Kick and snare accents, hats, bass onsets, syncopation, bass note length and silence | Delete short bass notes simply because they miss the kick; manufacture a rigid beat grid |
| **Guitar/riff** | Repeated phrase contour, distinctive riff attacks, chord movement, timing against bass | Replace a prominent guitar note with a weak high vocal artifact; collapse all notes to one line |
| **Vocal link** | Vocal entrances and melodic contour relative to guitar motifs; competing-voice priority | Treat source-separated high harmonics as equally important to the lead |
| **Harmony** | Chord stacks that reinforce bass and riffs; stable support at natural gaps | Add arbitrary “correct key” chord notes, or strip useful tension/blues notes |
| **Noise cleanup** | Reject weak isolated spectral artifacts, brief pitch spikes, and duplicated source-stem bleed *with evidence* | Optimize for note count or key membership alone |
| **DOS export** | Proper note starts, duration and velocity, distinct parts/channels, safe 8.3 MIDI files | Falsely claim >3 PSG tone channels or that four candidates are always four audible tones |

### Groove Clean acceptance criteria (for future development)

**Compare reference behavior and actual source audio, not absolute quotas.**

1. Audition rhythm-section-only material first: can drums and bass produce a coherent groove *without* guitar or vocals?
2. Add the guitar: does it lock into that groove and carry recognizable motifs without rapid unexplained voice theft?
3. Add the vocal: are phrasing and melody recognizable, with guitar bridging to the groove?
4. Check any note deletion: was it demonstrably a weak artifact, or did it remove a riff attack, bass accent, chord voicing, syncopation, or backbeat?
5. Track the changes in **onset alignment**, **role overlap**, **phrase continuity**, **unexpected gaps**, **false pitch outliers**, and **audible voice-stealing events**. A lower note count or higher percentage of four-note coverage alone is **not** a pass.
6. Always retain the untouched baseline MIDI and Build56 reference for A/B listening; new cleanup must be **optional** until demonstrated superior across more than one style.
7. Verify output on a physical Tandy 1000 EX (actual PSG/SPK4) as well as a laptop preview. The WAV preview is not a hardware-accurate synthesis reference.

For a new song from audio, **phase 1 prioritizes rhythm quality; phase 2 identifies its recurring guitar phrase; phase 3 preserves the vocal connection; phase 4 adds sparse supporting harmony**. This order is more important than a universal per-stem minimum note count.

## Reproducing / comparing this reference

- Keep the uploaded `SEVENT01.MID` outside Git; the repository stores **measurements and methodology only**, not commercial arrangements or source media.
- Confirm file identity on Windows: `certutil -hashfile SEVENT01.MID SHA256`. The expected hash appears above and in `SEVENT01_reference.json`.
- Use the existing `tools/tandyamp_studio/benchmark.py` for audio-source comparisons. It can accept `--reference-midi`, but **that does not make SEVENT01 an accurate ground-truth transcription of unrelated source audio**. It should be used as a *musical-quality comparator*, not aligned against Paranoid's waveform.
- Keep the reference distinct from the user-preferred **Paranoid SPK4 Build56** configuration in `defaults.py`. The former is a *composition/groove example*; the latter is the *audio-to-MIDI conversion default*. Both should remain unchanged while exploring optional Groove Clean.
- Exact event statistics here were computed from MIDI event timestamps, **not** extrapolated from a noisy waveform or an arbitrary 10-second listening sample.

**Guiding sentence for future development:** *Drums and bass make the funk; guitar rides that pocket and connects it to the vocals. Preserve that relationship, then remove noise.*
