# Winamp source review — clean-room design reference

Source reviewed: [alexfreud/winamp](https://github.com/alexfreud/winamp), `community` branch. This is a **Windows** Winamp project (Visual Studio 2019), not portable 8086/Tandy code. The owner also supplied a classic Winamp screenshot as a visual reference.

**License boundary:** The referenced [Winamp Collaborative License 1.0](https://github.com/alexfreud/winamp/blob/community/LICENSE.md) restricts redistribution of modified versions/forks. **No Winamp code, bitmap resources, fonts, icons, skins, logos or audio are included or adapted verbatim in MIT-licensed TandyAMP**. We use general UI structure and programming concepts, implemented independently.

## Original units studied and TandyAMP implementation

| Winamp reference | Design observation | Independent TandyAMP implementation |
| --- | --- | --- |
| [`draw_main.cpp`](https://github.com/alexfreud/winamp/blob/community/Src/Winamp/draw_main.cpp) | Distinct routines for elapsed time, song name, controls and state | Original compact LED display and status drawing; fixed position/time labels; minimal dirty updates |
| [`main_buttons.cpp`](https://github.com/alexfreud/winamp/blob/community/Src/Winamp/main_buttons.cpp) | Button events separated from drawing | TandyAMP has keyboard event handler and mouse hit testing, with eight centered transport buttons |
| [`draw_pe.cpp`](https://github.com/alexfreud/winamp/blob/community/Src/Winamp/draw_pe.cpp) | Playlist rows, highlighting and selection | Up to 64 names, alphabetic auto-scan when no explicit songs; seven visible rows following current track |
| [`draw_eq.cpp`](https://github.com/alexfreud/winamp/blob/community/Src/Winamp/draw_eq.cpp) | Separate visualization/equalizer drawing | VIS button toggles three-note monitor; not a true equalizer |
| [`classic_vis.cpp`](https://github.com/alexfreud/winamp/blob/community/Src/Winamp/classic_vis.cpp) | PCM-driven FFT/oscilloscope visualization | Not ported. V20 displays voice/velocity information directly from MIDI state |
| [`resource/`](https://github.com/alexfreud/winamp/tree/community/Src/Winamp/resource) | Sprite-based skin resource names (MAIN, CBUTTONS, POSBAR, etc.) | Reference only. TandyAMP draws independent pixel fonts and beveled rectangles in 16 colors |

## Current screen and controls

- **320×200 Tandy graphics, not VGA or Win32.** The reference screenshot's stacked windows have been condensed into a single main panel plus one lower pane that toggles between PLAYLIST and VOICE MONITOR.
- Top panel: current filename, elapsed clock, MIDI/drum mode, master volume, playback state and activity marker. The marker does not seek.
- Eight independent clickable/keyboard-controlled buttons: **PREV / PLAY / PAUSE / STOP / NEXT / VIS / LOOP / DRUM**.
- The original serial-mouse workaround renders an 8×11 software cursor, with `INT 33h` only for input; the old driver-owned graphics cursor is no longer used.
- Dirty-region renderer avoids repeatedly drawing the whole frame and panel.
- `TANDYAMP` without a filename automatically creates a **64-entry** alphabetized `*.MID` playlist from the current working directory; explicit song arguments override it.
- No literal bitmap/skin copying, playlist-row clicking, real EQ, seeking, shuffle or desktop windows.

## Next engineering priorities

1. Confirm current software mouse and long playlists on the real EX/CF setup; earlier physical videos covered an earlier version.
2. Improve hardware responsiveness without interfering with foreground PIT subtick MIDI scheduling.
3. Add real track durations/seek map only if profiling proves an acceptable memory and CPU cost. Do not label an activity bar as seek.
4. Consider original alternative palettes or fonts; no copying of Winamp's licensed assets.

See [UI_DESIGN.md](UI_DESIGN.md) for geometry and [PLAYER_ARCHITECTURE.md](PLAYER_ARCHITECTURE.md) for actual code architecture.

**Research documentation only.** This source review is not a claim that Winamp itself runs on DOS or that its code was ported.
