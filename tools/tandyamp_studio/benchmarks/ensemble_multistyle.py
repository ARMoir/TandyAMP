"""Offline multi-style benchmark of the same source-candidate ensemble.

This is **structural** scoring, not listening quality or source-audio
transcription accuracy. In particular, it checks zero alteration to core
musical lines, note-on/note-off integrity, and optional accompaniment
that does not exceed the Tandy voice budget.

  py -3.11 benchmarks\\ensemble_multistyle.py
"""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from arranger import Note, _psg_pitch
from ensemble_roles import arrange_ensemble


def note(role, start, end, pitch, velocity=90):
    return Note(start,end,pitch,velocity,role,
                {'bass':33,'melody':80,'guitar':30,'harmony':48,
                 'accomp':48,'drums':0}[role])


def scenarios():
    return {
        'rock_rhythm_and_sung_lead': [
            note('bass',0,2,40),note('guitar',0,2,64),
            note('melody',.3,2,72),note('drums',0,.08,36),
            note('drums',.5,.57,38),note('harmony',.5,1.7,67),
            note('harmony',.76,.84,79),
        ],
        'classical_counterpoint_no_drums': [
            note('melody',0,2,76),note('guitar',0,2,67),
            note('harmony',0,2,60,90),note('harmony',.20,1.80,64,95),
        ],
        'synth_bass_lead_and_pulse': [
            note('bass',0,2,36),note('melody',0,2,75),
            note('accomp',0,2,63,92),note('drums',0,.08,36),
        ],
        'native_three_tone_no_percussion': [
            note('bass',0,2,41),note('melody',0,2,72),
            note('harmony',0,2,60,88),
        ],
    }


def metrics(original, arranged, sampling=.01):
    anchor=lambda notes: sorted((x.part,x.start,x.end,x.pitch,x.velocity)
                               for x in notes if x.part in
                               ('bass','melody','guitar','drums'))
    max_concurrent=0
    t=max((n.end for n in original),default=0)
    for k in range(int(t/sampling)):
        at=(k+.5)*sampling
        sounding={_psg_pitch(n) for n in arranged
                  if n.part!='drums' and n.start<=at<n.end}
        max_concurrent=max(max_concurrent,len(sounding))
    return dict(source_notes=len(original),output_notes=len(arranged),
                protected_exact=anchor(original)==anchor(arranged),
                max_distinct_psg_pitches=max_concurrent)


def run():
    rows={}
    for name,song in scenarios().items():
        arranged,report=arrange_ensemble(song,spk4='off')
        rows[name]={**metrics(song,arranged),
                    'offered_support':report.offered_support,
                    'retained_support':report.accepted_support}
    return rows


if __name__=='__main__':
    rows=run()
    print(json.dumps(rows,indent=2,sort_keys=True))
    for name,row in rows.items():
        if not row['protected_exact']:
            raise SystemExit(f'{name}: protected phrase was modified')
        if row['max_distinct_psg_pitches'] > 3:
            raise SystemExit(f'{name}: PSG budget exceeded')
    if rows['rock_rhythm_and_sung_lead']['retained_support'] != 0:
        raise SystemExit('Overcrowded rock arrangement retained clashing pad')
    if rows['classical_counterpoint_no_drums']['retained_support'] != 1:
        raise SystemExit('Classical counterpoint lost its inner part')
    if rows['native_three_tone_no_percussion']['retained_support'] != 1:
        raise SystemExit('Three-tone arrangement was unnecessarily pruned')
    print('Multi-style ensemble benchmark passed')
