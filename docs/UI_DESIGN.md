# TandyAMP visual design — two balanced rows

The original classic Winamp screenshot provided by the project owner is used as a **design reference**, not as a source of code or artwork. TandyAMP uses independently drawn gray/blue chrome, dark displays, green text and a 5×7 font compatible with the original Tandy's **320×200, 16-color mode 09h**.

## Current 5×2 control layout

All **ten** functional buttons are the same **58×17 pixels**, with five equal-spaced controls per row. Columns begin at x=10, 70, 130, 190, 250 (2-pixel horizontal gaps).

| Row | Y range | Controls |
| --- | --- | --- |
| Playback | y=72–88 | PREV · PLAY · PAUSE · STOP · NEXT |
| Options | y=91–107 | VIS · LOOP · DRUM · SPK4 · MUTE |

SPK4 is no longer in the title bar. Its second-row button cycles **SPK4 OFF → SPK4 BASS → SPK4 ADPT → OFF** with each click or **K** keypress. The last label abbreviates ADAPT to fit the 58-pixel button. It remains an *optional bass-only* fourth pitched voice using PIT channel 2 (MIDI notes 24–52). MUTE is the **tenth real control**, not a spacer: **M** or a click mutes audio, and the next press restores the previous audible master volume. The label shows **MUTE ON/OFF**.

The widest eight-character captions are 47 pixels at the 5×7 font's six-pixel character pitch; a 58-pixel button provides ample inset. Mouse click zones are exactly the drawn rectangles. The original Winamp-inspired metal bevel and green status text remain.

## Screen allocation

| Region | Location / content |
| --- | --- |
| Upper frame | y=1–110: player title, time, track, volume, status |
| Title bar | y=3–15: title and mouse-driver status; no longer a separate SPK4 |
| Clock and song | y=19–63 in black inset windows |
| Activity marker | y=67–69, *not* a seek bar |
| First row | y=72–88, five transport buttons |
| Second row | y=91–107, five options including SPK4 and MUTE |
| Lower pane | y=112–197, playlist or **four-column live output monitor** |
| Playlist | seven visible songs with 8-pixel row spacing, from up to 64 entries |
| Bottom legend | y=187–196, **white-on-black** keyboard reminder for higher contrast |

The Winamp reference is vertically stacked; the EX cannot show three tall windows without tiny controls. Instead, one lower pane is toggled by **E** / VIS. There is no real EQ, draggable seek bar, shuffle or graphical file picker.

## Minimal redraws

Tandy video mode 09h has four interleaved 8 KiB banks at `B800:0000`, with two color pixels per byte. TandyAMP avoids full-screen refreshes during normal playback. Its ten buttons share a state-aware `draw_button()` routine that caches each button's prior pressed state. A general transport redraw updates only changed buttons; separate **UI_SPK4** and **UI_MUTE** dirty flags redraw only their button. Volume changes update the text field; the cursor is removed and restored only when there are actual changed regions.

Other elements update independently: clock each displayed second, selected playlist when the track changes, individual PSG voice bars when note/level changes, and only the old/new 12-pixel activity marker. The voice monitor has **four columns** (CH1/CH2/CH3/SPK4) but only three PSG oscillators. The PSG columns show **actual hardware attenuation** (0 loudest, 15 mute), not merely MIDI velocity, and identify the corresponding note below each bar. The SPK4 column lights only when a nonzero PIT2 divider has been programmed, and displays its **actual pitched note** (including an octave-up `^` marker in ADPT mode); the **READY** state means SPK4 is enabled but currently silent. **PAUSE** and **OFF** are distinct states. No FFT or PCM processing occurs. When VIS is displayed, changed meter values are inspected about six times per second and only the affected 40×29 bar plus its 40×8 label is repainted. The lower legend now uses white text over a black strip because its former gray-on-gray rendering was faint in the physical EX video. The newly lowered pane preserves seven playlist rows by tightening spacing rather than dropping songs.

## Serial mouse

Movement and button input still come from a DOS `INT 33h` driver (e.g. correctly configured CuteMouse). Because some drivers cannot render in the Tandy's banked graphics mode, TandyAMP draws its own **8×11 software arrow** and saves/restores underlying pixels. Its input code handles brief captured clicks, held-button debouncing, and either 320 or 640 horizontal mouse units. All ten buttons use the same geometry for drawing and hit-testing. `/NOMOUSE` and keyboard shortcuts remain available.

**MOUSE OK** confirms an INT 33h interface exists, not that the physical serial mouse is working. The current UI has passed host framebuffer tests; its appearance and responsiveness on the 7 MHz EX still require testing on real hardware.

## Development history

The physical EX recording confirmed an earlier GUI rendered and produced sound, but the old tiny buttons overlapped and status updates repainted too much. Later iterations centered the buttons, added DRUM, and temporarily placed SPK4 in the title bar. The current revision consolidates all controls into two equal rows of five while keeping individual-button redraw caching.

## Related documentation

- [README](../README.md): commands, MIDI behavior, shortcuts
- [PLAYER_ARCHITECTURE.md](PLAYER_ARCHITECTURE.md): code structure and hardware
- [WINAMP_REFERENCE.md](WINAMP_REFERENCE.md): original Winamp conceptual design reference and license boundaries

## SPK4 three-state button and adaptive-octave display

The lower second-row SPK4 control is a **three-position switch**, not a simple on/off toggle. Labels are **SPK4 OFF**, **SPK4 BASS** (faithful pitch, green), and **SPK4 ADPT** (adaptive octave, yellow). Keyboard K and serial mouse clicks share identical cycling: OFF → BASS → ADAPT → OFF. The button's state cache now stores **all three state values**, so BASS → ADAPT still causes a tiny 58×17 redraw. Its hit area and the two-row geometry are unchanged.

The four-column VIS pane continues to light SPK4 only for an *actual* programmed PIT2 output, not merely when its mode is enabled. If ADAPT shifts a bass note up one octave, the pitch label shows the audible note plus a `^` indicator (e.g., `C3^` for a raised C2). The engine keeps the octave stable for that specific MIDI note instead of changing it mid-sustain. This requires no extra screen scans, FFT, or disk processing.

## High-note balance indicator

The GUI now shows **HI SOFT** (green) or **HI RAW** (red) in the upper-right part of the track-display inset (near x=255, y=25). The **H** keyboard shortcut toggles the engine's high-register attenuation without restarting playback. The player has the same **ten buttons in two rows**; no eleventh button or narrow label has been introduced. When only H is pressed, the small **52×8 indicator** is repainted, not the track display, button grid, visualizer or playlist. If the live hardware attenuation of a high note changes, its corresponding existing meter updates independently as usual.
