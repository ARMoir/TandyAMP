/* TandyAMP MIDI engine -- original code, MIT. C89 and 16-bit DOS safe. */
#ifndef TANDYAMP_MIDI_H
#define TANDYAMP_MIDI_H

/* Original Windows 3.x CANYON.MID is ~34 KB; stay below a 64K data segment. */
#define TA_MAX_FILE 45056U
#define TA_MAX_TRACKS 24
#define TA_VOICES 3
#define TA_CHANNELS 16
#define TA_ACTIVE_NOTES 32
#define TA_DRUM_AUTO 0
#define TA_DRUM_ON 1
#define TA_DRUM_OFF 2
#define TA_SPK_OFF 0
#define TA_SPK_BASS 1
#define TA_SPK_ADAPT 2

typedef unsigned char ta_u8;
typedef unsigned short ta_u16;
typedef unsigned long ta_u32;
typedef signed long ta_s32;

typedef struct {
    ta_u16 pos, end, beginning;
    ta_u32 next_tick;
    ta_u8 running, active;
} TATrack;

typedef struct {
    signed short note;
    ta_u8 channel, velocity, held, sustained, level;
    ta_u32 stamp;
    signed short source; /* Active-note index, -1 for idle. */
} TAVoice;

typedef struct {
    signed short note;
    ta_u8 channel, velocity, held, sustained;
    ta_u8 gain, attenuation; /* Cached for cheap 8086 voice selection. */
    ta_u8 style, env_step; /* Original program-aware PSG envelope. */
    ta_u16 age_q8; /* Elapsed tone age, 1/256 of a BIOS tick, saturating. */
    ta_u16 period; /* Actual folded/bent hardware pitch. */
    ta_u32 stamp;
} TAActiveNote;

typedef struct {
    ta_u8 data[TA_MAX_FILE];
    ta_u16 bytes, division, track_count, format;
    TATrack tracks[TA_MAX_TRACKS];
    TAVoice voices[TA_VOICES];
    TAVoice speaker_voice; /* Optional PIT2 fourth pitched voice. */
    TAActiveNote notes[TA_ACTIVE_NOTES];
    ta_u8 cc_volume[TA_CHANNELS], cc_expression[TA_CHANNELS];
    ta_u8 cc_sustain[TA_CHANNELS];
    ta_u8 cc_program[TA_CHANNELS]; /* 0-127, 255 until program change. */
    ta_u8 cc_modulation[TA_CHANNELS]; /* MIDI CC1 vibrato depth. */
    signed short pitchbend[TA_CHANNELS];
    ta_u32 tempo_us, step_q8, clock_q8, max_ticks, sequence;
    ta_u16 clock_carry; /* Subtick fractional MIDI clock accumulation. */
    ta_u16 noise_left, noise_length;
    ta_u8 noise_mode, noise_base, noise_last;
    ta_u8 drum16; /* Resolved channel-16 percussion routing. */
    ta_u8 drum_mode; /* AUTO, ON, OFF; persists between songs. */
    ta_u8 drum_detected; /* File-scanning decision before override. */
    ta_u8 loaded, playing, paused;
    ta_u8 master_attenuation, mix_attenuation;
    ta_u8 master_boost; /* 0..5 extra attenuation steps recovered at 16..20. */
    ta_u8 treble_soft; /* 0=original, 1=slightly soften notes C6 and up. */
    ta_u8 speaker_enabled; /* 0=OFF, 1=BASS, 2=ADAPT, persisted across songs. */
    ta_u8 speaker_octave_up; /* True if ADAPT currently sounds one octave up. */
    ta_u32 speaker_adapt_stamp; /* Lock octave for the entire MIDI note. */
    ta_u16 speaker_divider; /* Real PIT2 output: 0=off, nonzero=sounding. */
} TAEngine;

extern TAEngine ta;
int ta_load(const char *filename);
void ta_begin(void);
void ta_stop(void);
void ta_tick(void); /* Legacy 1-BIOS-tick API for tests. */
void ta_advance(ta_u16 elapsed_q8); /* Units of 1/256 BIOS tick. */
void ta_pause(void);
void ta_noteoff_all(void);
void ta_set_volume(unsigned volume); /* 0=mute, 15=normal, 20=boost. */
unsigned ta_get_volume(void); /* User-facing 0..20 master setting. */
void ta_set_treble(unsigned soft); /* Conservative high-note balance switch. */
void ta_set_speaker(unsigned mode); /* OFF -> BASS -> ADAPT, optional PIT2. */
ta_u32 ta_elapsed_seconds(void);
const char *ta_error(void);

/* Platform-specific, zero-based tone slot; attenuation: 0 loudest, 15 mute. */
void ta_psg_tone(int slot, ta_u16 divider, ta_u8 attenuation);
void ta_psg_silence(void);
void ta_pc_speaker(ta_u16 pit_divisor); /* 0=mute, else PIT2 tone */
void ta_psg_noise(ta_u8 mode, ta_u8 attenuation);
void ta_psg_noise_level(ta_u8 attenuation);

#endif

