# Guide-free AutoTune: do not interrupt completed notes

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
