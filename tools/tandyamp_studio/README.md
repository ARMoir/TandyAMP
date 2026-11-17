# TandyAMP Studio (laptop-side tools)

Windows-friendly **offline arranger** for turning an existing MIDI file, YouTube video link, or an MP3/WAV/FLAC/OGG using optional AI transcription, into small type-0 `.MID` files for the 7 MHz Tandy 1000 EX. All expensive analysis runs on the modern laptop, **not on the V20**. It is an early, independently written companion tool, not part of `TANDYAMP.EXE`.

## Quick start on Windows

1. Install **64-bit Python 3.11**, with the `py` launcher, from python.org (Tkinter is included in the normal Windows installer).
2. Open Command Prompt in `tools\tandyamp_studio` and run `py -3.11 -m pip install -r requirements.txt`.
3. Double-click `launch_studio.bat`. Select or drag in an **existing MIDI** for the most reliable results. Choose output folder, preset and SPK4 setting, then click **Convert for TandyAMP**.
4. Copy the generated `????????.MID` files and `PLAY.BAT` to the same directory as `TANDYAMP.EXE` on your DOS CF card, `CD` to that directory and type `PLAY`.

**Cleaner experimental audio arrangement:** Demucs stems now get role-specific filtering *before* PSG allocation: low-confidence/very short bass, vocal and harmonic artifacts are reduced; bass and vocals are kept monophonic, while the guitar/other stem can keep two concurrent pitches. Pitched note velocity is only a heuristic strength signal, not a calibrated ML confidence. A drum-stem onset classifier compares low/mid/high band energy (rather than assigning every ambiguous onset to snare), optionally aligns near beat positions, and suppresses repeated chatter so the Tandy's single PSG noise channel is less overloaded. This can remove real fills, so compare by ear.

**SPK4 behavior:** BASS remains conservative and requires **three other distinct pitched notes** before assigning low bass to PIT2. ADAPT now allows the speaker bass alongside **two** other distinct pitched notes; one other pitch, high note overflow and unison duplicates are still excluded. The MIDI and the 16-bit DOS runtime were updated together. ADAPT may sound louder because PC speaker output is inherently on/off, so use BASS if it dominates the mix. The new preview approximates PSG pitch quantization, three PSG tone channels, drum decays/envelopes and optional PIT2 bass; it remains **non-cycle-accurate**, and actual Tandy/monitor sound will differ.

**Audio input (experimental):** Install heavier dependencies with `py -3.11 -m pip install -r requirements-audio.txt`. Basic Pitch transcribes pitches; it may require an ONNX/TensorFlow backend and a working audio decoder/FFmpeg depending on your environment. Optional **Separate stems** invokes Demucs (large model download, heavy RAM/CPU/GPU usage) and independently transcribes bass, vocals and other, plus heuristic drum onsets. Without stems, pitched audio is directly transcribed; drum reconstruction is not available. Rock drum analysis requires `--stems`. These operations have not been end-to-end verified on every Windows/Python/ML environment. Run first with an existing `.MID`.

## V6: Restore note fullness without exceeding Tandy hardware

The earlier TandyAMP Studio stages reduced vocals to one simultaneous note and guitar/other to two **before** scoring notes across the three PSG tones plus optional SPK4. This could produce technically clean but thin, disconnected renditions. The observed V5 Paranoid output contained roughly **54 seconds of bass-only sound**, **10 seconds with no pitched notes**, and about **65 seconds with only one pitched voice** in a ~160-second file. The latest work changes the strategy.

**Notes: Full** is now the default for **audio transcription** (GUI dropdown or `--note-preservation full`). It lowers the per-stem velocity and short-note gates, keeps credible overlapping guitar and vocal candidates from Basic Pitch, and only limits polyphony when the final, hardware-aware PSG/PIT2 voice allocator makes its selection. The latter **still emits at most three PSG tones and an eligible separate bass**, never fictional extra hardware channels. The bass stem remains monophonic. The alternative **Notes: Clean** (or `--note-preservation clean`) reproduces the earlier V5 per-stem filtering, giving a useful A/B control.

Audio conversions now report **input-after-transcription** versus **final-hardware-output** coverage: seconds with no pitched notes, one voice, two voices, three-plus voices, and bass-only sound. This reveals whether a sparse passage came from Basic Pitch failing to detect it, pre-arrangement cleanup, or the physical Tandy channel budget. A fuller arrangement is not guaranteed to be more accurate; some false pitches may return, so the two modes are intentionally selectable.

Use the latest Studio code, the original audio source and a fresh output folder:

```bat
py -3.11 studio.py --cli "https://www.youtube.com/watch?v=Uq42HUUJFzU" --stems --drum-style rock --preset balanced --note-preservation full --spk4 adapt --preview -o "C:\Users\alexr\Music\TANDY_FULL"
```

For an apples-to-apples comparison with the older cleanup (separate output directory):

```bat
py -3.11 studio.py --cli "https://www.youtube.com/watch?v=Uq42HUUJFzU" --stems --drum-style rock --preset balanced --note-preservation clean --spk4 adapt --preview -o "C:\Users\alexr\Music\TANDY_CLEAN"
```

The YouTube MP3 cache remains active. Both commands repeat the Demucs/Basic Pitch pipeline because **the original audio must be transcribed again**; importing an already-optimized `BLACKS01.MID` cannot recreate notes missing from its source conversion. Existing MIDI imports keep their normal behavior regardless of the Notes dropdown.

## V5 rock beat awareness and preview balance

The **rock** drum option now looks for a plausible alternating snare backbeat in the **detected** tempo grid, and suppresses only **weaker kick candidates** when stronger nearby kick evidence exists. If no reliable snare phase or meaningful dynamic contrast is found, it behaves conservatively rather than assuming a metronomic beat. It never synthesizes new kick, snare or hi-hat events, and does not touch the vocal/guitar transcription. This reduces weak repeated kick attacks without blindly deleting real accents.

A strong independent high-frequency hat onset can now replace a nearby **weak** kick in rock mode, when it has clear spectral evidence. Strong kicks and snares remain protected, and the one PSG noise channel still handles only one event at a time.

The **preview WAV only** has a quieter bass PSG voice, quieter PIT2-bass simulation and less dominant noise-channel drums, so the guitar line is easier to judge. This does **not** alter the real DOS TANDYAMP sound or the 16-bit build. The preview remains approximate, not a cycle-accurate SN76489 or PIT emulator.

To compare with earlier versions, use the same source and preset but a new output directory:

```bat
py -3.11 studio.py --cli "https://www.youtube.com/watch?v=Uq42HUUJFzU" --stems --drum-style rock --preset balanced --spk4 adapt --preview -o "C:\Users\alexr\Music\TANDY_V5"
```

The cached YouTube MP3 is reused automatically, though stem separation/transcription still runs each time. Judge improvements by listening on the actual Tandy as well as the preview.

## Rock rhythm improvements (experimental)

The Studio GUI now has a **Drums** selector: **auto** (existing style, default) or **rock**. The CLI equivalent is `--drum-style rock`, and it only affects drum transcription when you use `--stems`. Neither mode alters an existing user-supplied MIDI file or the pitched guitar melody.

The new isolated-drum-stem analysis runs **two onset detectors**: full-spectrum kicks/snares and a separate high-frequency (6–10.4 kHz) spectral-novelty detector. Independent, sufficiently strong high-band attacks may become MIDI hi-hat 42. Hats are **not added merely because they're missing**; there is no generated metronome/cymbal pattern. A recovered hat is suppressed if the PSG's one noise channel is already occupied by a nearby kick/snare. The rock option is more receptive to genuine high-band attacks, dampens repetitive kick retriggers, and allows a strong snare transient to win an overlapping noise-channel collision.

Bass notes are no longer flattened to a minimum MIDI velocity of 64: quieter notes retain their source dynamics (with a safety floor of 46). Quiet bass may deliberately fail the DOS PC-speaker gating threshold, because PIT2 has no volume register. The preview now runs a mild one-pole low-pass after mixing to soften sharp digital sample edges; this is an approximate laptop listening aid, **not a modification of the Tandy hardware or DOS sound driver**.

A useful rock recording test with the latest source is:

```bat
py -3.11 studio.py --cli "https://www.youtube.com/watch?v=Uq42HUUJFzU" --stems --drum-style rock --preset balanced --spk4 adapt --preview -o "C:\Users\alexr\Music\TANDY_V4"
```

The existing YouTube MP3 cache will be reused if present, but Demucs/Basic Pitch still need to process the audio. The output log prints **independent high-band attacks**, **recovered hats**, the final kick/snare/hat counts and the bass velocity range. If hi-hats remain scarce, the underlying separated drum stem might not contain enough usable evidence; the program will not invent them to reach a target ratio. Compare the new preview and MIDI with the V3 versions by ear before judging improvement.

## Audio quality: balanced drums and bass

With `--stems`, the converter now measures **spectral attack novelty** in the separated drum stem instead of classifying drums from the recording's absolute low-frequency energy. Per-song low/mid/high calibration and weak beat-position hints help distinguish kick (MIDI 36), snare (38), and hat (42). Ambiguous onsets are discarded rather than assigned a made-up class. Hit-to-hit velocity differences are preserved instead of saturating near maximum.

The arranger **no longer forces all bass notes to velocity 107**. It retains dynamics with a minimum level for useful PSG bass; sufficiently quiet notes may still be gated off by the one-bit PIT2 speaker. Tiny same-pitch bass fragmentation can be merged without destroying separate riff attacks. The offline arranger's SPK4 ADAPT mode now matches the DOS engine's two-other-distinct-pitch requirement, while BASS keeps three.

**This cleanup happens when the laptop transcribes new audio**, not when importing an already-generated MIDI file. Rerun from the source audio with the latest Studio code:

```bat
py -3.11 studio.py --cli "https://www.youtube.com/watch?v=VIDEO_ID" --stems --preset balanced --spk4 adapt --preview -o "C:\Music\TANDY_V3"
```

The conversion log prints the kick/snare/hat breakdown and bass velocity range. A heavily lopsided drum output emits a warning instead of silently pretending it is accurate. The produced MIDI remains format 0 and DOS-size-limited. These are heuristic improvements; audio quality still needs listening tests.

## Audio transcription troubleshooting

**Basic Pitch loads, then fails with `No module named 'pkg_resources'`:** This is not a missing Basic Pitch installation. An older `resampy` dependency still imports `pkg_resources`, which setuptools **82+** removed. In the same Python 3.11 environment used by the launcher, run:

```bat
py -3.11 -m pip install "setuptools>=70,<82"
py -3.11 -c "import pkg_resources; from basic_pitch.inference import predict; print('Basic Pitch OK')"
```

Future `requirements-audio.txt` installs include the temporary setuptools compatibility pin. The newer Studio error message identifies the actual missing dependency rather than incorrectly telling you to reinstall Basic Pitch. If you still see a failure, run the conversion from Command Prompt to keep the full Python traceback visible. CoreML and TFLite backend warnings on Windows are usually informational when the TensorFlow backend is available.

## YouTube links and fully command-line use

TandyAMP Studio now accepts a **single YouTube video URL** in both the GUI input box and the CLI. This uses [yt-dlp](https://github.com/yt-dlp/yt-dlp)'s embedded Python API and FFmpeg to extract an MP3 first, then feeds it to the optional Basic Pitch / Demucs transcription pipeline. The downloader does **not** use a YouTube API key, save login cookies, scrape playlists, or bypass DRM/paywalls. Download only audio you own or are permitted to download, and follow the site's terms.

### Reuse cached YouTube MP3 files

Studio now **checks for an existing MP3 before downloading** a YouTube video. Its stable cache is under your user's OS temporary directory:

`%TEMP%\tandyamp-youtube-cache\VIDEO_ID-192.mp3`

The cache key is the **YouTube video ID and selected MP3 bitrate**, so a `watch?v=...` URL and a `youtu.be/...` URL match correctly, while `--mp3-quality 256` has its own MP3. An intact cached MP3 is reused without calling YouTube, yt-dlp or FFmpeg again. Studio logs **Using cached YouTube MP3** so you know it skipped downloading. The GUI also avoids offering FFmpeg installation if the requested MP3 is already in the cache.

New downloads are checked for a plausible MP3 header/size and published to the cache using atomic file replacement. A truncated or obviously invalid cached file is ignored and replaced after a new download. This is a basic integrity check rather than a full audio decode. The cache is outside each run's temporary work directory, so it survives normal program exits; Windows Disk Cleanup or manual removal may still delete it. Earlier versions of Studio removed their temporary downloads, so only downloads **saved by this version onward** are guaranteed to be reusable.

`--keep-mp3` continues to copy a source MP3 into the MIDI output folder, and `--mp3-only` still saves a titled MP3 under `-o`. Both can reuse the cache. To force a fresh download, remove the matching `VIDEO_ID-BITRATE.mp3` and its `.json` metadata from the cache. This cache reduces repeated downloads, **not** the separate Demucs/Basic Pitch processing time.

### Guided FFmpeg setup inside Studio

The new **Check / Install FFmpeg** button detects whether both ffmpeg.exe and ffprobe.exe are on PATH. If either is missing, the GUI shows the Windows command (winget install --id Gyan.FFmpeg --exact), asks for **explicit permission** to install a third-party tool, and runs winget in the background only if approved. It never runs an installer at startup or without approval. The Convert button offers the same guided setup before a YouTube download when FFmpeg is missing.

Close and reopen Studio after installation so its process sees the updated PATH. In noninteractive CLI mode, no installation is performed; a missing dependency produces a copyable winget command and a manual download URL. Windows Package Manager may require additional Windows prompts.

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
| `--drum-style auto|rock` | Drum onset cleanup strategy when using `--stems`; default auto |
| `--note-preservation full|clean` | Audio transcription note retention; full is the new default, clean matches V5 |
| `--preview` | Export an approximate 30-second WAV |
| `--mp3-only` | Download MP3 to `-o` and exit; **no AI or MIDI conversion** |
| `--keep-mp3` | Keep `SOURCE.MP3` in the resulting DOS-MIDI folder |
| `--mp3-quality 128|192|256|320` | FFmpeg MP3 extraction bitrate; default 192 kbps |
| `--help` | List all arguments |

**Output:** YouTube MIDI conversions use a separate safe folder with the video's title and ID, containing compact `*.MID` segments and `PLAY.BAT`. The per-run download workspace is deleted, but the validated source MP3 remains in the reusable OS Temp cache; `--keep-mp3` also copies it into the MIDI output folder. `--mp3-only` writes a single `<title>_<video-id>.mp3` file under the selected output folder. Existing files are not silently overwritten. Single-video links are supported; playlists, channels, search pages, and arbitrary web URLs are deliberately not followed. If YouTube makes a video unavailable, the program reports the yt-dlp error.

## Command line examples

```cmd
py -3.11 studio.py "C:\Music\song.mid" --spk4 adapt --preset balanced --preview
py -3.11 studio.py "C:\Music\song.mp3" --spk4 bass --stems --preset quality
py -3.11 studio.py "C:\Music\song.wav" --spk4 off --preset performance
```

Output goes under `TANDY_OUT\<input>_TANDY` by default or under `-o YOUR_OUTPUT\<input>_TANDY`. Output MIDI names are DOS 8.3-safe (six-letter stem + `01.MID`, `02.MID`, etc.). The DOS `PLAY.BAT` uses `/NOSPK4`, `/SPK4`, or `/SPK4:ADAPT` as selected. **BASS and ADAPT arrange speaker bass differently**: ADAPT can reserve bass with two other distinct pitched notes, while BASS requires three, so use the generated `PLAY.BAT` or set the button to the matching mode. The `--preview` WAV is a bounded PSG/PIT2/noise approximation with note envelopes; **not** a hardware-accurate emulator.

## Optimization rules

- Selects up to **three distinct audible PSG pitches** at a time, with melody priority and note-continuity bias. ADAPT permits PIT2 bass when at least two other PSG pitches exist; BASS requires three.
- If enabled and useful, reserves a **bass note from MIDI 24–52** for PIT2 **when the selected SPK4 mode's distinct-pitch requirement is met**. Otherwise bass competes normally for the three PSG channels. Real SPK4 still has no independent volume control; TandyAMP may gate a reserved note off.
- Folds very low/high notes into more useful octaves; preserves strong bass velocity to satisfy TandyAMP's speaker gate. A `quality` preset is more permissive in the upper register; `balanced` reduces piercing highs; `performance` trims very high notes and short events.
- Converts percussion to TandyAMP-supported **kick 36, snare 38, hat 42**, reducing simultaneous hits to fit its **single noise oscillator**. Stem-derived drum identification is only a heuristic.
- Produces single-track **type-0 MIDI**, fixed 120 BPM encoding with original performance timing in seconds, and a compact event stream for the DOS parser. Files are capped at **42,000 bytes** (safety below TandyAMP's 45,056-byte limit), and split at at most 180 seconds or earlier if the file is too large. Handles notes spanning a split by continuing them in the next segment. Rejects an output folder containing the same filenames rather than silently overwriting. Limits the output set to **64** items to match the DOS automatic playlist.
- Does not embed proprietary source music, ML models or copyrighted MP3 files in the repository/releases.

## Testing and limitations

Run lightweight tests with `py -3.11 -m unittest discover -s tests -v`. They check four-voice eligibility, file size splitting, 8.3 names, valid SMF output, and sustained notes crossing boundaries; no MP3 inference required. These tests also run in GitHub CI.

Audio-to-MIDI reconstruction of full commercial mixes is **not reliably lossless**: chords, sung melody, overlapping harmonics, bass pitch and drums can be misdetected, even with stem separation. Program changes and expressive MIDI controllers are simplified, and original MIDI timing is re-encoded at 120 BPM. The TandyAMP PSG is a three-tone + noise device with an optional **fourth PC-speaker bass**, not a GM synthesizer. SPK4 ADAPT is a **runtime playback option** on the EX, not something this MIDI file can encode. Physical EX listening is still required to judge the conversion.

## Files

`studio.py` (CLI/Tkinter GUI), `youtube.py` (yt-dlp download), `convert_cli.bat` (no-GUI Windows wrapper), `arranger.py` (MIDI decode/optimization/export), `transcribe.py` (optional Basic Pitch/Demucs audio), `postprocess.py` (pitch/noise cleanup), `preview.py` (bounded PSG/noise/PIT2 WAV preview), `tests/` (regressions). This directory is **not included in the DOS release ZIP**; that ZIP still contains only the DOS EXE, demo MIDI and LICENSE.
