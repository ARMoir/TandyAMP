# Classic Winamp source reference for TandyAMP

**Source for design research:** [alexfreud/winamp](https://github.com/alexfreud/winamp), branch `community`. This is a Windows Winamp codebase with a Visual Studio 2019 build, not DOS/8086 code. The project owner also provided an original Winamp screenshot as the visual guide.

**Rights boundary:** This source repository currently carries the [Winamp Collaborative License (WCL) 1.0](https://github.com/alexfreud/winamp/blob/community/LICENSE.md), which explicitly restricts redistribution of modified Winamp code and forks. Its resources contain original Winamp bitmap artwork. **Do not copy source code, artwork, bitmaps, icons, fonts, skin resources, or audio from that repository into MIT-licensed TandyAMP.** We can independently implement general UI conventions and documented behavior; attribution does not waive copying restrictions.

## Concrete components reviewed

| Reference in alexfreud/winamp | What it does | TandyAMP interpretation |
| --- | --- | --- |
| [`Src/Winamp/draw_main.cpp`](https://github.com/alexfreud/winamp/blob/community/Src/Winamp/draw_main.cpp) | Draws main player title, song name, time display, shuffle/repeat, bitrate display, buttons | Draw original compact LED-style clock and song-name region; replace PC audio bitrate with `3-VOICE / MIDI / tempo` indicators |
| [`Src/Winamp/main_buttons.cpp`](https://github.com/alexfreud/winamp/blob/community/Src/Winamp/main_buttons.cpp) | Separates transport-button events (previous/play/pause/stop/next) from drawing | One shared `player_command()` handler for both hotkeys and future serial-mouse button clicks |
| [`Src/Winamp/draw_pe.cpp`](https://github.com/alexfreud/winamp/blob/community/Src/Winamp/draw_pe.cpp) | Draws playlist rows, current selection, title, and track time | Compact playlist with single-row highlight, scroll window, and text clipping; keyboard navigation first |
| [`Src/Winamp/draw_eq.cpp`](https://github.com/alexfreud/winamp/blob/community/Src/Winamp/draw_eq.cpp) | Independently draws equalizer controls and graph | Switchable Tandy three-voice activity panel; label explicitly **VOICE MONITOR**, not a real audio equalizer |
| [`Src/Winamp/classic_vis.cpp`](https://github.com/alexfreud/winamp/blob/community/Src/Winamp/classic_vis.cpp) | Computes classic visualizations from PCM (including spectrum/oscilloscope processing) | **Do not port FFT/PCM visualization** to a 7 MHz EX. Use the MIDI engine's existing note-on, velocity, pitch and envelope states directly |
| [`Src/Winamp/resource/`](https://github.com/alexfreud/winamp/tree/community/Src/Winamp/resource) | Includes `MAIN.BMP`, `CBUTTONS.BMP`, `POSBAR.BMP`, `Pledit.bmp`, `Eqmain.bmp`, `SPEC.BMP`, `numbers.bmp`, etc. | Palette and composition **reference only**. Produce our own 16-color shapes, fonts, buttons and indicators without copying images |

## Proposed TandyAMP UI behavior

The source Winamp reference is a multi-window desktop player. We have only **320×200 16-color Tandy video mode 09h**, so retain the feeling rather than the actual stacked-window geometry.

| Screen region | Visual treatment | Behavior and budget |
| --- | --- | --- |
| Top title bar | Dark metal-gray bevel, small white text | One-row name and version; no redraw except when state changes |
| Player display | Black inset, original green 5×7 LED glyphs | Elapsed time, MIDI song name, `PLAY/PAUSE/STOP`, small tempo and voice count indicators |
| Progress line | Narrow gray track with bright moving position | Implement proper time-seeking **only after** the MIDI parser can create an accurate duration / seek map; v0.1 progress currently indicates activity, not seek |
| Transport controls | Original beveled Previous / Play / Pause / Stop / Next | Keyboard and eventual clickable mouse must use exactly the same command actions |
| Lower panel | Same frame, toggle `PLAYLIST` / `VOICE MONITOR` | Playlist: active row + scrolling. Monitor: three tone columns and optional noise icon; never pretend to be 10-band EQ |
| Playlist options | Small repeat/shuffle indicators | Implement actual shuffle only when playlist cursor and RNG state work; no inert cosmetic buttons |
| CLI | `TANDYAMP /TXT SONG.MID`, `/LOOP`, multiple filenames | GUI is only an alternative front end. Music timing, play/pause/stop, and playlist operations remain independent of drawing |

### Practical implementation order

1. **Preserve correct MIDI timing first.** v0.1 is still quantized to the ~18.2 Hz BIOS clock and hasn't been measured on physical EX hardware. A higher-resolution, correctly restored timer is more important than visual polish.
2. Refactor transport input into **one command dispatcher** shared by keyboard, CLI mode and eventual serial-mouse hit-testing. UI draws should observe state, never perform MIDI decoding.
3. Replace any regular full-screen redraw with **dirty rectangles**, especially time digits, volume bars, song-name marquee, and playlist highlight. Retain a static background.
4. Add playlist loading / scrolling and true duration accounting. Show an explicit unknown-time indicator rather than a fake time scale when the file has no precomputed total.
5. Add a small original Tandy-specific **skin palette table** (gray/blue and optional alternative palettes) rather than importing Winamp resource bitmaps.

## What not to do

- No Win32, DirectDraw, bitmap blitting, DSP/FFT, plugins, Windows APIs, Winamp project files, or `*.BMP` assets as dependencies.
- No literal pixel-perfect replication or copying UI sprite layouts from the original licensed bitmaps.
- No claim that the three PSG voices can reproduce a multi-band EQ: the monitor shows **MIDI note activity**, not measured sound spectrum.
- No use of the Winamp Collaborative License source in this repository's MIT implementation.
- No direct use of the Miles `TANDY.ADV` proprietary code; refer to [TANDY_ADV_ANALYSIS.md](TANDY_ADV_ANALYSIS.md) for factual hardware insights only.

**Status:** Design reference and engineering notes. This document does **not** claim new TandyAMP UI functionality was implemented.
