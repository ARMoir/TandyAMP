/* Original synthetic playback regressions; no third-party MIDI required. */
#include "../src/midi.h"
#include <assert.h>
#include <stdio.h>
static unsigned writes;
void ta_psg_tone(int s,ta_u16 p,ta_u8 a)
{ assert(s>=0 && s<3 && p>=1 && p<=1023 && a<=15);writes++; }
void ta_psg_noise(ta_u8 m,ta_u8 a){assert(m<=7 && a<=15);}
void ta_psg_noise_level(ta_u8 a){assert(a<=15);}
void ta_psg_silence(void){}
static int sounding(int channel,int note)
{
    unsigned i;
    for(i=0;i<3;i++)
        if(ta.voices[i].note==note && ta.voices[i].channel==channel)return 1;
    return 0;
}
int main(void)
{
    assert(ta_load("tests/ordered.mid"));
    ta_begin();
    /* Later note-off on track 0 must follow earlier note-on on track 1. */
    ta_tick();
    assert(!sounding(0,72));
    assert(ta.playing);
    assert(ta_load("tests/chord.mid"));
    ta_begin();writes=0;
    ta_advance(1);
    assert(writes==3); /* One final assignment, no transient chord notes. */
    assert(ta_load("tests/muted.mid"));
    ta_begin();ta_advance(1);
    assert(!sounding(0,76));
    assert(sounding(1,72));
    assert(sounding(2,48));
    assert(sounding(3,64));
    /* Raising expression makes the still-held note eligible again. */
    ta_tick();
    assert(sounding(0,76));
    puts("PASS: cross-track ordering, chord write budget, muted voice recovery");
    return 0;
}
