/* TandyAMP MIDI engine -- original code, MIT. C89 and 16-bit DOS safe. */
#ifndef TANDYAMP_MIDI_H
#define TANDYAMP_MIDI_H

#define TA_MAX_FILE 28672U
#define TA_MAX_TRACKS 12
#define TA_VOICES 3
#define TA_CHANNELS 16

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
} TAVoice;

typedef struct {
    ta_u8 data[TA_MAX_FILE];
    ta_u16 bytes, division, track_count, format;
    TATrack tracks[TA_MAX_TRACKS];
    TAVoice voices[TA_VOICES];
    ta_u8 cc_volume[TA_CHANNELS], cc_expression[TA_CHANNELS];
    ta_u8 cc_sustain[TA_CHANNELS];
    signed short pitchbend[TA_CHANNELS];
    ta_u32 tempo_us, step_q8, clock_q8, max_ticks, sequence;
    ta_u8 loaded, playing, paused;
} TAEngine;

extern TAEngine ta;
int ta_load(const char *filename);
void ta_begin(void);
void ta_stop(void);
void ta_tick(void);
void ta_pause(void);
void ta_noteoff_all(void);
ta_u32 ta_elapsed_seconds(void);
const char *ta_error(void);

/* Platform-specific, zero-based tone slot; attenuation: 0 loudest, 15 mute. */
void ta_psg_tone(int slot, ta_u16 divider, ta_u8 attenuation);
void ta_psg_silence(void);

#endif
