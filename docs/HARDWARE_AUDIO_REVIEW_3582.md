# TandyAMP — physical EX audio review of 3582.mp4

**Source:** Owner-provided 30.2-second Tandy 1000 EX phone recording, `3582.mp4`, November 16, 2026. The analysis below uses the file's original 48 kHz AAC stereo audio, decoded to **24 kHz mono** for RMS and frequency analysis. It is an acoustically captured signal, **not** the raw PSG hardware output, so microphone placement, automatic gain, speaker response, background noise and room acoustics matter.

## Evidence from the recording

| Segment | RMS level | Highest sample within segment |
| --- | ---: | ---: |
| 0–3 seconds | −53.7 dBFS | −36.5 dBFS |
| 3–6 seconds | −45.7 dBFS | −29.3 dBFS |
| 9–12 seconds | −41.3 dBFS | −27.2 dBFS |
| 15–18 seconds | −36.6 dBFS | −23.7 dBFS |
| 18–21 seconds | −36.0 dBFS | −23.6 dBFS |
| 21–24 seconds | −36.1 dBFS | −23.5 dBFS |
| 24–27 seconds | −37.8 dBFS | −18.3 dBFS |
| 27–30 seconds | −38.7 dBFS | −23.9 dBFS |

The total decoded signal has approximately **−38.8 dBFS RMS** and a highest sample about **−18.3 dBFS**. **No near-full-scale digital clipping samples** were observed; this does not prove an undistorted analog Tandy output, because a phone can record an already distorted speaker at a low digital level.

The RMS rises by roughly **18 dB** between the first 3 seconds and the middle of the clip. This could be a musical crescendo, additional simultaneous notes, camera movement or phone automatic gain. In the photograph the TandyAMP display reads `VOL 15`, so the clip cannot establish how the 16–20 boost sounds on hardware.

A strong, narrow component around **1,749 Hz**, with a matching third harmonic around **5,244 Hz**, is continuously prominent from approximately **13.8 to 23.8 seconds** (~10 seconds). The strong harmonic relationship is consistent with a square-wave tone. This could represent an intentionally held MIDI note, a MIDI sustain-pedal passage or a missed note-off / trapped voice. **It is not enough to diagnose a bug without comparing the note events in the user's actual CANYON.MID.** Other changing pitched components include approximately **328 Hz** and **1,576 Hz**. A persistent low-frequency component around **120 Hz** could be a bass note, electrical/room noise or a mix artifact; it cannot independently confirm fourth-voice activation.

## What changed in TandyAMP

1. VIS now shows **CH1–CH3 plus SPK4**. The extra bar lights only when PIT2 actually has a nonzero programmed output, not merely when SPK4 is enabled.
2. PSG meter heights now follow **final attenuation** including velocity, gain, limiter and master volume, instead of raw MIDI velocity.
3. Current MIDI pitch labels appear under each bar, letting recordings reveal whether a high voice appears stuck at one pitch.
4. SPK4 shows **OFF**, **READY**, **PAUSE**, or the currently sounding bass note (e.g., C2).
5. The bottom shortcut legend is white on black for improved contrast; change-only redraw behavior is preserved.

## Recommended next physical test

Record the same 15–25 second song section once with SPK4 **OFF** and again **ON**, keeping both the DOS volume setting and camera position fixed. A direct line-level capture (with safe electrical isolation/attenuation if appropriate for the hardware) would be more comparable than different phone positions. If a high pitch remains visible long after its corresponding MIDI note-off, compare the recording with the owner's original CANYON.MID before adding automatic stuck-note suppression. Use `/VOL:15` first and try 18 or 20 only with speaker comfort in mind.

**Caveat:** The actual volume and source of individual sounds cannot be inferred reliably from the video display alone. The analysis reports numerical features of the *recorded* audio; it is not a full transcription of CANYON.MID and does not prove sound hardware or MIDI-engine correctness.
