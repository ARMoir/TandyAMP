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
def vlq(n):
    result=[n&127]
    n>>=7
    while n:
        result.insert(0,(n&127)|128)
        n>>=7
    return bytes(result)
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
# Dense multi-channel arrangement: melody and bass must survive chords;
# General MIDI channel 10 drums must use independent noise channel.
dense=(tempo+note(0,0x90,76,120)+note(0,0x91,45,95)+
       note(0,0x92,64,82)+note(0,0x93,69,70)+
       note(0,0x99,38,110)+note(0,0x99,42,95)+note(0,0x9f,38,100)+
       note(48,0x80,76,0)+note(0,0x81,45,0)+
       note(0,0x82,64,0)+note(0,0x83,69,0)+ending)
Path("tests/dense.mid").write_bytes(header(0,1)+chunk(b"MTrk",dense))
# Regression: original Windows 3.x CANYON.MID is roughly 34 KB.
# Long ignored meta event validates large files and 16-bit track offsets.
padding=b"\x00\xff\x7f"+vlq(34000)+bytes(34000)
large=(tempo+padding+note(0,0x90,60,100)+note(96,0x80,60,0)+ending)
Path("tests/large.mid").write_bytes(header(0,1)+chunk(b"MTrk",large))
# Legacy channel 16 is clearly percussion (kick, snare, hats).
legacy=(tempo+note(0,0x9f,36,110)+note(12,0x9f,42,90)+
        note(12,0x9f,38,110)+note(12,0x9f,42,95)+
        note(12,0x9f,36,100)+note(12,0x9f,46,90)+ending)
Path("tests/legacy16.mid").write_bytes(header(0,1)+chunk(b"MTrk",legacy))
# A channel-16 melody must NOT auto-detect as percussion.
mel16=(tempo+note(0,0x9f,60,105)+note(12,0x9f,62,105)+
       note(12,0x9f,64,105)+note(12,0x9f,65,105)+
       note(12,0x9f,67,105)+note(12,0x9f,69,105)+ending)
Path("tests/melody16.mid").write_bytes(header(0,1)+chunk(b"MTrk",mel16))
Path("tests/bad.mid").write_bytes(b"MThd"+b"\x00"*12)
print("PASS: generated deterministic MIDI inputs")
Path("tests/overflow.mid").write_bytes(header(0,1)+b"MTrk"+b"\xff"*4)

# Track order is not event order: off at tick 2 must follow on at tick 1.
a=note(2,0x80,72,0)+vlq(94)+b"\xff\x2f\x00"
b=note(1,0x90,72,100)+vlq(95)+b"\xff\x2f\x00"
Path("tests/ordered.mid").write_bytes(header(1,2)+chunk(b"MTrk",a)+chunk(b"MTrk",b))
# Dense same-timestamp chord must select only once, after all notes arrive.
chord=b"".join(note(0,0x90,60+i,80+i) for i in range(12))
Path("tests/chord.mid").write_bytes(header(0,1)+chunk(b"MTrk",chord+note(96,0xb0,120,0)+ending))
muted=(note(0,0xb0,11,0)+note(0,0x90,76,127)+note(0,0x91,72,90)
       +note(0,0x92,48,90)+note(0,0x93,64,90)+note(1,0xb0,11,127)
       +note(96,0xb0,120,0)+ending)
Path("tests/muted.mid").write_bytes(header(0,1)+chunk(b"MTrk",muted))


