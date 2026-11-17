/* Opt-in fourth-voice regression against original MIDI allocator and
   mocked PIT2 hardware (no user music or PC clock assumptions). */
#include <assert.h>
#include <stdio.h>
#include "../src/midi.c"

static ta_u16 pit_divider=0;
static unsigned pit_on_calls=0,pit_off_calls=0;
void ta_pc_speaker(ta_u16 divisor)
{
    if(divisor){pit_on_calls++;pit_divider=divisor;}
    else {pit_off_calls++;pit_divider=0;}
}
void ta_psg_tone(int slot,ta_u16 divider,ta_u8 att)
{
    assert(slot>=0 && slot<3 && divider>0 && divider<=1023 && att<=15);
}
void ta_psg_noise(ta_u8 mode,ta_u8 att){assert(mode<=7 && att<=15);}
void ta_psg_noise_level(ta_u8 att){assert(att<=15);}
void ta_psg_silence(void){}

static void play_four(ta_u8 bass)
{
    clear_synth();
    ta.playing=1;
    on(0,72,127);on(1,64,127);on(2,55,127);on(3,bass,127);
    flush_mix();
}
static void check_bass_exclusive(ta_u8 note,ta_u16 divider)
{
    unsigned i;
    assert(ta.speaker_voice.note==note);
    assert(ta.speaker_voice.source>=0);
    assert(pit_divider==divider);
    assert(ta.speaker_divider==divider);
    for(i=0;i<TA_VOICES;i++)assert(ta.voices[i].note!=note);
}
int main(void)
{
    unsigned calls,i;
    clear_synth();ta.playing=1;
    assert(ta.speaker_enabled==0);
    /* No speaker for a chord lacking a fourth part. */
    on(0,72,127);on(1,64,127);on(2,48,127);
    flush_mix();
    ta_set_speaker(1);
    assert(pit_divider==0 && ta.speaker_voice.source<0);

    /* A fourth LOW bass part goes to PIT2; other 3 remain on PSG. */
    play_four(48);
    ta.clock_q8=98765UL;
    ta_set_speaker(1);
    assert(ta.clock_q8==98765UL);
    assert(ta.speaker_enabled);
    check_bass_exclusive(48,9121);
    calls=pit_on_calls;
    flush_mix();
    assert(calls==pit_on_calls); /* unchanged register: zero port writes */

    /* The 1.193182MHz PIT2 divider retains the genuine deep octave,
       rather than the PSG's folded, one-octave-higher low-bass pitch. */
    play_four(36);
    check_bass_exclusive(36,18243);
    play_four(24);
    check_bass_exclusive(24,36485);
    play_four(52);
    check_bass_exclusive(52,7240);

    /* MIDI pitch bend works at the correct low frequency. */
    ta.pitchbend[3]=4096;  /* +1 semitone */
    render_channel(3);
    flush_mix();
    assert(pit_divider<7240 && pit_divider>6450);
    ta.pitchbend[3]=-4096;
    render_channel(3);
    flush_mix();
    assert(pit_divider>7240);

    /* High and out-of-range notes are NEVER assigned to SPK4,
       even when they overflow the existing three PSG channels. */
    play_four(53);
    assert(ta.speaker_voice.source<0 && pit_divider==0);
    play_four(60);
    assert(ta.speaker_voice.source<0 && pit_divider==0);
    play_four(90);
    assert(ta.speaker_voice.source<0 && pit_divider==0);
    play_four(23);
    assert(ta.speaker_voice.source<0 && pit_divider==0);

    /* No phantom fourth tone from duplicate PSG or unison pitches. */
    clear_synth();ta.playing=1;
    on(0,72,127);on(1,72,127);on(2,64,127);on(3,48,127);
    flush_mix();
    assert(ta.speaker_voice.source<0 && pit_divider==0);

    /* Live toggle must not restart the MIDI timeline or lose notes. */
    play_four(48);
    assert(pit_divider==9121);
    ta.clock_q8=100023UL;
    ta_set_speaker(0);
    assert(pit_divider==0 && ta.speaker_voice.source<0);
    assert(ta.clock_q8==100023UL);
    ta_set_speaker(1);
    assert(pit_divider==9121 && ta.clock_q8==100023UL);

    /* Bass returns to PSG if a melody voice is released. */
    off(0,72);flush_mix();
    assert(pit_divider==0 && ta.speaker_voice.source<0);
    for(i=0;i<TA_VOICES;i++)if(ta.voices[i].note==48)break;
    assert(i<TA_VOICES);

    play_four(48);
    assert(pit_divider==9121);
    ta_pause();
    assert(ta.paused && pit_divider==0 && ta.speaker_divider==0);
    ta_pause();
    assert(!ta.paused && pit_divider==9121);
    ta_set_volume(0);
    assert(pit_divider==0);
    ta_set_volume(15);
    assert(pit_divider==9121);
    ta_stop();
    assert(pit_divider==0 && ta.speaker_divider==0 &&
           !ta.playing && pit_off_calls>0);
    assert(ta.speaker_enabled==1);
    clear_synth();
    assert(ta.speaker_enabled && ta.speaker_voice.source<0);
    ta_set_speaker(0);
    assert(!ta.speaker_enabled && !pit_divider);

    /* Three modes preserve the original BASS output. ADAPT may move
       the same low MIDI note up one octave for small-speaker clarity. */
    assert(TA_SPK_OFF==0 && TA_SPK_BASS==1 && TA_SPK_ADAPT==2);
    ta_set_speaker(TA_SPK_BASS);
    play_four(24);
    assert(ta.speaker_divider==36485 && ta.speaker_octave_up==0);
    ta_set_speaker(TA_SPK_ADAPT);
    assert(ta.speaker_enabled==TA_SPK_ADAPT);
    check_bass_exclusive(24,18243); /* C1 -> C2 */
    assert(ta.speaker_octave_up==1 && ta.speaker_voice.note==24);
    {
        ta_u32 stable_stamp=ta.speaker_adapt_stamp;
        ta_u16 stable_divider=ta.speaker_divider;
        unsigned j;
        /* Even a big PSG loudness change must not shift THIS held
           bass note's octave. Pitch only follows its MIDI bend. */
        for(j=0;j<TA_VOICES;j++)ta.voices[j].level=14;
        render_speaker();
        assert(ta.speaker_divider==stable_divider);
        assert(ta.speaker_adapt_stamp==stable_stamp);
        assert(ta.speaker_octave_up==1);
        ta.pitchbend[3]=4096;
        render_channel(3);flush_mix();
        assert(ta.speaker_divider<stable_divider);
        assert(ta.speaker_octave_up==1);
    }
    /* Original octave is still required for upper bass notes. */
    play_four(48);
    assert(ta.speaker_divider==9121 && !ta.speaker_octave_up);
    /* Adaptive placement considers whether melody overlaps the raised
       octave and whether the rest of the music masks the bass. */
    play_four(36);
    for(i=0;i<TA_VOICES;i++)ta.voices[i].level=4;
    assert(choose_adaptive_octave(36)==1);
    for(i=0;i<TA_VOICES;i++)ta.voices[i].level=12;
    assert(choose_adaptive_octave(36)==0);
    ta.voices[1].note=48;ta.voices[1].level=0;
    assert(choose_adaptive_octave(36)==0); /* overlap with raised C3 */
    /* ADAPT uses PIT2 with bass + two distinct PSG tones;
       BASS still requires three other tones for conservative operation. */
    clear_synth();ta.playing=1;
    on(0,72,127);on(1,64,127);on(3,48,127);
    flush_mix();
    check_bass_exclusive(48,9121);
    ta_set_speaker(TA_SPK_BASS);
    assert(pit_divider==0 && ta.speaker_voice.source<0);
    ta_set_speaker(TA_SPK_ADAPT);
    check_bass_exclusive(48,9121);
    /* One other tone is insufficient, even for ADAPT. */
    off(0,72);flush_mix();
    assert(pit_divider==0 && ta.speaker_voice.source<0);
    clear_synth();ta.playing=1;
    on(0,72,127);on(1,72,127);on(3,48,127);flush_mix();
    assert(pit_divider==0 && ta.speaker_voice.source<0);

    /* Non-bass source notes remain strictly excluded in adaptive mode. */
    play_four(60);
    assert(!ta.speaker_divider && ta.speaker_voice.source<0);
    ta_set_speaker(TA_SPK_OFF);
    assert(ta.speaker_divider==0 && !ta.speaker_enabled);
    assert(ta.speaker_octave_up==0);

    /* Smart selection is opt-in and never leaks from one song to another.
       Guitar (channel 4/program 30) should survive weak high harmonics.
       Other voices join only when room exists, and a held support voice
       should not flicker when a slightly louder note arrives. */
    clear_synth();ta.playing=1;
    ta_set_speaker(TA_SPK_OFF);
    assert(!smart_voice_mode);
    ta.cc_program[0]=80;
    ta.cc_program[2]=48;
    ta.cc_program[3]=48;
    ta.cc_program[4]=30;
    on(4,64,95);on(0,72,95);on(0,96,35);
    on(2,60,88);on(3,67,60);
    handle_cc(0,119,77);flush_mix();
    assert(smart_voice_mode);
    {
        int have_guitar=0,have_vocal=0,have_harmony=0;
        for(i=0;i<TA_VOICES;i++){
            if(ta.voices[i].note==64 && ta.voices[i].channel==4)have_guitar=1;
            if(ta.voices[i].note==72 && ta.voices[i].channel==0)have_vocal=1;
            if(ta.voices[i].note==60 && ta.voices[i].channel==2)have_harmony=1;
            assert(ta.voices[i].note!=96); /* weak high harmonic muted */
        }
        assert(have_guitar && have_vocal && have_harmony);
    }
    off(2,60);flush_mix(); /* accompanying chord fills vacated slot */
    {
        int have_support=0;
        for(i=0;i<TA_VOICES;i++)
            if(ta.voices[i].channel==3 && ta.voices[i].note==67)
                have_support=1;
        assert(have_support);
    }
    on(3,69,63);flush_mix(); /* weak competing support cannot steal */
    {
        int have_held=0;
        for(i=0;i<TA_VOICES;i++){
            if(ta.voices[i].note==67 && ta.voices[i].channel==3)
                have_held=1;
            assert(ta.voices[i].note!=69);
        }
        assert(have_held);
    }
    off(3,67);flush_mix();
    {
        int have_new=0;
        for(i=0;i<TA_VOICES;i++)
            if(ta.voices[i].note==69 && ta.voices[i].channel==3)
                have_new=1;
        assert(have_new);
    }
    /* Soft channel diversity leaves room for vocal and bass among a
       strong guitar chord, without disabling polyphonic guitar solos. */
    clear_synth();ta.playing=1;ta_set_speaker(TA_SPK_OFF);
    ta.cc_program[0]=80;ta.cc_program[1]=33;ta.cc_program[4]=30;
    handle_cc(0,119,77);
    on(4,60,95);on(4,64,95);on(4,67,95);
    on(0,72,95);on(1,36,120);flush_mix();
    {
        int guitar=0,vocal=0,bass=0;
        for(i=0;i<TA_VOICES;i++){
            if(ta.voices[i].channel==4)guitar++;
            if(ta.voices[i].channel==0)vocal++;
            if(ta.voices[i].channel==1)bass++;
        }
        assert(guitar==1 && vocal==1 && bass==1);
    }
    off(0,72);off(1,36);flush_mix();
    for(i=0;i<TA_VOICES;i++)assert(ta.voices[i].channel==4);
    handle_cc(0,119,0);
    assert(!smart_voice_mode);
    handle_cc(0,119,77);
    clear_synth();
    assert(!smart_voice_mode);
    ta_set_speaker(TA_SPK_BASS);

    puts("PASS: MIDI 24..52 bass-only PIT2 (true octave), bends, "
         "three-way adaptive octave lock, note collisions, live toggle and mute");
    return 0;
}
