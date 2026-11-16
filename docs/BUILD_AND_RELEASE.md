# Building, testing and releasing TandyAMP

**Repository:** [ARMoir/TandyAMP](https://github.com/ARMoir/TandyAMP), default branch `main`.
**Current development target:** Tandy 1000 EX, 7 MHz NEC V20, real-mode DOS, Tandy PSG port `0xC0`, Tandy graphics mode `09h`.

## Source tree

| Files | Role |
| --- | --- |
| `src/main.c` | DOS frontend, command-line parsing, current-directory playlist scan, GUI, mouse, PSG I/O |
| `src/midi.c` / `src/midi.h` | MIDI decode, tempo scheduling, synthesizer/voice pool, percussion and volume |
| `tests/make_test_mid.py` | Generates synthetic format-0/1, malformed, dense and channel-16 test inputs |
| `tests/midi_test.c` | MIDI parser and format/boundary tests |
| `tests/playback_test.c` | Event ordering and note/voice behavior |
| `tests/mixer_test.c` | Mix model and volume/attenuation tests |
| `tests/review_test.c` | Paused boost, failed-load silence, PIT2 fallback, adaptive collisions and malformed lengths; optional full-MIDI sweep |
| `tests/treble_test.c` | Upper-register priority continuity, C6/A6 trim, 165 ms sustain, volume-20 boost, hard MIDI silence and live toggle |
| `tests/ui_test.c` | Simulated Tandy VRAM drawing, ten-button two-row layout (SPK4 and MUTE together), software mouse, minimal repaint and directory playlist auto-discovery |
| `tests/speaker_test.c` | Optional fourth PIT2 voice allocation, live toggle and mute/stop regressions |
| `tools/make_demo.py` | Produces an original 16-second `DEMO.MID` |
| `.github/workflows/build-dos.yml` | Primary DOS build, tests, package, release and cleanup |
| `.github/workflows/blank.yml` | Older placeholder CI workflow (echo-only); **does not build TandyAMP** |

## Manual DOS cross-build

Use a working **Open Watcom 2.0** installation with DOS 16-bit support and its tools in your environment. From the repository root:

```sh
wcl -bt=dos -0 -ms -os -s -zq -fe=TANDYAMP.EXE src/main.c src/midi.c
python3 tools/make_demo.py
```

`TANDYAMP.EXE` is a real-mode MZ executable; it is **not** a Win32 EXE. The `-0` target uses 8086-compatible instructions, suitable for the NEC V20. Copy `TANDYAMP.EXE` and optionally `DEMO.MID` to the CF/floppy DOS filesystem.

## Local host regression tests

On a system with `python3` and a C89-capable GCC (these are **host tests**, not substitutes for playing on the EX):

```sh
python3 tests/make_test_mid.py
gcc -std=c89 -O2 -Wall -Wextra -pedantic -o tests/midi_test tests/midi_test.c src/midi.c
./tests/midi_test tests/test0.mid tests/test1.mid tests/bad.mid tests/dense.mid tests/large.mid tests/legacy16.mid tests/melody16.mid
gcc -std=c89 -O2 -Wall -Wextra -pedantic -o tests/ui_test tests/ui_test.c src/midi.c
./tests/ui_test
gcc -std=c89 -O2 -Wall -Wextra -pedantic -o tests/playback_test tests/playback_test.c src/midi.c
./tests/playback_test
gcc -std=c89 -O2 -Wall -Wextra -pedantic -o tests/mixer_test tests/mixer_test.c
./tests/mixer_test
gcc -std=c89 -O2 -Wall -Wextra -pedantic -o tests/treble_test tests/treble_test.c
./tests/treble_test
gcc -std=c89 -O2 -Wall -Wextra -pedantic -o tests/speaker_test tests/speaker_test.c
./tests/speaker_test
gcc -std=c89 -O2 -Wall -Wextra -pedantic -o tests/expressive_test tests/expressive_test.c
./tests/expressive_test
gcc -std=c89 -O2 -Wall -Wextra -pedantic -o tests/review_test tests/review_test.c
./tests/review_test
python3 tests/check_docs.py
```

The UI tests include **actual pixel/framebuffer comparisons** and exercise the current-directory scanner in a fixture folder; the MIDI tests verify event/voice scheduling on a host. None emulate the EX's serial port or sound circuit fully.

## GitHub Actions, release policy, and package contents

The **primary workflow** is [`build-dos.yml`](../.github/workflows/build-dos.yml), triggered by pushes to `main` affecting source/tests/tools/docs/README/workflow or by manual dispatch. It:

1. Checks out source and generates original test MIDI files.
2. Runs MIDI, UI/mouse/playlist, playback, mixer and documentation consistency checks.
3. Sets up Open Watcom 2.0 and compiles the DOS executable.
4. Generates original `DEMO.MID` and packages **only** `TANDYAMP.EXE`, `DEMO.MID`, `LICENSE` into a ZIP. A release check rejects Markdown in the ZIP.
5. Uploads the current Actions artifact.
6. On successful `main` build, publishes tag `tandyamp-build-N` as the **latest GitHub Release**, with both the ZIP and individual `TANDYAMP.EXE`/`DEMO.MID` assets.
7. **Only after publication is verified**, deletes previous `tandyamp-build-*` releases/tags and older `TandyAMP-DOS-*` Actions artifacts. Unrelated releases, commits and workflow logs are not touched.

Download the most recent packaged build at **[Releases/latest](https://github.com/ARMoir/TandyAMP/releases/latest)**. **Older successful builds are intentionally removed** on each new success; for reproducibility, previous source commits remain in the repository's history.

Documentation files are kept in the repository, **not copied into the DOS release ZIP**. This is intentional for faster/cleaner 16-bit DOS deployment and consistent with the owner's packaging preference.

## Real hardware testing checklist

1. Reboot into plain DOS if a separate resident SimCity sound TSR has taken control of the PSG.
2. With a compatible installed DOS mouse driver, use `CTMOUSE /S14 /M` only when appropriate for the actual serial port; use `/NOMOUSE` if necessary.
3. Put at least two `.MID` files in the current DOS directory. Launch `TANDYAMP` without arguments and verify an alphabetic list and automatic first-song playback.
4. Press `N` / `P` / `Space` / `D` / `K` / `M` and `+` / `-`. Verify the 8x11 cursor, button hit testing and no cursor trails.
5. Use `/TXT` as a fallback for testing the MIDI engine independently of the graphics.
6. Listen for lost/stuck notes and timing drift, particularly in dense sections. Compare with an earlier tested build only if needed; older release packages are removed automatically.

**Evidence:** earlier recordings confirmed actual MIDI sound and GUI on a real 7 MHz EX; latest mouse and playlist changes are tested in GitHub Actions but not yet individually verified on-device.

## Preservation and attribution

TandyAMP's own code is MIT licensed. The legacy Miles `TANDY.ADV` and original Winamp source/assets were used only for independent technical/design study, not redistributed. See [TANDY_ADV_ANALYSIS.md](TANDY_ADV_ANALYSIS.md) and [WINAMP_REFERENCE.md](WINAMP_REFERENCE.md).

## Fourth speaker tone rollout

The latest optional `/SPK4` output is covered by a mocked PIT2 backend in the host tests. Build and automated tests **do not reproduce real Tandy EX speaker balance**. The ordinary three-voice mode is default and should be compared with the same MIDI track after toggling SPK4 on via the K key or clicking its second-row button. If the extra voice is harsh or inaudible through a particular output, disable it without rebooting; no change to the existing Windows image, AUTOEXEC.BAT or PIT channel 0 hardware timing is made.

### SPK4 bass-only acceptance test

`tests/speaker_test.c` verifies the PIT2 input is restricted to MIDI **24-52 (C1-E3)**, that the **true low-frequency PIT2 dividers** (including pitch bending) are used instead of octave-folded PSG values, and that three other distinct tone parts are required. It tests exclusion of high notes, pause/resume, disabling the button, master mute and clean stop. `tests/ui_test.c` verifies the **58x17 SPK4** button is aligned in the second row, reacts to K and clicks, displays ON/OFF, and repaints only its own region when the playlist is visible.

### Two rows of buttons: regression coverage

Current host framebuffer tests validate both five-button rows, all ten 58x17 labels and mouse click hitboxes, SPK4's bass-only live toggle, the MUTE button's previous-volume restoration, zero-change redraw caching and the lower playlist's retained seven visible rows. Open Watcom DOS compilation follows the tests; playback on actual EX hardware remains necessary.

### Loudness and volume-range regressions

`tests/mixer_test.c` verifies the corrected 6,144-power mix ceiling (formerly 1,024), full-volume solo PSG output, safe four-channel power summing, gain above the normal level at `/VOL:20`, unchanged hard silence for MIDI-off notes, and master mute. `tests/ui_test.c` checks keyboard volume stepping and that the MUTE button restores a boosted volume. The DOS `/VOL:0..20` command line is documented in the README and independently checked against the current source. The volume change does not promise amplification beyond the SN76489 attenuation register's physical maximum; compare 15 and 20 on a known melody on the actual EX.

### Four-channel monitor and audio-review regression

Host tests verify that SPK4 being **enabled** but not programmed into PIT2 displays **READY**, while an actual nonzero `ta.speaker_divider` displays the yellow fourth bar and bass pitch. They check that the three PSG meters depend on final attenuation, changing only MIDI velocity without changing hardware output causes **zero redraw writes**, the speaker output is cleared on stop/pause, and the shortcut footer has high contrast. The enhanced monitor is polled roughly **6 times/s** only while visible and retains the low-redraw strategy. See the separate [audio and recording review](HARDWARE_AUDIO_REVIEW_3582.md) for observations from physical hardware.

### Three-way SPK4 acceptance checks

`tests/speaker_test.c` now checks the original BASS divider, adaptive octave placement, �2-semitone pitch-overlap avoidance, quiet/loud PSG conditions, pitch-bend continuity, and the note-stamp lock (no mid-note octave jumping). `tests/ui_test.c` cycles OFF  BASS  ADAPT  OFF through both keyboard dispatch and captured serial mouse clicks, checks the three distinct button paint states and verifies that the VIS note label reflects a raised octave. `/SPK4`, `/SPK4:ADAPT`, and `/NOSPK4` are documented without changing the DOS release ZIP contents.

### High-register improvement acceptance tests

`tests/treble_test.c` validates the smooth scoring transition from MIDI 96 (C7) to 97 (C#7), that notes below C6 are untouched, C6+ gets one 2 dB hardware step, a sustained MIDI 93 (A6) gets a second step after ~165 ms, **the reduction survives maximum software volume 20**, and hard MIDI silence/stop is preserved. H toggles are live and neither detune held notes nor reset the MIDI clock. `tests/ui_test.c` verifies `HI SOFT` / `HI RAW` coloring and small-region redraw budgets. GitHub Actions runs both host regressions before the Open Watcom DOS build. The hardware still requires an A/B listening test; softening a PSG square wave by attenuation does not remove its odd harmonics.

