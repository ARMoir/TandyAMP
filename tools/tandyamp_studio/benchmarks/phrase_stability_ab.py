"""Same-source MIDI proposal A/B for reusable stronger audio phrase stabilization.

A controlled fixture models vocal detector restarts, one high guitar beep,
an intentional repeated bass attack, and tiny guitar/lead gaps. Reports
event counts, note duration and missing signal between source notes.
This does NOT claim acoustic quality of a commercial MP3.
"""
from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from arranger import Note
from score_polish import (reject_register_spikes, stabilize_audio_candidates,
                          connect_legato_gaps)


def n(role,t,end,pitch,v=88):
    return Note(t,end,pitch,v,role,
                {'melody':80,'guitar':30,'bass':33,'drums':0,'harmony':48}[role])


def fixture():
    bass=[n('bass',t,t+.16,40,88) for t in (0,.2,.4,.6,.8,1.)]
    melody=[
        n('melody',0,.14,67,98),
        n('melody',.16,.32,67,77),
        n('melody',.34,.50,67,65),
        n('melody',.58,.78,69,97),
        n('melody',.83,1.10,71,98),
    ]
    guitar=[n('guitar',t,t+.16,52,89) for t in
            (0,.2,.4,.6,.8,1.)]
    guitar.append(n('guitar',.50,.58,76,108))
    drums=[n('drums',t,t+.06,36,94) for t in (0,.4,.8)]
    return bass+melody+guitar+drums


def metrics(notes):
    vocals=[n.end-n.start for n in notes if n.part=='melody']
    return {
        'note_events':len(notes),
        'vocal_events':len(vocals),
        'median_vocal_note_ms':round(1000*statistics.median(vocals),1),
        'extreme_guitar_events':sum(n.part=='guitar' and n.pitch>=76
                                    for n in notes),
        'rhythm_events':sum(n.part=='drums' for n in notes),
    }


def run():
    raw=fixture()
    filtered,report=reject_register_spikes(raw)
    stabilized,stats=stabilize_audio_candidates(filtered)
    polished,links=connect_legato_gaps(stabilized)
    return {
      'before':metrics(raw),
      'after':metrics(polished),
      'removed_register_spikes':report.removed_register_spikes,
      'source_fragments_joined':stats['merged_source_fragments'],
      'vocal_jitter_removed':stats['removed_pitch_jitter'],
      'micro_gaps_connected':links,
    }


if __name__=='__main__':
    data=run()
    print(json.dumps(data,indent=2,sort_keys=True))
    if data['after']['median_vocal_note_ms']<=data['before']['median_vocal_note_ms']:
        raise SystemExit('Vocal duration did not improve')
    if data['after']['extreme_guitar_events']!=0:
        raise SystemExit('Isolated guitar harmonic was not suppressed')
    if data['after']['rhythm_events']!=data['before']['rhythm_events']:
        raise SystemExit('Drum attacks were altered')
    if data['source_fragments_joined'] < 2:
        raise SystemExit('Fragment stitching was too weak')
    print('Phrase-stability A/B benchmark passed')
