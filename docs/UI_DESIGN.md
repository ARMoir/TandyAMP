# Winamp-inspired interface reference

The project owner supplied a reference screenshot of a classic Winamp window stack (player, equalizer, playlist). It shows a compact dark-gray metal interface, narrow blue title bars, black displays with green LED typography, beveled metallic transport controls, a small spectrum visualizer, and bright-green playlist entries.

**TandyAMP does not copy the screenshot's bitmaps, fonts, logos, or Winamp program code.** It recreates the general interaction ideas using original drawing code and a 5x7 pixel font compatible with the Tandy's 16-color mode 09h.

## How that becomes a 320×200 EX screen

The original reference is approximately 267×422 vertically. The EX provides only **320×200** in the desired 16-color mode, so reproducing all three tall windows simultaneously would leave controls unreadably small.

v0.1 instead combines:
1. **Main player** (screen y=1–98): TANDYAMP title, LED-style elapsed time, song title, activity line, playback progress animation, and seven bevel-style transport keys.
2. **Switchable lower pane** (screen y=101–198): playlist with the active song highlighted; pressing **E** switches to three PSG voice-level bars inspired by the equalizer/visualizer.
3. **Keyboard shortcuts**: SPACE, N, P, S, R, E, L, Q/ESC, with equivalent launch options for text-mode/headless use.

This is **an original Winamp-inspired interface**, not a pixel-exact clone. The beveled keys are currently visible indicators only; mouse clicking is not yet implemented.

## Color budget

The GUI deliberately uses a small subset of the Tandy's indexed 16-color palette:

- 0 black for the displays and playlist background
- 1/9 blue highlights for title bars
- 7/8 light and dark gray for beveled chrome
- 10 bright green for current track and three-channel activity
- 14 yellow for highlights and LED accents
- 15 white for selected title text

It uses a banked framebuffer at B800:0000: **four 8 KB banks, 160 bytes per scanline, 2 pixels per byte**, ordered by scanline number modulo four. No VGA dependency or full-frame redraw each timer tick.

## Hardware priorities

Do not sacrifice correct note-offs and tempo just to animate the display. v0.1 schedules sound in foreground polling on the BIOS 18.2 Hz tick and redraws partial regions. This is a baseline, not a precision metronome.

Planned: higher-precision, safe MIDI timer; input-driven clickable buttons through a PC-compatible serial mouse; incremental seek bar, song metadata, file browser, playlist loading, and user-selected skins. A true frequency equalizer isn't realistic on three square-wave oscillators; the lower panel is a **voice visualizer**, not a signal-processing equalizer.

## External reference

Owner-provided Winamp 2-era screenshot in the conversation, used as a visual reference only. It is intentionally not redistributed with the project.

## Winamp source-code UI research

The original [Winamp classic player repository](https://github.com/alexfreud/winamp) has been reviewed for conceptual ideas: main player, playlist, equalizer display, button event handling and spectrum visualizer. For a file-by-file analysis and the restrictions against copying the original code or bitmaps, see [WINAMP_REFERENCE.md](WINAMP_REFERENCE.md). The three Tandy tone channels need a lightweight voice monitor, **not** Winamp's PCM FFT spectrum code.

## Physical EX UI review and redraw fixes

The owner's real-hardware video `3578.mp4` showed transport labels spilling into adjacent narrow button borders. In the original source, 33-pixel buttons were spaced 37 pixels apart, but labels were placed at hard-coded x positions independent of each button's text width. Several labels ran into their neighbor's vertical bevel, visibly obscuring text.

The revised implementation uses **7 × 42-pixel** buttons, each spaced 44 pixels from the next starting at x=8, with text centered using `(button_width - (length*6-1))/2`. The longest label, `PAUSE`, occupies only 29 pixels, leaving at least 6 pixels of inset on either side. `VIS` replaces the ambiguous `EQ` button because the lower panel monitors real PSG voice activity, rather than offering an equalizer.

The video also confirmed that periodic status refreshes were clearing 100×34 and 179×35 display panes, redrawing a full 298-pixel progress line, and rebuilding the entire visualizer every few clock ticks. The revised dirty-region renderer now updates only:

- **Clock:** the 95×10-digit strip, and only when the displayed second changes.
- **Title/metadata:** the upper-right display only when a song changes (rather than every 5 ticks).
- **Play/pause/stop indicators:** the left 95×13 strip and the seven button faces only after a transport command.
- **Playlist:** the lower pane only when the track selection changes or the panel is toggled.
- **Voice meters:** a single 40×42 rectangle only when that specific note, velocity or activity state changes.
- **Activity line:** the previous and next 12×1 pixel markers only when the indicator moves.

No full-screen erase occurs in the normal playback timer loop. On the host build, `tests/ui_test.c` renders the actual four-bank 16-color framebuffer and asserts that button glyph pixels do not overflow, the song title appears, repeated unchanged status draws cause **zero video writes**, and normal clock/meter updates stay far below full-screen redraw costs. This test runs before publishing each GitHub release. The actual performance improvement on the Tandy EX remains to be measured on hardware.

## 2026-11-16 Tandy EX mouse-pointer compatibility update

The initial graphical release used `INT 33h AX=0001h` to ask the DOS mouse driver to draw a graphics cursor. Bank-switched Tandy video mode `09h` is not necessarily recognized by the driver; this can leave the pointer invisible even when `INT 33h AX=3` reports valid mouse movement and buttons. It also **unconditionally halved CX**, which was wrong for drivers exposing actual 320-pixel horizontal coordinates.

The new implementation keeps the mouse driver responsible only for **input** and draws an original 8×11 black/white arrow into the four-bank Tandy framebuffer. For each cursor movement, it saves the underlying pixels at cursor-mask positions, restores the previous position, and draws at the new location. Every UI dirty-region repaint first removes the cursor and reinstates it afterward, eliminating ghosted pixels and driver-drawn cursor corruption. With no mouse movement or UI changes, no VRAM writes occur.

Startup now checks whether the INT 33h vector points to a real routine, resets the driver, and calibrates 320-versus-640 horizontal units using the standard position/position-read functions. DOS `INT 33h AX=5` is used to capture short left-button clicks even if the button was released between polls, and `AX=3` retains a fallback edge detector. The player displays `MOUSE OK` or `NO MOUSE` near the title bar. `/NOMOUSE` provides a keyboard-only fallback. Serial-mouse detection remains the responsibility of an installed DOS mouse TSR, such as `CTMOUSE /S14 /M` on the known EX COM1/IRQ4 setup.

### Regression coverage

`tests/ui_test.c` now checks software cursor save/restore against the full simulated 32 KB video framebuffer, cursor movement over a button and then a dirty redraw, zero-write idle behavior, X coordinate scaling, held-click debouncing, and press-count handling for very short clicks. The new pointer code has no driver graphics callback, no DOS interrupt handler, and should remain responsive without repainting the entire screen. **The source is hardware-unverified until tested with the physical mouse on the EX.**
