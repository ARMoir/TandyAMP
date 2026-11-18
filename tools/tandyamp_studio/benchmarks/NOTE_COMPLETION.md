# Guide-free AutoTune: do not interrupt completed notes

## Stronger phrase continuity (new default for guide-free Tuned audio)

The first filter corrected isolated register glitches, but the rebuilt
lead and guitar still sounded like disconnected detector *fragments*.
The new stage works **both before and after phrase reconstruction**:

**Before selecting phrases:** Consecutive same-pitch detections are
combined *per musical role and pitch*, even when an unrelated harmonic
candidate is interspersed in the transcription. The role-specific
maximum gap is **95 ms for melody, 75 ms for guitar and 50 ms for
bass**. Strong new attacks, drum-aligned guitar/bass pick attacks, and
clearly intentional long repeated vocal syllables remain separate.
A very brief, distinctly weaker **1–2 semitone vocal/guitar pitch
wobble** inside an otherwise consistent note can be removed.

**Guitar beep reduction:** A short, isolated note at least **12
semitones above** the locally established guitar register is now
eligible for rejection, *even when its decoder velocity appears
high*. It must also be unsupported by surrounding similar pitches.
A sustained or repeated high-register guitar passage is protected.
Lower outliers and other roles retain the more conservative
19-semitone threshold.

**After selecting phrases:** Confirmed guitar and vocal notes can be
held across accidental gaps of up to **65 ms (guitar)** or
**85 ms (vocal melody)** by ending the old pitch at the next
original note-on. The algorithm does not change that next attack,
extend bass rests, alter percussion timing, add notes or create
polyphony. A gap larger than the threshold is treated as a real rest.

This is *not* turning every pair of notes into a sustain. Music needs
breathing space, rhythmic rests, and repeated attacks. These are
source-relative cleanup rules that apply to vocals, violins, synth
leads, guitars, keyboards and other melodic roles, not a template
for any artist, song, key or genre.

The enhanced `POLISH.TXT` now reports **source fragments combined**
and **weak pitch wobbles removed**; `PITCH.TXT` includes
**legato micro-gaps connected**. The original `INPUT.json` stays
untouched; `CLEAN.json` contains the exact candidates that enter
phrase reconstruction.

### Repeatable A/B coverage

```bat
py -3.11 benchmarks\phrase_stability_ab.py
```

This tests known artificial vocal double detections, a high guitar
harmonic, bass/drum attacks and micro-gaps. The regression suite
additionally covers chromatic ornaments, classical instrument lines,
strong repeated vocal syllables, real high guitar solos and deliberate
rests. A full YouTube conversion still requires a fresh run; these
synthetic cases are **not** a claim about hardware audio quality.



**Status:** Implemented in the **guide-free audio `--arrangement tuned` path**.
The approved **MIDI-guided PARATUNE** take, imported MIDI/classic,
MAX RAW and the DOS player are left untouched.

## Reusable musical decisions

1. **Question a register spike, not the instrument's register.**
   Each part is compared with notes that surround it *in that part*
   within ~0.8 seconds. Reject only an isolated pitch at least 19
   semitones from the local median, if there are at least two notes
   before and after, no nearby same-register evidence, **and** the
   note has low local velocity or an implausibly short duration.
   Keep a legitimate high solo, octave movement, bass drop, chromatic
   riff, sustained note or coordinated passage.
2. **Merge likely duplicate same-pitch starts.** A note within
   55 ms of the previous note's ending can become one longer note
   when attacks are close or the later note is much weaker. Protect
   strong new attacks, kick/snare-aligned onsets, rhythmic repeated
   picking and new vocal syllables. The role-sensitive maximum
   onset spacings are 150 ms (bass/guitar) and 190 ms (lead),
   not a rule that every repeated note must be held.
3. **Commit before sounding.** Guide-free phrase scoring disallows
   transitions that overlap an already selected note. The automatic
   guitar backing helper cannot cut a previously committed pitch
   short just because a new estimate appears. After selection, a
   competing note is **declined whole**—never given an abbreviated
   few milliseconds or moved to an invented onset.

These apply to *musical roles*, not the title/artist/key/meter or
a rock-only classifier. Existing hardware limits still apply:
three SN76489 pitches, one noise channel, and optional eligible
SPK4 bass; no fake extra harmony.

### Provenance / A-B testing

The original estimates are preserved in `INPUT.json`.
A guide-free tuned conversion additionally writes:

- `CLEAN.json` — candidates after local extreme-register filtering
- `POLISH.TXT` — register-cleanup counts
- `PITCH.TXT` — additional whole-note commitment and same-pitch merge
  counts
- `SCORE.json`, `METRICS.json`, `BLACKS01.MID` — reconstructed
  score and final output, unchanged DOS export scheme

Use the repeatable script:

```bat
py -3.11 benchmarks\score_polish_ab.py "C:\Users\alexr\Music\ENSEMBLE_TEST.zip"
```

The script can analyze a Studio ZIP without AI model downloads, or
run deterministic synthetic fixtures when invoked without arguments.
The full Pipeline still needs to be rerun against the *same audio*
before declaring the new musical mix better.

### Findings on the user's ENSEMBLE_TEST.zip (before the new implementation)

- **3,293** transcribed note events in `INPUT.json`.
- **1,663** events in the previously arranged `METRICS.json`
  (682 bass, 308 guitar, 220 melody, 453 drums).
- **31** isolated extreme-register candidates meet the conservative
  context rule in the *raw* audio transcription.
- On the **already exported** 1,663 note events, the conservative
  same-pitch repair identifies **143 merges** (80 bass, 22 guitar,
  41 melody). This is a postprocessing diagnostic, not a full
  end-to-end retune result. It is deliberately less aggressive than
  merging all adjacent same-pitch notes.
- The raw bass estimates include one low-confidence note **MIDI 71**
  at approximately **4.09 seconds**, more than two octaves above
  its local bass context. It is not a legitimate note simply because
  the pitch detector printed it.

### Acceptance gates

- A strong new pick, drum-aligned bass reattack or valid high-register
  melodic passage must survive.
- No selected note may be truncated for a later competing estimate.
- Neither bass/drum accent timing nor source time should be quantized.
- A full-song listening test and physical Tandy test are required;
  automated MIDI statistics do **not** measure musical quality.
