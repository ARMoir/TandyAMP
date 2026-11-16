# MIDI-to-Tandy PSG research and implementation audit

**Audited November 16, 2026** against the actual `src/midi.c`, `src/midi.h`, `src/main.c`, host tests and GitHub workflow on `main`. This is **research and a prioritized roadmap**, not a claim that every idea below has been implemented. Newer functionality requires on-device testing on a 7 MHz NEC V20 Tandy 1000 EX.

## Short answer

**No, all known Tandy/MIDI tricks have not been implemented.** TandyAMP already supports Standard MIDI Files 0/1, a 24-track / 44 KiB limit, 64-entry directory playlists, tempo events, three-voice prioritization, 32 remembered notes, unison consolidation, bass octave folding, MIDI velocity/expression and pitch bends, GM noise drums, channel-16 percussion detection, and conservative automatic gain leveling. It uses an independent integer pitch table and a foreground PIT sub-tick scheduler, but still has considerable room for musical improvements.

### Status by technique

| Technique | Code status | Evidence / trade-off |
| --- | --- | --- |
| Three Tandy PSG tones, software note pool, age/salience-aware allocation | **Implemented** | `rebuild_voices()`, 32-note pool, three hardware slots |
| Consolidate identical rendered pitches and restore still-held notes | **Implemented** | Actual PSG divider comparison; mixer/playback tests |
| MIDI SMF 0/1, tempo, running status, PPQN | **Implemented** | `consume_event()`, `ta_advance()`; rejects SMF 2 / SMPTE |
| 10-bit note dividers, semitone pitch bend, fold low bass notes | **Implemented** | `period_for()`; no heavy floating-point runtime |
| CC7/CC11, note velocity, sustain, master loudness | **Implemented** | `attenuation()`, `handle_cc()`, `ta_set_volume()` |
| Noise percussion on GM channel 10; optional channel 16 | **Implemented** | `drum_on()`, `update_noise()`, `detect_drum16()` |
| Volume peak limiting based on logarithmic 2 dB hardware steps | **Implemented** | `flush_mix()`; simulated power, not acoustic measurement |
| PIT subtick scheduling instead of original 18 Hz event grid | **Implemented** | Foreground mode-2 PIT polling and ~6.9 ms slices |
| Per-instrument pluck, soft and sustained tone envelopes | **Implemented (lightweight)** | Program Change sets a simple per-note decay profile; immediate note-off, not full ADSR release |
| GM program-change-aware envelope categories | **Implemented (limited)** | Zero-based GM programs select pluck/soft/sustain; no realistic instrument waveforms |
| MIDI modulation wheel CC1 vibrato / portamento | **Partial** | CC1 now applies restrained divider modulation. Automatic program-based vibrato and portamento remain unimplemented |
| Selective high-rate arpeggiation of chords on a single PSG channel | **Not implemented** | Three-voice allocator selects a note per voice; it does not time-multiplex extra chord tones |
| Tracker-style tone slides, step envelopes, echo/retrigger | **Not implemented** | Candidate for a small optional synthesis layer; avoid expensive high-rate FX |
| Offline MIDI → three-voice optimized stream / optional compact format | **Not implemented** | Native MID parsing remains on the EX. A host-side converter could precompute reduced polyphony, dividers, envelopes and event timing |
| Time-saving PSG register-difference cache at the final I/O layer | **Implemented** | Tone divider changes issue two writes, volume-only changes one, unchanged registers zero; noise latch always retriggers |
| Noise timed from third tone channel (noise mode 3/7) | **Not implemented** | Can create pitched noise/deeper rhythmic textures, **but ties up tone channel 2** and may interfere with a third melody |
| Native Tandy 15-bit noise modeling in a host reference synthesizer | **Not implemented** | Tandy noise LFSR behavior differs from several Sega variants; relevant for offline preview, not for playing registers on real hardware |
| Direct `TANDY.ADV` use / BIOS audio-routing write `out 61h,68h` | **Intentionally not implemented** | Proprietary Miles driver cannot serve as our native music engine; blindly rewriting 61h may disturb EX hardware selection |
| Software PWM / high-frequency PCM through PSG volume | **Not planned as a default** | CPU-heavy, reduces simultaneous music quality and can monopolize a 7 MHz V20 |
| Winamp UI seeking, scrolling clickable rows, full equalizer | **Not implemented** | Separate UX projects; not required to synthesize good PSG music |

## External resources and concrete findings

All sources below are for **independent algorithm study**. Check and honor licenses before borrowing implementation code or data. Do not add third-party MIDI, ROMs, Winamp skins, Miles assets, MODs or SoundFonts to this repository.

### 1. TNDY Tracker: tracker effects and compact PSG playback

- [JKnipperts/TNDY-Tracker](https://github.com/JKnipperts/TNDY-Tracker): Borland Pascal tracker with an assembly player at [`PLAYER.ASM`](https://github.com/JKnipperts/TNDY-Tracker/blob/master/PLAYER.ASM).
- Implements **portamento, volume/tone slides, arpeggio**, imported AGI/Tandy music and compact `.TND` files; source also supports configurable I/O ports.
- **Lesson:** Track the musical gesture (note, note-off, envelopes and pitch slide) separately from PSG register writes. A few bytes of precomputed per-note effect state could improve expressive melody without importing its song format.
- **Not:** a general-purpose Standard MIDI File loader. Directly integrating the old Pascal/assembly playback system is unlikely to simplify the current engine.

### 2. Monotone: virtual channels and integer effects

- [MobyGamer/MONOTONE](https://github.com/MobyGamer/MONOTONE), [MONOTONE.TXT](https://github.com/MobyGamer/MONOTONE/blob/master/MONOTONE.TXT).
- Uses **virtual channels** whose events are mapped to simple physical sound hardware. Documents frequency-based slides, vibrato and tracker arpeggio effects.
- **Lesson:** Keep virtual notes/state in software (already done) while allowing bounded, optional pitch/volume modulation at the output stage. Use integer tables or Q-format state on the EX.

### 3. Mod2PSG2 and Furnace: instrument envelopes, noise macros

- [Mod2PSG2 description / MID import](https://www.smspower.org/Music/Mod2PSG2): imports `.MID`, `.MOD`, `.VGM` and supports **volume envelopes and vibrato** in tracker instruments.
- [Furnace PSG instrument notes](https://github.com/tildearrow/furnace/blob/master/doc/4-instrument/psg.md): separate **volume, arpeggio, pitch and noise-mode macros**.
- **Lesson:** Three cheap envelope profiles—`pluck`, `soft`, `sustain`—based on GM program family plus note duration offer much greater variation than giving every note an identical unchanging square wave. Use 16-level hardware attenuation rather than arbitrary floating-point DSP.

### 4. MIDI-to-PSG conversion with program-aware expressive controls

- [akiyan/midi2vgm](https://github.com/akiyan/midi2vgm), especially [`genpsg.py`](https://github.com/akiyan/midi2vgm/blob/main/scripts/genpsg.py) and [`psg_voice.py`](https://github.com/akiyan/midi2vgm/blob/main/scripts/psg_voice.py).
- Its PSG-only VGM converter explicitly reduces a MIDI arrangement to **three melody tones plus noise**, **folds unplayable pitches**, picks relevant channels from **note count/range**, and uses short **pluck/soft/sustain** volume profiles. The helper also supports bounded **vibrato**.
- **Lesson:** The per-program envelope strategy and *offline* selection of the three most meaningful parts are excellent candidates for TandyAMP. The converter is aimed at Game Gear/Genesis SN76489 rather than a native EX application; use ideas, not binaries or source snippets.

### 5. PSGTools: pre-rendered register streams and clock conversion

- [hightower70/PSGTools](https://github.com/hightower70/PSGTools) contains VGM-to-PSG conversion, optional compression, frame-rate resampling and SN76489 clock correction.
- **Lesson:** Add an **optional desktop preconverter** from MIDI to a compact `.TAM` event stream, preserving playable native `.MID` support. Cache full register values, emit only changes, quantize times explicitly, and support clock-rate variants. Never blindly play Sega-specific VGM PSG data on Tandy without confirming clock and noise behavior.

### 6. SN76489 and Tandy-specific noise behavior

- [SMS Power SN76489 hardware reference](https://www.smspower.org/Development/SN76489) describes **10-bit dividers**, **2 dB per volume step**, **white vs periodic noise**, and noise clocking from the third tone channel. **Tandy/older chip variants use a 15-bit noise LFSR**, versus 16-bit in several Sega variants.
- **Lesson:** An external preview/diagnostic simulator should model the **Tandy chip variant**, including noise reset. Do not mistake a converted Sega VGM for an exact Tandy sound. Tone-channel-2-clocked noise creates a trade-off: more interesting drum timbre but one less independent pitch if the noise follows it.

### 7. DOSMid: low-end DOS MIDI timing / architecture reference

- [DOSMid](https://dosmid.sourceforge.net/) targets **8086-class** DOS and documents a minimum memory footprint, while warning a faster 286 helps complex arrangements.
- **Lesson:** Keep disk I/O and graphics out of the music-critical loop, maintain compact event state and optimize for 7 MHz instead of introducing expensive modern DSP. TandyAMP already has a foreground PIT scheduler; measure remaining latency on the actual EX.

## Prioritized experiments

| Priority | Experiment | Why it matters | Resource / risk |
| --- | --- | --- | --- |
| **P1** | Offline MIDI→PSG analysis tool on modern PC: annotate melody/bass/harmony, note contention, out-of-range pitches and estimated PSG register writes; produce an **audio-free report first** | Quickly reveals what Canyon loses without increasing EX CPU usage | Low hardware risk |
| **Implemented; tune on EX** | Original program-aware **volume envelopes** (pluck/soft/sustain), bounded stepped attenuation from the MIDI program | Adds some instrument distinction while keeping note-off immediate | Hardware listening still required |
| **P1** | **Voice-leading hysteresis**: penalize pointless voice swaps, retain coherent bass and melody, and add short retrigger damping | Improves recognizable music and reduces clicks from crowded chords | Medium, extensive golden MIDI tests |
| **P2** | Compact **pre-rendered PSG event cache** `.TAM` (optional), with a native `.MID` fallback | Simplifies playback work on 7 MHz V20 and permits offline higher-quality reduction | Medium–high file format / code |
| **P2** | Optional, restrained **software arpeggio** for overflow chords, 1 voice at a time, disable when it destabilizes timing | Approximate extra polyphony and fuller harmonies | Medium–high; can make tunes warble |
| **Implemented; benchmark** | Cache hardware divider and attenuation per PSG tone slot; retain deliberate drum retrigger | Reduces unnecessary I/O writes | Hardware listening still required |
| **CC1 implemented; rest P3** | Restrained integer CC1 vibrato now works; portamento and extra retrigger envelopes remain experiments | More expressive held melody | Keep vibrato modest on real hardware |
| **P3** | Tandy-specific PSG/noise preview renderer and alternate tone2-clocked percussion | Better offline comparison and special drum textures | Nontrivial modeling, possible loss of third melody |
| **Defer** | Per-sample PCM on PSG, complex reverb, full FFT, arbitrary filter chains | Exceed hardware budget; not sensible for 7 MHz V20 during polyphonic MIDI | High risk, low benefit |

## Suggested verification approach

1. Establish a known hardware baseline using one simple type-0 MIDI and the owner-provided Canyon file; record elapsed time, audible melody, and any note dropouts.
2. Build **synthetic, distributable MIDI fixtures**, not copyrighted game MIDI: dense triads with a bass, drums concurrent with bass/third voice, melody retriggers, held notes and tempo changes.
3. Compare deterministic *event-order and register-write traces* between versions. Measure maximum notes retained, stolen-note frequency, redundant port writes, envelope transitions and simulated peak power.
4. Benchmark for a **7 MHz NEC V20** and refuse optional synthesis effects that exceed timing/write budgets. A native DOS mode remains available for any song without preconversion.
5. Only promote a change after listening on real EX hardware. **A GitHub Actions pass proves compilation and model-level correctness, not audible quality.**

## License and source caution

- The source/code for TandyAMP remains independently authored and MIT licensed.
- `TANDY.ADV` is proprietary and is not linked or distributed.
- The external projects above use different licensing regimes. Verify any project's current license **before copying even a small implementation fragment**; prefer independent register/math descriptions.
- Any future offline converter should not distribute copyrighted user MIDI, SoundFonts, tracker modules, Winamp skin resources or emulator ROMs.

See [PLAYER_ARCHITECTURE.md](PLAYER_ARCHITECTURE.md) for the code architecture and [README](../README.md) for supported command-line options and current limits.

## PIT2 fourth voice — now implemented as opt-in

Inspired by [TNDY Tracker](https://github.com/JKnipperts/TNDY-Tracker)'s independent PC-speaker track, TandyAMP now has optional **`/SPK4`** and **K** / **SPK4 second-row button**. When MIDI includes a **low bass note 24–52 (C1–E3) plus three other distinct PSG pitches**, PIT2 plays only that reserved bass, never an overflow treble note. An original native PIT2 note-divider table preserves the true low bass octave instead of copying the PSG's octave-folded divider. If no eligible bass is present, normal PSG playback is unchanged. This uses integer pitch/divider calculations and direct port 42h/43h/61h operations. The option is OFF by default; listen carefully on the EX because the speaker tone is **not independently volume-controlled** and may have a different balance. No preconversion or extra hardware is needed. A fourth PSG tone oscillator has *not* been added: this is a separate timer voice; the noise channel is still available for drums.

The implementation and unit tests are in `src/midi.c`, `src/main.c` and `tests/speaker_test.c`. It has not yet been verified acoustically on the physical EX. Relevant Tandy audio-mux reference: [PCjr/Tandy multiplexer engineering](https://nerdlypleasures.blogspot.com/2013/06/ibm-pcjr-and-tandy-1000-sound.html).

**2026-11-16 bass restriction and UI correction:** Added host tests for MIDI 24, 36, 48, 52 and for rejection of notes 23, 53, 60, 90; a fourth part without a valid bass is not sent to PIT2. The SPK4 was moved from its former 64×16 title switch into a 58×17 second-row button, retaining visible ON/OFF labeling, full hit testing and its own redraw flag. It remains off by default; physical EX output balance is unverified.

### Balanced control grid

As the native sound options grew, the former narrow transport row became crowded. The current interface has **two even rows of five 58×17 buttons**, with SPK4 next to DRUM and a functional MUTE button that restores the last audible master volume. Per-button redraw caching preserves V20 performance despite the larger controls.

### 2026-11-16 gain-stage revision after real EX listening

The owner reported that the former maximum volume 15 sounded quiet and values below 12 were barely audible. Code inspection found an important issue: the old automatic limiter targeted **1,024** modeled power even though a single full PSG tone represented **4,096**, unnecessarily lowering solo sound by at least four 2 dB register steps. This was corrected to a **6,144-power** ceiling with tests for both single-tone loudness and bounded multi-tone mixes. Master volume was also extended from **0–15 to 0–20**: levels 16–20 recover up to five software attenuation steps, subject to the still-active limiter and hardware saturation. Silence and mute remain hard zeros. This only uses existing 4-bit PSG hardware; SPK4 has no speaker volume register. Actual acoustic balance on the physical Tandy EX must still be checked.

### 2026-11-16 hardware visualizer and audio diagnostic

A real EX phone recording `3582.mp4` exposed a lack of indication whether SPK4 was actually sounding, despite its ON button. TandyAMP now exposes the **programmed PIT2 divider** for its fourth visualization channel, and uses actual final PSG output attenuation for CH1–CH3 rather than note velocity. Note labels can assist investigation of a long high-pitched sustained tone without imposing FFT analysis on the NEC V20. No software audio enhancer was added based solely on a phone recording: the observed approximately 10-second 1.75 kHz tone might be score-driven, so changing note-off behavior prematurely could break legitimate music. See [HARDWARE_AUDIO_REVIEW_3582.md](HARDWARE_AUDIO_REVIEW_3582.md) for numerical findings.

### 2026-11-16: Experimental adaptive SPK4 octave, no preconversion

A new optional three-way SPK4 cycle **OFF → BASS → ADAPT** preserves faithful fourth-bass output as an easy comparison mode. The experimental mode inspects three PSG note pitches and their final attenuation, then chooses *once per incoming MIDI bass note* whether to keep its octave or raise it 12 semitones. To protect musical balance, it prevents pitches near existing PSG notes and locks the octave to the active note's sequence stamp. This cannot make PIT2 electrically louder; an upper octave may be more audible on a small internal speaker. The original bass-only MIDI-source range 24–52 and 3-distinct-PSG-note requirement remain unchanged. The VIS pane shows actual pitched note names, marked `^` when raised. The feature requires listening tests on a real Tandy 1000 EX before being treated as an audio improvement.

### High-end findings and V20-native mitigation

The 30-second EX recording described in [HARDWARE_AUDIO_REVIEW_3582.md](HARDWARE_AUDIO_REVIEW_3582.md) includes a prominent sustained ~1,749 Hz tone with a third harmonic near 5,244 Hz, consistent with MIDI A6 from an SN76489 square-wave oscillator. No source MIDI event analysis establishes that the note is stuck; the player must not prematurely cut legitimate sustains. Source inspection also revealed a clear discontinuity: the lead melody voice's +5,000 priority score ended abruptly at MIDI 96 (C7), so MIDI 97 (C#7) was disproportionately likely to be lost.

**Implemented:** preserve upper melody notes with smooth priority taper instead of a C7 cutoff. Add conservative **HI SOFT** attenuation (default; can toggle to RAW with **H**, or launch `/NOHISOFT`). C6+ is attenuated one 2 dB PSG step; F#6+ is attenuated a second step after ~165 ms, targeting long A6-like tones. The trim is applied *after* user volume boost and consistently accounted in the limiter and actual programmed PSG attenuation. There is no floating-point DSP, no digital low-pass filter, no forced octave lowering of treble, and no artificial note-off. This is a low-cost loudness/priority improvement that needs A/B verification on the physical EX.
