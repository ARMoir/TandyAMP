# TandyAMP — implemented architecture and engineering roadmap

**Status:** This document describes the current code in `src/main.c`, `src/midi.c` and `src/midi.h`, plus clearly separated future work. It supersedes the old v0.1 proposal (which incorrectly described a 28 KB/12-track, 18 Hz-only, keyboard-only prototype).

## Runtime data flow

```text
Command line: explicit files OR current-directory *.MID discovery
                         |
                         v
        64-entry case-insensitive DOS playlist
                         |
                         v
       File loader (up to 44 KiB, 24 SMF tracks)
                         |
                         v
     SMF 0/1 parser: delta VLQ, running status,
              track events and tempo changes
                         |
                         v
    Timestamp-ordered event groups / MIDI note state
             (up to 32 active notes)
                         |
                         v
      Pitch/velocity/CC/sustain/bend; volume leveling
                         |
                         v
        3-voice PSG allocation and duplicate
         divider merging; noise percussion
                         |
                         v
             Tandy PSG at I/O 0xC0

    Foreground PIT timing  <--->  transport state
          |                         |
          +------- GUI / keys / mouse +-----+
                   (dirty areas only)
```

## Implemented subsystems

### MIDI decoding and timing

- Loads Standard MIDI Files **type 0 and 1**, supports PPQN ticks, up to **24 tracks** and **45,056 bytes per song**. SMPTE timing and type 2 are rejected.
- Merges tracks by absolute event timestamp rather than simply consuming tracks in index order. Events at one MIDI timestamp update the note pool together before voice selection.
- Maintains program state for MIDI note on/off, velocity, sustain pedal, CC7 volume, CC11 expression and pitch bend. Handles tempo meta events, running status and end-of-track.
- Uses PIT channel 0 with the standard **65536 divisor** and temporary **mode 2** for a monotonic sub-BIOS-tick counter. Polling is in the foreground and subdivides work into up to **32 Q8 subticks**, ~6.9 ms at the normal 18.2 Hz BIOS rate. PIT mode 3 is restored on normal exit; **no new IRQ handler is installed**.
- Timer precision does not guarantee identical real-hardware rhythm under GUI or disk I/O load. Earlier EX recordings confirm playback, but new code needs repeat verification there.

### MIDI synthesis and arrangement

New live expressive engine: Program Change events are stored per MIDI channel; selected zero-based GM families use lightweight original pluck/soft/sustain profiles, each note remembering its shape and age. The player also responds to CC1 with a restrained ~5 Hz triangle vibrato using integer PSG-divider modulation. Voice scoring now gives stronger continuity preference. Final tone/volume I/O is cached (noise mode writes intentionally always retrigger). **No preprocessing or altered MIDI formats** are required; these are V20-side features. Note-off remains immediate and there is currently no full ADSR release tail, polyphonic arpeggiation, or complex program timbre emulation.


- Stores up to **32** active notes (held/sustained/eligible), maps them to **three hardware tone voices** while avoiding simultaneous duplicate PSG dividers.
- Prioritizes musically salient notes, can restore a held note after a stolen voice is freed, and updates selection when CC volume/expression changes. Bass notes below the normal SN76489 pitch floor are octave-folded.
- Uses hardware noise for General MIDI channel 10 drums, with short envelopes. A conservative pre-scan can recognize legacy channel-16 drum patterns; `/DRUM16` and `/NODRUM16` override it. Changing drum mode with `D` restarts the song.
- The 16-level master volume (`/VOL:0..15`) applies to tones and percussion. Always-on integer-based automatic leveling attenuates dense mixes and recovers slowly. It is an **estimated hardware-output budget**, not a microphone-based loudness measure.
- The notes and sound logic are **original**; the Miles `TANDY.ADV` was used only as a factual register/algorithm reference, never linked or copied.

### DOS interface and playlist

- `TANDYAMP` with no song arguments performs a **non-recursive `*.MID` scan of the current working directory**, alphabetically sorts matches ignoring case, stores up to 64 entries, and starts track 1.
- `/LOOP` repeats the list. `N` / `P` navigate; if filenames are passed they are used **instead** of the scan and preserve the supplied order.
- Rejects empty directory, excessive path length or too many explicit tracks with messages before drawing the GUI. Does **not** currently skip unsupported songs automatically once playback tries to load them.
- GUI uses video BIOS mode `09h` (320×200, 16 colors). Pixel routines write to Tandy's four interleaved 8 KB video banks at `B800:0000`.
- Text-only `/TXT` mode does not request the graphics mouse cursor.

### Visuals, controls and serial mouse

- Eight **36-pixel transport buttons**: PREV / PLAY / PAUSE / STOP / NEXT / VIS / LOOP / DRUM, plus a separate **64×16-pixel SPK4 titlebar button** with ON/OFF status for the extra PIT2 tone. K toggles the same setting. Their actions share the keyboard input dispatcher.
- Upper area: filename, elapsed-time clock, playback state, drum detection mode, master volume and animated *activity marker*. The marker is not a scrub/seek bar.
- Lower pane shows a seven-row window onto the **64-entry** playlist or a **three-tone voice monitor**; it is not an FFT spectrum or equalizer.
- Dirty-region renderer updates only changed clock digits, labels, selection, activity dots, meters or buttons rather than redrawing the whole image every timer pass.
- Mouse support uses standard DOS `INT 33h` to detect movement and clicks (not raw serial I/O). To work around graphics-driver issues in Tandy banked mode `09h`, an original **8×11 software cursor** saves and restores its covered pixels. It probes 320 vs 640 X units, records short clicks via AX=5, and reports `MOUSE OK` / `NO MOUSE`. `/NOMOUSE` disables it.
- Serial-mouse operation on the physical EX requires a loaded compatible DOS mouse driver, e.g. a known working CuteMouse serial configuration. The GUI and cursor tests run on a **simulated framebuffer**, not the real RS-232 port.

## Tests and reproducible build

`tests/make_test_mid.py` creates original synthetic inputs; `tests/midi_test.c` tests format/track bounds and percussion; `tests/playback_test.c` and `tests/mixer_test.c` test event ordering, note allocation and estimated gain. `tests/ui_test.c` exercises the real UI drawing implementation on host-allocated Tandy VRAM and validates cursor restoration, clicking, coordinate scaling, redraw budgets and automatic directory playlists.

`.github/workflows/build-dos.yml` runs these tests, builds a DOS EXE with Open Watcom 2.0 and publishes the result only on success. See [BUILD_AND_RELEASE.md](BUILD_AND_RELEASE.md).

## Still not implemented / known limitations

- No MIDI type 2, SMPTE timing, unlimited file length or general GM wavetable instruments.
- Only three simultaneous PSG pitches; extra MIDI polyphony must be approximated.
- No visual seek, accurate full-song duration bar, file chooser, clickable playlist song rows, user-selectable skins, shuffle or true EQ.
- The current CLI auto-scan is **current-directory only**, not recursive, and caps the list at 64.
- A supported mouse driver does not guarantee EX serial-device detection or cursor smoothness; actual EX retest pending.
- Priority next: listen to recent builds on the real EX, validate serial mouse movement, test large playlists on CF media, then improve UI responsiveness and note quality without introducing slow framebuffer writes.

## Historical research used

- [TANDY.ADV analysis](TANDY_ADV_ANALYSIS.md): factual 96-note, 128-step loudness, allocation and register observations. MIDI/PSG code is independently authored.
- [Winamp design reference](WINAMP_REFERENCE.md): conceptual workflow and chrome only; no Winamp code/assets copied.
- [UI design](UI_DESIGN.md): screen geometry, cursor/redraw details, and changes documented from the real EX recording.
- [README](../README.md): user instructions, commands and current limitations.
- [MIDI/PSG implementation audit and new resources](MIDI_PSG_RESEARCH.md): detailed implemented/partial/pending findings and prioritized experiments.

## Optional hardware PC-speaker voice (SPK4)

The player retains three PSG tone channels and their noise channel. When users opt in with **`/SPK4`**, the enlarged **SPK4** titlebar button or **K**, the allocator can reserve **only MIDI 24–52 (C1–E3) bass notes** for PIT2. It first confirms three other distinct playable PSG pitches; otherwise no fourth voice is used. The original three PSG voices carry the other parts, never the reserved bass. Unlike conversion from an already octave-folded PSG divider, PIT2 uses an independently generated 1,193,182 Hz **true-bass MIDI divider table**, with integer ±2-semitone pitch-bend interpolation. This avoids playing deep bass an octave too high. The physical backend writes mode 3 to port 43h, counter low/high bytes to port 42h, and read-modify-writes **only bits 0–1 of port 61h** to enable/disable the speaker. **PIT0 timing and BIOS tick configuration are unchanged.**

Because the PC-speaker channel has no per-voice attenuation, TandyAMP gates quiet extra notes rather than forcing them at full level. Toggle OFF, note release, pause, stop, exit and master mute turn off the extra tone. The option is OFF by default and preserved between songs if enabled. Testing uses a mocked PIT2 output for note allocation and switch state, but the actual acoustic blend and port 61h routing require hardware validation on the real EX.
