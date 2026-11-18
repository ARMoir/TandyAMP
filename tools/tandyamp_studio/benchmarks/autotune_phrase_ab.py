"""A/B benchmark: old note-by-note guitar gating vs coherent phrase gating.

This synthetic fixture has KNOWN target phrase notes, a short high overtone,
an overlapping repeated pitch fragment, a real following riff note and a
simultaneous false octave. Reports correct-pitch coverage and false notes.
No MP3/transcription/model download or physical listening is involved.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from arranger import Note
from pitch_arranger import _monophonic, _coherent_guitar_line


def note(start, end, pitch, velocity):
    return Note(start,end,pitch,velocity,'guitar',30)


def fixture():
    desired = [
        note(0,.95,52,95),
        note(.98,1.45,57,96),
        note(1.65,2.20,64,94),
        note(2.30,2.55,52,95),
        note(2.55,2.83,52,95),
    ]
    proposals = desired + [
        note(.34,.40,76,51), # spurious high harmonic over a ringing E3
        note(.50,.58,52,55), # spurious restart of same E3
        note(1.65,1.95,76,53), # competing octave at exact riff attack
    ]
    return desired, proposals


def stats(output, desired, step=.01):
    end=max(n.end for n in desired)
    correct=wrong=silent=overfull=0
    for k in range(int(end/step)):
        at=(k+.5)*step
        truth={n.pitch for n in desired if n.start<=at<n.end}
        actual={n.pitch for n in output if n.start<=at<n.end}
        correct+=int(truth==actual)
        wrong+=int(bool(actual-truth))
        silent+=int(bool(truth) and not bool(actual))
        overfull+=int(len(actual)>1)
    return {
       'source_notes':len(output),
       'correct_frames':correct,
       'wrong_pitch_frames':wrong,
       'missing_phrase_frames':silent,
       'polyphonic_guitar_frames':overfull,
       'sampled_frames':int(end/step),
    }


def run():
    truth, proposals=fixture()
    old=_monophonic(proposals,.006)
    new=_coherent_guitar_line(proposals,.006)
    return {'legacy':stats(old,truth),'coherent':stats(new,truth),
            'expected_note_count':len(truth),'candidate_count':len(proposals)}


def main():
    result=run()
    print(json.dumps(result,indent=2,sort_keys=True))
    old,new=result['legacy'],result['coherent']
    if new['correct_frames'] <= old['correct_frames']:
        raise SystemExit('New riff selection did not improve phrase correctness')
    if new['wrong_pitch_frames'] >= old['wrong_pitch_frames']:
        raise SystemExit('New selection did not reduce false pitches')
    if new['polyphonic_guitar_frames'] != 0:
        raise SystemExit('New guitar part still has multiple simultaneous pitches')
    if new['source_notes'] != result['expected_note_count']:
        raise SystemExit('True note/attack count not preserved')
    print('AutoTune guide-free riff-continuity benchmark passed')


if __name__=='__main__':
    main()
