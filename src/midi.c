/* TandyAMP Standard MIDI File 0/1 player, 8086-class C89, MIT.
   File limits intentional: bounded memory and interrupt-free DOS I/O.
   No DOS calls occur from timer interrupts: foreground polls BIOS ticks. */
#include "midi.h"
#include <stdio.h>
#include <string.h>

TAEngine ta;
static void render_voice(unsigned i);
static void rebuild_voices(void);
static void silence_noise(void);
static const char *last_error="OK";
static ta_u8 synth_dirty=0, controllers_dirty=0;
static ta_u16 output_period[TA_VOICES];
static ta_u16 speaker_output=0;
static ta_u16 release_clock=0;
static ta_u16 envelope_clock=0, vibrato_clock=0;
static ta_u8 vibrato_phase=0;
/* One original 8-step, zero-centered triangle, no run-time sin/floating point. */
static const signed char vibrato_curve[8]={0,1,2,1,0,-1,-2,-1};
static ta_u8 noise_output=15, noise_trigger=0, mix_dirty=0;
static void flush_mix(void);
/* Approximate power at the PSG's 2 dB attenuation steps, no float on DOS. */
static const ta_u16 power_level[16]={
    4096,2584,1631,1029,649,410,258,163,103,65,41,26,16,10,6,0
};
/* Previous mixer target 1024 was quieter than even ONE full-level note
   (power 4096), imposing at least 8 dB attenuation at any loudness.
   Target 6144 = 1.5 full-power channels: one loud note reaches PSG
   attenuation 0; multiple loud voices still get bounded sum limiting.
   This is a modeled *relative* level, not calibrated acoustic output. */
#define TA_MIX_POWER_CEILING 6144U
#define TA_MAX_VOLUME 20U
#define TA_UNBOOSTED_VOLUME 15U
/* Preserve genuine silence: raw 15 is the PSG's mute code and MUST NOT
   be revived by software boost. Likewise master volume 0 stays silent. */
static ta_u8 effective_atten(ta_u8 raw,unsigned mix)
{
    unsigned out;
    if(raw>=15U || ta.master_attenuation>=15U)return 15;
    out=(unsigned)raw+mix+ta.master_attenuation;
    if(out<=ta.master_boost)return 0;
    out-=ta.master_boost;
    return (ta_u8)(out>15U?15U:out);
}

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
    synth_dirty=controllers_dirty=0;
    ta.mix_attenuation=0;
    release_clock=0;
    envelope_clock=vibrato_clock=0;
    vibrato_phase=0;
    noise_output=15;noise_trigger=0;
    mix_dirty=0;
    for(c=0;c<TA_CHANNELS;c++){
        ta.cc_volume[c]=127;
        ta.cc_expression[c]=127;
        ta.cc_sustain[c]=0;
        ta.cc_program[c]=255; /* No explicit program change => neutral. */
        ta.cc_modulation[c]=0;
        ta.pitchbend[c]=0;
    }
    for(v=0;v<TA_ACTIVE_NOTES;v++)ta.notes[v].note=-1;
    for(v=0;v<TA_VOICES;v++){
        ta.voices[v].source=-1;
        ta.voices[v].note=-1;
        ta.voices[v].held=0;
        ta.voices[v].sustained=0;
        ta.voices[v].level=15;
        output_period[v]=0;
    }
    ta.speaker_voice.source=-1;
    ta.speaker_voice.note=-1;
    ta.speaker_voice.level=15;
    ta_pc_speaker(0);
    speaker_output=0;
    ta.speaker_divider=0;
    ta.noise_left=0;
    ta.noise_length=0;
    ta.noise_last=15;
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
    ta.clock_carry=0;
    ta.playing=1;
    ta.paused=0;
    prepare_tracks();
}
void ta_stop(void)
{
    ta.playing=0;
    ta.paused=0;
    silence_noise();
    ta_pc_speaker(0);
    speaker_output=0;
    ta.speaker_divider=0;
    ta_psg_silence();
}
void ta_pause(void)
{
    if(!ta.playing)return;
    ta.paused=!ta.paused;
    if(ta.paused){
        unsigned i;
        ta_psg_silence();
        ta_pc_speaker(0);
        speaker_output=0;
        ta.speaker_divider=0;
        for(i=0;i<TA_VOICES;i++)ta.voices[i].level=15;
        noise_output=15;
    }
    else {
        /* Restoring active notes is done by note_render_all below. */
        unsigned i;
        for(i=0;i<TA_VOICES;i++){
            TAVoice *v=&ta.voices[i];
            if(v->note>=0)render_voice(i);
        }
        if(ta.noise_left){noise_trigger=1;flush_mix();}
        if(ta.speaker_enabled){controllers_dirty=1;flush_mix();}
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
    ta_u16 p,edge;
    ta_s32 result,d;
    /* Hardware cannot make pitches below ~109 Hz. Fold bass up octaves
       instead of rendering all low notes as one indistinct 109 Hz buzz. */
    while(note<45)note=(ta_u8)(note+12);
    p=note_period[note];
    if(bend>0)edge=note_period[note<125?note+2:127];
    else edge=note_period[note>1?note-2:0];
    d=(ta_s32)((signed short)edge-(signed short)p)*(ta_s32)(bend>=0?bend:-bend);
    result=(ta_s32)p + d/8192L;
    if(result<1L)result=1;
    if(result>1023L)result=1023;
    return (ta_u16)result;
}
/* Program numbers are zero-based GM. Without a program change preserve
   the older plain PSG sound; otherwise use a modest instrument profile. */
static ta_u8 style_for_program(ta_u8 program)
{
    if(program<=15 || (program>=24 && program<=31))return 1; /* keys/plucks */
    if((program>=16 && program<=23) ||
       (program>=32 && program<=47) ||
       (program>=104 && program<=111))return 2; /* soft wind/bass/ethnic */
    return 0; /* organ, strings, brass, pads or unknown -> sustained */
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
static void render_voice(unsigned i)
{
    TAVoice *v=&ta.voices[i];
    ta_u16 p=1;
    unsigned a=15;
    if(v->note>=0 && !ta.paused){
        p=ta.notes[v->source].period;
        if(ta.cc_modulation[v->channel]){
            ta_s32 change=(ta_s32)p*ta.cc_modulation[v->channel]*
                vibrato_curve[vibrato_phase]/32768L;
            ta_s32 shifted=(ta_s32)p+change;
            if(shifted<1)shifted=1;
            if(shifted>1023)shifted=1023;
            p=(ta_u16)shifted;
        }
        a=effective_atten(ta.notes[v->source].attenuation,
                          ta.mix_attenuation);
    }
    if(v->level!=a || (a<15 && output_period[i]!=p)){
        ta_psg_tone(i,p,(ta_u8)a);
        v->level=(ta_u8)a;output_period[i]=p;
    }
}
/* Keep independent note-on state even when the three hardware channels
   are full. A stolen held note can resume when a channel becomes free. */
static ta_s32 note_priority(const TAActiveNote *n)
{
    ta_s32 score;
    if(n->note<0)return -100000L;
    score=(n->held?1000L:200L)+(ta_s32)n->gain*3L;
    if(n->note>=60 && n->note<=96)score+=180L;
    if(n->note>=44 && n->note<60)score+=70L;
    if(n->note<36 || n->note>104)score-=90L;
    if(n->channel==0)score+=30L;
    score-=(ta_s32)n->env_step*12L; /* Prefer still-prominent parts. */
    return score;
}
/* Standard 1.193182MHz PIT channel 2 versus 3.579545MHz PSG/32.
   A 10-bit PSG period converts to approximately period*32/3. */
/* PIT2 plays the *real*, unfolded low bass: MIDI 24..52 (C1..E3).
   Calculated independently from 1193182 Hz / equal-tempered frequency.
   Endpoints 22..54 support the standard +/-2 semitone pitch bend. */
#define TA_SPK_BASS_MIN 24
#define TA_SPK_BASS_MAX 52
static const ta_u16 pit_bass_dividers[33]={
    40953,38655,36485,34437,32505,30680,28958,27333,25799,
    24351,22984,21694,20477,19327,18243,17219,16252,15340,
    14479,13667,12899,12175,11492,10847,10238,9664,9121,
    8609,8126,7670,7240,6833,6450
};
static ta_u16 speaker_divider_for(ta_u8 note,signed short bend)
{
    ta_s32 base,edge,value;
    unsigned n;
    ta_u16 mag;
    if(note<TA_SPK_BASS_MIN || note>TA_SPK_BASS_MAX)return 0;
    n=(unsigned)note-22U;
    mag=(ta_u16)(bend<0?-(ta_s32)bend:bend);
    base=pit_bass_dividers[n];
    edge=pit_bass_dividers[(bend>=0)?n+2U:n-2U];
    value=base+((edge-base)*(ta_s32)mag)/8192L;
    if(value<18L)value=18L;
    if(value>65535L)value=65535L;
    return (ta_u16)value;
}
static int speaker_note_audible(const TAActiveNote *n)
{
    unsigned attenuation=(unsigned)n->attenuation+
        ta.mix_attenuation+ta.master_attenuation;
    return n->note>=TA_SPK_BASS_MIN && n->note<=TA_SPK_BASS_MAX &&
           attenuation<=8U;
}
/* Reserve a low-bass note only if THREE OTHER distinct playable PSG
   pitches exist. Otherwise leave normal three-tone playback untouched.
   This also ensures SPK4 is never handed a high melody overflow. */
static signed short choose_speaker_bass(void)
{
    unsigned i,j,k;
    signed short best=-1;
    ta_s32 best_score=-200000L;
    if(!ta.speaker_enabled || !ta.playing || ta.paused)return -1;
    for(i=0;i<TA_ACTIVE_NOTES;i++){
        TAActiveNote *n=&ta.notes[i];
        ta_u16 distinct[3];
        unsigned count=0;
        ta_s32 score;
        if(!speaker_note_audible(n))continue;
        for(j=0;j<TA_ACTIVE_NOTES && count<3;j++){
            TAActiveNote *other=&ta.notes[j];
            int duplicate=0;
            if(i==j || other->note<0 || other->attenuation>=15 ||
               other->note==n->note)continue;
            for(k=0;k<count;k++)
                if(distinct[k]==other->period)duplicate=1;
            if(!duplicate)distinct[count++]=other->period;
        }
        if(count<3)continue;
        score=(ta_s32)(TA_SPK_BASS_MAX-n->note)*1000L+
              note_priority(n)/4L;
        if(ta.speaker_voice.source==(signed short)i)score+=300L;
        if(score>best_score){
            best_score=score;
            best=(signed short)i;
        }
    }
    return best;
}
static void render_speaker(void)
{
    TAVoice *v=&ta.speaker_voice;
    ta_u16 divisor=0;
    if(ta.speaker_enabled && ta.playing && !ta.paused &&
       v->source>=0 && v->note>=0){
        TAActiveNote *n=&ta.notes[v->source];
        unsigned att=(unsigned)n->attenuation+
            ta.mix_attenuation+ta.master_attenuation;
        /* No volume register on PIT2. Don't let quiet notes sound loud:
           gate the fourth voice out when software attenuation is high. */
        if(speaker_note_audible(n) && att<=8U)
            divisor=speaker_divider_for((ta_u8)n->note,
                                        ta.pitchbend[n->channel]);
    }
    if(divisor!=speaker_output){
        ta_pc_speaker(divisor);
        speaker_output=divisor;
    }
    /* This is actual programmed PIT2 output, not just SPK4 enabled.
       The UI must never show activity simply because /SPK4 was set. */
    ta.speaker_divider=divisor;
}
void ta_set_speaker(unsigned enabled)
{
    ta.speaker_enabled=(ta_u8)(enabled!=0U);
    if(!ta.speaker_enabled){
        ta.speaker_voice.source=-1;
        ta.speaker_voice.note=-1;
        if(speaker_output){
            ta_pc_speaker(0);
            speaker_output=0;
        }
        ta.speaker_divider=0;
    }
    synth_dirty=controllers_dirty=1;
    if(ta.playing && !ta.paused)flush_mix();
}
static void rebuild_voices(void)
{
    signed short selected[TA_VOICES];
    unsigned k,i,j;
    ta_s32 best,score;
    int found,already;
    /* Decide bass before three-PSG allocation so a real bass note
       can occupy PIT2, leaving PSG voices for melody and harmony. */
    {
        signed short bass=choose_speaker_bass();
        ta.speaker_voice.source=bass;
        if(bass>=0){
            TAActiveNote *n=&ta.notes[bass];
            ta.speaker_voice.note=n->note;
            ta.speaker_voice.channel=n->channel;
            ta.speaker_voice.velocity=n->velocity;
            ta.speaker_voice.held=n->held;
            ta.speaker_voice.sustained=n->sustained;
            ta.speaker_voice.stamp=n->stamp;
        }else ta.speaker_voice.note=-1;
    }
    for(k=0;k<TA_VOICES;k++){
        best=-200000L;
        found=-1;
        for(i=0;i<TA_ACTIVE_NOTES;i++){
            TAActiveNote *n=&ta.notes[i];
            if(n->note<0)continue;
            if(n->attenuation==15)continue;
            if(ta.speaker_voice.source>=0 &&
               n->note==ta.speaker_voice.note)continue;
            already=0;
            for(j=0;j<k;j++)if(selected[j]>=0 &&
                ta.notes[selected[j]].period==n->period)already=1;
            if(already)continue;
            score=note_priority(n);
            /* Reserve the first voice for the tune, next for available bass.
               This keeps long chords from replacing the audible melody. */
            if(k==0 && n->note>=60 && n->note<=96)score+=5000L;
            if(k==1 && selected[0]>=0 &&
               ta.notes[selected[0]].note>=60 && n->note<60)score+=5000L;
            for(j=0;j<k;j++)if(selected[j]>=0 &&
                ta.notes[selected[j]].channel==n->channel)score-=100L;
            for(j=0;j<TA_VOICES;j++)
                if(ta.voices[j].source==(signed short)i)score+=110L; /* voice-leading hysteresis */
            if(score>best || (score==best && found>=0 &&
                n->stamp>ta.notes[found].stamp)){
                best=score;
                found=(int)i;
            }
        }
        selected[k]=(signed short)found;
    }
    /* Mute only evicted physical slots, not all three on every note. */
    for(i=0;i<TA_VOICES;i++){
        already=0;
        for(k=0;k<TA_VOICES;k++)
            if(selected[k]>=0 && selected[k]==ta.voices[i].source)already=1;
        if(!already && ta.voices[i].source>=0){
            ta.voices[i].source=-1;
            ta.voices[i].note=-1;
        }
    }
    for(k=0;k<TA_VOICES;k++){
        TAActiveNote *n;
        TAVoice *v;
        if(selected[k]<0)continue;
        for(i=0;i<TA_VOICES;i++)if(ta.voices[i].source==selected[k])break;
        if(i==TA_VOICES)
            for(i=0;i<TA_VOICES;i++)if(ta.voices[i].source<0)break;
        if(i==TA_VOICES)continue;
        n=&ta.notes[selected[k]];
        v=&ta.voices[i];
        if(v->source!=selected[k] || v->note!=n->note ||
           v->velocity!=n->velocity || v->channel!=n->channel){
            v->source=selected[k];
            v->note=n->note;
            v->channel=n->channel;
            v->velocity=n->velocity;
            v->held=n->held;
            v->sustained=n->sustained;
            v->stamp=n->stamp;
        }else{
            v->held=n->held;
            v->sustained=n->sustained;
        }
    }
}
/* Apply one common reduction to tones AND percussion before any new sound
   reaches the PSG. Fast attack, one 2 dB release step per ~220 ms. Never boost
   quiet passages; preserve relative voice levels and avoid rapid pumping. */
static void flush_mix(void)
{
    unsigned i,g,sum,a;
    ta_u8 raw[4];
    if(!synth_dirty && !controllers_dirty && !mix_dirty &&
       !noise_trigger && release_clock<1024U)return;
    if(synth_dirty)rebuild_voices();
    synth_dirty=controllers_dirty=0;
    mix_dirty=0;
    for(i=0;i<TA_VOICES;i++)
        raw[i]=ta.voices[i].note<0?15:
            ta.notes[ta.voices[i].source].attenuation;
    raw[3]=ta.noise_left?ta.noise_last:15;
    for(g=0;g<15;g++){
        sum=0;
        for(i=0;i<4;i++){
            a=effective_atten(raw[i],g);
            sum+=power_level[a];
        }
        if(sum<=TA_MIX_POWER_CEILING)break;
    }
    if(g>=ta.mix_attenuation){
        ta.mix_attenuation=(ta_u8)g;release_clock=0;
    }else if(release_clock>=1024U){
        ta.mix_attenuation--;release_clock=0;
    }
    for(i=0;i<TA_VOICES;i++)render_voice(i);
    render_speaker();
    a=effective_atten(raw[3],ta.mix_attenuation);
    if(ta.paused)a=15;
    if(noise_trigger && ta.noise_left && !ta.paused)
        ta_psg_noise(ta.noise_mode,(ta_u8)a);
    else if(noise_output!=a)ta_psg_noise_level((ta_u8)a);
    noise_output=(ta_u8)a;noise_trigger=0;
}
unsigned ta_get_volume(void)
{
    return TA_UNBOOSTED_VOLUME-ta.master_attenuation+ta.master_boost;
}
void ta_set_volume(unsigned volume)
{
    if(volume>TA_MAX_VOLUME)volume=TA_MAX_VOLUME;
    if(volume<=TA_UNBOOSTED_VOLUME){
        ta.master_attenuation=(ta_u8)(TA_UNBOOSTED_VOLUME-volume);
        ta.master_boost=0;
    }else{
        ta.master_attenuation=0;
        ta.master_boost=(ta_u8)(volume-TA_UNBOOSTED_VOLUME);
    }
    if(!ta.playing || ta.paused)return;
    /* Re-evaluate limiter and fourth-bass eligibility. A boosted voice
       still cannot exceed the PSG's actual maximum register level. */
    synth_dirty=controllers_dirty=1;
    flush_mix();
}
static void silence_noise(void)
{
    ta.noise_left=0;
    ta.noise_last=15;
    mix_dirty=1;
    noise_trigger=0;
    if(noise_output!=15)ta_psg_noise_level(15);
    noise_output=15;
}
/* SN76489 independent fourth (noise) channel: drums do not consume tones. */
static void drum_on(ta_u8 channel,ta_u8 note,ta_u8 velocity)
{
    ta_u8 mode=5;
    ta_u16 life=620;
    switch(note){
    case 35:case 36:mode=2;life=900;break; /* bass drum */
    case 38:case 40:mode=5;life=720;break; /* snare */
    case 42:case 44:mode=4;life=240;break; /* closed hat */
    case 46:mode=4;life=550;break;         /* open hat */
    case 49:case 51:case 57:mode=4;life=1300;break; /* cymbals */
    case 41:case 43:case 45:case 47:case 48:case 50:
        mode=1;life=800;break; /* toms */
    default:mode=5;life=520;break;
    }
    ta.noise_mode=mode;
    ta.noise_length=life;
    ta.noise_left=life;
    ta.noise_base=attenuation(channel,velocity);
    ta.noise_last=ta.noise_base;
    noise_trigger=1;
}
static void update_noise(ta_u16 elapsed_q8)
{
    ta_u32 step;
    ta_u8 volume;
    if(!ta.noise_left)return;
    if(elapsed_q8>=ta.noise_left){
        silence_noise();
        return;
    }
    ta.noise_left=(ta_u16)(ta.noise_left-elapsed_q8);
    step=((ta_u32)(ta.noise_length-ta.noise_left)*9UL)/ta.noise_length;
    volume=(ta_u8)(ta.noise_base+step);
    if(volume>15)volume=15;
    if(volume!=ta.noise_last){
        ta.noise_last=volume;
        mix_dirty=1;
    }
}
/* Update tone shapes at most every 128 sub-ticks (~27.5ms).  The V20
   never evaluates any full PCM or general MIDI oscillator envelopes.
   A plucked/keyboard note loses one PSG attenuation step every ~110ms
   (at most six); a softer voice fades at ~330ms (up to two steps).
   Sustained or unspecified instruments retain the original note level.
   Note-off stays immediate: no lingering tail or stuck-note hazard. */
static void update_tone_effects(ta_u16 elapsed_q8)
{
    unsigned i,step,add,changed=0;
    TAActiveNote *n;
    envelope_clock=(ta_u16)(envelope_clock+elapsed_q8);
    if(envelope_clock>=128U){
        add=(unsigned)(envelope_clock&(~127U));
        envelope_clock=(ta_u16)(envelope_clock&127U);
        for(i=0;i<TA_ACTIVE_NOTES;i++){
            n=&ta.notes[i];
            if(n->note<0 || n->style==0)continue;
            if(n->age_q8<8192U){
                unsigned age=n->age_q8+add;
                n->age_q8=(ta_u16)(age>8192U?8192U:age);
            }
            if(n->style==1){
                step=n->age_q8/512U;
                if(step>6U)step=6U;
            }else{
                step=n->age_q8/1536U;
                if(step>2U)step=2U;
            }
            if(step!=n->env_step){
                unsigned a=(unsigned)attenuation(n->channel,n->velocity)+step;
                if(a>15U)a=15U;
                n->env_step=(ta_u8)step;
                n->attenuation=(ta_u8)a;
                changed=1;
            }
        }
        if(changed)synth_dirty=1;
    }
    /* Only a MIDI modulation command enables vibrato. A four-cycle
       triangle at ~5 Hz changes a handful of divider bits, never a
       global note-pool reallocation. */
    vibrato_clock=(ta_u16)(vibrato_clock+elapsed_q8);
    if(vibrato_clock>=120U){
        vibrato_clock=(ta_u16)(vibrato_clock%120U);
        vibrato_phase=(ta_u8)((vibrato_phase+1U)&7U);
        for(i=0;i<TA_VOICES;i++){
            TAVoice *v=&ta.voices[i];
            if(v->note>=0 && ta.cc_modulation[v->channel]){
                controllers_dirty=1;
                break;
            }
        }
    }
}
static void render_channel(ta_u8 channel)
{
    unsigned i;
    for(i=0;i<TA_ACTIVE_NOTES;i++){
        TAActiveNote *n=&ta.notes[i];
        if(n->note<0 || n->channel!=channel)continue;
        n->gain=(ta_u8)((ta_u32)n->velocity*ta.cc_volume[channel]
                       *ta.cc_expression[channel]/16129UL);
        {
            unsigned a=(unsigned)attenuation(channel,n->velocity)+n->env_step;
            n->attenuation=(ta_u8)(a>15U?15U:a);
        }
        n->period=period_for((ta_u8)n->note,ta.pitchbend[channel]);
    }
    synth_dirty=controllers_dirty=1;
}
static void off(ta_u8 channel,ta_u8 note)
{
    unsigned i;
    if(channel==9 || (channel==15 && ta.drum16))return;
    for(i=0;i<TA_ACTIVE_NOTES;i++){
        TAActiveNote *n=&ta.notes[i];
        if(n->note==note && n->channel==channel && n->held){
            n->held=0;
            if(ta.cc_sustain[channel])n->sustained=1;
            else {n->note=-1;n->sustained=0;}
        }
    }
    synth_dirty=1;
}
static void on(ta_u8 channel,ta_u8 note,ta_u8 vel)
{
    unsigned i,slot=0;
    ta_s32 worst=200000L,score;
    if(vel==0){off(channel,note);return;}
    if(channel==9 || (channel==15 && ta.drum16)){
        drum_on(channel,note,vel);
        return;
    }
    /* Rearticulate same note; then find an unused pool entry. */
    for(i=0;i<TA_ACTIVE_NOTES;i++)
        if(ta.notes[i].note==note && ta.notes[i].channel==channel)break;
    if(i==TA_ACTIVE_NOTES)
        for(i=0;i<TA_ACTIVE_NOTES;i++)if(ta.notes[i].note<0)break;
    if(i==TA_ACTIVE_NOTES){
        for(i=0;i<TA_ACTIVE_NOTES;i++){
            score=note_priority(&ta.notes[i]);
            if(score<worst || (score==worst &&
               ta.notes[i].stamp<ta.notes[slot].stamp)){
                worst=score;slot=i;
            }
        }
        i=slot;
    }
    ta.notes[i].note=note;
    ta.notes[i].channel=channel;
    ta.notes[i].velocity=vel;
    ta.notes[i].gain=(ta_u8)((ta_u32)vel*ta.cc_volume[channel]
                           *ta.cc_expression[channel]/16129UL);
    ta.notes[i].attenuation=attenuation(channel,vel);
    ta.notes[i].style=style_for_program(ta.cc_program[channel]);
    ta.notes[i].env_step=0;
    ta.notes[i].age_q8=0;
    ta.notes[i].period=period_for(note,ta.pitchbend[channel]);
    ta.notes[i].held=1;
    ta.notes[i].sustained=0;
    ta.notes[i].stamp=ta.sequence++;
    synth_dirty=1;
}
static void handle_cc(ta_u8 c,ta_u8 cc,ta_u8 val)
{
    unsigned i;
    if(cc==1){ta.cc_modulation[c]=val;controllers_dirty=1;}
    if(cc==7){ta.cc_volume[c]=val;render_channel(c);}
    if(cc==11){ta.cc_expression[c]=val;render_channel(c);}
    if(cc==64){
        ta.cc_sustain[c]=(val>=64);
        if(val<64)for(i=0;i<TA_ACTIVE_NOTES;i++){
            TAActiveNote *n=&ta.notes[i];
            if(n->note>=0 && n->channel==c && n->sustained && !n->held)
                n->note=-1;
        }
        synth_dirty=1;
    }
    if(cc==120 || cc==123){
        for(i=0;i<TA_ACTIVE_NOTES;i++)
            if(ta.notes[i].note>=0 && ta.notes[i].channel==c)
                ta.notes[i].note=-1;
        synth_dirty=1;
        if(c==9 || (c==15 && ta.drum16))silence_noise();
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
    case 0xc0: ta.cc_program[c]=d1;break;
    case 0xe0:
        ta.pitchbend[c]=(signed short)((((ta_u16)d2<<7)|d1)-8192);
        render_channel(c);
        break;
    default: break;
    }
    next_delta(t);
}

/* Inspect complete MIDI track data without altering playback cursors.
   A legacy non-GM file may use channel 16 for drums, but a drum-like pitch
   number alone is insufficient evidence: require repeated kick/snare + hats. */
static ta_u8 detect_drum16(void)
{
    unsigned i,total=0,known=0,bass=0,hats=0,channel10=0;
    for(i=0;i<ta.track_count;i++){
        TATrack t=ta.tracks[i];
        int ok;
        ta_u8 status,b,kind,channel,d1,d2;
        ta_u32 len;
        t.pos=t.beginning;
        t.running=0;
        while(t.pos<t.end){
            (void)vlq(&t,&ok);
            if(!ok || t.pos>=t.end)break;
            b=ta.data[t.pos];
            if(b&128){
                status=b;
                t.pos++;
                if(status>=0x80 && status<=0xef)t.running=status;
                else t.running=0;
            }else{
                status=t.running;
                if(status<0x80 || status>0xef)break;
            }
            if(status==0xff){
                if(t.pos>=t.end)break;
                t.pos++;
                len=vlq(&t,&ok);
                if(!ok || len>(ta_u32)(t.end-t.pos))break;
                t.pos=(ta_u16)(t.pos+len);
                continue;
            }
            if(status==0xf0 || status==0xf7){
                len=vlq(&t,&ok);
                if(!ok || len>(ta_u32)(t.end-t.pos))break;
                t.pos=(ta_u16)(t.pos+len);
                continue;
            }
            if(status<0x80 || status>=0xf0 || t.pos>=t.end)break;
            channel=(ta_u8)(status&15);
            kind=(ta_u8)(status&0xf0);
            d1=ta.data[t.pos++];
            d2=0;
            if(kind!=0xc0 && kind!=0xd0){
                if(t.pos>=t.end)break;
                d2=ta.data[t.pos++];
            }
            if(d1>127 || d2>127)break;
            if(kind!=0x90 || d2==0)continue;
            if(channel==9){if(channel10<65535U)channel10++;continue;}
            if(channel!=15)continue;
            if(total<65535U)total++;
            switch(d1){
            case 35:case 36:case 38:case 40:
                bass++;known++;break;
            case 42:case 44:case 46:
                hats++;known++;break;
            case 41:case 43:case 45:case 47:case 48:case 49:
            case 50:case 51:case 57:
                known++;break;
            default:break;
            }
        }
    }
    /* Prefer a false negative (user can press D) to wrecking a melody. */
    return (ta_u8)(channel10==0 && total>=6 && known*4UL>=total*3UL
                   && bass>=2 && hats>=2);
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
    n=fread(ta.data,1,TA_MAX_FILE,f);
    if(n==TA_MAX_FILE && fgetc(f)!=EOF){
        fclose(f);
        last_error="MIDI too large (44 KB limit)";
        return 0;
    }
    fclose(f);
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
        last_error="Use type 0/1 with at most 24 tracks";return 0;
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
    ta.drum_detected=detect_drum16();
    ta.drum16=(ta_u8)(ta.drum_mode==TA_DRUM_ON ||
       (ta.drum_mode==TA_DRUM_AUTO && ta.drum_detected));
    last_error="OK";
    ta.loaded=1;
    ta.playing=0;
    return 1;
}
void ta_advance(ta_u16 elapsed_q8)
{
    unsigned i;
    int active,found;
    ta_u32 motion,next,group=0;
    if(!ta.playing || ta.paused || !elapsed_q8)return;
    if(release_clock<1024U){
        if(elapsed_q8>=1024U-release_clock)release_clock=1024U;
        else release_clock=(ta_u16)(release_clock+elapsed_q8);
    }
    update_noise(elapsed_q8);
    update_tone_effects(elapsed_q8);
    /* Q8 MIDI time, with another Q8 carry for sub-BIOS-tick scheduling. */
    motion=ta.step_q8*(ta_u32)elapsed_q8+ta.clock_carry;
    ta.clock_q8+=motion>>8;
    ta.clock_carry=(ta_u16)(motion&255UL);
    /* Merge tracks by absolute event time, not track index. All events at
       one timestamp update the note pool before choosing hardware voices.
       Input is bounded by TA_MAX_FILE; every event advances or ends a track. */
    for(;;){
        found=-1;
        next=0xffffffffUL;
        for(i=0;i<ta.track_count;i++){
            if(ta.tracks[i].active && ta.tracks[i].next_tick<=next){
                if(found<0 || ta.tracks[i].next_tick<next){
                    next=ta.tracks[i].next_tick;
                    found=(int)i;
                }
            }
        }
        if(found<0 || next>(ta.clock_q8>>8))break;
        if(next!=group){
            flush_mix();
            group=next;
        }
        consume_event(&ta.tracks[found]);
    }
    flush_mix();
    active=0;
    for(i=0;i<ta.track_count;i++)if(ta.tracks[i].active)active=1;
    if(!active)ta_stop();
}
void ta_tick(void)
{
    ta_advance(256U);
}
ta_u32 ta_elapsed_seconds(void)
{
    /* Approximate MIDI time at the current tempo; GUI uses BIOS ticks. */
    ta_u32 quarters=(ta.clock_q8>>8)/(ta.division?ta.division:96);
    return (quarters*(ta.tempo_us/1000UL))/1000UL;
}
const char *ta_error(void){return last_error;}

