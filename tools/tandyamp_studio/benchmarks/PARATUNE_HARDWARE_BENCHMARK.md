# Paranoid hardware baseline

The approved take is `DOS/PARATUNE.MID` from `Paranoid_Pitch_Comparison.zip`.
It plays the first 23.79 seconds of the arrangement. The November 18, 2026
recording beside the Tandy 1000 EX confirmed the result on the hardware.
The recording is a playback reference for the MIDI.

The take used Balanced, Smart voice selection and SPK4 off. The source
transcription used six-stem Demucs, Sensitive, Full, Rock drums and
Accompaniment off. The note and timing evidence is recorded in
[`PARATUNE_reference.json`](PARATUNE_reference.json).

## Replay the exact audition

The audition used Julio LeMa's 1997 sequencer MIDI for the guitar, bass and
drum shapes. Its beats were aligned to the recording. The vocal retained its
detected attacks, with pitch corrected against the guide. The intro keeps
the low pedal under the riff. Once the vocal enters, the guitar supports it
with the fifth above the backing root.

Run from `tools/tandyamp_studio` with the reference MIDI and the archived
transcription from the session:

```bat
py -3.11 benchmarks\paratune.py "Paranoid.mid" "paranoid-live-evidence.json" -o "PARATUNE.MID"
```

The script verifies both inputs and checks the output against the approved
MIDI. Its SHA-256 is
`b805d921db12b81f2575921fb49b29adb173997a52ac16e9c82bb50f42742b65`.
Copy the approved MIDI beside `TANDYAMP.EXE` and use `TANDYAMP /NOSPK4`
for a hardware comparison with the original audition settings.

## Use the approach on other songs

Tuned is the default for audio and YouTube. Studio can estimate small pitch
repairs from the stems and shared harmony by itself. An authored MIDI guide
can supply intended pitches and a clearer rhythm part when you have one.
Use `--reference-midi`, with `--reference-channels` and
`--reference-alignment` when you need to map parts and beats explicitly.

The hardware recording, original song audio and sequencer MIDI are private
benchmark inputs. The repository contains the method and checksums.
