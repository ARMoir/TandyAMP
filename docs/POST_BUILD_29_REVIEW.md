# Review of changes after build 29

Reviewed the 17 commits from build-29 source `39c520a` through `eed9f0d`:
software mouse cursor and coordinate calibration; automatic playlists;
documentation checks; envelopes and modulation; PSG I/O caching; optional
PIT2 bass; two-row controls and mute; 0-20 volume; four-column monitoring;
adaptive bass octave; upper-register priority and SOFT/RAW treble.

## Corrections

- **Pause/resume:** apply changed volume, treble and speaker settings through
  allocation and the limiter before restoring any output. Boost while paused
  previously allowed stale attenuation on resume.
- **Failed load:** stop all outputs, including PIT2, before opening a new song.
  Missing/malformed files cannot leave SPK4 stuck; refresh GUI status as well.
- **Adaptive octave:** compare against the PSG's folded low notes, rather
  than only original MIDI note numbers, when avoiding pitch collisions.
- **PIT2 gate:** return reserved bass to PSG allocation if the new limiter
  setting gates the speaker off. One bounded recalculation preserves budget.
- **Large directories:** retain the alphabetically first 64 MIDI files even
  when directory enumeration encounters later names first.
- **Malformed MIDI:** validate track lengths before offset addition, so
  wrapping 32-bit lengths cannot masquerade as short tracks.
- **Windows host tests:** use native Windows directory enumeration to run
  the real UI/playlist tests under MSVC. DOS still uses its original APIs.

## Validation and limits

Existing MIDI, playback, mixer, expressive, speaker, treble, UI/mouse and
documentation suites are retained. `tests/review_test.c` adds interaction
regressions; the UI suite adds descending discovery of 70 files and insertion
into a full playlist.

The user-supplied 23,066-byte Canyon MIDI completed in all 12 combinations of
SPK4 OFF/BASS/ADAPT, volume 15/20, and treble RAW/SOFT. Every 6.9 ms simulation
slice stayed within the modeled PSG power budget, PIT2 remained bass-only,
and every run ended silent. This MIDI is not redistributed. Optional sweep:

```sh
./tests/review_test /path/to/CANYON.MID
```

Mouse tests cover framebuffer restoration, coordinate scaling, captured clicks
and controls. They do not emulate a physical serial mouse or its driver ISR.
Mouse behavior and audio quality still require a physical EX test. Existing
sound defaults and the 0-20 volume range are preserved.
