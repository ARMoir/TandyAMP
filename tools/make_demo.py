#!/usr/bin/env python3
"""Create an original 16-second three-voice MIDI demo for TandyAMP.
No third-party music or audio is copied into this file. MIT licensed.
"""
from pathlib import Path
import struct

PPQN=96
def vlq(v):
    a=[v&0x7f]
    v>>=7
    while v:
        a.insert(0,(v&0x7f)|0x80)
        v>>=7
    return bytes(a)
def ev(delta,data):
    return vlq(delta)+bytes(data)

# C-Am-F-G: simple original arpeggiated tune at 120 BPM.
progression=[
    (48,60,67),(45,60,69),(41,57,65),(43,59,67),
    (48,64,72),(45,64,69),(41,60,65),(43,62,71),
]
melody=[72,74,76,79,76,74,72,71,69,72,74,76,72,71,69,67,
        76,79,81,79,76,74,72,74,72,71,69,67,69,71,72,72]
notes=[]
notes += [ev(0,(0xff,0x51,3,0x07,0xa1,0x20))] # 500,000 us/quarter
notes += [ev(0,(0xc0,80))]  # general MIDI square lead program, PSG remains square
for i,lead in enumerate(melody):
    bass,center,top=progression[(i//4)%len(progression)]
    # Keep at most three simultaneously sounding notes on the EX.
    notes += [ev(0,(0x90,bass,85))]
    notes += [ev(0,(0x91,center,68))]
    notes += [ev(0,(0x92,lead,110))]
    notes += [ev(96,(0x80,bass,0))]
    notes += [ev(0,(0x81,center,0))]
    notes += [ev(0,(0x82,lead,0))]
notes += [ev(0,(0xff,0x2f,0))]
stream=b"".join(notes)
out=(b"MThd"+struct.pack(">IHHH",6,0,1,PPQN)
    +b"MTrk"+struct.pack(">I",len(stream))+stream)
path=Path("DEMO.MID")
path.write_bytes(out)
print(f"Created {path}: {len(out)} bytes; 32 beats, approx. 16 seconds")
