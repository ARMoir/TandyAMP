"""Optional laptop-only MP3/WAV transcription; never imported for MIDI-only use."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

from arranger import Note

if TYPE_CHECKING:
    from phrase_score import ScoreEvidence


def _predict(path: Path, part: str | None, profile: str = 'standard',
             cache_dir: Path | None = None) -> list[Note]:
    from prediction_cache import decoder_settings
    settings = decoder_settings(part, profile)
    try:
        from basic_pitch import ICASSP_2022_MODEL_PATH
        from basic_pitch.inference import predict
    except ModuleNotFoundError as exc:
        # An ImportError *inside* installed Basic Pitch is not proof that Basic
        # Pitch is missing. Preserve the real missing module for diagnostics.
        if exc.name == 'basic_pitch':
            raise RuntimeError(
                'Basic Pitch is not installed. Run: '
                'py -3.11 -m pip install -r requirements-audio.txt'
            ) from exc
        if exc.name == 'pkg_resources':
            raise RuntimeError(
                'Basic Pitch dependency resampy cannot import pkg_resources. '
                'setuptools 82+ removed it. Run: '
                'py -3.11 -m pip install "setuptools>=70,<82"'
            ) from exc
        raise RuntimeError(
            'Basic Pitch could not load dependency {!r}: {}. '
            'See the Python traceback in the console.'.format(
                exc.name, exc
            )
        ) from exc
    except ImportError as exc:
        raise RuntimeError(
            'Basic Pitch initialization failed ({}): {}. '
            'See the Python traceback in the console.'.format(
                type(exc).__name__, exc
            )
        ) from exc
    # The public Basic Pitch predict() API requires the installed model path.
    if cache_dir is not None:
        from prediction_cache import predict_cached
        midi = predict_cached(path, ICASSP_2022_MODEL_PATH, predict,
                              cache_dir, part, profile)
    elif profile == 'standard':
        _, midi, _ = predict(str(path), ICASSP_2022_MODEL_PATH)
    else:
        _, midi, _ = predict(
            str(path), ICASSP_2022_MODEL_PATH,
            onset_threshold=settings['onset_thresh'],
            frame_threshold=settings['frame_thresh'],
            minimum_note_length=settings['min_note_len'] * 256 / 22050 * 1000)
    notes = []
    for instrument in midi.instruments:
        for n in instrument.notes:
            role = part or ('bass' if n.pitch <= 54 else 'melody' if n.pitch >= 68 else 'harmony')
            notes.append(Note(float(n.start), float(n.end), int(n.pitch), int(n.velocity), role,
                              33 if role == 'bass' else 80 if role == 'melody'
                              else 30 if role == 'guitar'
                              else 0 if role == 'piano' else 48))
    return notes


def _drum_onsets(path: Path, style: str = 'auto',
                 raw_mode: bool = False,
                 beat_times: list[float] | None = None) -> list[Note]:
    """Recover three rock drum classes without manufacturing rhythmic notes.

    Two onset detectors run on the *separated drum stem*:
    (1) full-spectrum onsets for kick/snare and
    (2) >6 kHz spectral novelty for hats/cymbals that a kick-led detector
        regularly misses. The Tandy's single noise oscillator is respected
        when deconflicting candidates.
    """
    if style not in ('auto', 'rock'):
        raise ValueError('Drum style must be auto or rock')
    try:
        import librosa
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            'Drum onset analysis requires librosa and numpy. '
            'Run: py -3.11 -m pip install -r requirements-audio.txt'
        ) from exc
    from bisect import bisect_left
    from collections import Counter
    from postprocess import (classify_drum_transient, drum_velocity,
                             normalize_drum_fluxes, recover_high_hats,
                             refine_drum_hits)

    samples, sr = librosa.load(str(path), sr=22050, mono=True)
    if len(samples) < 2048:
        return []
    hop = 256
    envelope = librosa.onset.onset_strength(y=samples, sr=sr, hop_length=hop)
    frames = librosa.onset.onset_detect(
        onset_envelope=envelope, sr=sr, hop_length=hop, backtrack=False
    )
    if not len(frames):
        return []

    strengths = np.asarray([envelope[min(int(i), len(envelope)-1)]
                            for i in frames], dtype=float)
    quiet, loud = np.percentile(strengths, [18, 90])

    beats = []
    try:
        _tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=envelope, sr=sr, hop_length=hop, trim=False
        )
        beats = list(librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop))
    except (ValueError, TypeError, RuntimeError):
        pass
    if beat_times is not None:
        beat_times.extend(float(t) for t in beats)

    fft_size = 1024
    taper = np.hanning(fft_size)
    freqs = np.fft.rfftfreq(fft_size, 1.0/sr)
    bands = (
        (freqs >= 40) & (freqs < 270),
        (freqs >= 300) & (freqs < 4200),
        (freqs >= 4500) & (freqs < 10400),
    )

    def attack_at(frame: int):
        at = float(librosa.frames_to_time(frame, sr=sr, hop_length=hop))
        center = int(at*sr)
        before_end = center-int(.012*sr)
        before_start = before_end-fft_size
        after_start = center+int(.003*sr)
        if before_start < 0 or after_start+fft_size > len(samples):
            return None
        before = np.abs(np.fft.rfft(samples[before_start:before_end]*taper))
        after = np.abs(np.fft.rfft(samples[after_start:after_start+fft_size]*taper))
        novel = np.maximum(after-.88*before, 0)**2
        low, mid, high = [float(novel[mask].sum()) for mask in bands]
        return (at, low, mid, high)

    raw = []
    for idx, frame in enumerate(frames):
        attack = attack_at(int(frame))
        if attack is None:
            continue
        at, low, mid, high = attack
        backbeat_hint = False
        if len(beats) >= 4:
            j = bisect_left(beats, at)
            near = [k for k in (j-1, j) if 0 <= k < len(beats)]
            if near:
                closest = min(near, key=lambda k: abs(at-beats[k]))
                backbeat_hint = (abs(at-beats[closest]) <= .065 and
                                 closest % 2 == 1)
        raw.append((at, low, mid, high, backbeat_hint,
                    float(strengths[idx])))

    # Independent high-frequency onset envelope: don't infer hats merely
    # from the scarcity of MIDI note 42 in the classification results.
    spectrum = np.abs(librosa.stft(samples, n_fft=fft_size,
                                   hop_length=hop)).astype('float32')
    high_mask = (freqs >= 6000) & (freqs < 10400)
    high_envelope = np.zeros(spectrum.shape[1], dtype='float32')
    if high_mask.any() and spectrum.shape[1] > 1:
        high_envelope[1:] = np.maximum(
            np.diff(spectrum[high_mask, :], axis=1), 0
        ).sum(axis=0)
    del spectrum

    high_raw = []
    if high_envelope.max() > 0:
        high_frames = librosa.onset.onset_detect(
            onset_envelope=high_envelope, sr=sr, hop_length=hop,
            backtrack=False, wait=8, pre_max=3, post_max=3,
            pre_avg=8, post_avg=8, delta=.035
        )
        positive = high_envelope[high_envelope > 0]
        floor = max(float(np.percentile(positive, 52)),
                    float(high_envelope.max())*.035)
        for frame in high_frames:
            frame = int(frame)
            strength = float(high_envelope[min(frame, len(high_envelope)-1)])
            if strength < floor:
                continue
            attack = attack_at(frame)
            if attack is not None:
                high_raw.append((attack, strength))

    # Calibrate *all* attack spectra on the recording itself, not against
    # a hardcoded power level from some other song.
    all_bands = [(x[1], x[2], x[3]) for x in raw]
    all_bands.extend((x[0][1], x[0][2], x[0][3]) for x in high_raw)
    calibrated = normalize_drum_fluxes(all_bands)

    candidates = []
    for (at, _l, _m, _h, hint, strength), xyz in zip(raw, calibrated):
        category = classify_drum_transient(*xyz, backbeat_hint=hint)
        if category is not None:
            velocity = drum_velocity(strength, float(quiet), float(loud))
            candidates.append(Note(at, at+.07, category, velocity,
                                   'drums', 0))
    high_offset = len(raw)
    recovered = recover_high_hats(
        [(item[0][0], item[1], *xyz)
         for item, xyz in zip(high_raw, calibrated[high_offset:])],
        candidates, style=style
    )
    combined = candidates + recovered
    if raw_mode:
        # MAX RAW preserves every detected drum transient on its own MIDI
        # event, without debouncing, velocity leveling or noise-voice caps.
        # Spectrally ambiguous broad onsets use a best-guess classification.
        # These are estimates, NOT the original drum-score MIDI notes.
        all_drums = []
        for (at, _l, _m, _h, _hint, strength), bands3 in zip(raw, calibrated):
            kind = classify_drum_transient(*bands3)
            if kind is None:
                kind = (36, 38, 42)[max(range(3),
                                      key=lambda i: bands3[i])]
            all_drums.append(Note(at, at + .07, kind,
                                  drum_velocity(strength, float(quiet),
                                                float(loud)), 'drums', 0))
        for (at, _l, _m, _h), strength in high_raw:
            # Do not discard a detected hat merely because a kick overlaps.
            all_drums.append(Note(at, at + .045, 42,
                                  drum_velocity(strength, float(quiet),
                                                float(high_envelope.max())
                                                if high_envelope.max() > 0 else 1.0),
                                  'drums', 0))
        print('MAX RAW drums: {} detected broad attacks + {} high-frequency '
              'attacks, no drum pruning'.format(len(raw), len(high_raw)),
              flush=True)
        return sorted(all_drums, key=lambda n: (n.start, n.pitch))
    result = refine_drum_hits(combined, beats, style=style)
    before = dict(Counter(n.pitch for n in combined))
    after = dict(Counter(n.pitch for n in result))
    print('Drum analysis: {} broad onsets, {} independent high-band attacks, '
          '{} recovered hats; {} classified {}, {} retained {} '
          '(36=kick, 38=snare, 42=hat)'.format(
              len(frames), len(high_raw), len(recovered), len(combined),
              before, len(result), after), flush=True)
    return result


def remove_guitar_bleed(guitar: list[Note], other: list[Note]) -> list[Note]:
    """Remove duplicated overlap, preserving independently sustained tails.

    A short guitar attack must not erase a much longer other-stem note.
    Only matched intervals are removed; no durations or pitches are invented.
    """
    if not guitar:
        return other
    from collections import defaultdict
    from dataclasses import replace
    by_pitch: dict[int, list[Note]] = defaultdict(list)
    for n in guitar:
        by_pitch[n.pitch].append(n)
    kept = []
    for n in other:
        fragments = [(n.start, n.end)]
        for g in by_pitch.get(n.pitch, []):
            overlap = max(0.0, min(n.end,g.end) - max(n.start,g.start))
            if (overlap >= min(.12, (n.end-n.start)*.55)
                    and abs(n.start-g.start) <= .14):
                remaining = []
                for start, end in fragments:
                    if g.end <= start or g.start >= end:
                        remaining.append((start, end))
                    else:
                        if g.start > start:
                            remaining.append((start, g.start))
                        if g.end < end:
                            remaining.append((g.end, end))
                fragments = remaining
        # Match Full-mode harmony's minimum; don't leave tiny edge clicks.
        kept.extend(replace(n, start=start, end=end)
                    for start, end in fragments if end-start >= .060)
    return sorted(kept, key=lambda n: (n.start, n.end, n.pitch))


def transcribe_audio(path: Path, stems: bool = False,
                     drum_style: str = 'auto',
                     preservation: str = 'full',
                     guitar_separation: bool = False,
                     accompaniment: str = 'off',
                     profile: str = 'standard',
                     raw_mode: bool = False,
                     score_evidence: ScoreEvidence | None = None,
                     tune_stems: bool = False) -> list[Note]:
    """Transcribe guitar/vocals/bass and optionally infer sustained harmony.

    The 6-stem guitar model is opt-in: its first use downloads more weights
    and its piano source can have bleed, so piano is not transcribed blindly.
    """
    from postprocess import clean_stem_notes
    from prediction_cache import decoder_settings
    decoder_settings(None, profile)
    if preservation not in ('full', 'clean'):
        raise ValueError('Note preservation must be full or clean')
    if accompaniment not in ('off', 'recover', 'harmonize'):
        raise ValueError('Accompaniment must be off, recover, or harmonize')
    if raw_mode:
        # Force the richest *source separation*, not an early three-voice
        # composition. No generated chord notes masquerade as source data.
        stems = True
        guitar_separation = True
        accompaniment = 'off'
        profile = 'raw'
    stems = stems or guitar_separation
    if accompaniment != 'off' and not stems:
        raise ValueError('Chord accompaniment requires --stems or '
                         '--guitar-separation (a separated harmonic stem).')

    if not stems:
        if score_evidence is not None:
            # A mono mix still provides candidate pitches. It has no reliable
            # per-instrument signal levels or separated drum beat evidence.
            return _predict(path, None, profile=profile)
        notes = _predict(path, None)
        cleaned = []
        for part in ('bass', 'melody', 'harmony'):
            group = [n for n in notes if n.part == part]
            cleaned.extend(clean_stem_notes(group, part,
                                            preservation=preservation))
        print(f'Cleaned direct transcription: {len(notes)} -> '
              f'{len(cleaned)} pitched events', flush=True)
        return cleaned

    try:
        import demucs  # noqa: F401; check before launching subprocess
    except ImportError as exc:
        raise RuntimeError('Stem separation needs Demucs. See requirements-audio.txt') from exc

    model = 'htdemucs_6s' if guitar_separation else 'htdemucs'
    with tempfile.TemporaryDirectory(prefix='tandyamp-stems-') as temp:
        output = Path(temp)
        print('Separating with Demucs {} (may take a while)...'.format(model),
              flush=True)
        cmd = [sys.executable, '-m', 'demucs', '-n', model, '-o', str(output),
               str(path)]
        subprocess.run(cmd, check=True)
        root = output / model / path.stem
        return transcribe_stems(root, guitar_separation=guitar_separation,
                                drum_style=drum_style, preservation=preservation,
                                accompaniment=accompaniment, profile=profile,
                                raw_mode=raw_mode,
                                **({'score_evidence': score_evidence}
                                   if score_evidence is not None else {}),
                                **({'tune_stems': True} if tune_stems else {}))


def stem_levels(path: Path) -> list[float]:
    """Measure pre-normalization stem RMS in blocks of 50 ms."""
    import numpy as np
    import soundfile as sf

    with sf.SoundFile(path) as wav:
        return [float(np.sqrt(np.mean(block ** 2)))
                for block in wav.blocks(blocksize=round(wav.samplerate * .05),
                                        dtype='float32')]


def transcribe_stems(root: Path, *, guitar_separation: bool = True,
                     drum_style: str = 'rock', preservation: str = 'full',
                     accompaniment: str = 'off', profile: str = 'standard',
                     cache_dir: Path | None = None,
                     diagnostics_dir: Path | None = None,
                     raw_mode: bool = False,
                     score_evidence: ScoreEvidence | None = None,
                     tune_stems: bool = False) -> list[Note]:
    """Shared Studio/benchmark pipeline, with optional inspectable checkpoints."""
    from postprocess import clean_stem_notes
    from diagnostics import save_stage
    if guitar_separation:
        stems_to_transcribe = [
            ('bass', 'bass'), ('vocals', 'melody'), ('guitar', 'guitar'),
            ('other', 'harmony')
        ]
        if raw_mode:
            # The six-stem model exposes piano as a separate fifth pitched
            # stem. Unlike the arranged pipeline, MAX RAW does not omit it.
            stems_to_transcribe.append(('piano', 'piano'))
    else:
        stems_to_transcribe = [
            ('bass', 'bass'), ('vocals', 'melody'), ('other', 'harmony')
        ]

    groups: dict[str, list[Note]] = {}
    for name, part in stems_to_transcribe:
        wav = root / (name + '.wav')
        if not wav.exists():
            raise RuntimeError(f'Demucs did not produce {wav}')
        print(f'Transcribing {name}...', flush=True)
        raw = (_predict(wav, part) if profile == 'standard' and cache_dir is None
               else _predict(wav, part, profile=profile, cache_dir=cache_dir))
        if diagnostics_dir is not None:
            save_stage(diagnostics_dir, name + '-raw', raw)
        if score_evidence is not None:
            score_evidence.levels[part] = stem_levels(wav)
        keep_proposals = raw_mode or (score_evidence is not None and preservation == 'full')
        kept = raw if keep_proposals else clean_stem_notes(
            raw, part, preservation=preservation)
        if tune_stems and score_evidence is not None and not raw_mode and kept:
            from stem_pitch import measure_stem_pitch

            pitch = measure_stem_pitch(wav, part)
            score_evidence.pitches[part] = pitch
            tuned = [pitch.retune(n) for n in kept]
            score_evidence.pitch_corrections[part] = sum(a.pitch != b.pitch
                                                        for a, b in zip(kept, tuned))
            kept = tuned
        print(f'  {name}: {len(raw)} -> {len(kept)} notes '
              f'{"without pruning" if keep_proposals else "after cleanup"}',
              flush=True)
        groups[name] = kept
        if diagnostics_dir is not None:
            save_stage(diagnostics_dir, name + '-clean', kept)

    if guitar_separation and not raw_mode and score_evidence is None:
        before = len(groups['other'])
        groups['other'] = remove_guitar_bleed(groups['guitar'],
                                             groups['other'])
        print(f'  other: {before} -> {len(groups["other"])} events after '
              'removing guitar-bleed overlap (sustained tails retained)', flush=True)

    notes: list[Note] = []
    for name, _part in stems_to_transcribe:
        notes.extend(groups[name])

    if diagnostics_dir is not None:
        save_stage(diagnostics_dir, 'before-accompaniment', notes)

    if accompaniment != 'off':
        from accompaniment import analyze_accompaniment_audio
        harmonic_stem = root / ('guitar.wav' if guitar_separation
                                else 'other.wav')
        print('Analyzing stable chords in {} for {} accompaniment...'.format(
            harmonic_stem.name, accompaniment), flush=True)
        notes.extend(analyze_accompaniment_audio(
            harmonic_stem, notes, mode=accompaniment))

    drums = root / 'drums.wav'
    if drums.exists():
        print('Estimating beat-aware kick/snare/hat onsets...', flush=True)
        drum_options = {}
        if score_evidence is not None:
            drum_options['beat_times'] = score_evidence.beats
        if raw_mode:
            drum_options['raw_mode'] = True
        notes.extend(_drum_onsets(drums, style=drum_style, **drum_options))
    return notes
