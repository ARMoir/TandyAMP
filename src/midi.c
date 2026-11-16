/* TandyAMP Standard MIDI File 0/1 player, 8086-class C89, MIT.
   File limits intentional: bounded memory and interrupt-free DOS I/O.
   No DOS calls occur from timer interrupts: foreground polls BIOS ticks. */
#include "midi.h"
#include <stdio.h>
#include <string.h>

TAEngine ta;
static const char *last_error="OK";

static ta_u16 rd16(ta_u16 p)
{
    return (ta_u16)(((ta_u16)ta.data[p]<<8)|ta.data[p+1]);
}
static ta_u32 rd32(ta_u16 p)
{
    return ((ta_u32)rd16(p)<<16) | rd16((ta_u16)(p+2));
}
static int within(ta_u32 p,ta_u32 n)
{
    return p<=ta.bytes && n<=ta.bytes-p;
}
static ta_u32 vlq(TATrack *t, int *valid)
{
    ta_u32 v=0;
    unsigned i; ta_u8 c=0;
    *valid=0;
    for(i=0;i<4;i++) {
        if(t->pos>=t->end) return 0;
        c=ta.data[t->pos++];
        v=(v<<7)|(c&127);
        if(!(c&128)){ *valid=1; return v; }
    }
    return 0;
}
static void next_delta(TATrack *t)
{
    int ok;
    ta_u32 delta;
    if(t->pos>=t->end){t->active=0;return;}
    delta=vlq(t,&ok);
    if(!ok || t->next_tick>0xffffffffUL-delta) {
        t->active=0;
        return;
    }
    t->next_tick+=delta;
}
static void set_step(void)
{
    ta_u32 ms=ta.tempo_us/1000UL;
    ta_u32 v;
    if(ms<1)ms=1;
    /* BIOS tick = ~54.925 ms. Q8 MIDI-ticks/timer-tick.
       Intermediate <= 32767 * 14055 < 2^32, 8086 safe. */
    v=((ta_u32)ta.division*14055UL)/ms;
    if(v<1)v=1;
    if(v>60000UL)v=60000UL;
    ta.step_q8=v;
}
static void clear_synth(void)
{
    unsigned c,v;
    ta.sequence=1;
    for(c=0;c<TA_CHANNELS;c++){
        ta.cc_volume[c]=127;
        ta.cc_expression[c]=127;
        ta.cc_sustain[c]=0;
        ta.pitchbend[c]=0;
    }
    for(v=0;v<TA_VOICES;v++){
        ta.voices[v].note=-1;
        ta.voices[v].held=0;
        ta.voices[v].sustained=0;
        ta.voices[v].level=15;
    }
    ta_psg_silence();
}
void ta_noteoff_all(void)
{
    clear_synth();
}
static void prepare_tracks(void)
{
    unsigned i;
    for(i=0;i<ta.track_count;i++){
        TATrack *t=&ta.tracks[i];
        t->pos=t->beginning;
        t->running=0;
        t->active=1;
        t->next_tick=0;
        next_delta(t);
    }
}
void ta_begin(void)
{
    if(!ta.loaded)return;
    clear_synth();
    ta.tempo_us=500000UL;
    set_step();
    ta.clock_q8=0;
    ta.playing=1;
    ta.paused=0;
    prepare_tracks();
}
void ta_stop(void)
{
    ta.playing=0;
    ta.paused=0;
    ta_psg_silence();
}
void ta_pause(void)
{
    if(!ta.playing)return;
    ta.paused=!ta.paused;
    if(ta.paused)ta_psg_silence();
    else {
        /* Restoring active notes is done by note_render_all below. */
        unsigned i;
        for(i=0;i<TA_VOICES;i++){
            TAVoice *v=&ta.voices[i];
            if(v->note>=0)render_voice(i);
        }
    }
}
/* MIDI note 0..127 to SN76489 divider at 3.579545 MHz / 32.
   Independently computed from equal-tempered frequencies.
   10-bit saturation for unrepresentable bass notes. */
static const ta_u16 note_period[128]={
1023,1023,1023,1023,1023,1023,1023,1023,1023,1023,1023,1023,
1023,1023,1023,1023,1023,1023,1023,1023,1023,1023,1023,1023,
1023,1023,1023,1023,1023,1023,1023,1023,1023,1023,1023,1023,
1023,1023,1023,1023,1023,1023,1023,1023,1023,1017,960,906,
855,807,762,719,679,641,605,571,539,508,480,453,
428,404,381,360,339,320,302,285,269,254,240,226,
214,202,190,180,170,160,151,143,135,127,120,113,
107,101,95,90,85,80,76,71,67,64,60,57,
53,50,48,45,42,40,38,36,34,32,30,28,
27,25,24,22,21,20,19,18,17,16,15,14,
13,13,12,11,11,10,9,9
};
static ta_u16 period_for(ta_u8 note, signed short bend)
{
    ta_u16 p=note_period[note];
    ta_u16 edge;
    ta_s32 result,d;
    if(bend>0)edge=note_period[note<125?note+2:127];
    else edge=note_period[note>1?note-2:0];
    d=(ta_s32)((signed short)edge-(signed short)p)*(ta_s32)(bend>=0?bend:-bend);
    result=(ta_s32)p + d/8192L;
    if(result<1L)result=1;
    if(result>1023L)result=1023;
    return (ta_u16)result;
}
static ta_u8 attenuation(ta_u8 chan,ta_u8 velocity)
{
    /* 0..127 velocity * channel volume * expression mapped to 16 PSG steps.
       32-bit intermediates avoid overflow on 16-bit targets. */
    ta_u32 a=(ta_u32)velocity*ta.cc_volume[chan]*ta.cc_expression[chan];
    ta_u32 level=(a*15UL+1024191UL)/2048383UL;
    if(level>15)level=15;
    return (ta_u8)(15-level);
}
static void render_voice(unsigned i);
static void render_voice(unsigned i)
{
    TAVoice *v=&ta.voices[i];
    if(v->note<0 || ta.paused) {
        ta_psg_tone(i,1,15);
    } else {
        ta_psg_tone(i,period_for((ta_u8)v->note,ta.pitchbend[v->channel]),
                    attenuation(v->channel,v->velocity));
    }
}
static void render_channel(ta_u8 channel)
{
    unsigned i;
    for(i=0;i<TA_VOICES;i++)
        if(ta.voices[i].note>=0 && ta.voices[i].channel==channel)
            render_voice(i);
}
static void off(ta_u8 channel,ta_u8 note)
{
    unsigned i;
    for(i=0;i<TA_VOICES;i++){
        TAVoice *v=&ta.voices[i];
        if(v->note==note && v->channel==channel && v->held){
            v->held=0;
            if(ta.cc_sustain[channel])v->sustained=1;
            else {
                v->note=-1;
                v->sustained=0;
                render_voice(i);
            }
        }
    }
}
static void on(ta_u8 channel,ta_u8 note,ta_u8 vel)
{
    unsigned i,slot=0;
    ta_u32 oldest=0xffffffffUL;
    if(vel==0){off(channel,note);return;}
    /* Prefer re-articulation, then an idle slot; otherwise steal oldest. */
    for(i=0;i<TA_VOICES;i++){
        if(ta.voices[i].note==note && ta.voices[i].channel==channel){
            slot=i;break;
        }
    }
    if(i==TA_VOICES){
        for(i=0;i<TA_VOICES;i++)if(ta.voices[i].note<0){slot=i;break;}
        if(i==TA_VOICES){
            for(i=0;i<TA_VOICES;i++)
                if(ta.voices[i].stamp<oldest){
                    oldest=ta.voices[i].stamp;
                    slot=i;
                }
        }
    }
    ta.voices[slot].note=note;
    ta.voices[slot].channel=channel;
    ta.voices[slot].velocity=vel;
    ta.voices[slot].held=1;
    ta.voices[slot].sustained=0;
    ta.voices[slot].stamp=ta.sequence++;
    render_voice(slot);
}
static void handle_cc(ta_u8 c,ta_u8 cc,ta_u8 val)
{
    unsigned i;
    if(cc==7){ta.cc_volume[c]=val;render_channel(c);}
    if(cc==11){ta.cc_expression[c]=val;render_channel(c);}
    if(cc==64){
        ta.cc_sustain[c]=(val>=64);
        if(val<64)for(i=0;i<TA_VOICES;i++){
            TAVoice *v=&ta.voices[i];
            if(v->note>=0 && v->channel==c && v->sustained && !v->held){
                v->note=-1;
                v->sustained=0;
                render_voice(i);
            }
        }
    }
    if(cc==120 || cc==123)for(i=0;i<TA_VOICES;i++)
        if(ta.voices[i].note>=0 && ta.voices[i].channel==c) {
            ta.voices[i].note=-1;render_voice(i);
        }
}
static void consume_event(TATrack *t)
{
    ta_u8 first,status,c,d1,d2,meta;
    ta_u32 count;
    int ok;
    if(t->pos>=t->end){t->active=0;return;}
    first=ta.data[t->pos];
    if(first&0x80){
        status=first;
        t->pos++;
        if(status>=0x80 && status<=0xef)t->running=status;
        else t->running=0;
    }else {
        status=t->running;
        if(status<0x80 || status>0xef){t->active=0;return;}
    }
    if(status==0xff){
        if(t->pos>=t->end){t->active=0;return;}
        meta=ta.data[t->pos++];
        count=vlq(t,&ok);
        if(!ok || count>t->end-t->pos){t->active=0;return;}
        if(meta==0x51 && count==3){
            ta.tempo_us=((ta_u32)ta.data[t->pos]<<16)
                       |((ta_u32)ta.data[t->pos+1]<<8)|ta.data[t->pos+2];
            if(ta.tempo_us<1000UL)ta.tempo_us=1000UL;
            set_step();
        }
        if(meta==0x2f){t->active=0;return;}
        t->pos=(ta_u16)(t->pos+count);
        next_delta(t);
        return;
    }
    if(status==0xf0 || status==0xf7){
        count=vlq(t,&ok);
        if(!ok || count>t->end-t->pos){t->active=0;return;}
        t->pos=(ta_u16)(t->pos+count);
        next_delta(t);
        return;
    }
    if(status<0x80 || status>=0xf0){t->active=0;return;}
    c=status&15;
    if(t->pos>=t->end){t->active=0;return;}
    d1=ta.data[t->pos++];
    if(status>=0xc0 && status<0xe0)d2=0;
    else {
        if(t->pos>=t->end){t->active=0;return;}
        d2=ta.data[t->pos++];
    }
    if(d1>127 || d2>127){t->active=0;return;}
    switch(status&0xf0){
    case 0x80: off(c,d1);break;
    case 0x90: on(c,d1,d2);break;
    case 0xb0: handle_cc(c,d1,d2);break;
    case 0xe0:
        ta.pitchbend[c]=(signed short)((((ta_u16)d2<<7)|d1)-8192);
        render_channel(c);
        break;
    default: break;
    }
    next_delta(t);
}
int ta_load(const char *filename)
{
    FILE *f;
    ta_u32 p,len,end,header_len;
    unsigned i;
    size_t n;
    ta.loaded=0;ta.playing=0;
    ta_psg_silence();
    f=fopen(filename,"rb");
    if(!f){last_error="Cannot open MIDI file";return 0;}
    n=fread(ta.data,1,TA_MAX_FILE+1U,f);
    fclose(f);
    if(n>TA_MAX_FILE){last_error="MIDI too large (28 KB limit)";return 0;}
    ta.bytes=(ta_u16)n;
    if(!within(0,14) || memcmp(ta.data,"MThd",4)!=0){
        last_error="Not a Standard MIDI File";return 0;
    }
    header_len=rd32(4);
    if(header_len<6 || header_len>64 || !within(8,header_len)){
        last_error="Invalid MIDI header";return 0;
    }
    ta.format=rd16(8);
    ta.track_count=rd16(10);
    ta.division=rd16(12);
    if(ta.format>1 || ta.track_count<1 || ta.track_count>TA_MAX_TRACKS){
        last_error="Use type 0/1 with at most 12 tracks";return 0;
    }
    if(!ta.division || (ta.division&0x8000)){
        last_error="SMPTE division not supported";return 0;
    }
    p=8+header_len;
    for(i=0;i<ta.track_count;i++){
        if(!within(p,8) || memcmp(ta.data+(ta_u16)p,"MTrk",4)!=0){
            last_error="Missing MIDI track header";return 0;
        }
        len=rd32((ta_u16)(p+4));
        end=p+8+len;
        if(end>ta.bytes){last_error="Truncated MIDI track";return 0;}
        ta.tracks[i].beginning=(ta_u16)(p+8);
        ta.tracks[i].end=(ta_u16)end;
        p=end;
    }
    last_error="OK";
    ta.loaded=1;
    ta.playing=0;
    return 1;
}
void ta_tick(void)
{
    unsigned i,remaining=384;
    int active;
    if(!ta.playing || ta.paused)return;
    ta.clock_q8+=ta.step_q8;
    /* Bound processing to protect 7 MHz CPUs from hostile/corrupt files. */
    do{
        active=0;
        for(i=0;i<ta.track_count && remaining;i++){
            TATrack *t=&ta.tracks[i];
            if(t->active && t->next_tick<=(ta.clock_q8>>8)){
                consume_event(t);
                remaining--;
                active=1;
            }
        }
    }while(active && remaining);
    active=0;
    for(i=0;i<ta.track_count;i++)if(ta.tracks[i].active)active=1;
    if(!active)ta_stop();
}
ta_u32 ta_elapsed_seconds(void)
{
    /* Approximate MIDI time at the current tempo; GUI uses BIOS ticks. */
    ta_u32 quarters=(ta.clock_q8>>8)/(ta.division?ta.division:96);
    return (quarters*(ta.tempo_us/1000UL))/1000UL;
}
const char *ta_error(void){return last_error;}
