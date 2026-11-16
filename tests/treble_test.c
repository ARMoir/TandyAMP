/* High-note balance and priority regression. No prerecorded MIDI needed.
   Compile with host GCC; the tested synthesis code is the same C89
   source used by Open Watcom for the Tandy 1000 EX. */
#include <assert.h>
#include <stdio.h>
#include "../src/midi.c"

static ta_u8 levels[3]={15,15,15};
static ta_u16 dividers[3]={0,0,0};
static unsigned writes=0;
void ta_psg_tone(int s,ta_u16 p,ta_u8 a)
{
    assert(s>=0 && s<3 && p>=1 && p<=1023 && a<=15);
    levels[s]=a; dividers[s]=p; writes++;
}
void ta_psg_noise(ta_u8 m,ta_u8 a){assert(m<=7 && a<=15);}
void ta_psg_noise_level(ta_u8 a){assert(a<=15);}
void ta_psg_silence(void)
{
    unsigned i;
    for(i=0;i<3;i++)levels[i]=15;
}
void ta_pc_speaker(ta_u16 p){(void)p;}
static unsigned sounding_level(void)
{
    unsigned i;
    for(i=0;i<3;i++)if(levels[i]<15)return levels[i];
    return 15;
}
static ta_u16 sounding_period(void)
{
    unsigned i;
    for(i=0;i<3;i++)if(levels[i]<15)return dividers[i];
    return 0;
}
static void begin_note(ta_u8 note)
{
    clear_synth();ta.playing=1;
    on(0,note,127);
    flush_mix();
    assert(sounding_period()!=0 && sounding_level()<15);
}
int main(void)
{
    TAActiveNote n;
    ta_s32 c7,csharp7;
    ta_u16 p;
    ta_u32 clock;
    unsigned before;
    /* The original engine abruptly dropped the main-voice melody
       bonus at MIDI 97. Priority must now decrease smoothly. */
    memset(&n,0,sizeof(n));
    n.held=1;n.gain=127;n.note=96;
    c7=note_priority(&n);
    n.note=97;
    csharp7=note_priority(&n);
    assert(csharp7<c7 && c7-csharp7<100L);
    assert(csharp7>note_priority(&n)-100L);
    assert(treble_extra_atten(&n)==0);

    begin_note(72); /* C5: unaffected in both modes */
    p=sounding_period();
    before=sounding_level();
    ta_set_treble(1);
    assert(ta.treble_soft==1 && sounding_level()==before);
    assert(sounding_period()==p);
    ta_set_treble(0);
    assert(sounding_level()==before);

    begin_note(84); /* C6: one attenuation step */
    before=sounding_level();p=sounding_period();
    clock=12345UL;ta.clock_q8=clock;
    ta_set_treble(1);
    assert(sounding_level()==before+1U);
    assert(sounding_period()==p && ta.clock_q8==clock);
    ta_set_treble(1); /* no-op should not cause extra writes */
    {
        unsigned count=writes;
        ta_set_treble(1);
        assert(writes==count);
    }
    ta_set_treble(0);
    assert(sounding_level()==before && sounding_period()==p);
    assert(ta.clock_q8==clock);

    begin_note(93); /* A6: 1749 Hz, the recording's prominent high note */
    before=sounding_level();
    assert(before==0);
    ta_set_treble(1);
    assert(sounding_level()==1); /* ~2 dB from note-on */
    p=sounding_period();
    update_tone_effects(640);flush_mix();
    assert(sounding_level()==1);
    update_tone_effects(128);flush_mix(); /* ~165 ms */
    assert(ta.notes[0].age_q8>=768);
    assert(sounding_level()==2); /* ~4 dB when sustained */
    assert(sounding_period()==p); /* does not detune the note */
    ta_set_treble(0);
    assert(sounding_level()==before);
    assert(sounding_period()==p);
    ta_set_treble(1);
    assert(sounding_level()==2);

    begin_note(97); /* C#7: still playable after priority fix */
    ta_set_treble(1);
    assert(sounding_level()==1);
    update_tone_effects(768);flush_mix();
    assert(sounding_level()==2);

    /* Even boosted 20 must retain treble softening. Adding the trim
       before boost instead would silently cancel it. */
    begin_note(93);
    ta_set_volume(20);
    ta_set_treble(0);
    assert(sounding_level()==0);
    ta_set_treble(1);
    assert(sounding_level()==1);
    update_tone_effects(768);flush_mix();
    assert(sounding_level()==2);
    handle_cc(0,7,0);flush_mix();
    assert(sounding_level()==15); /* genuine silence is never revived */

    /* Unrelated PSG and PIT2 behavior is unchanged; mute stays silent. */
    begin_note(69);
    ta_set_treble(1);
    assert(sounding_level()==0);
    ta_set_volume(0);
    assert(sounding_level()==15);
    ta_stop();
    assert(sounding_level()==15);
    puts("PASS: continuous C7 melody priority, C6/A6 trims, held-note "
         "decay, 20-step boost, no pitch drift, MIDI mute and live H toggle");
    return 0;
}
