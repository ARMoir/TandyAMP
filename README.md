# TandyAMP

**Planned DOS MIDI player for the Tandy 1000 three-voice sound chip (SN76489-compatible PSG).**

TandyAMP aims to play ordinary Standard MIDI Files (`.MID`) with an efficient, Winamp-inspired graphical interface on original Tandy-class hardware, starting with the **Tandy 1000 EX, NEC V20 at 7 MHz**. The program will target the built-in three-tone-plus-noise PSG at I/O port `0xC0`, rather than requiring an MPU-401, Sound Blaster, or external MIDI hardware.

> **Status: research / initial design.** This repository does not yet contain a working player, MIDI parser, or sound engine. The technical research below is a reference for clean-room development, not executable code.

## Research and design notes

- **[TANDY.ADV reverse-engineering findings](docs/TANDY_ADV_ANALYSIS.md)** — observations from the Miles Tandy music driver supplied with DOS SimCity Classic v2.00, including pitch tables, MIDI-scale attenuation, three-voice arbitration, pitch bends, PSG register order, and cautious audio routing.
- **[TandyAMP implementation blueprint](docs/PLAYER_ARCHITECTURE.md)** — which techniques to reuse conceptually, suggested MIDI event scheduler and voice allocator, and performance priorities for 7 MHz hardware.

The existing [Tandy EX sound BIOS compatibility research](https://github.com/ARMoir/WIN31DSK/tree/TANDY30/tools/tandy30/simcity-ex-sound) relates to *digital effect approximation for SimCity v1.02*. **TandyAMP is a separate MIDI music player** and can take advantage of note-on/note-off and controller events directly.

## Intended features

1. Standard MIDI File type 0/1 loading, tracks, variable-length delta times, running status, and tempo-map scheduling.
2. Three prioritized PSG melody/harmony channels; optional noise/percussion mapped from MIDI channel 10.
3. Note/velocity envelopes, pitch bend, sustain, and controlled channel stealing within three hardware voices.
4. Winamp-inspired Tandy graphics, keyboard control, optional serial mouse, progress and playlist display.
5. Small-memory, real-mode 16-bit DOS build, with playback scheduling kept independent of GUI redraws.

The most important milestone is **one ordinary MIDI file playing with correct timing and note-offs through all three tone channels on the real EX**. The GUI comes after reliable synthesis.

## Compatibility, rights and testing

- Hardware reference: Tandy 1000 EX with NEC V20 at 7 MHz and onboard three-voice sound. Other Tandy/PCjr systems will require verification.
- The original Miles `TANDY.ADV` is **proprietary** and is not included. Its binary behavior is documented for independently written code; the music-driver protocol is not an interchangeable API for this project.
- No DOS SimCity executables, Creative Voice sound effects, or other proprietary source/audio data are stored here.
- Suggested third-party inspirations, subject to verifying licenses before incorporating code: [DOSMid](https://dosmid.sourceforge.net/) (MIDI sequencing) and [TNDY Tracker](https://github.com/JKnipperts/TNDY-Tracker) (Tandy PSG playback).

