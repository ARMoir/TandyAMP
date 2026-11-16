/* Exercise actual program-aware PSG shapes and MIDI modulation logic.
   Original test, no copyrighted MIDI content or external libraries. */
#include <assert.h>
#include <stdio.h>
#include "../src/midi.c"

static ta_u16 pitches[3];
static ta_u8 levels[4]={15,15,15,15};
static unsigned writes=0;
void ta_psg_tone(int s,ta_u16 p,ta_u8 a){
    assert(s>=0 && s<3 && p>0 && p<=1023 && a<=15);
    pitches[s]=p;levels[s]=a;writes++;
}
void ta_psg_noise(ta_u8 m,ta_u8 a){assert(m<=7 && a<=15);levels[3]=a;}
void ta_psg_noise_level(ta_u8 a){assert(a<=15);levels[3]=a;}
void ta_pc_speaker(ta_u16 divider){(void)divider;}
void ta_psg_silence(void){
    unsigned i;for(i=0;i<4;i++)levels[i]=15;
}
static unsigned loud_voices(void){
    unsigned i,n=0;for(i=0;i<3;i++)if(levels[i]<15)n++;return n;
}
static unsigned sounding_pitch(void){
    unsigned i;for(i=0;i<3;i++)if(levels[i]<15)return pitches[i];return 0;
}
int main(void){
    unsigned prev,base,i,different=0,first;
    assert(style_for_program(255)==0);
    assert(style_for_program(0)==1);
    assert(style_for_program(25)==1);
    assert(style_for_program(35)==2);
    assert(style_for_program(48)==0);
    clear_synth();ta.playing=1;
    on(0,72,110);flush_mix();
    assert(loud_voices()==1);
    assert(ta.notes[0].style==0);
    base=ta.notes[0].attenuation;
    update_tone_effects(2048);flush_mix();
    assert(ta.notes[0].env_step==0 && ta.notes[0].attenuation==base);
    off(0,72);flush_mix();assert(loud_voices()==0);

    /* Program 1 -> fast pluck; controller 7 recalculates gain while
       retaining envelope progress instead of resetting its timer. */
    clear_synth();ta.playing=1;ta.cc_program[0]=0;
    on(0,72,100);flush_mix();
    assert(ta.notes[0].style==1);
    base=ta.notes[0].attenuation;
    update_tone_effects(512);flush_mix();
    assert(ta.notes[0].age_q8==512);
    assert(ta.notes[0].env_step==1);
    assert(ta.notes[0].attenuation==base+1);
    handle_cc(0,7,60);flush_mix();
    assert(ta.notes[0].env_step==1);
    assert(ta.notes[0].attenuation==(ta_u8)(attenuation(0,100)+1));
    update_tone_effects(4096);flush_mix();
    assert(ta.notes[0].env_step==6);
    prev=ta.notes[0].attenuation;
    update_tone_effects(8192);flush_mix();
    assert(ta.notes[0].env_step==6 && ta.notes[0].attenuation==prev);
    off(0,72);flush_mix();assert(loud_voices()==0);

    /* Bass and some wind/ethnic programs decay gently. */
    clear_synth();ta.playing=1;ta.cc_program[0]=35;
    on(0,60,100);flush_mix();
    assert(ta.notes[0].style==2);
    update_tone_effects(1536);flush_mix();
    assert(ta.notes[0].env_step==1);
    update_tone_effects(4096);flush_mix();
    assert(ta.notes[0].env_step==2);

    /* Strings/sustained notes never lose volume from a pluck envelope. */
    clear_synth();ta.playing=1;ta.cc_program[0]=48;
    on(0,69,100);flush_mix();
    base=ta.notes[0].attenuation;
    update_tone_effects(8192);flush_mix();
    assert(ta.notes[0].env_step==0 && ta.notes[0].attenuation==base);

    /* CC1 creates restrained variable pitch without modifying original
       base periods or restarting held notes. At CC1=0, pitch returns. */
    first=sounding_pitch();
    handle_cc(0,1,127);
    flush_mix();
    for(i=0;i<8;i++){
        update_tone_effects(120);flush_mix();
        if(sounding_pitch()!=first)different=1;
    }
    assert(different);
    assert(ta.notes[0].period==first);
    handle_cc(0,1,0);flush_mix();
    assert(sounding_pitch()==first);
    assert(loud_voices()==1);

    /* Channel state is reset for the next song. */
    clear_synth();
    assert(ta.cc_program[0]==255 && ta.cc_modulation[0]==0);
    assert(vibrato_phase==0);
    printf("PASS: program profiles, envelope timing, sustained notes, "
           "controller gain, CC1 vibrato and reset (%u tone writes).\n",writes);
    return 0;
}
