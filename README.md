# TandyAMP v0.1

**A Winamp-inspired MIDI player for the original Tandy 1000 EX** — real-mode DOS, 16-bit Open Watcom C, and the computer's onboard SN76489-compatible three-voice sound generator at port `0xC0`.

The first version is a **compiled and automatically tested prototype**. It has **not yet been tested on the physical 7 MHz NEC V20 Tandy EX**. The graphical design is inspired by the reference Winamp screenshot supplied by the project owner; the program uses its own pixel font, UI layout, and original code/assets.

## Download / install

1. Open the latest **[TandyAMP DOS build](https://github.com/ARMoir/TandyAMP/actions/workflows/build-dos.yml)**.
2. Download the `TandyAMP-DOS-v0.1` artifact ZIP.
3. Extract `TANDYAMP.EXE` and `DEMO.MID` to the **same directory** on your Tandy's CF card.
4. Reboot into plain DOS first if the SimCity `SCEXSND` TSR is installed: the music player needs exclusive access to the sound chip.
5. Run:

```dos
TANDYAMP DEMO.MID
```

The demo is an original 16-second MIDI tune generated from `tools/make_demo.py`. No copyrighted music is bundled.

## Command-line options

```dos
TANDYAMP DEMO.MID
TANDYAMP SONG1.MID SONG2.MID SONG3.MID
TANDYAMP /TXT DEMO.MID
TANDYAMP /LOOP DEMO.MID SONG2.MID
TANDYAMP /GUI DEMO.MID
TANDYAMP /HELP
```

| Option | What it does |
| --- | --- |
| `/GUI` or `-G` | Default Tandy 320×200, 16-color graphical player |
| `/TXT` or `-T` | Text-mode player, useful in DOSBox or on other text displays |
| `/LOOP` or `-L` | Loop the complete playlist |
| `/HELP`, `-H`, `/?` | Show usage and keyboard controls |

Supply up to **8 MIDI filenames** on the command line, separated by spaces. MIDI files with spaces in DOS-visible names must be quoted using the shell's normal rules. For the v0.1 prototype, files must be **28 KB or smaller** and use MIDI **type 0 or 1**, with **12 tracks or fewer** and PPQN timing (SMPTE time division is not yet supported).

### Keyboard controls

| Key | Action |
| --- | --- |
| `SPACE` | Pause/resume |
| `S` | Stop |
| `R` | Replay the current song |
| `N` | Next track |
| `P` | Previous track |
| `E` | Toggle playlist / three-channel visualizer |
| `L` | Toggle playlist loop |
| `Q` or `Esc` | Quit, silence chip, return to DOS |

The Winamp-style control buttons are **visual in v0.1**; use the keyboard. Serial-mouse support, clickable controls, a file picker, seeking, and a genuine equalizer are not yet implemented. The equalizer-inspired panel currently displays **three live channel levels**, not frequency-domain audio bands.

## Current implementation

- Real 8086-compatible, small-model DOS MZ executable, built with `wcl -bt=dos -0 -ms`.
- Direct Tandy mode `09h`, 320×200, 16 colors, four-bank video memory, and a compact 5×7 pixel font (no VGA requirement).
- Standard MIDI File type 0/1 parser; variable-length delta times, multi-track playback, running status, tempo changes.
- Three PSG tone channels, per-note velocity and MIDI CC7/CC11 volume, CC64 sustain, all-notes-off, note-off and voice stealing.
- Fixed-point integer pitch-bend approximation using our independently computed 128-note divider table, derived from the 3.579545 MHz PSG clock.
- Playback advances using the BIOS **18.2 Hz tick** in the foreground. This is an intentionally simple first version; some fast passages and tight rhythmic events may suffer up to ~55 ms of quantization and UI redraw delays. A more precise timer is a future milestone.
- No resident driver, no AUTOEXEC or Windows image changes.

## Development / reproducible build

Code and scripts are all in this repository:

| File | Purpose |
| --- | --- |
| `src/main.c` | Original Winamp-inspired Tandy GUI, keyboard/CLI, PSG port I/O |
| `src/midi.c` / `src/midi.h` | SMF decoder, tempo handling, MIDI channel state and three-voice synthesis |
| `tools/make_demo.py` | Generates the included original `DEMO.MID` |
| `tests/make_test_mid.py` | Creates test MIDI formats 0, 1 and malformed input |
| `tests/midi_test.c` | Verifies parser and PSG behavior using host output stubs |
| `.github/workflows/build-dos.yml` | Open Watcom 8086 DOS build and CI test artifacts |

GitHub Actions compiles the MIDI engine under GCC/C89, runs the synthetic MIDI tests, installs Open Watcom and produces a real-mode MZ DOS executable. **Passing CI does not establish actual audio, graphics or timing performance on a physical EX**, which remains the immediate next test.

## TANDY.ADV reverse-engineering reference

Our original engineering research on the Miles `TANDY.ADV` driver is preserved in [docs/TANDY_ADV_ANALYSIS.md](docs/TANDY_ADV_ANALYSIS.md). It covers the note period and MIDI attenuation lookup tables, three-tone voice allocation, pitch bends, register write ordering and risks of blindly setting audio multiplexer port `0x61`.

The proprietary Miles `TANDY.ADV` driver and original SimCity assets are **not** part of this project.

See [docs/PLAYER_ARCHITECTURE.md](docs/PLAYER_ARCHITECTURE.md) for the longer-term design.

## License

The newly written TandyAMP code and generated demo are MIT-licensed; see [LICENSE](LICENSE). No third-party MIDI player code has yet been copied into the project.
