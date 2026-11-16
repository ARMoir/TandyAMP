/* Fourth-voice regression: actual MIDI allocator with a mocked PIT2 backend.
   The ordinary 3-tone behavior is unchanged unless the user opts in. */
#include <assert.h>
#include <stdio.h>
#include "../src/midi.c"

static ta_u16 pit_divider=0;
static unsigned pit_on_calls=0,pit_off_calls=0;
static unsigned psg_writes=0;
void ta_pc_speaker(ta_u16 divisor)
{
    if(divisor){pit_on_calls++;pit_divider=divisor;}
    else {pit_off_calls++;pit_divider=0;}
}
void ta_psg_tone(int slot,ta_u16 divider,ta_u8 att)
{
    assert(slot>=0 && slot<3 && divider>0 && divider<=1023 && att<=15);
    psg_writes++;
}
void ta_psg_noise(ta_u8 mode,ta_u8 att){assert(mode<=7 && att<=15);}
void ta_psg_noise_level(ta_u8 att){assert(att<=15);}
void ta_psg_silence(void){}

int main(void)
{
    unsigned calls;
    ta_u16 expected;
    clear_synth();
    ta.playing=1;
    assert(ta.speaker_enabled==0);
    on(0,72,127);on(1,64,127);on(2,55,127);on(3,48,127);
    flush_mix();
    assert(ta.speaker_voice.source<0);
    assert(pit_divider==0 && pit_on_calls==0);
    assert(ta.voices[0].note>=0 && ta.voices[1].note>=0 &&
           ta.voices[2].note>=0);

    /* Enabling in the middle of playback is immediate; timeline preserved. */
    ta.clock_q8=98765UL;
    ta_set_speaker(1);
    assert(ta.clock_q8==98765UL && ta.speaker_enabled==1);
    assert(ta.speaker_voice.source>=0 && ta.speaker_voice.note>=0);
    expected=speaker_divider_for(
        ta.notes[ta.speaker_voice.source].period);
    assert(expected>=18 && expected<65536UL);
    assert(pit_divider==expected);
    calls=pit_on_calls;
    flush_mix(); /* idle state must not rewrite PIT2 */
    assert(pit_on_calls==calls);

    /* Instant disable must mute, not restart or lose held PSG notes. */
    ta_set_speaker(0);
    assert(pit_divider==0 && ta.speaker_voice.source<0);
    assert(ta.clock_q8==98765UL);
    ta_set_speaker(1);
    assert(pit_divider>0);
    /* A mix below the 4-note threshold cannot waste the speaker. */
    off(3,48);flush_mix();
    assert(pit_divider==0 && ta.speaker_voice.source<0);

    /* Note-on again: pause and stop always clear PIT2 gate. */
    on(3,48,127);flush_mix();
    assert(pit_divider>0);
    ta_pause();
    assert(ta.paused && pit_divider==0);
    ta_pause();
    assert(!ta.paused && pit_divider>0);
    ta_set_volume(0);
    assert(pit_divider==0);
    ta_set_volume(15);
    assert(pit_divider>0);
    ta_stop();
    assert(pit_divider==0 && !ta.playing && pit_off_calls>0);

    /* Option survives a fresh song's reset; no stray note remains. */
    assert(ta.speaker_enabled==1);
    clear_synth();
    assert(ta.speaker_enabled==1 && ta.speaker_voice.source<0);
    ta_set_speaker(0);
    assert(ta.speaker_enabled==0 && pit_divider==0);
    puts("PASS: fourth PIT2 voice toggle, overflow-only selection, "
         "pitch mapping, pause/resume, stop and master mute");
    return 0;
}
