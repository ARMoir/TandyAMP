# TandyAMP Studio (laptop-side tools)

Windows-friendly **offline arranger** for turning an existing MIDI file, or an MP3/WAV/FLAC/OGG using optional AI transcription, into small type-0 `.MID` files for the 7 MHz Tandy 1000 EX. All expensive analysis runs on the modern laptop, **not on the V20**. It is an early, independently written companion tool, not part of `TANDYAMP.EXE`.

## Quick start on Windows

1. Install **64-bit Python 3.11**, with the `py` launcher, from python.org (Tkinter is included in the normal Windows installer).
2. Open Command Prompt in `tools\tandyamp_studio` and run `py -3.11 -m pip install -r requirements.txt`.
3. Double-click `launch_studio.bat`. Select or drag in an **existing MIDI** for the most reliable results. Choose output folder, preset and SPK4 setting, then click **Convert for TandyAMP**.
4. Copy the generated `????????.MID` files and `PLAY.BAT` to the same directory as `TANDYAMP.EXE` on your DOS CF card, `CD` to that directory and type `PLAY`.

**Audio input (experimental):** Install heavier dependencies with `py -3.11 -m pip install -r requirements-audio.txt`. Basic Pitch transcribes pitches; it may require an ONNX/TensorFlow backend and a working audio decoder/FFmpeg depending on your environment. Optional **Separate stems** invokes Demucs (large model download, heavy RAM/CPU/GPU usage) and independently transcribes bass, vocals and other, plus heuristic drum onsets. Without stems, pitched audio is directly transcribed; drum reconstruction is not available. These operations have not been end-to-end verified on every Windows/Python/ML environment. Run first with an existing `.MID`.

## Command line examples

```cmd
py -3.11 studio.py "C:\Music\song.mid" --spk4 adapt --preset balanced --preview
py -3.11 studio.py "C:\Music\song.mp3" --spk4 bass --stems --preset quality
py -3.11 studio.py "C:\Music\song.wav" --spk4 off --preset performance
```

Output goes under `TANDY_OUT\<input>_TANDY` by default or under `-o YOUR_OUTPUT\<input>_TANDY`. Output MIDI names are DOS 8.3-safe (six-letter stem + `01.MID`, `02.MID`, etc.). The DOS `PLAY.BAT` uses `/NOSPK4`, `/SPK4`, or `/SPK4:ADAPT` as selected. **BASS and ADAPT create the same note arrangement; the TandyAMP runtime decides which octave SPK4 plays**, so use the generated `PLAY.BAT` or set the button to the matching mode. The `--preview` WAV is a rough square-wave sketch **not** a hardware-accurate Tandy PSG emulator.

## Optimization rules

- Selects up to **three distinct audible PSG pitches** at a time, with melody priority and note-continuity bias.
- If enabled and useful, reserves a **bass note from MIDI 24–52** for PIT2 **only when three other distinct pitches coexist**. Otherwise bass competes normally for the three PSG channels. Real SPK4 still has no independent volume control; TandyAMP may gate a reserved note off.
- Folds very low/high notes into more useful octaves; preserves strong bass velocity to satisfy TandyAMP's speaker gate. A `quality` preset is more permissive in the upper register; `balanced` reduces piercing highs; `performance` trims very high notes and short events.
- Converts percussion to TandyAMP-supported **kick 36, snare 38, hat 42**, reducing simultaneous hits to fit its **single noise oscillator**. Stem-derived drum identification is only a heuristic.
- Produces single-track **type-0 MIDI**, fixed 120 BPM encoding with original performance timing in seconds, and a compact event stream for the DOS parser. Files are capped at **42,000 bytes** (safety below TandyAMP's 45,056-byte limit), and split at at most 180 seconds or earlier if the file is too large. Handles notes spanning a split by continuing them in the next segment. Rejects an output folder containing the same filenames rather than silently overwriting. Limits the output set to **64** items to match the DOS automatic playlist.
- Does not embed proprietary source music, ML models or copyrighted MP3 files in the repository/releases.

## Testing and limitations

Run lightweight tests with `py -3.11 -m unittest discover -s tests -v`. They check four-voice eligibility, file size splitting, 8.3 names, valid SMF output, and sustained notes crossing boundaries; no MP3 inference required. These tests also run in GitHub CI.

Audio-to-MIDI reconstruction of full commercial mixes is **not reliably lossless**: chords, sung melody, overlapping harmonics, bass pitch and drums can be misdetected, even with stem separation. Program changes and expressive MIDI controllers are simplified, and original MIDI timing is re-encoded at 120 BPM. The TandyAMP PSG is a three-tone + noise device with an optional **fourth PC-speaker bass**, not a GM synthesizer. SPK4 ADAPT is a **runtime playback option** on the EX, not something this MIDI file can encode. Physical EX listening is still required to judge the conversion.

## Files

`studio.py` (CLI/Tkinter GUI), `arranger.py` (MIDI decode/optimization/export), `transcribe.py` (optional Basic Pitch/Demucs audio), `preview.py` (approximate square-wave WAV), `tests/` (regressions). This directory is **not included in the DOS release ZIP**; that ZIP still contains only the DOS EXE, demo MIDI and LICENSE.
