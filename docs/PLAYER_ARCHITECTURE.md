# TandyAMP — implementation blueprint

> **Implementation status (v0.1):** The initial Standard MIDI File type 0/1 parser, three-tone PSG renderer, Open Watcom 8086 MZ build, MIDI tests, original demo, DOS command-line options, and the 320×200 Winamp-inspired GUI now exist in `src/midi.c`, `src/main.c`, `tools/make_demo.py`, and `.github/workflows/build-dos.yml`. The original sections below describe the longer-term architecture. Current limitations: BIOS 18.2 Hz timing, 28 KB / 12-track limit, no mouse or seek UI, no file picker, limited instrument timbre. **Physical Tandy EX testing remains pending.** See [UI_DESIGN.md](UI_DESIGN.md) for the reference-image adaptation.

This is a proposal for a new program, **not a description of software already implemented**.

## Target and overall flow

```text
MIDI file (.MID, type 0/1)
       |
       v
SMF parser (header, tracks, running status, delta-time VLQ)
       |
       v
Merged timestamped events / tempo map
       |
       v
Bounded-time scheduler  ---- transport state (play/pause/seek)
       |
       v
MIDI channel / note state (note-on, note-off, sustain, velocity, CCs)
       |
       v
Three-voice allocator + optional noise/percussion policy
       |
       v
Integer note period + velocity/volume lookup + pitch bends
       |
       v
Tandy SN76489-compatible PSG at I/O port 0xC0
```

The UI reads the current transport and channel state; **the sound engine must never depend on a redraw**. Avoid full-screen redraws on every music event.

## What we learned from the original TANDY.ADV

- **96-note period tables** demonstrate efficient lookup-based note-to-divider mapping. Recreate the table independently from equal-tempered MIDI frequencies, with an explicit policy for out-of-range notes.
- **128-level attenuation table** demonstrates efficient MIDI-style volume control. Calculate TandyAMP's own mapping from velocity × CC7 × CC11; cap each hardware attenuation command to 0..15 and test note-offs.
- **Three-slot voice allocation** is an essential part of music quality, not an afterthought. Compare oldest-note, quietest-note, most-salient-note and sustained-note policies using synthetic MIDI test sequences.
- **Pitch bend via integer interpolation** is achievable on a V20. Keep the fixed-point intermediate types wide enough to avoid overflows.
- **Direct PSG writes to port 0xC0** need a robust channel-specific latch/data command encoder, preferably using cached register values.
- **Port 0x61 audio routing** is a hardware configuration concern requiring model-specific read/modify/write; do not hardcode the Miles driver's 0x68 setting.

See [the offsets and detailed observations](TANDY_ADV_ANALYSIS.md) for evidence.

## First deliverable: audible MIDI before graphics

An independently compiled real-mode DOS program should:
1. Open one specified `.MID` file from disk and decode type 0 or type 1 tracks; gracefully reject unsupported cases.
2. Schedule note-on, note-off and tempo changes with consistent elapsed time. A timer faster than 18.2 Hz may be required; keep DOS calls out of time-critical interrupt handlers.
3. Use three PSG tone channels with deterministic note stealing and no stuck notes.
4. Handle end-of-track, explicit stop and Ctrl-C/exit safely (silence PSG and restore any modified interrupt/system state).
5. Record deterministic test traces and compare tempo/note order against the expected MIDI event stream.
6. Be timed on a real 7 MHz NEC V20 before adding animation or graphic skins.

## Graphical player milestone

Target a compact **Winamp-inspired** UI in Tandy's 320×200 16-color mode: song title, elapsed time, position bar, play/pause/stop/next, three-channel indicators, simple file browser and optional playlist. Aim for keyboard-first and mouse-optional; repaint only dirty rectangles. This is an interface design target, **not an implemented feature**.

## Integration boundaries

- MIDI timing/parser can be written in Open Watcom 16-bit C; PSG I/O and any timer-critical code can use small assembly routines where profiling demonstrates a benefit.
- Research from [DOSMid](https://dosmid.sourceforge.net/) and [TNDY Tracker](https://github.com/JKnipperts/TNDY-Tracker) is useful, but **verify licenses and attribution requirements before incorporating third-party code**. Prefer independent implementations of the small hardware-specific routines.
- Do not import proprietary Miles `.ADV` drivers or SimCity assets into this repository.
- This is separate from [SCEXSND](https://github.com/ARMoir/WIN31DSK/tree/TANDY30/tools/tandy30/simcity-ex-sound), which is a digital-sound BIOS translator rather than a MIDI sequencer.
