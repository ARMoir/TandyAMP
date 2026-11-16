/* Exercise the actual mixer with original events, including folded unisons. */
#include <assert.h>
#include <stdio.h>
#include "../src/midi.c"
static ta_u16 periods[3];
static ta_u8 levels[4]={15,15,15,15};
void ta_psg_tone(int s,ta_u16 p,ta_u8 a){periods[s]=p;levels[s]=a;}
void ta_psg_noise(ta_u8 m,ta_u8 a){(void)m;levels[3]=a;}
void ta_psg_noise_level(ta_u8 a){levels[3]=a;}
void ta_pc_speaker(ta_u16 divider){(void)divider;}
void ta_psg_silence(void){unsigned i;for(i=0;i<4;i++)levels[i]=15;}
static unsigned voices(void){unsigned i,n=0;for(i=0;i<3;i++)if(levels[i]<15)n++;return n;}
static void check_mix(void)
{
    unsigned i,j,sum=0;
    for(i=0;i<4;i++)sum+=power_level[levels[i]];
    assert(sum<=TA_MIX_POWER_CEILING);
    for(i=0;i<3;i++)for(j=i+1;j<3;j++)
        assert(levels[i]==15 || levels[j]==15 || periods[i]!=periods[j]);
}
int main(int argc,char **argv)
{
    unsigned old,i,baseline,boosted;
    /* The former 1024-power ceiling capped even ONE loud note below the
       hardware's max 4096 model. New ceiling lets solo velocity 127
       actually reach PSG attenuation 0 while limiting chord power. */
    clear_synth();ta.playing=1;
    on(0,72,127);flush_mix();
    assert(power_level[0]==4096U);
    assert(TA_MIX_POWER_CEILING>=4096U);
    assert(ta.mix_attenuation==0 && levels[0]==0);
    check_mix();
    /* A dense mix is still bounded. */
    on(1,64,127);on(2,55,127);flush_mix();
    check_mix();assert(ta.mix_attenuation>0);
    clear_synth();ta.playing=1;
    on(0,72,127);on(1,72,127);on(2,36,127);on(3,48,127);
    on(4,64,127);drum_on(9,38,127);flush_mix();
    assert(voices()==3);check_mix();assert(ta.mix_attenuation>0);
    /* Either doubled source can end; the other must remain available. */
    off(0,72);flush_mix();assert(voices()==3);check_mix();
    clear_synth();on(0,72,100);on(1,72,100);flush_mix();
    assert(voices()==1);
    ta.pitchbend[1]=4096;render_channel(1);flush_mix();
    assert(voices()==2);check_mix();
    ta.pitchbend[1]=0;render_channel(1);flush_mix();
    assert(voices()==1);check_mix();
    /* Master mute covers percussion and resume; stopped volume stays silent. */
    drum_on(9,38,127);flush_mix();ta_set_volume(0);
    for(i=0;i<4;i++)assert(levels[i]==15);
    ta_pause();ta_set_volume(15);
    for(i=0;i<4;i++)assert(levels[i]==15);
    ta_pause();check_mix();assert(voices()==1);
    /* Both supported drum routes reach the leveled noise output. */
    silence_noise();on(9,38,127);flush_mix();assert(levels[3]<15);
    silence_noise();ta.drum16=1;on(15,38,127);flush_mix();assert(levels[3]<15);
    ta_stop();ta_set_volume(15);
    for(i=0;i<4;i++)assert(levels[i]==15);
    /* Release cannot jump back to full volume on the next quiet event. */
    clear_synth();ta.playing=1;on(0,72,127);on(1,64,127);on(2,48,127);
    flush_mix();old=ta.mix_attenuation;assert(old>0);
    off(1,64);off(2,48);flush_mix();assert(ta.mix_attenuation==old);
    release_clock=1024;flush_mix();assert(ta.mix_attenuation==old-1);
    check_mix();
    /* A quiet single voice is not boosted by automatic leveling. */
    clear_synth();on(0,72,50);flush_mix();
    assert(ta.mix_attenuation==0);
    assert(levels[0]==attenuation(0,50));
    /* A user may request 16..20. These values reclaim otherwise unused
       attenuation rather than trying to program a non-existent PSG level
       beyond 0. The limiter remains active at every gain setting. */
    clear_synth();ta.playing=1;
    assert(ta_get_volume()==15);
    on(0,72,64);flush_mix();
    baseline=levels[0];check_mix();
    ta_set_volume(20);
    boosted=levels[0];
    assert(ta_get_volume()==20 && ta.master_boost==5);
    assert(boosted<baseline && boosted>=0);check_mix();
    ta_set_volume(100);
    assert(ta_get_volume()==20);check_mix();
    ta_set_volume(15);
    assert(ta_get_volume()==15 && ta.master_boost==0);
    /* A real MIDI "off" channel must never be made audible by boost. */
    ta_set_volume(20);
    handle_cc(0,7,0);flush_mix();
    assert(voices()==0);
    ta_set_volume(0);
    assert(ta_get_volume()==0 && ta.master_attenuation==15);
    for(i=0;i<4;i++)assert(levels[i]==15);
    ta_set_volume(15);
    /* Include noise in gain/limiter behavior as well. */
    clear_synth();ta.playing=1;
    ta_set_volume(20);
    on(0,72,127);on(1,64,127);on(2,55,127);
    drum_on(9,38,127);flush_mix();
    check_mix();
    ta_set_volume(15);
    check_mix();

    /* Optional user-owned MIDI: verify every scheduler slice, not just samples. */
    if(argc>1){
        assert(ta_load(argv[1]));ta_begin();
        for(i=0;i<30000U && ta.playing;i++){ta_advance(32);check_mix();}
        assert(!ta.playing);printf("Canyon completed in %u slices.\n",i);
    }
    puts("PASS: unisons, folded bass, bends, louder solo/20-step boost, 6144 mix ceiling, CC7 silence, mute, pause/stop");
    return 0;
}
