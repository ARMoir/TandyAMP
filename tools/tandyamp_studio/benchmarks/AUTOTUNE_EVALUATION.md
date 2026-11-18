# AutoTune ("tuned") — benchmarks and known limits

**Reviewed:** 2026-11-18. **Code baseline:** `35412895`, "Tune separated stems before shared harmony correction."  
**Purpose:** Keep pitch evidence, musical phrase reconstruction, and final Tandy note allocation testable **separately**; do not claim a guide-free recording has been validated solely because unit tests pass.

## What the new AutoTune actually does

For an audio/YouTube input (without a reference MIDI), the current `tuned` mode:

1. Runs Demucs separation / Basic Pitch transcription.
2. When available, measures fundamental/harmonic pitch evidence **independently in bass, guitar, vocal and other stems** (`stem_pitch.py`). That measurement can correct local ±2-semitone decoder errors when the signal consistently supports them.
3. Builds bass/drums/guitar/vocal **phrases**, with natural note timing (`phrase_score.py`), rather than selecting every instantaneous pitch independently.
4. Applies local phrase checks, then cross-stem harmony correction (`pitch_arranger.py`).
5. Exports the relatively small result as DOS-compatible MIDI, with TandyAMP's real voice budget handled by the player.

**Important comparison caveat:** The hardware-approved **PARATUNE.MID** excerpt is 23.79 seconds and used **an authored MIDI guide for the guitar, bass and drums**. That guide is **not** present in an ordinary two-argument YouTube conversion. Reproducing the approved take proves *guide mode*, not the musical accuracy of the fully automatic, guide-free path. Do not claim those are apples-to-apples benchmarks.

## Benchmarked bug: missed sustained notes while a short overlay ends

Previously, the shared-harmony helper `_near_note` returned **only the most recently started note** at the requested time. An earlier note could still be ringing while an overlapping brief note had already stopped. The tuner then incorrectly concluded there was **no** sounding note in that part. That can remove harmonic context from pitch checks and backing-guitar decisions.

**Fix:** Search backwards among previously started notes for the most recent one that **is actually still active**. This does not fabricate notes, alter source timestamps or affect the already-approved MIDI-guide arrangement code. The implementation is intentionally small.

### Real, user-provided earlier Paranoid transcription

Measured from the archived **`INPUT.json`** (2682 candidate events; SHA-256 `b56433d11612e9f70c6c18d253294aed79b58469b0754057b6fe885a5a024f2e`). Sampled every 25 ms through the length of each pitched part. The ground truth for this test is **which extracted MIDI candidate is still sounding**; it is *not* acoustic/source-song pitch ground truth.

| Pitched part | Frames with an active note | Previous "last attack" missed frames | Corrected lookup missed frames |
| --- | ---: | ---: | ---: |
| Bass | 5,355 | 0 | 0 |
| Guitar | 4,583 | **95** | **0** |
| Vocal melody | 2,685 | **58** | **0** |
| Harmony | 2,110 | **61** | **0** |
| **Total** | **14,733** | **214 (1.45%)** | **0** |

This result is on **an older transcribed-note inventory**, not on a fresh run of the latest source-separation and tuning models. The WAV/source MP3, Demucs model weights and original YouTube extraction are not stored in the repository and were not reprocessed as part of this test.

Run the benchmark on any saved Studio checkpoint:

```bat
py -3.11 benchmarks\autotune_context.py "C:\Music\SomeConversion\INPUT.json"
```

Or run the synthetic held-note fixture (no source required):

```bat
py -3.11 benchmarks\autotune_context.py
```

The benchmark prints **legacy_misses vs tuned_misses**, number of active frames and processing time for each part. It requires only the Studio's lightweight `mido` dependency.

## New direct spectral-stem benchmark (passed)

[Executable synthetic audio benchmark](autotune_stem_synthetic.py) is run by
[Studio CI](../../../.github/workflows/studio-ci.yml) on every Studio change.
It synthesizes known isolated audio at **22,050 samples/second** and measures
the *real* `measure_stem_pitch` / `StemPitch.retune` functions with NumPy,
SciPy and SoundFile. No Demucs/Basic Pitch weights, YouTube download, or
commercial sound recordings are necessary.

**Results on the November 18, 2026 Linux GitHub Actions runner:**

| Stem | Known actual MIDI note | Strongest measured | Repaired one-semitone error to | Tuning offset (true → estimated) | CPU analysis time |
| --- | ---: | ---: | ---: | --- | ---: |
| Bass E2 | 40 | **40** | **40** | 0 → 0 cents | 0.591 s |
| Guitar E3, **second harmonic louder than fundamental** | 52 | **52** | **52** | 0 → 0 cents | 0.008 s |
| Vocal A4, **22 cents sharp** | 69 | **69** | **69** | +22 → +22 cents | 0.009 s |

The bass timing includes first-use FFT/runtime warmup; do not compare the
numbers as a speed ranking of instruments. These are **three generated
two-second isolated tones**, not a polyphonic source recording. Accuracy
here does **not** imply correct guitar chords, expressive vocals, drum
classification, model source separation or a cohesive Tandy MIDI.

To reproduce locally (requires `numpy`, `scipy`, `soundfile`):

```bat
py -3.11 benchmarks\autotune_stem_synthetic.py
```

The benchmark must fail if the strongest pitch, repaired pitch, or tuning
estimate diverges from the known synthetic ground truth beyond its explicit
tolerance. It exercises the actual stem-analysis code, not a rewritten
stand-in.

## Guide-free phrase contention: targeted revision

**Change proposed for AutoTune `tuned` without a MIDI guide:** The
automatic guitar part no longer promotes each new weak detected pitch to
the foreground or keeps two guitar notes with the same onset.

- A very brief, weak upper harmonic can be ignored when the existing
  guitar fundamental is still audible.
- Consecutive weak estimates of the **same** pitch can be held as one
  note, but strong repeated picks remain separate attacks.
- Genuine new pitches interrupt the held riff at a specific onset
  rather than fighting over two simultaneous guitar voices.
- Simultaneous pitch estimates choose the stronger sustained guitar
  candidate rather than blindly favoring the highest pitch first.
- Weak semitone pitch corrections require **another sounding stem to
  support the target pitch**. A supposedly “correct” key signature or
  a chord root alone is not enough to overwrite an actual blues/chromatic
  note. Independent observed pitch evidence can validate out-of-key
  musical tones.

### Harmonic guard: source-supported fifths only

Another guide-free rule previously **changed a guitar root into its
fifth** when it matched the bass root under a vocal phrase—even without
an audible fifth detected in the source. This can add an unsupported
backing pitch to an already crowded song.

The new rule **keeps the original guitar pitch** unless a separate
guitar/harmony source proposal contains a matching fifth with enough
duration (at least 140 ms), velocity (at least 63) and overlap.
It still allows the established backing-note hold/velocity behavior,
and a demonstrably present power-chord fifth can still support the
vocal. A 30 ms weak high harmonic cannot authorize that change.

Three regression cases cover (a) no supported fifth, (b) a supported
source fifth, and (c) a weak fleeting artifact. This gate is only in
automatic tuning: the **approved guide-based PARATUNE arrangement is
unchanged**.

These are small guide-free changes to `_automatic_mix` and its cross-stem
tuner; **the authored-MIDI `_reference_mix` path is untouched**.

### Measured A/B result (same synthetic candidate notes)

The GitHub Actions run on November 18, 2026 sampled each candidate
arrangement at **10-millisecond intervals** for **2.83 seconds**, using
the known five-note riff as ground truth.

| Metric | Old guitar gate | New coherent guitar gate |
| --- | ---: | ---: |
| Correct pitch-set frames / 283 | 173 | **283** |
| Frames missing the expected phrase | 74 | **0** |
| Frames sounding an incorrect pitch | 36 | **0** |
| Pitched guitar note events | 7 | **5** |
| Frames with multiple simultaneous guitar notes | 0 | **0** |

The old same-onset selector already output a single note but could
prioritize a **higher, weaker octave artifact**; the new selector favors
stronger sustained evidence. Other false high notes prematurely cut
a held riff, resulting in missing notes until the next phrase attack.

**Interpretation:** This is a reproducible improvement against **synthetic
known MIDI candidates only**. It establishes better phrase continuity,
but does not measure how accurately Basic Pitch recognizes a YouTube
performance or how pleasing the hardware playback is.

The [reproducible A/B benchmark](autotune_phrase_ab.py) creates a
known riff, a short false high harmonic, a false repeated E3 fragment,
a simultaneous octave artifact, and a real repeated picked attack.
It compares the previous `_monophonic` path with the new
`_coherent_guitar_line` on **correct-pitch coverage, false-pitch frames,
missing phrase frames and unintended guitar polyphony** using 10 ms
samples. The fixture uses generated MIDI evidence, *not* copyrighted
music or external source separation. This is a regression benchmark for
a specific failure mode, not proof that an entire YouTube song sounds
better.

```bat
py -3.11 benchmarks\autotune_phrase_ab.py
```

GitHub Actions now runs it after the 201+ unit tests and the isolated
stem-fundamental benchmark. The hardware-approved PARATUNE recipe and
default Studio settings remain unchanged.

## Regression / acceptance checks

- A long guitar or bass note must remain visible to the harmony checker even after a shorter overlapping note has ended.
- A genuinely finished note **must not** be extended beyond its end; the fix changes *context retrieval*, not note duration.
- A valid strong chromatic note or a note in a true rest must not be pitch-corrected simply because another note played earlier.
- The supported harmony correction may still repair a nearby weak semitone error when a continuing part supplies matching pitch evidence.
- Existing `PARATUNE` guide behavior, Build56/Classic, MAX RAW and DOS player stay unchanged.

## Next benchmark stages (not yet passed or claimed)

1. **Expanded synthetic audio:** The single-note bass, harmonic-rich guitar and detuned-vocal cases **passed** above. Next test deliberately **polyphonic guitar chords, pitch bends and mixed/stem-leakage audio**, because those are harder and have not been validated.
2. **Guide-free song A/B:** Hold source MP3, Demucs weights and transcription model constant. Compare before/after `tuned` MIDI and actual PSG/SPK4 auditions. Report phrase dropouts, false notes, note lengths, drum/bass alignment and recognizable riff/vocal contour.
3. **Reference-guided song A/B:** Use the identical recording with a known authored score, align time, and compare the guide-free arrangement against guide mode. Reference guidance should be reported as an additional input—not an automatic transcription win.
4. **Actual Tandy listening:** Record the physical Tandy 1000 EX playback at fixed volume/mode. A smaller file or more corrected notes does not alone establish better music.

**Overall criterion:** *The simplest cohesive score that still sounds like the song on the Tandy*, not the highest possible number of candidate MIDI notes.
