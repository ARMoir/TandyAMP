# TandyAMP visual design and graphics implementation

The owner supplied an original classic Winamp player/equalizer/playlist screenshot as a **reference**, not a resource to ship. TandyAMP independently recreates the compact metallic feel: navy title bars, dark insets, green LED-style lettering, gray beveled transport controls and a black playlist. No licensed Winamp artwork or bitmap has been copied.

## Actual 320×200 layout (Tandy mode 09h)

| Area | Coordinates / role |
| --- | --- |
| Main panel | roughly y=1–98; title, clock, song name and MIDI/drum/volume information |
| Clock | inset near x=7–116, y=19–63; shows elapsed minutes/seconds |
| Track display | x≈123–312, y=19–63; track filename and mode/volume |
| Activity marker | y≈68; 12-pixel moving indicator only — **not** a seek bar |
| Controls | y=74–94; **eight 36-pixel buttons** at x=8 + 38 × index; **ninth SPK4 52-pixel title-bar button** at x=151, y=3–16 |
| Lower panel | y≈101–198; either playlist or **three-tone monitor** |
| Playlist | up to seven visible entries around the active item, in a list of up to **64** |
| Voice monitor | three bars driven from software voice note/velocity/activity, not audio FFT |
| Software cursor | original 8×11 black/white sprite, drawn in banked graphics memory |

Actual bottom-row button labels (left to right): **PREV, PLAY, PAUSE, STOP, NEXT, VIS, LOOP, DRUM**. The new ninth **SPK4** titlebar button independently toggles an optional fourth PIT2 PC-speaker tone; its pressed state reflects the feature and its shortcut is **K**. The previous seven-button layout was revised to accommodate DRUM. Each 5×7 glyph uses a six-pixel advance and is horizontally centered so it does not obscure neighboring bevels.

The original 267×422 stacked Winamp screenshot cannot be fitted literally onto 320×200 without illegible controls, so the lower region **switches modes** with `E` / VIS rather than opening a second window. There is no functional equalizer, 10-band EQ slider, drag seek bar, file browser or resizable skin yet.

## Rendering / performance

Tandy mode `09h` places 16-color pixel pairs at `B800:0000` across **four 8 KB banks**, indexed by scanline modulo four, at **160 bytes per scanline**. TandyAMP draws with an original 5×7 bitmap font, direct writes to VRAM and integer geometry.

A full background/frame draw occurs on GUI entry. During playback the dirty-region renderer changes only necessary areas:

- clock digits when the display second changes;
- filename, drum state and master volume when their associated state changes;
- button faces on transport, loop, VIS or drum mode changes;
- playlist pane on selection or mode change;
- separate 40×42 voice meters only when their represented note, velocity or activity changes;
- the 12×1 activity marker at its former and new positions.

Host framebuffer tests verify button text bounds, display title, zero-write idle redraws and upper bounds on common updates. These checks reduce risk on a **7 MHz NEC V20** but do not establish measured hardware FPS or sound jitter.

## Mouse cursor and click handling

The first mouse code used `INT 33h AX=1` to ask a DOS driver to draw its own pointer. Some serial-mouse drivers recognize `INT 33h` but **do not render a pointer in Tandy banked graphics mode 09h**. The updated player draws its own 8×11 arrow, saving and restoring each pixel underneath the cursor. Before repainting the UI it removes the pointer; after repainting it re-reads the changed background and draws it again, avoiding cursor trails.

`INT 33h` is still used for **input**: reset/presence, coordinate bounds, position and button state, and AX=5 click counts for short clicks. Startup probes 320-versus-640 horizontal units, and keyboard operation is always available. Titlebar text says `MOUSE OK` if the DOS interface was detected, `NO MOUSE` otherwise; it **does not prove the physical serial mouse was found**. A DOS serial mouse driver such as CuteMouse must be loaded first. `/NOMOUSE` disables detection/cursor.

The software cursor path and click dispatch are CI-tested with a simulated framebuffer. Physical EX mouse confirmation is pending.

## Evolution from the real EX video

The earlier recording `3578.mp4` showed the main player and audible MIDI on physical hardware, while button labels overlapped neighboring borders. The original 33-pixel buttons were enlarged and centered; later the layout changed again to **eight 36-pixel** buttons for DRUM.

Originally the player frequently repainted most of the song display and entire visualizer on a timer. That was replaced by cached/dirty sections, so clock and voice changes do not repeatedly redraw static UI. The video proves an earlier GUI ran on the EX; improvements since then require their own on-device evaluation.

## References and boundaries

- [README](../README.md): launch, keyboard, mouse setup and limitations
- [PLAYER_ARCHITECTURE.md](PLAYER_ARCHITECTURE.md): audio and UI data flow
- [WINAMP_REFERENCE.md](WINAMP_REFERENCE.md): specific Winamp source units reviewed and licensing
- Owner-provided classic Winamp screenshot; intentionally not redistributed

## Optional fourth voice UI

The eight existing 36-pixel transport buttons are **unchanged**. The additional **52×13 SPK4 button** is centered between the title and mouse-status indicator in the titlebar (x=151..202, y=3..15). It uses the same original 5×7 font and pressed/unpressed palette as the row buttons; no existing label is squeezed or clipped. A click or **K** calls the same `ta_set_speaker()` engine control and marks only the button and, when visible, the voice-monitor pane dirty. The switch is available during playback, paused or stopped, with no forced MIDI replay. The lower monitor text indicates when the extra channel is enabled, although only the three PSG tones have true volume meters.
