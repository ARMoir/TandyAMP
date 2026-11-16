# TandyAMP v0.1

**A Winamp-inspired MIDI player for the original Tandy 1000 EX** - real-mode DOS, 16-bit Open Watcom C, and the computer's onboard SN76489-compatible three-voice sound generator at port `0xC0`.

The project is a **compiled and automatically tested prototype**. It has **not yet been tested on the physical 7 MHz NEC V20 Tandy EX**. The graphical design is inspired by the reference Winamp screenshot supplied by the project owner; the program uses its own pixel font, UI layout, and original code/assets.

## Download / install

1. Open the **[latest TandyAMP release](https://github.com/ARMoir/TandyAMP/releases/latest)** (a successful GitHub Actions build is published automatically).
2. Download the `TandyAMP-DOS-build-N.zip` asset, or download `TANDYAMP.EXE` and `DEMO.MID` individually.
3. Extract `TANDYAMP.EXE` and `DEMO.MID` to the **same directory** on your Tandy's CF card.
4. Reboot into plain DOS first if the SimCity `SCEXSND` TSR is installed: the music player needs exclusive access to the sound chip.
5. Run:

```dos
TANDYAMP DEMO.MID
```

The demo is an original 16-second MIDI tune generated from `tools/make_demo.py`. No copyrighted music is bundled.

## Automatic current-directory playlist

In the DOS directory containing your music, type `TANDYAMP` to find any `.MID` files without listing them. Names are sorted alphabetically, matching DOS's case-insensitive filename conventions. The player supports **up to 64 tracks** in this automatic playlist (approximately 4 KB for filenames); it reports when additional files were skipped. A directory with no `.MID` files displays a clear message and exits without switching video modes. Each MIDI file must still satisfy the player's 44 KB / 24-track limits.

This searches the **current working directory**, not the directory where the EXE is stored if those differ. For example, `CD \\MIDI` before running `C:\\APPS\\TANDYAMP.EXE`. Explicit filenames override discovery. Keyboard Next/Previous and the graphical playlist work as before.

## Command-line options

```dos
TANDYAMP
TANDYAMP /LOOP
TANDYAMP /TXT
TANDYAMP DEMO.MID
TANDYAMP SONG1.MID SONG2.MID SONG3.MID
TANDYAMP /TXT DEMO.MID
TANDYAMP CANYON.MID
TANDYAMP /DRUM16 CANYON.MID
TANDYAMP /NODRUM16 CANYON.MID
TANDYAMP /LOOP DEMO.MID SONG2.MID
TANDYAMP /GUI DEMO.MID
TANDYAMP /NOMOUSE DEMO.MID
TANDYAMP /HELP
```

| Option | What it does |
| --- | --- |
| `/GUI` or `-G` | Default Tandy 320x200, 16-color graphical player |
| `/TXT` or `-T` | Text-mode player, useful in DOSBox or on other text displays |
| `/LOOP` or `-L` | Loop the complete playlist |
| `/NOMOUSE` | Run keyboard-only without initializing INT 33h or drawing a pointer |
| `/HELP`, `-H`, `/?` | Show usage and keyboard controls |
| `/DRUM16` | Force legacy channel 16 to percussion |
| `/NODRUM16` | Force channel 16 to melodic notes |
| `/AUTODRUM16` | Conservative automatic detection (default) |

**Run `TANDYAMP` without any filenames** to automatically build a playlist from the current directory's `*.MID` files, sorted alphabetically, then begin the first song. `TANDYAMP /LOOP` repeats that directory playlist, while `TANDYAMP /TXT` plays it in text mode. The scan does not recurse into subdirectories. When one or more filenames are supplied explicitly, **only those files** are played in the order supplied. Supply up to **64 MIDI filenames** on the command line, separated by spaces. MIDI files with spaces in DOS-visible names must be quoted using the shell's normal rules. For this build, files must be **44 KB or smaller** and use MIDI **type 0 or 1**, with **24 tracks or fewer** and PPQN timing (SMPTE time division is not yet supported).

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
| `D` | Cycle channel 16 drums: AUTO  ON  OFF; restart current song |
| `Q` or `Esc` | Quit, silence chip, return to DOS |

The compact interface now has **eight 36-pixel buttons**, including DRUM. Press **D** or click DRUM with a compatible DOS INT 33h mouse driver to cycle AUTO  ON  OFF. The selected and resolved state appear next to the song title. Changing modes restarts the song for consistent playback. Mouse clicks are implemented for all eight buttons. TandyAMP now **draws its own 8×11 software mouse pointer** in Tandy mode 09h instead of asking the mouse driver to draw one (which often fails in banked Tandy modes). The program uses DOS INT 33h for movement and buttons, automatically checks 320-vs-640 X coordinate ranges, captures brief button presses, and shows `MOUSE OK` or `NO MOUSE` in the title bar. On the EX, load CuteMouse for your serial mouse before running TandyAMP, for example `CTMOUSE /S14 /M` if that is the configuration that works in DOS. The optional `/NOMOUSE` switch disables mouse input and the pointer. Actual EX mouse behavior still needs verification in hardware. A file picker, seeking, and a genuine equalizer are not yet implemented. The visualizer displays three live channel levels, not frequency-domain audio bands.

## Current implementation

- Real 8086-compatible, small-model DOS MZ executable, built with `wcl -bt=dos -0 -ms`.
- Direct Tandy mode `09h`, 320x200, 16 colors, four-bank video memory, and a compact 5x7 pixel font (no VGA requirement).
- **Real-EX UI cleanup:** eight compact, centered and non-overlapping 36-pixel controls, including DRUM; the now-playing area also reports automatic or forced drum routing.
- **Dirty-region screen updates:** static background is drawn once; clock changes redraw only its digits, song/title and playlist update on track changes, playback indicators change on input, the activity marker erases only its old 12-pixel segment, and each voice meter redraws only when its note or level changes. Avoids periodic full-screen/panel redraws on the 7 MHz V20.
- Standard MIDI File type 0/1 parser; variable-length delta times, multi-track playback, running status, tempo changes.
- Three PSG tone channels with 32 active MIDI notes remembered; melody/bass-aware allocation means temporarily stolen notes can return after release.
- General MIDI channel 10 percussion uses independent SN76489 noise channel with short volume envelopes. A conservative scan auto-detects likely old channel-16 percussion (repeat kick/snare and hi-hat patterns); `D`, DRUM button or CLI override ambiguous files. Standard channel 10 is always percussion.
- Per-note velocity, MIDI CC7/CC11 volume, CC64 sustain, all-notes-off and pitch bend.
- Fixed-point integer pitch-bend approximation using our independently computed 128-note divider table, derived from the 3.579545 MHz PSG clock.
- Foreground playback reads the original BIOS tick and the latched PIT counter without installing an IRQ handler or altering BIOS/DOS time. Music is scheduled in at most ~6.9 ms slices instead of ~55 ms chunks. GUI drawing can still delay events on a 7 MHz V20; hardware timing needs another recording.
- Low bass pitches below the SN76489's ~109 Hz floor are octave-folded rather than all clamped to one note.
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

GitHub Actions compiles the MIDI engine under GCC/C89, runs the synthetic MIDI and host framebuffer regression tests (including zero-write idle and small redraw budgets), installs Open Watcom and produces a real-mode MZ DOS executable. After **every successful run on main**, it publishes a downloadable GitHub release tagged `tandyamp-build-N`. Only after validating the published release does it delete previous `tandyamp-build-*` releases/tags and older `TandyAMP-DOS-*` Actions artifacts. The current release and current run's artifact are retained; unrelated GitHub releases, run histories/logs, and source commits are not deleted. **Passing CI does not establish actual audio, graphics or timing performance on a physical EX**, which remains the immediate next test.

## TANDY.ADV reverse-engineering reference

Our original engineering research on the Miles `TANDY.ADV` driver is preserved in [docs/TANDY_ADV_ANALYSIS.md](docs/TANDY_ADV_ANALYSIS.md). It covers the note period and MIDI attenuation lookup tables, three-tone voice allocation, pitch bends, register write ordering and risks of blindly setting audio multiplexer port `0x61`.

The proprietary Miles `TANDY.ADV` driver and original SimCity assets are **not** part of this project.

See [docs/PLAYER_ARCHITECTURE.md](docs/PLAYER_ARCHITECTURE.md) for the longer-term design.

## Classic Winamp source as a design reference

The original Winamp source in [alexfreud/winamp](https://github.com/alexfreud/winamp) offers useful reference points for separate player/playlist drawing, keyboard and button dispatch, and compact visualization. See [docs/WINAMP_REFERENCE.md](docs/WINAMP_REFERENCE.md) for a source-file map, Tandy-specific UI plan, and important licensing boundaries. All TandyAMP code and graphics remain independently authored.

## License

The newly written TandyAMP code and generated demo are MIT-licensed; see [LICENSE](LICENSE). No third-party MIDI player code has yet been copied into the project.

# Playback timing and dense arrangements

The playback engine now merges MIDI tracks in timestamp order and chooses
the three tone voices once per event timestamp. This avoids transient notes
and repeated PSG writes while assembling a dense chord. Channel volume and
expression affect voice priority; muted notes remain tracked but cannot take
a hardware voice away from an audible part. Raising their volume can restore
them without another note-on. Selection weights are cached for the 8086.

The DOS timer uses PIT channel 0 mode 2 with divisor 65536 while the player
runs. This keeps the normal BIOS IRQ rate but supplies one countdown per
tick. The previous subtick reader assumed that behavior while the default
mode 3 counts down twice per tick, causing time to jump backward mid-tick.
Normal mode 3 is restored on exit. No new interrupt handler is installed.

Validation covers synthetic multi-track ordering, dense chord write counts,
volume/expression voice recovery, the existing MIDI suite and UI redraw tests.
The supplied 23,066-byte `01 - Trip Through the Grand Canyon.mid` has now been
run through the host playback engine for its complete duration. Its 60-second
hardware recording also matched the build-28 timing at approximately normal speed.
The new mixer still needs a listening check on the physical Tandy.
Use `TANDYAMP CANYON.MID` after giving your local copy a DOS-compatible name;
automatic channel-16 percussion detection and the D override remain available.

## Unique pitches and comfortable volume

Voice selection now compares actual PSG dividers after octave folding and
pitch bend. Duplicate notes from different instruments share one tone slot;
other held notes can use the remaining slots. Each original note remains
tracked independently, so ending one doubled part does not end the other.
Pitch bends that separate the pitches can use separate slots again.

Automatic loudness leveling is enabled by default and always active. An
integer lookup table estimates combined tone and percussion power from the
PSG's 2 dB volume steps. Loud mixes receive immediate common attenuation;
recovery is limited to one step about every 220 ms. Quiet passages are never
boosted. This reduces sudden level changes while retaining musical dynamics.
It estimates chip output, not measured room loudness; set the speaker volume
to suit your listening distance.

- Press **+ / -** to adjust master volume without restarting the song.
- The now-playing panel shows **VOL 00..15**; **00 is mute**.
- Use `TANDYAMP /VOL:12 CANYON.MID` for a lower starting level.
- Default master volume is 15, with automatic leveling still applied.
- Master volume affects both tones and percussion and persists across songs.

Full-file Canyon simulation found zero duplicate audible dividers at every
6.9 ms scheduler slice, with estimated combined output within the mix budget.
For the 15-20 second passage, mean simulated tone power fell about 7.5 dB
versus build 28. The modeled opening-to-that-passage difference fell from
about 11.7 dB to 6.1 dB. These are tone-power estimates, not microphone SPL
measurements. Original synthetic tests also cover folded unisons, independent
note-offs, bend separation/rejoining, release timing, percussion, master mute,
pause/resume and stop. The user-owned Canyon MIDI is not bundled or committed.

