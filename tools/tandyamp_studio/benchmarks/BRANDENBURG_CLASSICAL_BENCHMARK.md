# Brandenburg Concerto No. 6, first movement — classical benchmark

**Role:** Reference for continuing musical lines, counterpoint, harmonic motion and purposeful instrument doubling **without drums**. This is not a recommended classical-specific processing engine. The MIDI is a user-provided reference, **not included in this repository**.

## Verified source properties

| Property | Value |
| --- | --- |
| Uploaded filename | `03 - Brandenburg Concerto No.6 1st movement.mid` |
| SHA-256 | `ea1b3eb9f744f4d60d8283f2d5083d827d864c3a7a1da7dc78e53b2d2529e464` |
| Size | 11,283 bytes |
| Format | MIDI type 1, four tracks, 480 ticks/quarter |
| Encoded tempo | 750,000 microseconds/beat (80 BPM) |
| Total track duration | 51.00 seconds; last pitched note ends near 49.125 s |
| Total complete note pairs | 1,445 |
| Percussion notes | 0 |

| Zero-based channel | GM instrument | Notes |
| --- | --- | ---: |
| 0 | String Ensemble 1, program 48 | 918 |
| 1 | Harpsichord, program 6 | 131 |
| 2 | Violin, program 40 | 396 |

**Intentional doubling:** all **396/396 violin notes** have an *exact* channel-0 string-ensemble note match in pitch, start time and end time. **129/131 harpsichord notes** have the same exact pitch/start/end match in the string-ensemble part (strict event matching in source MIDI). A previous less exact comparison described 127/131; the source-MIDI exact-match count is 129/131.

The three performed instrument channels are simultaneously active for **48.75 seconds**. Onset spacing frequently uses **0.1875-second** subdivisions, which reflect this particular encoding—not a mandatory quantization grid for all classical music.

## How this changes the arranging decision

- A genuine doubled note indicates the underlying **melodic line matters**. At the final PSG allocation, one oscillator may play that pitch, but the line should remain protected.
- Bass movement, leading upper phrase, and an independent counterline or suspension are the three natural *roles* for this passage. Track the phrases over time rather than always switching to the loudest new note.
- Preserve repeated notes, entrances/exits, dissonance, passing tones, cadences and expressive durations. Do **not** delete a note because it fails a chord-key filter.
- No drums means the rhythm is carried by **interlocking instruments**, not by manufacturing kick/snare/hat beats.
- Try a deliberately simple final 2–3-tone arrangement first, keeping the most meaningful voice movement, rather than rendering 1,445 note events through three PSG channels at random.

## What is and isn't proved

This file shows coordinated, intentionally overlapping parts and exact timing relationships. The MIDI alone cannot prove how faithfully the original recording's timbre, historical instrumentation or expressive phrasing translates to the Tandy. The uploaded file is already a MIDI composition, not a mixed YouTube waveform to transcribe.

**Acceptance test:** A listener can follow the main line and a responding line, with underlying harmonic movement, when rendered on the actual Tandy. A higher event count alone is not a success.

See [unified musical design rules](../DESIGN_RULES.md).
