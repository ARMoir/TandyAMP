/* Host-only deterministic MIDI engine test. Original code, MIT. */
#include "../src/midi.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned on_count=0, mute_count=0, max_simultaneous=0;
void ta_psg_tone(int slot,ta_u16 period,ta_u8 attenuation)
{
    unsigned active=0,i;
    if(slot<0||slot>2||period<1||period>1023||attenuation>15)abort();
    if(attenuation<15)on_count++;else mute_count++;
    for(i=0;i<3;i++)if(ta.voices[i].note>=0)active++;
    if(active>max_simultaneous)max_simultaneous=active;
}
void ta_psg_silence(void){mute_count++;}

int main(int argc,char **argv)
{
    unsigned n,i,live;
    if(argc<4)return 2;
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
    if(!on_count || !mute_count){fprintf(stderr,"PSG had no notes or mute\n");return 8;}
    printf("PASS: SMF0/SMF1, tempo, note-on/off, chord stealing, MIDI bounds; %u PSG writes\n",on_count);
    return 0;
}
