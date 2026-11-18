"""Reproducible note-finish, duplicate-attack and outlier benchmark.

No copyrighted source material is committed. With no arguments this runs
synthetic multi-style fixtures in CI. To inspect a real Studio diagnostic ZIP:

  py -3.11 benchmarks\\score_polish_ab.py C:\\Music\\ENSEMBLE_TEST.zip

The real-ZIP mode measures *saved source and output note candidates*,
NOT a fresh Demucs/Basic Pitch/full-song conversion and not listening.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from arranger import Note
from score_polish import (reject_register_spikes,
                          merge_duplicate_attacks,commit_role_notes)


def load_notes(raw: list[dict]) -> list[Note]:
    return [Note(**row) for row in raw]


def benchmark(original:list[Note],final:list[Note]) -> dict:
    _, cleaned_report=reject_register_spikes(original)
    merged, dupes=merge_duplicate_attacks(final)
    committed, conflicts=commit_role_notes(merged)
    roles=lambda notes:dict(sorted(Counter(n.part for n in notes).items()))
    # We deliberately neither fabricate new attacks nor alter timing
    # when a valid note already owns a PSG role.
    return {
      'input_candidates':len(original),
      'raw_register_outliers_rejected':cleaned_report.removed_register_spikes,
      'final_notes_before_postprocessing':len(final),
      'same_pitch_restarts_merged':dupes,
      'competing_new_notes_not_started':conflicts,
      'final_notes_after_postprocessing':len(committed),
      'before_roles':roles(final),
      'after_roles':roles(committed),
    }


def synthetic() -> tuple[list[Note],list[Note]]:
    def n(role,start,end,pitch,velocity=86):
        program={'bass':33,'guitar':30,'melody':80,'harmony':48,
                 'drums':0}[role]
        return Note(start,end,pitch,velocity,role,program)
    bass=[n('bass',t,t+.15,40,86) for t in (0,.2,.4,.6,.8,1.)]
    incoming=bass+[n('bass',.5,.73,71,50),
                   n('guitar',0,.09,52,88),
                   n('guitar',.09,.2,52,63),
                   n('guitar',.28,.70,57,91),
                   n('melody',.12,.73,67,97),
                   n('drums',0,.07,36)]
    return incoming,[n for n in incoming if n.pitch!=71]


def from_zip(path:Path) -> tuple[list[Note],list[Note]]:
    with zipfile.ZipFile(path) as archive:
        def get(suffix:str) -> list[Note]:
            matches=[x for x in archive.namelist()
                     if x.endswith(suffix)]
            if len(matches)!=1:
                raise ValueError(f'Expected one {suffix} in {path}')
            parsed=json.loads(archive.read(matches[0]))
            return load_notes(parsed['notes'])
        return get('INPUT.json'),get('METRICS.json')


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('diagnostic_zip',type=Path,nargs='?')
    a=parser.parse_args()
    original,final=(from_zip(a.diagnostic_zip)
                    if a.diagnostic_zip else synthetic())
    data=benchmark(original,final)
    print(json.dumps(data,indent=2,sort_keys=True))
    if a.diagnostic_zip is None:
        if data['raw_register_outliers_rejected']!=1:
            raise SystemExit('Synthetic extreme-register spike regression')
        if data['same_pitch_restarts_merged']<1:
            raise SystemExit('Synthetic repeated-note merging regression')
        if data['after_roles'].get('melody')!=1:
            raise SystemExit('Protected lead was lost')
    print('Note cleanup benchmark passed')


if __name__=='__main__':
    main()
