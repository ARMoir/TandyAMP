/* Host-only deterministic MIDI engine test. Original code, MIT. */
#include "../src/midi.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned on_count=0, mute_count=0, max_simultaneous=0;
static unsigned noise_count=0, noise_mute_count=0;
static unsigned saw_melody=0, saw_bass=0;
void ta_psg_tone(int slot,ta_u16 period,ta_u8 attenuation)
{
    unsigned active=0,i;
    if(slot<0||slot>2||period<1||period>1023||attenuation>15)abort();
    if(attenuation<15)on_count++;else mute_count++;
    for(i=0;i<3;i++)if(ta.voices[i].note>=0)active++;
    if(active>max_simultaneous)max_simultaneous=active;
}
void ta_psg_noise(ta_u8 mode,ta_u8 attenuation)
{
    if(mode>7 || attenuation>15)abort();
    if(attenuation<15)noise_count++;
}
void ta_psg_noise_level(ta_u8 attenuation)
{
    if(attenuation>15)abort();
    if(attenuation==15)noise_mute_count++;
}
void ta_psg_silence(void){mute_count++;}

int main(int argc,char **argv)
{
    unsigned n,i,live;
    if(argc<8)return 2;
    for(n=1;n<3;n++){
        if(!ta_load(argv[n])){fprintf(stderr,"LOAD %s: %s\n",argv[n],ta_error());return 3;}
        if(ta.format!=n-1){fprintf(stderr,"Incorrect SMF format\n");return 4;}
        ta_begin();
        for(i=0;i<120 && ta.playing;i++)ta_tick();
        if(ta.playing){fprintf(stderr,"Playback did not terminate\n");return 5;}
        live=0;
        for(i=0;i<3;i++)if(ta.voices[i].note>=0)live++;
        if(live>3 || max_simultaneous>3){fprintf(stderr,"Too many hardware notes\n");return 6;}
    }
    if(ta_load(argv[3])){fprintf(stderr,"Malformed file accepted\n");return 7;}
    ta.drum_mode=TA_DRUM_ON; /* Explicit legacy override. */
    if(!ta_load(argv[4])){fprintf(stderr,"LOAD %s: %s\n",argv[4],ta_error());return 9;}
    ta_begin();
    ta_advance(32);
    for(i=0;i<3;i++){
        if(ta.voices[i].note==76)saw_melody=1;
        if(ta.voices[i].note==45)saw_bass=1;
    }
    if(!saw_melody || !saw_bass){
        fprintf(stderr,"Melody or bass lost in dense chord\n");return 10;
    }
    if(noise_count<1){
        fprintf(stderr,"Channel 10/16 drums failed to reach noise channel\n");return 11;
    }
    for(i=0;i<250 && ta.playing;i++)ta_advance(32);
    if(ta.playing){fprintf(stderr,"Dense MIDI did not terminate\n");return 12;}
    if(!noise_mute_count){fprintf(stderr,"Noise envelope never silenced\n");return 13;}
    ta.drum_mode=TA_DRUM_AUTO;
    if(!ta_load(argv[5])){fprintf(stderr,"LOAD large MIDI: %s\n",ta_error());return 14;}
    ta_begin();
    for(i=0;i<120 && ta.playing;i++)ta_tick();
    if(ta.playing){fprintf(stderr,"Large MIDI did not terminate\n");return 15;}
    ta.drum_mode=TA_DRUM_AUTO;
    if(!ta_load(argv[6]) || !ta.drum_detected || !ta.drum16){
        fprintf(stderr,"Legacy channel 16 percussion was not detected\n");return 16;
    }
    ta.drum_mode=TA_DRUM_OFF;
    if(!ta_load(argv[6]) || ta.drum16 || !ta.drum_detected){
        fprintf(stderr,"DRUM OFF override failed\n");return 17;
    }
    ta.drum_mode=TA_DRUM_AUTO;
    if(!ta_load(argv[7]) || ta.drum16){
        fprintf(stderr,"Melodic channel 16 wrongly classified as drums\n");return 18;
    }
    ta.drum_mode=TA_DRUM_ON;
    if(!ta_load(argv[7]) || !ta.drum16){
        fprintf(stderr,"DRUM ON override failed\n");return 19;
    }
    if(!on_count || !mute_count){fprintf(stderr,"PSG had no notes or mute\n");return 8;}
    printf("PASS: SMF0/1, auto/forced DRUM16, dense melody/bass, 34KB MIDI, 4th noise channel, note releases, subtick scheduler; %u PSG writes\n",on_count);
    return 0;
}

