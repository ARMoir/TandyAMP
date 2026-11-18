# DEMO.MID — hardware-native three-voice benchmark

**Role:** A tiny original, clean example of music written for TandyAMP's three PSG tone channels. It is **not** a universal target for half-second notes, fixed velocities, no percussion or monotonous chord structure.

## Verified source properties

| Property | Value |
| --- | --- |
| Filename | `DEMO.MID` |
| SHA-256 | `267fb5847ea8466680fd8d0e01eca1f3308180b6036263cdb62289096c9c3138` |
| Size | **804 bytes** |
| MIDI format | Type 0, one track, 96 PPQN |
| Duration | **16 seconds** |
| Complete note pairs | **96** (32 on each of three channels) |
| Percussion events | **0** |
| Timing | Every note lasts **0.5 s**, with regular half-second attacks |

| Zero-based channel | Function | Note range (MIDI) | Fixed velocity | Notes |
| --- | --- | --- | ---: | ---: |
| 0 | Lower harmonic foundation | 41–48 (F2–C3) | 85 | 32 |
| 1 | Middle harmony | 57–64 (A3–E4) | 68 | 32 |
| 2 | Upper melody | 67–81 (G4–A5) | 110 | 32 |

All three roles are coordinated and available throughout the 16-second passage. There is no competing drum noise and no need to invoke a fourth voice.

## Design rules drawn from DEMO

1. **Every audible note should have a purpose.** Three complementary roles can sound stronger than dozens of competing MIDI notes.
2. **Clarity beats maximum density.** Reserve sound channels for the important melodic contour, a coherent low foundation and a useful answer/harmony.
3. **Voice consistency is valuable.** Don't let quiet incidental notes steal an oscillator mid-phrase.
4. **Do not turn this demonstration into a straitjacket.** A real song may need rubato, rests, syncopation, different note lengths, percussion, SPK4 and dynamics. The 0.5-second grid is this demo's design, not a requirement.
5. **Hardware usage is conditional.** The absence of drums and SPK4 can be a feature. An optimized track need not keep every oscillator busy.

**Acceptance test:** a short, identifiable three-part melody survives conversion with clean timing, distinct voice roles and no unnecessary switching on the real Tandy.

See [unified musical design rules](../DESIGN_RULES.md).
