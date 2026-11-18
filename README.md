# TandyAMP — Winamp-inspired MIDI player for Tandy 1000 DOS

**CORE phrase smoothing:** TandyAMP Studio now holds fragmented notes, connects very small lead gaps, and removes narrowly identified pitch blips, protecting real attacks and bass/drum groove. It runs automatically for CORE audio inputs, not for imported MIDI; see [Studio documentation](tools/tandyamp_studio/README.md#core-smoothing--hold-connect-or-remove-opt-in-via-core). The DOS player and Build56 defaults are unchanged.

**New KISS CORE mode:** `--arrangement core` produces a deliberately sparse Tandy arrangement: drums and bass establish the groove; one guitar riff connects it to one vocal melody. Additional harmony enters only where meaningful. This is opt-in; [Studio instructions](tools/tandyamp_studio/README.md#core-the-kiss-four-part-tandy-arrangement-new-opt-in). Build56 remains the default, and no DOS code changes are required.

**New optional musical arranger:** The laptop Studio now supports `--arrangement musical`, an experimental offline **foundation / identity / support** simplifier. See [Studio usage](tools/tandyamp_studio/README.md#new-experiment-musical--the-simplest-tandy-arrangement) and [implementation](tools/tandyamp_studio/musical_arranger.py). Build56 stays the default and MAX RAW stays separate.

**Musical design philosophy:** [The TandyAMP Studio arrangement design rules](tools/tandyamp_studio/DESIGN_RULES.md). **The goal is the simplest MIDI that still sounds like the song on the Tandy**, not the most complete note dump.

**Musical-quality references:** [SEVENT01 (rock/groove)](tools/tandyamp_studio/benchmarks/SEVENT01_MUSICAL_BENCHMARK.md), [Brandenburg (counterpoint)](tools/tandyamp_studio/benchmarks/BRANDENBURG_CLASSICAL_BENCHMARK.md), and [DEMO.MID (hardware-native)](tools/tandyamp_studio/benchmarks/DEMO_HARDWARE_BENCHMARK.md).
For rock, **drums and bass establish the groove, and guitar bridges it
to the vocals**; for classical music, independent melodic lines matter
more. The final Tandy MIDI should be simple without losing the core.
Studio's preferred Build56 Paranoid recipe remains the conversion default. The benchmark is documented guidance for future
optional Groove Clean work, not a new note-removal setting or DOS
player change.

The [post-build-29 review](docs/POST_BUILD_29_REVIEW.md) documents fixes for
pause/resume loudness, failed-load speaker silence, adaptive bass overlap,
PIT2-to-PSG fallback, oversized MIDI tracks and alphabetical playlist truncation.

**Current status (November 16, 2026):** A working-source, reproducible 16-bit DOS player for the Tandy 1000 EX / 7 MHz NEC V20 and its built-in three-tone-plus-noise PSG (port `0xC0`). Earlier builds were recorded **running with audible MIDI and graphics on a real Tandy EX**. The latest automatic directory playlist, mouse cursor, and volume/mixer changes have passed CI but **have not all been confirmed on the physical EX**.

This is an independently written **real-mode DOS** application. No Windows, VGA, Sound Blaster, MPU-401, third-party MIDI host, TSR sound driver, or proprietary Winamp/Miles code is needed for sound. Graphics use **Tandy mode 09h (320×200, 16 colors)**.

## Quick start: play the whole directory

1. Get the **[latest release](https://github.com/ARMoir/TandyAMP/releases/latest)**. Download the `TandyAMP-DOS-build-N.zip` asset (or the stand-alone `TANDYAMP.EXE`).
2. Copy `TANDYAMP.EXE` onto your DOS disk/CF card. It may be in the music directory or elsewhere.
3. From **plain DOS**, change into the directory containing your MIDI files and run the player:

```dos
C:
CD \MIDI
TANDYAMP
```

With **no filenames**, TandyAMP finds `*.MID` in the **current working directory** (not recursively), sorts names case-insensitively, builds a playlist of **up to 64 files**, and starts the first entry. Press `N` / `P` to navigate; use `/LOOP` to repeat the list. The current working directory is where you ran the command, **not necessarily the EXE's own folder**.

```dos
TANDYAMP /LOOP
TANDYAMP /TXT
TANDYAMP CANYON.MID
TANDYAMP INTRO.MID CANYON.MID ENDING.MID
C:\APPS\TANDYAMP.EXE /LOOP
```

Explicit filenames **override discovery**: only the names provided are added, in the order given. The scan matches `.MID` (case-insensitively), not `.MIDI`, and does not traverse subdirectories. It reports if more than 64 qualifying files were found. If no `.MID` files are found, it displays a message and exits before changing graphics mode.

The ZIP contains only **`TANDYAMP.EXE`, `DEMO.MID`, and `LICENSE`**; Markdown documentation and source are in GitHub, **not** in the DOS ZIP. `DEMO.MID` is an original generated sample tune.

## Command-line reference

| Option | Behavior |
| --- | --- |
| *(no filename)* | Discover and play the current directory's `*.MID` files alphabetically |
| `FILE.MID [NEXT.MID ...]` | Play only the explicitly specified songs in the given order |
| `/GUI`, `-G` | 320×200 16-color Tandy GUI (default) |
| `/TXT`, `-T`, `/TEXT` | Text-mode player; no mouse graphics |
| `/LOOP`, `-L` | Repeat the playlist when its last song finishes |
| `/VOL:0..20` | Master output: **0 = mute**, **15 = normal**, **16–20 = additional software gain** where PSG headroom exists |
| `/HISOFT` | Enable gentle high-register balancing (default) |
| `/NOHISOFT` | Preserve original RAW treble levels for comparison |
| `/DRUM16` | Force legacy MIDI channel 16 to percussion |
| `/NODRUM16` | Treat channel 16 as melody |
| `/AUTODRUM16` | Use conservative channel-16 drum detection (default) |
| `/NOMOUSE` | No DOS mouse initialization or on-screen mouse pointer |
| `/SPK4` | Fourth PC-speaker voice in faithful BASS mode (original octave) |
| `/SPK4:ADAPT` | Experimental adaptive bass-octave mode |
| `/NOSPK4` | Disable the extra speaker voice (default OFF) |
| `/HELP`, `-H`, `/?` | Print command-line help |

Options can be used with either an explicitly named song or the automatically discovered directory playlist. `/TXT` is useful for debugging or displays without Tandy graphics.

## Keyboard and GUI buttons

| Key | Action | On-screen button |
| --- | --- | --- |
| `Space` | Pause/resume | PAUSE / PLAY |
| `P` | Previous song | PREV |
| `N` | Next song | NEXT |
| `S` | Stop | STOP |
| `R` | Restart current song | PLAY when stopped |
| `E` | Toggle playlist / PSG voice monitor | VIS |
| `L` | Toggle playlist looping | LOOP |
| `D` | Cycle legacy channel-16 drums: AUTO → ON → OFF; restarts the current song | DRUM |
| `K` | Cycle OFF → BASS → ADAPT → OFF without restarting playback | SPK4 (second row) |
| `M` | Mute or restore the previously audible master volume | MUTE (second row) |
| `H` | Toggle high notes between **SOFT** and **RAW** without restarting | Keyboard only |
| `+` / `-` | Increase / decrease master volume without restarting | Keyboard only |
| `Q` / `Esc` | Silence PSG and quit to DOS | Keyboard only |

The ten controls now form **two evenly spaced rows of five 58×17-pixel buttons**. The first row is PREV, PLAY, PAUSE, STOP, NEXT; the second is VIS, LOOP, DRUM, SPK4, MUTE. SPK4 displays OFF / BASS / ADPT (short for Adaptive), and MUTE displays ON/OFF. Each button skips repainting when its pressed state hasn't changed. The lower pane shows up to seven visible playlist rows or a **four-column output monitor** (three PSG tones plus optional SPK4 bass); it is **not an audio equalizer**. PSG bars follow the final programmed attenuation rather than raw MIDI velocity. SPK4 explicitly shows **OFF**, **READY**, **PAUSE**, or its currently programmed bass note (e.g., **C2**), so enabled and actually sounding are distinguishable. The small moving line is an **activity marker**, not a draggable seek bar. There is currently **no shuffle, file chooser, direct playlist-row selection, or seek command**. The source preserves the original Winamp-like appearance without copying its assets.

## Serial mouse on the EX

An installed **DOS INT 33h mouse driver** is required for mouse control. The application does **not** directly read the serial port. On the known EX setup, CuteMouse has worked in DOS with an invocation like:

```dos
CTMOUSE /S14 /M
TANDYAMP
```

Only use that CuteMouse command if it matches your actual serial port/driver setup. The GUI displays **MOUSE OK** if an INT 33h driver is detected, or **NO MOUSE** otherwise. TandyAMP draws its own 8×11 software arrow in Tandy mode 09h, avoids trails via save/restore of covered pixels, auto-checks 320-versus-640 X coordinate reporting, and accepts left-clicks on all ten buttons in two equal rows. A driver may be present without its serial mouse actually functioning; **MOUSE OK only confirms that the interface was detected**, not verified movement. The current code's mouse behavior is CI-tested but still requires final physical EX testing. To bypass it use `/NOMOUSE`.

## MIDI features and technical limits

| Area | Implemented / limit |
| --- | --- |
| File types | Standard MIDI File **type 0 or 1**; PPQN timing; MIDI running status and tempo events |
| Size | At most **45,056 bytes (44 KiB)** per file |
| Tracks | At most **24** tracks per MIDI file |
| Playlist | **64** filenames max, 63 characters per stored name; automatic scan is current-directory only |
| Music | Three simultaneous SN76489-compatible tone outputs; fourth PSG noise channel for drums; **optional fourth pitched PC-speaker voice** (PIT2) with `/SPK4` or the SPK4 button |
| Arrangement | Tracks up to **32 active MIDI notes** in software; tone choices prioritize melody/bass, avoid duplicate hardware pitches, and can restore held notes after a voice becomes free; increased voice-continuity weighting reduces unnecessary switching |
| MIDI controls | Note-on/off, velocity, volume CC7, expression CC11, sustain CC64, pitch bend, stop/all-notes-off |
| Percussion | General MIDI channel 10 uses the noise channel; optional auto/forced legacy channel-16 drums |
| Pitches | Integer divider table, pitch bending, octave folding for bass below the PSG's frequency floor |
| Loudness | Master volume `0..20` (15 normal, 16–20 extra PSG gain); integer 6,144-power limiter; optional SOFT/RAW high-register balancing with a small header indicator |
| Timing | Foreground scheduling in ≤32/256 of a BIOS tick (~6.9 ms) using PIT channel 0; the normal BIOS IRQ rate is retained |
| GUI | Tandy video mode `09h`, 320×200 × 16 colors; original 5×7 font; dirty-rectangle updates; optional INT 33h mouse |
| Missing | SMPTE time division, more than three simultaneous tone voices, complete GM instruments, seeking, shuffle, file browser and a true EQ |

On startup, the program uses PIT channel 0 **mode 2 with the standard 65536 divisor** for monotonic subticks and restores normal **mode 3** on normal program exit. It does not install an IRQ handler or change the 18.2 Hz BIOS tick frequency. GUI work can still delay events on a 7 MHz V20. Long MIDI files, unsupported formats, and corrupted tracks are reported as errors rather than silently treated as supported. Only the first song's load is checked before switching video mode; subsequent failing tracks can stop the sequence.

**Loudness correction:** Previous builds limited every mix against a modeled 1,024-power ceiling, even though **one full PSG channel alone** is modeled as 4,096. This unnecessarily reduced the loudness of solo melodies as well as dense arrangements. The ceiling is now **6,144**, so a solo full-velocity tone can reach native PSG register attenuation 0, while louder multi-part mixes still get automatic gain limiting. **Software volume 16–20** offsets up to five steps of MIDI/PSG attenuation (up to ~10 dB *where headroom exists*) but cannot exceed the actual hardware maximum, and the limiter prevents excessive modeled multi-channel output. True MIDI silence (PSG attenuation 15) remains silent even at /VOL:20. Note-on velocity and instrument-relative levels still matter. Use `/VOL:15` as the normal baseline, `/VOL:18` for stronger output, or `/VOL:20` for maximum available gain; reduce it if the internal speaker distorts. The file `01 - Trip Through the Grand Canyon.mid` was tested in the host playback engine but is **not** included in the release.

## Build, tests, and releases

The authoritative source is on **[GitHub](https://github.com/ARMoir/TandyAMP)**:

| Path | Purpose |
| --- | --- |
| `src/main.c` | DOS entry point, automatic playlist scan, command line, GUI, PSG I/O, software mouse |
| `src/midi.c` / `src/midi.h` | MIDI parser, scheduling, three-voice allocation, percussion, mixing and volume |
| `tools/make_demo.py` | Generate the original `DEMO.MID` |
| `tests/make_test_mid.py` | Generate reproducible MIDI test files |
| `tests/midi_test.c` | MIDI format, drum and parser regression tests |
| `tests/playback_test.c` / `tests/mixer_test.c` | Note/event ordering, voice allocation and mix-level checks |
| `tests/expressive_test.c` | Program-change envelopes, controller 1 vibrato, envelope timing and note-off regressions |
| `tests/speaker_test.c` | Fourth PIT2 voice selection, live toggle, note-off, pause/stop and master-mute tests |
| `tests/ui_test.c` | Pixel-font bounds, button hit areas, software cursor, minimal redraws and directory playlist discovery |
| `tests/check_docs.py` | Checks documentation links, feature limits and release packaging against source |
| `.github/workflows/build-dos.yml` | Test, compile, package and publish DOS builds |
| `docs/BUILD_AND_RELEASE.md` | Manual build commands, CI/release retention and troubleshooting |

The GitHub workflow runs host tests, installs Open Watcom 2.0, builds a real-mode DOS EXE with `wcl -bt=dos -0 -ms -os -s -zq`, and makes a three-file ZIP. **Only after a successful build and published release** does it remove previous `tandyamp-build-*` releases/tags and older `TandyAMP-DOS-*` artifacts. Other releases, source commits, and Actions history remain intact. The ongoing download URL is **[Releases / latest](https://github.com/ARMoir/TandyAMP/releases/latest)**.

### Related documentation

- [Current player architecture](docs/PLAYER_ARCHITECTURE.md)
- [UI and mouse design / historical fixes](docs/UI_DESIGN.md)
- [Clean-room Winamp inspiration](docs/WINAMP_REFERENCE.md)
- [Historical Miles TANDY.ADV disassembly findings](docs/TANDY_ADV_ANALYSIS.md)
- [Rebuild, test and publish](docs/BUILD_AND_RELEASE.md)
- [MIDI/PSG research audit and prioritized opportunities](docs/MIDI_PSG_RESEARCH.md)

## Troubleshooting and status

- **No files found:** `CD` to the directory containing `*.MID`. `TANDYAMP` without filenames does not scan where the executable lives unless it is the current directory.
- **Cannot open MIDI / unsupported type:** Try a smaller format-0/1 file within 44 KiB and 24 tracks. Unsupported songs are not converted automatically.
- **NO MOUSE:** Load/check your compatible DOS serial mouse driver before launch; `/NOMOUSE` keeps keyboard operation available. Hardware testing remains necessary.
- **No sound:** Ensure you're on the original Tandy PSG hardware and another player or SimCity sound TSR is not controlling it. Reboot to unload a resident TSR.
- **Timing varies / sounds crowded:** The 7 MHz V20 is hardware-limited, and three-tone polyphony is not General MIDI. Try a simpler arrangement or lower output with `/VOL:12`.

**Evidence boundary:** Earlier EX recordings demonstrate that the player draws and produces audible sound. GitHub CI checks parsing, rendering and timing models, **not** exact sound quality, serial port behavior or loudness on the physical EX. The latest build should be evaluated on that hardware.

## Rights

TandyAMP code and its generated demo are MIT licensed; see [LICENSE](LICENSE). It ships no proprietary SimCity/Miles audio or code, no Winamp assets, and no user-owned Canyon MIDI file.

## New native expressive PSG features (build after #33)

No preconversion is required: ordinary `.MID` files play directly on the EX. When a file sends a MIDI **Program Change**, piano/keyboard and guitar/plucked families receive a gentle stepped decay, bass/wind families a slower stepped decay, and sustained families keep their note level. Files that do not specify a program retain the older sustained tone behavior. MIDI **CC1 modulation-wheel** messages now apply a small integer pitch vibrato to already-playing notes. Note-offs remain immediate to avoid stuck notes. These effects cost at most a small amount of integer work every ~27 ms, plus occasional port writes. Some instrument/program mappings are necessarily approximate on three square-wave channels.

The three-voice selector now more strongly favors keeping the same audible notes when musical importance is similar. Final PSG I/O is cached: unchanged registers are not resent; new drum hits still retrigger the noise latch. These changes are not a wavetable/sound-font renderer, cannot create more than three simultaneous tone voices, and remain **hardware-audio-unverified** until listened to on the real EX.

## Optional fourth pitched voice — SPK4

**Default OFF.** The **SPK4** button is now grouped with the other audio controls in the second row, alongside DRUM and MUTE, and is clickable using the serial mouse. Press **K** or click SPK4 to cycle **OFF → BASS → ADAPT → OFF**, without restarting the song. `/SPK4` launches in faithful BASS mode; `/SPK4:ADAPT` launches with adaptive bass octaves; `/NOSPK4` disables it. All options also work with automatically discovered `*.MID` playlists.

SPK4 is **strictly bass-only**: it accepts MIDI notes **24–52 (C1–E3)**, never melody or high notes. When the song contains an eligible low bass **plus three other distinct PSG pitches**, the bass is reserved for **PIT channel 2** while the other three notes play through the Tandy PSG. This potentially gives four simultaneous pitched notes **plus PSG noise percussion**. If fewer than three other distinct pitches exist, or no low bass is eligible, the PC speaker stays silent and normal three-tone playback continues. The selected bass uses a native 1.193182 MHz PIT2 divider, keeping its **real low octave** rather than playing the PSG's octave-folded approximation, including ±2-semitone pitch bend. It stops immediately when released, paused, muted, switched off or when the player exits. The MIDI timing PIT channel 0 remains at its normal frequency. This is an implementation inspired by the independent fourth-track mechanism documented in [TNDY Tracker](https://github.com/JKnipperts/TNDY-Tracker); no original tracker code was copied.

**Important hardware difference:** PIT2 has **no independent volume register or instrument timbre**. An extra tone is therefore gated on only when its computed attenuation is sufficiently strong, but when on it can sound harsher or louder than PSG notes. On the Tandy 1000 EX the PIT2 source can mix with the PSG; output through particular external audio connections can depend on port 61h routing. TandyAMP intentionally changes **only speaker gate bits 0–1** of port 61h and leaves other audio-route bits intact; it does not override the motherboard's routing to force an external output. The physical EX sound balance must still be checked. Disable with K if the extra note is distracting.

**Current SPK4 interface:** The button remains in row two (x=190–247, y=91–107), with three short, readable labels: **SPK4 OFF**, **SPK4 BASS**, **SPK4 ADPT**. The switch updates its cached display even when transitioning between BASS and ADPT (both active), repainting only its own 58×17 region. Only source MIDI bass notes 24–52 are considered for PIT2. The tone choice and interface changes are covered by host tests; confirm the physical sound level on the EX.

### Two equal rows and the MUTE button

All ten controls are **58×17 pixels** with five buttons in each row: **PREV / PLAY / PAUSE / STOP / NEXT** at y=72–88, and **VIS / LOOP / DRUM / SPK4 / MUTE** at y=91–107. This replaces the crowded single-row and separate title-bar SPK4 layouts. The lower panel starts at y=112 and **retains seven playlist entries**, using slightly tighter row spacing. Keyboard shortcuts and existing functionality remain intact.

**MUTE** is functional, not a placeholder. Press **M** or click the far-right button in row two to silence the output; do it again to restore the previous audible master volume. The existing `+`/`-` keys now span **0–20**, and `/VOL:0..20` is accepted. MUTE restores boosted volume settings as well. Both SPK4 and MUTE have their own low-cost dirty redraw paths. The layout has automated framebuffer and mouse tests, but should be checked on the physical EX display for readability.

### Hardware volume limit and SPK4

The SN76489's 4-bit attenuation register has a maximum level at **attenuation 0**; there is no extra physical volume register value beyond that. TandyAMP's volume settings 16–20 **undo software attenuation**, not add hardware amplification. Very loud or dense passages may reach the hardware ceiling and therefore change little. The separate PC-speaker SPK4 tone has **no programmable gain**, so this change boosts the three PSG voices and noise percussion, not the analog amplitude of PIT2.

## Real-output visualizer and physical EX recording review

The **VIS** view now displays four columns: **CH1, CH2, CH3, SPK4**. The three PSG bars use the engine's actual 0–15 hardware attenuation after velocity, master-volume boost, and automatic mix limiting (not just MIDI velocity). Beneath the bars, note labels such as `C4` / `G#5` identify exactly which pitches the allocator currently holds. The fourth PIT2 column is **not** a fictitious fourth PSG meter: it lights in yellow only while the engine has programmed an actual bass divider into PIT channel 2; otherwise it says **OFF**, **READY**, or **PAUSE**. The SPK4 button still indicates the user's enabled preference, separately from actual activity.

The monitor now checks for changes approximately **six times per second** while open, but only repaints columns whose note, hardware level, or activity changed. It doesn't perform FFT or add sound-processing work to the V20. The lower shortcut legend is now **white text on black**, addressing the poor contrast seen in the owner's EX recording.

An analysis of the attached 30-second physical EX recording `3582.mp4` found the recorded RMS rose from roughly **−54 dBFS** (0–3 s) to **−36 dBFS** (18–24 s). The highest recorded sample was around **−18 dBFS**, with **no observed digital clipping**. A stable prominent tone around **1.75 kHz** persisted for about **10 seconds**, approximately 14–24 s. That might be an intentional MIDI sustain or a note-off issue; a phone recording cannot establish which. The new note labels should make future comparisons against the original MIDI easier. [See the detailed recording review](docs/HARDWARE_AUDIO_REVIEW_3582.md). These are *recording* levels affected by the microphone, distance and automatic gain, not calibrated Tandy speaker SPL measurements.

### Experimental SPK4 Adaptive Bass

**Three states:** SPK4 OFF (no extra tone); **SPK4 BASS** (original true-octave bass); **SPK4 ADPT** (experimental adaptive bass). Use the button or **K** to cycle, or launch `TANDYAMP /SPK4:ADAPT CANYON.MID`. The existing `/SPK4` remains the original faithful bass mode and the default is still OFF.

ADAPT considers only low MIDI **source** notes **24–52** and still requires three other distinct PSG notes. It may **raise the selected bass one octave**, never arbitrarily detune it or use higher melody notes as its source. Very deep bass (MIDI 24–35) is raised when no nearby PSG note would collide; middle-low notes (36–43) are raised only if at least two other PSG voices are strong (hardware attenuation 0–6) and there is no note within ±2 semitones of the raised pitch. Source bass 44–52 stays at its original octave. The decision uses **small integer comparisons**, occurs **once per MIDI note**, and is locked for that note's lifetime (even if the PSG gets louder). Pitch bend is still applied normally. The four-column VIS monitor displays the **actual pitched octave** when SPK4 sounds, appending a `^` indicator when raised (e.g., C2 becomes `C3^`).

This is intended to improve perceived bass clarity on the small internal speaker, not to increase PC-speaker voltage or loudness. It remains **unverified on the real EX** and should be compared at the same master volume against faithful BASS mode.

## High-register balance: new SOFT / RAW comparison

TandyAMP now starts in **HI SOFT** mode. Press **H** while music plays to toggle **HI SOFT ↔ HI RAW** instantly, or use `/HISOFT` (default) or `/NOHISOFT` on the command line. The current mode is shown near **NOW PLAYING**. This uses a tiny independent status redraw, **not** another crowded control button; the established two rows of five stay unchanged.

**SOFT** reduces the hardware amplitude of high melody notes *slightly*: notes starting at MIDI **84 (C6)** are reduced by one PSG attenuation step (~2 dB). Very high notes starting at MIDI **90 (F#6)** are reduced by a second step (~4 dB total) after approximately **165 ms** of continuous sustain. In particular, that targets the long A6-like ~1.75 kHz tone identified in the previous physical EX recording. The note's pitch, MIDI note-off and sustain-pedal behavior are **unchanged**. High melody priority also no longer collapses suddenly at MIDI 97 (C#7): it now tapers progressively instead of losing a 5,000-point bonus.

The treble reduction is applied **after master boost**, so it still works at volume **20**, but **before final PSG output and in the same calculation used by the limiter**, so actual hardware attenuation, volume-budget accounting and the visualizer remain consistent. This is **not** frequency-domain filtering: the Tandy PSG produces square waves, and no software low-pass, EQ, octave substitution or PCM processing was added. SOFT simply reduces how dominant piercing upper notes sound. Integer operations and an existing envelope timer are reused. The default can be switched off instantly for a true A/B comparison.

Recommended hardware test: play the same Canyon section with `/VOL:15` and alternate **H** between SOFT and RAW; then repeat at volume 18 or 20. Pay particular attention to the ~14–24-second high sustained tone. The new setting is tested by host regressions but has **not** yet been acoustically verified on the physical 7 MHz EX.



## TandyAMP Studio: laptop-side MP3/MIDI converter

The experimental [TandyAMP Studio](tools/tandyamp_studio/README.md) in `tools/tandyamp_studio/` converts existing MIDI, YouTube video URLs and optionally MP3/WAV audio into DOS-safe, three-PSG-voice plus optional SPK4 bass arrangements. It offers a complete no-GUI command line with yt-dlp/FFmpeg MP3 extraction, a Windows GUI, optional Demucs/Basic Pitch transcription, 8.3 filenames, automatic file splitting and a DOS `PLAY.BAT`. The Python tools are not bundled in the three-file DOS ZIP.
