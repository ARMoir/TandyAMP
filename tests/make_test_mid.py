#!/usr/bin/env python3
"""Generate tiny synthetic, noncopyrighted Standard MIDI Files for tests."""
from pathlib import Path
import struct
def chunk(name,data):
    return name+struct.pack(">I",len(data))+data
def header(fmt,tracks,ppqn=96):
    return chunk(b"MThd",struct.pack(">HHH",fmt,tracks,ppqn))
def note(dt,st,n,v):
    return bytes([dt,st,n,v])
tempo=b"\x00\xff\x51\x03\x07\xa1\x20"
ending=b"\x00\xff\x2f\x00"
# Type 0: chord, sustain pedal, velocity-zero note-off, and tempo changes.
one=(tempo+note(0,0x90,60,120)+note(0,0x90,64,96)+note(0,0x90,67,90)
     +note(24,0xb0,64,127)+note(24,0x80,60,0)
     +note(0,0x90,64,0)+note(0,0x80,67,0)
     +note(12,0xb0,64,0)+ending)
Path("tests/test0.mid").write_bytes(header(0,1)+chunk(b"MTrk",one))
# Type 1: separate tempo track and melody track, running status on note-offs.
metatrack=tempo+b"\x30\xff\x51\x03\x06\x1a\x80"+ending
melody=(note(0,0x90,69,120)+b"\x18\x45\x00"+ # running note-on velocity 0
        note(24,0x90,72,90)+note(24,0x80,72,0)+ending)
Path("tests/test1.mid").write_bytes(header(1,2)+chunk(b"MTrk",metatrack)+chunk(b"MTrk",melody))
Path("tests/bad.mid").write_bytes(b"MThd"+b"\x00"*12)
print("PASS: generated deterministic MIDI inputs")
