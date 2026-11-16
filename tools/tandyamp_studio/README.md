# TandyAMP Studio (laptop-side tools)

Windows-friendly **offline arranger** for turning an existing MIDI file, YouTube video link, or an MP3/WAV/FLAC/OGG using optional AI transcription, into small type-0 `.MID` files for the 7 MHz Tandy 1000 EX. All expensive analysis runs on the modern laptop, **not on the V20**. It is an early, independently written companion tool, not part of `TANDYAMP.EXE`.

## Quick start on Windows

1. Install **64-bit Python 3.11**, with the `py` launcher, from python.org (Tkinter is included in the normal Windows installer).
2. Open Command Prompt in `tools\tandyamp_studio` and run `py -3.11 -m pip install -r requirements.txt`.
3. Double-click `launch_studio.bat`. Select or drag in an **existing MIDI** for the most reliable results. Choose output folder, preset and SPK4 setting, then click **Convert for TandyAMP**.
4. Copy the generated `????????.MID` files and `PLAY.BAT` to the same directory as `TANDYAMP.EXE` on your DOS CF card, `CD` to that directory and type `PLAY`.

**Audio input (experimental):** Install heavier dependencies with `py -3.11 -m pip install -r requirements-audio.txt`. Basic Pitch transcribes pitches; it may require an ONNX/TensorFlow backend and a working audio decoder/FFmpeg depending on your environment. Optional **Separate stems** invokes Demucs (large model download, heavy RAM/CPU/GPU usage) and independently transcribes bass, vocals and other, plus heuristic drum onsets. Without stems, pitched audio is directly transcribed; drum reconstruction is not available. These operations have not been end-to-end verified on every Windows/Python/ML environment. Run first with an existing `.MID`.

## YouTube links and fully command-line use

TandyAMP Studio now accepts a **single YouTube video URL** in both the GUI input box and the CLI. This uses [yt-dlp](https://github.com/yt-dlp/yt-dlp)'s embedded Python API and FFmpeg to extract an MP3 first, then feeds it to the optional Basic Pitch / Demucs transcription pipeline. The downloader does **not** use a YouTube API key, save login cookies, scrape playlists, or bypass DRM/paywalls. Download only audio you own or are permitted to download, and follow the site's terms.

### Install YouTube support (Windows)

From `tools\tandyamp_studio` in Command Prompt:

```bat
py -3.11 -m pip install -r requirements-youtube.txt
```

This installs `yt-dlp[default]` including the required `yt-dlp-ejs` JavaScript challenge scripts. You must also install **FFmpeg and ffprobe executables** on your `PATH` (not just the similarly named Python package), and install **Deno 2.3+** on your `PATH` for yt-dlp's recommended YouTube JavaScript runtime. Confirm in a new Command Prompt:

```bat
ffmpeg -version
ffprobe -version
deno --version
```

YouTube's extractor behavior changes over time; if downloads stop working, upgrade with `py -3.11 -m pip install -U "yt-dlp[default]"`. See [FFmpeg](https://ffmpeg.org/download.html), [Deno installation](https://docs.deno.com/runtime/getting_started/installation/), and the [yt-dlp EJS guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

**For MP3-to-MIDI**, also install `py -3.11 -m pip install -r requirements-audio.txt`. **For MP3-only downloads**, AI packages and Demucs are not needed.

### Noninteractive commands

Every command with a positional input runs entirely in the console, with **no GUI**. Use `--cli` or `--no-gui` to force noninteractive mode and fail with an explanation if no input is specified. URLs must be **quoted** in Windows Command Prompt because they may contain `&`:

```bat
REM Download YouTube MP3 only, without AI or MIDI dependencies:
py -3.11 studio.py --cli "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --mp3-only -o "C:\Music\Downloaded"

REM YouTube -> MP3 -> 3 PSG tones + SPK4 bass -> DOS MIDI:
py -3.11 studio.py --cli "https://youtu.be/dQw4w9WgXcQ" --spk4 bass --preset balanced

REM Better experimental transcription through AI-separated stems:
py -3.11 studio.py --cli "https://youtu.be/dQw4w9WgXcQ" --stems --spk4 adapt --preview --keep-mp3

REM Local MIDI still requires no YouTube or AI packages:
py -3.11 studio.py --cli "C:\Music\CANYON.MID" --preset quality --spk4 off

REM Optional wrapper shortcut; passes all options to the Python CLI:
convert_cli.bat "https://youtu.be/dQw4w9WgXcQ" --mp3-only
```

### CLI switches

| Argument | Behavior |
| --- | --- |
| `INPUT` | Single YouTube watch/short/live link, or local .MID/.MP3/.WAV/.FLAC/.OGG file |
| `-o, --output FOLDER` | Output parent directory; default `./TANDY_OUT` |
| `--cli` / `--no-gui` | Never launch the GUI; requires input |
| `--gui` | Force graphical interface; optional INPUT pre-fills entry |
| `--preset quality|balanced|performance` | Offline voice-optimizing strategy |
| `--spk4 off|bass|adapt` | Speaker-mode selection in generated DOS `PLAY.BAT` |
| `--stems` | Optional Demucs separation before transcription |
| `--preview` | Export an approximate 30-second WAV |
| `--mp3-only` | Download MP3 to `-o` and exit; **no AI or MIDI conversion** |
| `--keep-mp3` | Keep `SOURCE.MP3` in the resulting DOS-MIDI folder |
| `--mp3-quality 128|192|256|320` | FFmpeg MP3 extraction bitrate; default 192 kbps |
| `--help` | List all arguments |

**Output:** YouTube MIDI conversions use a separate safe folder with the video's title and ID, containing compact `*.MID` segments and `PLAY.BAT`. Temporary MP3s are deleted unless `--keep-mp3` is specified. `--mp3-only` writes a single `<title>_<video-id>.mp3` file under the selected output folder. Existing files are not silently overwritten. Single-video links are supported; playlists, channels, search pages, and arbitrary web URLs are deliberately not followed. If YouTube makes a video unavailable, the program reports the yt-dlp error.

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

`studio.py` (CLI/Tkinter GUI), `youtube.py` (yt-dlp download), `convert_cli.bat` (no-GUI Windows wrapper), `arranger.py` (MIDI decode/optimization/export), `transcribe.py` (optional Basic Pitch/Demucs audio), `preview.py` (approximate square-wave WAV), `tests/` (regressions). This directory is **not included in the DOS release ZIP**; that ZIP still contains only the DOS EXE, demo MIDI and LICENSE.
