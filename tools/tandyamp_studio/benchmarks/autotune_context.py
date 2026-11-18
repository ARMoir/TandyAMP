"""Reproducible AutoTune held-note context benchmark.

Use a previously saved Studio INPUT.json (or a MIDI file) to quantify
the fraction of active musical notes missed by the historical last-attack
lookup. No web access, separation, neural model or commercial media required.

Example:
  py -3.11 benchmarks\autotune_context.py C:\Music\TANDY\INPUT.json

Run without a file to benchmark the synthetic held-note fixture. These
numbers describe *context retrieval*, not transcription accuracy or
hardware listening quality.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import defaultdict
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arranger import Note, load_midi
from pitch_arranger import _near_note


def legacy_note(notes: list[Note], starts: list[float], at: float) -> Note | None:
    i=bisect_right(starts, at)-1
    return notes[i] if i >= 0 and at < notes[i].end else None


def input_notes(path: Path | None) -> list[Note]:
    if path is None:
        return ([Note(0,2,40,96,'bass',33)] +
                [Note(.30+i*.17,.33+i*.17,50,55,'bass',33)
                 for i in range(9)])
    if path.suffix.lower() in ('.mid','.midi'):
        return load_midi(path)
    data=json.loads(path.read_text(encoding='utf-8'))
    rows=data['notes'] if isinstance(data, dict) else data
    return [Note(**row) for row in rows]


def run(notes: list[Note], sample_step: float = .025) -> dict:
    if sample_step <= 0:
        raise ValueError('sample_step must be positive')
    groups=defaultdict(list)
    for note in notes:
        if note.part!='drums' and note.end>note.start:
            groups[note.part].append(note)
    result={}
    for role, group in sorted(groups.items()):
        group.sort(key=lambda n:(n.start,n.end))
        starts=[n.start for n in group]
        elapsed=max(n.end for n in group)
        queries=int(elapsed/sample_step)+1
        active=old_misses=new_misses=0
        start_clock=perf_counter()
        for k in range(queries):
            at=k*sample_step
            i=bisect_right(starts,at)-1
            truth=next((group[j] for j in range(i,-1,-1)
                        if group[j].end>at), None)
            if truth is None:
                continue
            active+=1
            if legacy_note(group, starts, at) is None:
                old_misses+=1
            if _near_note(group,starts,at) is None:
                new_misses+=1
        result[role]=dict(queries=queries, active_frames=active,
                          legacy_misses=old_misses,
                          tuned_misses=new_misses,
                          runtime_seconds=round(perf_counter()-start_clock,3))
    return result


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',nargs='?',type=Path,
                        help='Studio INPUT.json or reference .mid')
    parser.add_argument('--step',type=float,default=.025)
    a=parser.parse_args()
    data=run(input_notes(a.source),a.step)
    print(json.dumps(data,indent=2,sort_keys=True))
    if any(row['tuned_misses'] for row in data.values()):
        raise SystemExit('AutoTune missed a still-sounding note')


if __name__=='__main__':
    main()
