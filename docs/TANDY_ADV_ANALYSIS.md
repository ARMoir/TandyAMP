# TANDY.ADV — Tandy three-voice music-driver findings

This document carries forward the binary analysis originally recorded in [WIN31DSK/TANDY_ADV_ANALYSIS.md](https://github.com/ARMoir/WIN31DSK/blob/TANDY30/tools/tandy30/simcity-ex-sound/TANDY_ADV_ANALYSIS.md) and applies it specifically to a **standalone Standard MIDI File player**. No Miles driver code or copyrighted waveform/audio data is included here.

## Provenance and limits

- Owner-supplied archive: `SimCity_DOS_EN_Version-20-Quaders-Release(1).zip`
- Original entry: `Sim City v2.00/DATA/TANDY.ADV`
- Binary size: **8,746 bytes**
- SHA-256: `ccf90daba63f33e686d89eb1205a817c90723f2dec6095978ad20c3a9b3cf80f`
- Embedded identifier: **"Tandy 3-voice internal sound"**
- Driver system: Miles Design Drivers (music/MIDI `.ADV` driver, not a digital-effect `.ADV` driver).

These observations are from disassembly and embedded data tables. All offsets below are **file offsets**, not runtime segment-relative addresses. Behavior inferred from assembly should be treated as an engineering reference rather than a validated public API or a license to redistribute the binary.

## Confirmed implementation characteristics

| File offset(s) | Observed implementation | TandyAMP design lesson |
| --- | --- | --- |
| `0x00DF` | Identifies **Tandy 3-voice internal sound** | Targets the same onboard tone/noise generator as the Tandy 1000 EX. |
| `0x00FD–0x015C` and `0x015D–0x01BC` | Two aligned **96-entry** note period lookup tables, split into low divisor bits and high divisor bits | Precompute notes in a compact format for fast, division-free note-on events. |
| `0x01BD–0x023C` | **128-entry** MIDI-like loudness-to-PSG attenuation table | Map MIDI velocity/controller volume to the PSG’s 16 attenuation levels while respecting its non-linear loudness response. |
| `0x023D–0x0242` | Channel-specific **tone/volume latch masks** | Precompute the PSG command bytes for voice 0, 1 and 2. |
| `0x035A–0x036F` | Writes silence to PSG at I/O `0xC0` and sends `0x68` to `0x61` | Explicit audio routing exists; copying `out 61h,68h` unconditionally is **not** safe. |
| `0x03D3–0x0435` | Periodic state update and refresh of active voices | Separate music timing from per-voice updates and UI drawing. |
| `0x0497–0x04E2` | Locates a free slot among three tone voices; falls back if all are used | Implement allocation, priorities and note stealing when polyphony exceeds three notes. |
| `0x05BC–0x069E` | Interpolates neighboring semitone divisors using signed arithmetic and a `0x2000` scale | Pitch bending / portamento can work with integer fixed-point arithmetic, no floating point. |
| `0x06B7–0x06D6` | Writes the PSG tone latch, divider data and volume commands in hardware order at `0xC0` | Use predictable, bounded I/O writes; verify any needed pacing on the physical EX. |

### Musical pitch model

The PSG produces a square wave, approximately

```text
frequency_hz ≈ 3,579,545 / (32 × period)
period ≈ 3,579,545 / (32 × frequency_hz)
```

The 10-bit divider `period` is limited to 1–1023 (the behavior of zero is device-dependent; do not use as a normal note).

The reconstructed note table included these octave-consistent examples:

| Table index | Period | Approx. pitch |
| ---: | ---: | ---: |
| 45 | 508 | 220 Hz |
| 57 | 254 | 440 Hz |
| 69 | 127 | 881 Hz |

For a fresh MIDI engine, calculate our **own** 10-bit note table from standard MIDI note frequencies, then validate clamp and out-of-range behavior. The historical lookup-table design is the useful technique; do not embed the Miles driver's proprietary tables verbatim.

### 128-to-16-step volume conversion

A Standard MIDI File can specify note velocity 1–127, channel volume controller CC7, and expression CC11. The hardware allows 16 levels of **attenuation** per tone channel: `0` is loudest and `15` is silent. A compact 128-entry precomputed mapping avoids expensive runtime math and supports independent voice envelopes.

The actual relation between MIDI loudness and perceived PSG volume should be tuned on the EX. **Do not infer that linear numeric attenuation gives linear audible loudness.** Also make sure a note-off silences the correct currently allocated voice.

### Voice allocation and pitch bends

Three PSG tones must represent potentially many MIDI notes. The ADV's free-slot allocation demonstrates a reasonable baseline:

1. Reuse a physical voice when its existing MIDI note is rearticulated.
2. Assign an unoccupied voice when available.
3. Otherwise choose a voice to steal based on a stable musical policy (priority, age, attack, sustain, volume or track).
4. Restore a still-held note when its voice becomes free **only if** the scheduler has retained the note state.

The engine should remember `track/channel/note` ownership and implement note-off, sustain pedal, program changes (limited timbral effect on PSG), CC7/CC11, and pitch bend. The ADV uses signed integer interpolation of semitone divisors; an original fixed-point approach can smoothly update a held note without costly recomputation.

### PSG programming and EX routing

- **Tone channels:** latch + high divider data, then attenuation; repeat for three voices only when values change.
- **Noise channel:** the fourth SN76489 voice can approximate percussion. This is a future design choice, not proof that the proprietary ADV offers full MIDI drum mapping.
- **I/O address:** `0xC0` for Tandy PSG.
- **Port `0x61`:** The ADV sets `0x68` as part of its startup path. On different Tandy models, port `61h` also participates in audio selection and other system behavior. **Never blindly write `0x68`** in a general-purpose player. Verify the EX-specific bit assignments; if required, do a documented read/modify/write and preserve or restore unrelated state. Even this should be hardware-tested.
- **I/O delay:** the ADV has short instruction gaps between PSG writes. Add a minimal delay only when actual hardware testing demonstrates glitches; 7 MHz V20 I/O may already supply enough spacing.

## What we should *not* reuse

- **Do not load `TANDY.ADV` as a standalone `.MID` player.** It is a component meant for a Miles host interface, and it does not provide a graphical application, file parser, or playlist.
- **Do not distribute its executable or a disassembly-derived source copy.** Implement algorithms independently using the factual, mathematical and register-level observations.
- **Do not reuse `SCEXSND` as TandyAMP's main synthesis engine.** `SCEXSND` tries to infer tones from anonymous 8-bit PCM; TandyAMP already has MIDI note events and can produce cleaner notes directly.
- Do not assume all simultaneous notes can be heard; three-tone hardware imposes a real polyphony ceiling.
- Do not assume MIDI timing is adequately served by the 18.2 Hz system tick. The chosen timing strategy needs accurate tempo and event handling without disrupting BIOS/DOS.
- Do not treat port `61h` configuration as a guaranteed volume boost.

## Recommended TandyAMP follow-ups

**First priority:** original 96+ note divider mapping, 128-step velocity attenuation, three voice states with correct note-off/stealing, and integer tempo scheduling. Next, pitch-bend interpolation and optional noise-channel drum accents. Leave routing changes, I/O pacing and visualizers until working hardware playback establishes a baseline.

## References

- [Original documented investigation on WIN31DSK](https://github.com/ARMoir/WIN31DSK/blob/TANDY30/tools/tandy30/simcity-ex-sound/TANDY_ADV_ANALYSIS.md).
- Owner-provided SimCity Classic DOS v2.00 `TANDY.ADV` and `README.TXT` (not redistributed).
- [Tandy 1000 SX Technical Reference Manual](https://www.lo-tech.co.uk/downloads/manuals/tandy/Tandy_1000SX_Technical_Reference_Manual.pdf) — PSG and audio routing design (model-specific differences apply).
- [PCjr / Tandy audio multiplexing discussion](https://nerdlypleasures.blogspot.com/2013/06/ibm-pcjr-and-tandy-1000-sound.html) — hardware family differences.
