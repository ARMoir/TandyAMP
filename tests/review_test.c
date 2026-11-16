/* Regressions found while reviewing the features added after build 29. */
#include <assert.h>
#include <stdio.h>
#include "../src/midi.c"
static ta_u8 levels[4]={15,15,15,15};
static ta_u16 pit=0;
void ta_psg_tone(int s,ta_u16 p,ta_u8 a){assert(p>0 && p<=1023);levels[s]=a;}
void ta_psg_noise(ta_u8 m,ta_u8 a){assert(m<=7);levels[3]=a;}
void ta_psg_noise_level(ta_u8 a){levels[3]=a;}
void ta_psg_silence(void){unsigned i;for(i=0;i<4;i++)levels[i]=15;}
void ta_pc_speaker(ta_u16 d){pit=d;}
static unsigned power(void)
{
    unsigned i,total=0;
    for(i=0;i<4;i++){assert(levels[i]<=15);total+=power_level[levels[i]];}
    return total;
}
static void chord(void)
{
    clear_synth();ta.playing=1;ta.paused=0;
    on(0,72,127);on(1,64,127);on(2,55,127);on(3,36,127);
    flush_mix();
}
int main(int argc,char **argv)
{
    unsigned mode,vol,soft,i;
    ta_set_volume(5);chord();assert(ta.mix_attenuation==0);
    ta_pause();ta_set_volume(20);assert(power()==0);
    ta_pause();assert(power()<=TA_MIX_POWER_CEILING);
    assert(power()>0); /* Do not solve the resume bug by leaving it muted. */
    ta_set_volume(15);ta_set_speaker(TA_SPK_BASS);chord();assert(pit);
    assert(!ta_load("tests/no-such-song.mid"));
    assert(!pit && !ta.speaker_divider && !ta.playing && !ta.loaded);
    assert(power()==0);
    chord();assert(pit);
    assert(!ta_load("tests/overflow.mid"));assert(!pit && power()==0);
    ta_set_speaker(TA_SPK_OFF);chord();
    for(i=0;i<TA_VOICES;i++)ta.voices[i].level=0;
    ta.voices[0].note=24; /* PSG folds C1 to C3, matching raised C2. */
    assert(choose_adaptive_octave(36)==0);
    /* Limiter attenuation must not strand a bass reserved for muted PIT2. */
    clear_synth();ta.playing=1;ta_set_speaker(TA_SPK_BASS);
    on(0,72,127);on(1,64,127);on(2,60,127);on(3,36,68);
    flush_mix();assert(!pit);
    for(i=0;i<TA_VOICES;i++)if(ta.voices[i].note==36)break;
    assert(i<TA_VOICES && levels[i]<15);
    assert(power()<=TA_MIX_POWER_CEILING);
    /* Entire supplied MIDI at normal/boost volume and each speaker/treble mode.
       This checks actual output budget, clean completion, and no stuck PIT2. */
    if(argc>1)for(mode=0;mode<3;mode++)for(vol=15;vol<=20;vol+=5)
        for(soft=0;soft<2;soft++){
            ta_set_volume(vol);ta_set_speaker(mode);ta_set_treble(soft);
            assert(ta_load(argv[1]));ta_begin();
            for(i=0;i<30000U && ta.playing;i++){
                ta_advance(32);assert(power()<=TA_MIX_POWER_CEILING);
                if(pit)assert(ta.speaker_voice.note>=24 && ta.speaker_voice.note<=52);
            }
            assert(!ta.playing && !pit && power()==0);
        }
    puts("PASS: paused boost resume, failed-load silence, length overflow, folded adaptive collision, optional 12-mode MIDI sweep");
    return 0;
}
