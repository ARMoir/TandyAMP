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
