"""Synthetic offline benchmark for the new AutoTune stem pitch estimator.

Creates three short isolated instrument stems with *known* frequencies
and runs the actual \`stem_pitch.measure_stem_pitch\` code. No Demucs,
Basic Pitch, YouTube download or model checkpoint is required.

Metrics: dominant candidate MIDI pitch, detected tuning cents, a
single-semitone pitch repair, and seconds per 2-second stem.

This is a lower-level pitch test, NOT a full transcription/arrangement
listening validation. It intentionally includes a guitar with a stronger
second harmonic than its fundamental.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
from time import perf_counter
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import numpy as np
import soundfile as sf

from arranger import Note
from stem_pitch import FRAME_SECONDS, measure_stem_pitch


def make_tone(pitch: int, *, cents: float = 0,
              harmonics: tuple[float,...]=(1.,.55,.25),
              duration: float = 2.0, rate: int = 22050
              ) -> np.ndarray:
    t=np.arange(round(rate*duration), dtype=np.float64)/rate
    freq=440 * (2 ** ((pitch+ cents/100-69)/12))
    x=np.zeros_like(t)
    for order, amplitude in enumerate(harmonics,1):
        x += amplitude * np.sin(2*np.pi*freq*order*t)
    # Brief fade avoids creating an artificial click at time zero.
    ramp=np.minimum(1.,t/.022)*np.minimum(1.,(duration-t)/.022)
    return (x * ramp / max(1.,np.max(np.abs(x))) * .85).astype('float32')


def run() -> dict[str, dict]:
    cases={
        'bass_E2': ('bass',40,0.,(1.,.72,.25)),
        'guitar_E3_harmonic': ('guitar',52,0.,(.58,1.,.40,.22)),
        'vocal_A4_detuned': ('melody',69,22.,(1.,.48,.2)),
    }
    results={}
    with tempfile.TemporaryDirectory(prefix='autotune-benchmark-') as work:
        for name,(role,pitch,cents,harmonics) in cases.items():
            path=Path(work)/(name+'.wav')
            sf.write(path,make_tone(pitch,cents=cents,
                                    harmonics=harmonics),22050)
            started=perf_counter()
            evidence=measure_stem_pitch(path,role)
            elapsed=perf_counter()-started
            frames=evidence.strength[
                int(.35/FRAME_SECONDS):int(1.65/FRAME_SECONDS)]
            salience=frames.mean(axis=0)
            winner=int(evidence.first+int(salience.argmax()))
            # A wrong decoded semitone must not survive strong stem evidence.
            candidate=Note(.35,1.65,pitch+1,72,role,33 if role=='bass'
                           else 30 if role=='guitar' else 80)
            repaired=evidence.retune(candidate)
            results[name]={
                'expected_midi':pitch,
                'highest_salience_midi':winner,
                'repaired_midi':repaired.pitch,
                'true_tuning_cents':cents,
                'estimated_tuning_cents':round(float(evidence.cents),1),
                'runtime_seconds':round(elapsed,3)
            }
    return results


def main() -> None:
    results=run()
    print(json.dumps(results,indent=2,sort_keys=True))
    for name,row in results.items():
        if row['highest_salience_midi'] != row['expected_midi']:
            raise SystemExit(f'{name}: high harmonic defeated fundamental')
        if row['repaired_midi'] != row['expected_midi']:
            raise SystemExit(f'{name}: incorrect semitone was not repaired')
        if abs(row['estimated_tuning_cents']-row['true_tuning_cents'])>28:
            raise SystemExit(f'{name}: tuning estimate is off by over 28 cents')
    print('AutoTune stem pitch benchmarks passed')


if __name__=='__main__':
    main()
