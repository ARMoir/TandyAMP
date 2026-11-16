/* TandyAMP -- DOS Winamp-inspired Tandy 16-color MIDI player
   Original MIT-licensed code. 16-bit real mode, 8086-compatible. */
#include "midi.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#ifdef __WATCOMC__
#include <dos.h>
#include <conio.h>
#else
#include <dirent.h>
#include <sys/stat.h>
#endif

#define MAX_SONGS 64
#define PATHLEN 64
#define SCREEN_W 320
#define SCREEN_H 200
#define VRAM_BANK 8192U
#define VRAM_STRIDE 160U

static char songs[MAX_SONGS][PATHLEN];
static unsigned song_count=0, song_current=0;
static int playlist_truncated=0;
static int text_mode=0, loop_mode=0, show_equalizer=0;
static int stopped=0, program_exit=0;
static ta_u32 song_ticks=0, last_refresh=0;
/* Deliberately tiny dirty-region set: no periodic full-screen repaints. */
#define UI_TRACK    0x01U
#define UI_PANEL    0x02U
#define UI_STATE    0x04U
#define UI_BUTTONS  0x08U
#define UI_CLOCK    0x10U
#define UI_PROGRESS 0x20U
#define UI_METERS   0x40U
#define UI_SPK4     0x80U
#define UI_MUTE     0x100U
#define UI_ALL      0x1ffU
/* Five consistently sized controls per row.  All labels fit in mode 09h. */
#define UI_BUTTON_COUNT 10U
#define UI_BUTTON_COLS 5U
#define UI_BUTTON_X 10U
#define UI_BUTTON_STEP 60U
#define UI_BUTTON_WIDTH 58U
#define UI_BUTTON_HEIGHT 17U
#define UI_BUTTON_Y 72U
#define UI_BUTTON_ROW_STEP 19U
#define UI_LOWER_PANEL_Y 112U
static unsigned ui_dirty=UI_ALL, old_marker=0xffffU;
static ta_u32 ui_last_seconds=0xffffffffUL;
static signed short meter_last_note[3]={-2,-2,-2};
static ta_u8 meter_last_velocity[3]={255,255,255};
static ta_u8 meter_last_active[3]={255,255,255};
static unsigned song_tick_part=0;
static unsigned last_audible_volume=15U;
static unsigned button_cache_valid=0;
static ta_u8 button_cache[UI_BUTTON_COUNT];
/* Original 8x11 software arrow: native INT 33h cursors may not display
   in Tandy mode 09h even when movement and button calls work. */
#define TA_POINTER_W 8U
#define TA_POINTER_H 11U
static unsigned mouse_x=160U,mouse_y=100U,mouse_x_divisor=2U;
static int mouse_present=0,mouse_enabled=1,mouse_was_down=0;
static int mouse_cursor_visible=0;
static ta_u8 mouse_under[TA_POINTER_H][TA_POINTER_W];
static const ta_u8 mouse_shape[TA_POINTER_H]={
    0x80,0xc0,0xe0,0xf0,0xf8,0xfc,0xfe,0xf0,0xd8,0x8c,0x84
};
#ifdef TANDYAMP_UI_TEST
/* Host-only visual regression instrumentation; zero DOS binary overhead. */
static unsigned long ui_pixels_written=0UL;
#endif

#ifdef __WATCOMC__
static unsigned char far * const vram=(unsigned char far *)MK_FP(0xB800,0);
static volatile ta_u32 far * const bios_tick=(volatile ta_u32 far*)MK_FP(0x40,0x6c);
static void put_sound(ta_u8 value){outp(0xc0,value);}
/* Optional PIT channel 2 fourth tone. PIT0 scheduler stays untouched.
   Only bits 0/1 of EX port 61h are changed, preserving audio routing. */
static ta_u16 pit2_current=0;
void ta_pc_speaker(ta_u16 divisor)
{
    unsigned char p;
    if(divisor==pit2_current)return;
    if(!divisor){
        if(pit2_current){
            p=(unsigned char)inp(0x61);
            outp(0x61,(unsigned char)(p&0xfcU));
        }
    }else{
        outp(0x43,0xb6);
        outp(0x42,(unsigned char)(divisor&255U));
        outp(0x42,(unsigned char)(divisor>>8));
        if(!pit2_current){
            p=(unsigned char)inp(0x61);
            outp(0x61,(unsigned char)(p|0x03U));
        }
    }
    pit2_current=divisor;
}
static void timer_start(void)
{
    /* Mode 3 counts down twice per BIOS tick. Use a single mode-2 ramp
       with the SAME 65536 divisor and IRQ rate for monotonic subticks. */
    _disable();
    outp(0x43,0x34);outp(0x40,0);outp(0x40,0);
    _enable();
}
static void timer_stop(void)
{
    _disable();
    outp(0x43,0x36);outp(0x40,0);outp(0x40,0);
    _enable();
}
/* Read free-running PIT channel 0: no new IRQ, no BIOS tick rate change.
   256 subunits per 54.9ms tick (~0.215ms timer resolution). */
static ta_u32 get_clock_q8(void)
{
    ta_u32 before,after;
    unsigned low,high,remaining;
    do {
        before=*bios_tick;
        outp(0x43,0x00);
        low=inp(0x40);
        high=inp(0x40);
        after=*bios_tick;
    } while(before!=after);
    remaining=(high<<8)|low;
    return (after<<8) + ((65535U-remaining)>>8);
}
static void set_mode(unsigned char mode)
{
    union REGS r;
    r.h.ah=0; r.h.al=mode;
    int86(0x10,&r,&r);
}
static int key_ready(void){return kbhit();}
static int next_key(void){return getch();}
#else
/* Host-only build supports CLI tests and build checks, not hardware playback. */
static unsigned char host_screen[32768];
static unsigned char * const vram=host_screen;
static ta_u32 fake_clock=0;
static void timer_start(void){}
static void timer_stop(void){}
#ifdef TANDYAMP_UI_TEST
static unsigned long test_psg_writes=0;
static void put_sound(ta_u8 value){(void)value;test_psg_writes++;}
#else
static void put_sound(ta_u8 value){(void)value;}
#endif
static ta_u32 get_clock_q8(void){return (fake_clock++)<<8;}
static void set_mode(unsigned char mode){(void)mode;}
static int key_ready(void){return 0;}
static int next_key(void){return 'q';}
#endif

#ifndef __WATCOMC__
static ta_u16 test_pc_speaker_divisor=0;
static unsigned test_pc_speaker_writes=0;
void ta_pc_speaker(ta_u16 divisor)
{
    if(divisor!=test_pc_speaker_divisor){
        test_pc_speaker_divisor=divisor;
        test_pc_speaker_writes++;
    }
}
#endif

/* Track only *actual* I/O state. A frequency change costs two PSG
   bytes; volume-only one; unchanged parameters zero. */
static ta_u16 last_hw_divider[3]={0,0,0};
static ta_u8 last_hw_attenuation[3]={255,255,255};
static ta_u8 last_hw_noise_attenuation=255;
void ta_psg_tone(int slot,ta_u16 divider,ta_u8 attenuation)
{
    ta_u8 latch,volume;
    if(slot<0||slot>=3)return;
    if(divider<1)divider=1;
    if(divider>1023)divider=1023;
    if(attenuation>15)attenuation=15;
    latch=(ta_u8)(0x80+(slot<<5));
    volume=(ta_u8)(0x90+(slot<<5));
    if(last_hw_divider[slot]!=divider){
        put_sound((ta_u8)(latch|(divider&15)));
        put_sound((ta_u8)((divider>>4)&63));
        last_hw_divider[slot]=divider;
    }
    if(last_hw_attenuation[slot]!=attenuation){
        put_sound((ta_u8)(volume|attenuation));
        last_hw_attenuation[slot]=attenuation;
    }
}
void ta_psg_noise_level(ta_u8 attenuation)
{
    if(attenuation>15)attenuation=15;
    if(last_hw_noise_attenuation!=attenuation){
        put_sound((ta_u8)(0xf0|attenuation));
        last_hw_noise_attenuation=attenuation;
    }
}
void ta_psg_noise(ta_u8 mode,ta_u8 attenuation)
{
    /* Deliberately reset the LFSR even for successive same-mode drums. */
    put_sound((ta_u8)(0xe0|(mode&7)));
    ta_psg_noise_level(attenuation);
}
void ta_psg_silence(void)
{
    unsigned i;
    put_sound(0x9f);
    put_sound(0xbf);
    put_sound(0xdf);
    put_sound(0xff);
    for(i=0;i<3;i++){
        last_hw_divider[i]=0;
        last_hw_attenuation[i]=15;
    }
    last_hw_noise_attenuation=15;
}

/* 5-column public-domain-style geometric pixel font, generated independently.
   Each byte is a vertical seven-pixel column, least significant bit at top. */
static const char glyph_chars[]=
" ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:-./_+?![]%";
static const unsigned char glyph_cols[][5]={
{0,0,0,0,0},
{0x7e,0x11,0x11,0x11,0x7e},
{0x7f,0x49,0x49,0x49,0x36},
{0x3e,0x41,0x41,0x41,0x22},
{0x7f,0x41,0x41,0x22,0x1c},
{0x7f,0x49,0x49,0x49,0x41},
{0x7f,0x09,0x09,0x09,0x01},
{0x3e,0x41,0x49,0x49,0x7a},
{0x7f,0x08,0x08,0x08,0x7f},
{0,0x41,0x7f,0x41,0},
{0x20,0x40,0x41,0x3f,0x01},
{0x7f,0x08,0x14,0x22,0x41},
{0x7f,0x40,0x40,0x40,0x40},
{0x7f,0x02,0x0c,0x02,0x7f},
{0x7f,0x04,0x08,0x10,0x7f},
{0x3e,0x41,0x41,0x41,0x3e},
{0x7f,0x09,0x09,0x09,0x06},
{0x3e,0x41,0x51,0x21,0x5e},
{0x7f,0x09,0x19,0x29,0x46},
{0x46,0x49,0x49,0x49,0x31},
{0x01,0x01,0x7f,0x01,0x01},
{0x3f,0x40,0x40,0x40,0x3f},
{0x1f,0x20,0x40,0x20,0x1f},
{0x7f,0x20,0x18,0x20,0x7f},
{0x63,0x14,0x08,0x14,0x63},
{0x07,0x08,0x70,0x08,0x07},
{0x61,0x51,0x49,0x45,0x43},
{0x3e,0x51,0x49,0x45,0x3e},
{0x00,0x42,0x7f,0x40,0x00},
{0x62,0x51,0x49,0x49,0x46},
{0x22,0x41,0x49,0x49,0x36},
{0x18,0x14,0x12,0x7f,0x10},
{0x2f,0x49,0x49,0x49,0x31},
{0x3e,0x49,0x49,0x49,0x32},
{0x01,0x71,0x09,0x05,0x03},
{0x36,0x49,0x49,0x49,0x36},
{0x26,0x49,0x49,0x49,0x3e},
{0x00,0x36,0x36,0x00,0x00},
{0x08,0x08,0x08,0x08,0x08},
{0x20,0x10,0x08,0x04,0x02},
{0x00,0x42,0x42,0x42,0x00},
{0x40,0x40,0x40,0x40,0x40},
{0x08,0x08,0x3e,0x08,0x08},
{0x02,0x01,0x51,0x09,0x06},
{0x06,0x09,0x09,0x09,0x06},
{0x00,0x7f,0x41,0x41,0},
{0x00,0x41,0x41,0x7f,0},
{0x23,0x13,0x08,0x64,0x62}
};
static void plot(unsigned x,unsigned y,ta_u8 c)
{
    unsigned off;
    ta_u8 old;
    if(x>=SCREEN_W||y>=SCREEN_H)return;
#ifdef TANDYAMP_UI_TEST
    ui_pixels_written++;
#endif
    off=((y&3U)*VRAM_BANK)+((y>>2)*VRAM_STRIDE)+(x>>1);
    old=vram[off];
    if(x&1U)vram[off]=(ta_u8)((old&0xf0)|(c&15));
    else vram[off]=(ta_u8)((old&0x0f)|(c<<4));
}
static void box(unsigned x,unsigned y,unsigned w,unsigned h,ta_u8 c)
{
    unsigned row,col,offset,left,right;
    ta_u8 both=(ta_u8)(c*17U);
    if(x>=320||y>=200)return;
    if(x+w>320)w=320-x;
    if(y+h>200)h=200-y;
    for(row=y;row<y+h;row++){
        offset=((row&3U)*VRAM_BANK)+((row>>2)*VRAM_STRIDE);
        left=x;
        right=x+w;
        if(left&1U){plot(left,row,c);left++;}
        for(col=left;col+1<right;col+=2){
            vram[offset+(col>>1)]=both;
#ifdef TANDYAMP_UI_TEST
            ui_pixels_written+=2UL;
#endif
        }
        if(right&1U)plot(right-1,row,c);
    }
}
static void frame(unsigned x,unsigned y,unsigned w,unsigned h,ta_u8 fill)
{
    box(x,y,w,h,0);
    box(x+1,y+1,w-2,h-2,fill);
    box(x,y,w,1,7);
    box(x,y,1,h,7);
    box(x,y+h-1,w,1,0);
    box(x+w-1,y,1,h,0);
}
static void character(unsigned x,unsigned y,char ch,ta_u8 color)
{
    unsigned i,j,idx=0;
    ta_u8 bits;
    const char *p;
    ch=(char)toupper((unsigned char)ch);
    p=strchr(glyph_chars,ch);
    if(p)idx=(unsigned)(p-glyph_chars);
    for(i=0;i<5;i++){
        bits=glyph_cols[idx][i];
        for(j=0;j<7;j++)if(bits&(1U<<j))plot(x+i,y+j,color);
    }
}
static void label(unsigned x,unsigned y,const char *str,ta_u8 color,unsigned maxchars)
{
    unsigned n=0;
    while(*str && n<maxchars && x+5<320){
        character(x,y,*str++,color);
        x+=6;n++;
    }
}
static void header(unsigned y,const char *title)
{
    box(2,y,316,13,1);
    box(3,y+1,314,1,9);
    label(8,y+3,title,15,48);
    label(293,y+3,"X",14,1);
}
static const char *leaf(const char *name)
{
    const char *p=name,*a=name;
    while(*p){if(*p=='/'||*p=='\\'||*p==':')a=p+1;p++;}
    return a;
}
/* Two balanced rows, using the existing 5x7 pixel font.
   All 10 buttons are live controls, not cosmetic placeholders. */
static const char *button_labels[UI_BUTTON_COUNT]={
    "PREV","PLAY","PAUSE","STOP","NEXT",
    "VIS","LOOP","DRUM","SPK4","MUTE"
};
static unsigned button_x(unsigned i)
{
    return UI_BUTTON_X+(i%UI_BUTTON_COLS)*UI_BUTTON_STEP;
}
static unsigned button_y(unsigned i)
{
    return UI_BUTTON_Y+(i/UI_BUTTON_COLS)*UI_BUTTON_ROW_STEP;
}
static int button_pressed(unsigned i)
{
    return (i==1 && ta.playing && !ta.paused)
        || (i==2 && ta.playing && ta.paused)
        || (i==5 && show_equalizer)
        || (i==6 && loop_mode)
        || (i==7 && ta.drum16)
        || (i==8 && ta.speaker_enabled)
        || (i==9 && ta.master_attenuation==15);
}
static void draw_button(unsigned i)
{
    unsigned x,y,w,tx,ty;
    int pressed;
    const char *caption;
    ta_u8 face,ink;
    if(i>=UI_BUTTON_COUNT)return;
    pressed=button_pressed(i);
    if((button_cache_valid&(1U<<i)) &&
       button_cache[i]==(ta_u8)pressed)return;
    button_cache_valid|=(1U<<i);
    button_cache[i]=(ta_u8)pressed;
    caption=button_labels[i];
    if(i==8)caption=pressed?"SPK4 ON":"SPK4 OFF";
    else if(i==9)caption=pressed?"MUTE ON":"MUTE OFF";
    x=button_x(i);y=button_y(i);
    face=(ta_u8)(pressed?1:7);
    ink=(ta_u8)(pressed?15:0);
    frame(x,y,UI_BUTTON_WIDTH,UI_BUTTON_HEIGHT,face);
    box(x+2,y+2,UI_BUTTON_WIDTH-4,1,
        (ta_u8)(pressed?9:15));
    w=(unsigned)strlen(caption)*6U-1U;
    tx=x+(UI_BUTTON_WIDTH-w)/2U;
    ty=y+(UI_BUTTON_HEIGHT-7U)/2U;
    if(i==8 || i==9){
        /* State is explicit, not inferred solely from a pressed bevel. */
        label(tx,ty,caption,ink,4);
        label(tx+30,ty,caption+5,
              (ta_u8)(pressed?(i==8?10:14):4),3);
    }else label(tx,ty,caption,ink,5);
}
static void draw_buttons(void)
{
    unsigned i;
    for(i=0;i<UI_BUTTON_COUNT;i++)draw_button(i);
}
static void draw_base(void)
{
    box(0,0,320,200,8);
    frame(1,1,318,110,8);
    header(3,"TANDYAMP MIDI PLAYER");
    frame(7,19,109,44,0);
    frame(123,19,189,44,0);
    box(8,67,302,3,0);
    box(10,68,298,1,8);
    frame(1,UI_LOWER_PANEL_Y,318,86,8);
    label(8,189,"SPACE PAUSE  K SPK4  M MUTE  D DRUM  Q QUIT",7,49);
}
static void draw_playlist(void)
{
    unsigned i,start;
    char n[5];
    box(3,127,314,59,0);
    if(!song_count){
        label(10,142,"PASS A MIDI FILE ON COMMAND LINE",10,43);
        return;
    }
    start=song_current>4?song_current-4:0;
    for(i=start;i<song_count && i<start+7;i++){
        unsigned y=129+(i-start)*8;
        ta_u8 col=(i==song_current)?14:10;
        if(i==song_current)box(5,y-1,306,8,1);
        sprintf(n,"%u.",i+1);
        label(10,y,n,col,3);
        label(29,y,leaf(songs[i]),col,43);
    }
}
/* Panel contents and hardware-driven meters are independent.
   The pane is only cleared on track change or VIS/playlist toggle. */
static void draw_panel(void)
{
    unsigned i;
    header(113,show_equalizer?"TANDYAMP VOICE MONITOR":"TANDYAMP PLAYLIST");
    if(!show_equalizer){
        draw_playlist();
        return;
    }
    box(3,127,314,59,0);
    label(8,129,ta.speaker_enabled?
          "3 PSG TONES + PC SPEAKER":"3 PSG TONE CHANNELS",7,35);
    for(i=0;i<3;i++){
        unsigned x=26+i*95;
        char n[4];
        box(x,141,40,33,8);
        sprintf(n,"CH%u",i+1);
        label(x+8,177,n,14,3);
        meter_last_note[i]=-2;
        meter_last_velocity[i]=255;
        meter_last_active[i]=255;
    }
}
static void draw_meters(void)
{
    unsigned i;
    if(!show_equalizer)return;
    for(i=0;i<3;i++){
        unsigned x=26+i*95,h;
        TAVoice *v=&ta.voices[i];
        ta_u8 playing=(ta_u8)(ta.playing && !ta.paused && v->note>=0);
        if(meter_last_note[i]==v->note &&
           meter_last_velocity[i]==v->velocity &&
           meter_last_active[i]==playing)continue;
        /* Only this voice's 40x33 bar is touched, not the whole pane. */
        box(x,141,40,33,8);
        if(playing){
            h=8U+(unsigned)v->velocity*24U/127U
              +((unsigned)v->note%4U)*2U;
            if(h>31U)h=31U;
            box(x+2,174-h,36,h,10);
            box(x+2,174-h,36,1,14);
        }
        meter_last_note[i]=v->note;
        meter_last_velocity[i]=v->velocity;
        meter_last_active[i]=playing;
    }
}
static void draw_track_info(void)
{
    char filename[64];
    const char *mode;
    box(129,24,179,35,0);
    label(135,25,"NOW PLAYING",7,24);
    if(song_count){
        strncpy(filename,leaf(songs[song_current]),27);
        filename[27]=0;
    }else strcpy(filename,"NO MIDI FILE");
    label(135,38,filename,10,27);
    if(ta.drum_mode==TA_DRUM_AUTO)
        mode=ta.drum16?"DR16 AUTO ON":"DR16 AUTO OFF";
    else if(ta.drum_mode==TA_DRUM_ON)mode="DR16 FORCED ON";
    else mode="DR16 FORCED OFF";
    label(135,51,mode,7,15);
    {
        char volume[8];
        sprintf(volume,"VOL %02u",15U-ta.master_attenuation);
        label(250,51,volume,7,7);
    }
}
static void draw_clock(void)
{
    char tm[20];
    ta_u32 secs=song_ticks/18UL;
    if(ui_last_seconds==secs)return;
    box(17,27,95,10,0);
    sprintf(tm,"%02lu:%02lu",secs/60UL,secs%60UL);
    label(20,28,tm,10,8);
    ui_last_seconds=secs;
}
static void draw_state(void)
{
    box(17,45,95,13,0);
    label(19,47,ta.playing?(ta.paused?"PAUSED":"PLAYING"):"STOPPED",14,12);
}
static void draw_progress(void)
{
    unsigned marker;
    if(old_marker!=0xffffU){
        box(10+old_marker,68,12,1,8);
        old_marker=0xffffU;
    }
    if(ta.loaded && ta.playing && !ta.paused){
        /* A small activity marker only; no costly full-width repaint. */
        marker=(unsigned)((song_ticks/6UL)%286UL);
        box(10+marker,68,12,1,14);
        old_marker=marker;
    }
}
/* Software pointer: restore only the pixels actually covered.
   Not dependent on the DOS mouse driver's graphics-cursor renderer. */
static ta_u8 mouse_read_pixel(unsigned x,unsigned y)
{
    unsigned off=((y&3U)*VRAM_BANK)+((y>>2)*VRAM_STRIDE)+(x>>1);
    ta_u8 b=vram[off];
    return (ta_u8)((x&1U)?(b&15U):(b>>4));
}
static void mouse_cursor_remove(void)
{
    unsigned i,j;
    if(!mouse_cursor_visible)return;
    for(i=0;i<TA_POINTER_H;i++)
        for(j=0;j<TA_POINTER_W;j++)
            if(mouse_shape[i]&(0x80U>>j))
                plot(mouse_x+j,mouse_y+i,mouse_under[i][j]);
    mouse_cursor_visible=0;
}
static void mouse_cursor_draw(void)
{
    unsigned i,j;
    if(!mouse_present || mouse_cursor_visible)return;
    for(i=0;i<TA_POINTER_H;i++)
        for(j=0;j<TA_POINTER_W;j++){
            ta_u8 edge,mask=mouse_shape[i];
            unsigned px=mouse_x+j,py=mouse_y+i;
            if(!(mask&(0x80U>>j)))continue;
            mouse_under[i][j]=mouse_read_pixel(px,py);
            edge=(ta_u8)(j==0U || i==0U || j==7U ||
                !(mask&(0x80U>>(j-1U))) ||
                (j<7U && !(mask&(0x80U>>(j+1U)))) ||
                (i<10U && !(mouse_shape[i+1U]&(0x80U>>j))));
            plot(px,py,(ta_u8)(edge?0:15));
        }
    mouse_cursor_visible=1;
}
static void mouse_move_to(unsigned x,unsigned y)
{
    if(!mouse_present)return;
    if(x>320U-TA_POINTER_W)x=320U-TA_POINTER_W;
    if(y>200U-TA_POINTER_H)y=200U-TA_POINTER_H;
    if(x==mouse_x && y==mouse_y && mouse_cursor_visible)return;
    mouse_cursor_remove();
    mouse_x=x;mouse_y=y;
    mouse_cursor_draw();
}
static unsigned mouse_logical_x(unsigned raw)
{
    unsigned x=raw/mouse_x_divisor;
    return x>319U?319U:x;
}
static int meter_changed(void)
{
    unsigned i;
    if(!show_equalizer)return 0;
    for(i=0;i<3;i++){
        const TAVoice *v=&ta.voices[i];
        ta_u8 active=(ta_u8)(ta.playing && !ta.paused && v->note>=0);
        if(v->note!=meter_last_note[i] ||
           v->velocity!=meter_last_velocity[i] ||
           active!=meter_last_active[i])return 1;
    }
    return 0;
}
static void draw_dirty(void)
{
    unsigned flags=ui_dirty;
    int clock_changed,progress_changed;
    if(text_mode)return;
    clock_changed=(ui_last_seconds!=song_ticks/18UL);
    progress_changed=(ta.playing && !ta.paused &&
        (unsigned)((song_ticks/6UL)%286UL)!=old_marker);
    /* A no-op really is zero VRAM writes, including cursor updates. */
    if(!flags && !clock_changed && !progress_changed && !meter_changed())
        return;
    /* Prevent cursor trails when dirty rectangles overlap the pointer. */
    mouse_cursor_remove();
    if(flags&UI_PANEL)draw_panel();
    if(flags&UI_BUTTONS)draw_buttons();
    else {
        if(flags&UI_SPK4)draw_button(8);
        if(flags&UI_MUTE)draw_button(9);
    }
    if(flags&UI_TRACK)draw_track_info();
    if((flags&UI_CLOCK) || clock_changed)draw_clock();
    if(flags&UI_STATE)draw_state();
    if(flags&UI_PROGRESS || progress_changed)draw_progress();
    if(show_equalizer)draw_meters();
    ui_dirty=0;
    mouse_cursor_draw();
}
static void draw_all(void)
{
    if(text_mode)return;
    draw_base();             /* called ONCE on entering graphics mode */
    button_cache_valid=0;
    ui_dirty=UI_ALL;
    ui_last_seconds=0xffffffffUL;
    old_marker=0xffffU;
    draw_dirty();
}

static int same(const char *a,const char *b)
{
    while(*a&&*b){
        if(toupper((unsigned char)*a)!=toupper((unsigned char)*b))return 0;
        a++;b++;
    }
    return !*a&&!*b;
}
/* With no explicit file arguments, discover DOS 8.3 .MID files in the
   CURRENT working directory.  Do not recurse and do not scan when the
   user supplied an explicit sequence.  Sorting avoids FAT directory-order
   surprises between boots; explicit arguments preserve their order. */
static int ends_with_mid(const char *name)
{
    size_t n=strlen(name);
    return n>=5U && name[n-4]=='.'
        && toupper((unsigned char)name[n-3])=='M'
        && toupper((unsigned char)name[n-2])=='I'
        && toupper((unsigned char)name[n-1])=='D';
}
static int song_compare(const char *a,const char *b)
{
    int x,y;
    do {
        x=toupper((unsigned char)*a++);
        y=toupper((unsigned char)*b++);
        if(x!=y)return x-y;
    }while(x!=0);
    return 0;
}
static void playlist_add_sorted(const char *name)
{
    unsigned i,j;
    if(!ends_with_mid(name) || strlen(name)>=PATHLEN)return;
    if(song_count>=MAX_SONGS){playlist_truncated=1;return;}
    for(i=0;i<song_count;i++){
        if(song_compare(name,songs[i])<0)break;
    }
    for(j=song_count;j>i;j--)
        memcpy(songs[j],songs[j-1],PATHLEN);
    strcpy(songs[i],name);
    song_count++;
}
static unsigned playlist_find_current_directory(void)
{
    song_count=0;
    song_current=0;
    playlist_truncated=0;
#ifdef __WATCOMC__
    {
        struct find_t found;
        unsigned status=_dos_findfirst("*.MID",0,&found);
        while(status==0){
            if(!(found.attrib&_A_SUBDIR))
                playlist_add_sorted(found.name);
            status=_dos_findnext(&found);
        }
    }
#else
    {
        DIR *dir=opendir(".");
        struct dirent *entry;
        if(dir){
            while((entry=readdir(dir))!=NULL){
                struct stat st;
                if(ends_with_mid(entry->d_name)
                   && stat(entry->d_name,&st)==0
                   && S_ISREG(st.st_mode))
                    playlist_add_sorted(entry->d_name);
            }
            closedir(dir);
        }
    }
#endif
    return song_count;
}

static void usage(void)
{
    puts("TandyAMP -- Tandy 1000 EX three-voice DOS MIDI player");
    puts("Usage: TANDYAMP [options] [FILE.MID ...]");
    puts("       No filenames: play *.MID in the current directory.");
    puts("Options: /TXT      text-only player (no Tandy graphics)");
    puts("         /GUI      Tandy 320x200 16-color screen (default)");
    puts("         /LOOP     repeat the entire playlist");
    puts("         /NOMOUSE  disable DOS mouse detection / pointer");
    puts("         /SPK4     enable fourth PC speaker tone");
    puts("         /NOSPK4   disable PC speaker tone (default)");
    puts("         /DRUM16   force legacy channel 16 drums on");
    puts("         /NODRUM16 force channel 16 drums off");
    puts("         /AUTODRUM16 auto drum routing (default)");
    puts("         /VOL:0..15 master volume, 0=mute (default 15)");
    puts("         /HELP     display this help");
    puts("Auto level limiting always on. No playlist recursion or seek.");
    puts("Keys: SPACE pause, S stop, R replay, N next, P previous");
    puts("      E voice monitor, L loop, D drums AUTO/ON/OFF");
    puts("      K toggle fourth PC speaker voice (SPK4 button)");
    puts("      M mute/unmute with previous volume restored");
    puts("      + or - change volume; Q or ESC quit.");
    puts("Playlist: 64 files max, alphabetical if auto-discovered.");
    puts("MIDI format 0/1, up to 24 tracks, up to 44 KB per file.");
}
static int start_song(unsigned n)
{
    if(song_count==0)return 0;
    if(n>=song_count)n=0;
    song_current=n;
    if(!ta_load(songs[song_current])){
        if(text_mode)printf("Cannot play %s: %s\n",songs[song_current],ta_error());
        stopped=1;
        return 0;
    }
    ta_begin();
    song_ticks=0;
    song_tick_part=0;
    stopped=0;
    if(text_mode)printf("Playing %u/%u: %s [DR16 %s%s]\n",
        song_current+1,song_count,songs[song_current],
        ta.drum_mode==TA_DRUM_AUTO?"AUTO ":"FORCED ",
        ta.drum16?"ON":"OFF");
    ui_dirty|=UI_ALL;
    ui_last_seconds=0xffffffffUL;
    return 1;
}
static void next_song(int backwards)
{
    unsigned n;
    if(!song_count)return;
    n=backwards?(song_current? song_current-1:song_count-1)
               :(song_current+1)%song_count;
    start_song(n);
}
static void input_key(int key)
{
    if(key==0 || key==0xe0)return;
    switch(toupper(key&255)){
    case '+':case '=':
        ta_set_volume(16U-ta.master_attenuation);
        if(ta.master_attenuation<15U)
            last_audible_volume=15U-ta.master_attenuation;
        ui_dirty|=UI_TRACK|UI_MUTE;break;
    case '-':case '_':
        ta_set_volume(ta.master_attenuation<15U?
                      14U-ta.master_attenuation:0U);
        if(ta.master_attenuation<15U)
            last_audible_volume=15U-ta.master_attenuation;
        ui_dirty|=UI_TRACK|UI_MUTE;break;
    case 'M':
        if(ta.master_attenuation==15U)
            ta_set_volume(last_audible_volume?last_audible_volume:15U);
        else{
            last_audible_volume=15U-ta.master_attenuation;
            ta_set_volume(0);
        }
        if(text_mode)printf("MUTE %s\n",
                           ta.master_attenuation==15U?"ON":"OFF");
        ui_dirty|=UI_TRACK|UI_MUTE;break;
    case 'Q':case 27:program_exit=1;break;
    case ' ':ta_pause();ui_dirty|=UI_STATE|UI_BUTTONS|UI_METERS|UI_PROGRESS;break;
    case 'S':ta_stop();stopped=1;ui_dirty|=UI_STATE|UI_BUTTONS|UI_METERS|UI_PROGRESS;break;
    case 'R':if(song_count)start_song(song_current);break;
    case 'N':next_song(0);break;
    case 'P':next_song(1);break;
    case 'L':loop_mode=!loop_mode;ui_dirty|=UI_BUTTONS;break;
    case 'E':show_equalizer=!show_equalizer;ui_dirty|=UI_PANEL|UI_BUTTONS|UI_METERS;break;
    case 'K':
        ta_set_speaker(!ta.speaker_enabled);
        if(text_mode)printf("SPK4 %s\n",ta.speaker_enabled?"ON":"OFF");
        ui_dirty|=UI_SPK4;
        if(show_equalizer)ui_dirty|=UI_PANEL; /* update monitor label */
        break;
    case 'D':
        ta.drum_mode=(ta_u8)((ta.drum_mode+1U)%3U);
        if(song_count)start_song(song_current);
        ui_dirty|=UI_TRACK|UI_BUTTONS|UI_STATE;
        break;
    }
}

/* All buttons can be driven by keyboard, or clicked via INT 33h driver. */
static int button_at(unsigned x,unsigned y)
{
    unsigned i;
    for(i=0;i<UI_BUTTON_COUNT;i++){
        unsigned bx=button_x(i),by=button_y(i);
        if(x>=bx && x<bx+UI_BUTTON_WIDTH &&
           y>=by && y<by+UI_BUTTON_HEIGHT)return (int)i;
    }
    return -1;
}
static void click_button(int id)
{
    if(id==0)input_key('P');
    else if(id==1){
        if(ta.playing && ta.paused)input_key(' ');
        else if(!ta.playing)input_key('R');
    }else if(id==2)input_key(' ');
    else if(id==3)input_key('S');
    else if(id==4)input_key('N');
    else if(id==5)input_key('E');
    else if(id==6)input_key('L');
    else if(id==7)input_key('D');
    else if(id==8)input_key('K');
    else if(id==9)input_key('M');
}
/* Same button/cursor behavior in native DOS and host regressions.
   INT 33h AX=5 remembers quick presses between position polls. */
static void mouse_sample(unsigned x,unsigned y,int down,
                         unsigned presses,unsigned pressed_x,unsigned pressed_y)
{
    int id=-1;
    if(!mouse_present)return;
    mouse_move_to(x,y);
    if(presses)id=button_at(pressed_x,pressed_y);
    else if(down && !mouse_was_down)id=button_at(x,y);
    if(id>=0)click_button(id);
    mouse_was_down=down;
}
#ifdef __WATCOMC__
static ta_u32 last_mouse_poll=0;
static int mouse_vector_exists(void)
{
    const unsigned short far *v=(const unsigned short far*)MK_FP(0,0x00cc);
    unsigned off=v[0],seg=v[1];
    const unsigned char far *code;
    if(!off && !seg)return 0;
    code=(const unsigned char far*)MK_FP(seg,off);
    return code[0]!=0xcfU;  /* uninstalled IRET vector */
}
static void mouse_call(union REGS *r)
{
    int86(0x33,r,r);
}
static void mouse_initialize(void)
{
    union REGS r;
    unsigned old_x,old_y,max_x;
    if(!mouse_enabled || !mouse_vector_exists())return;
    r.x.ax=0;mouse_call(&r); /* driver reset, cursor remains hidden */
    if(!r.x.ax)return;
    r.x.ax=7;r.x.cx=0;r.x.dx=639;mouse_call(&r);
    r.x.ax=8;r.x.cx=0;r.x.dx=199;mouse_call(&r);
    r.x.ax=3;mouse_call(&r);
    old_x=r.x.cx;old_y=r.x.dx;
    /* Probe right edge to recognize both 0..639 and 0..319 drivers. */
    r.x.ax=4;r.x.cx=639;r.x.dx=old_y;mouse_call(&r);
    r.x.ax=3;mouse_call(&r);
    max_x=r.x.cx;
    mouse_x_divisor=max_x>400U?2U:1U;
    if(mouse_x_divisor==1U){
        r.x.ax=7;r.x.cx=0;r.x.dx=319;mouse_call(&r);
        if(old_x>319U)old_x=319U;
    }
    r.x.ax=4;r.x.cx=old_x;r.x.dx=old_y;mouse_call(&r);
    /* Do NOT use AX=1 (driver-drawn graphics cursor).  Mode 09h is a
       Tandy-specific banked framebuffer that many drivers cannot draw. */
    mouse_present=1;
    r.x.ax=3;mouse_call(&r);
    mouse_x=mouse_logical_x(r.x.cx);
    if(mouse_x>320U-TA_POINTER_W)mouse_x=320U-TA_POINTER_W;
    mouse_y=r.x.dx>200U-TA_POINTER_H?200U-TA_POINTER_H:r.x.dx;
    mouse_was_down=(r.x.bx&1U)!=0;
    mouse_cursor_draw();
}
static void mouse_poll(ta_u32 clock)
{
    union REGS pos,press;
    unsigned presses,x,y;
    int down;
    if(!mouse_present || clock-last_mouse_poll<64UL)return;
    last_mouse_poll=clock; /* ~14ms sampling, no extra IRQ */
    pos.x.ax=3;mouse_call(&pos);
    down=(pos.x.bx&1U)!=0;
    press.x.ax=5;press.x.bx=0;mouse_call(&press);
    presses=press.x.bx;
    x=mouse_logical_x(pos.x.cx);
    y=pos.x.dx>199U?199U:pos.x.dx;
    mouse_sample(x,y,down,presses,mouse_logical_x(press.x.cx),
                 press.x.dx>199U?199U:press.x.dx);
}
static void mouse_shutdown(void)
{
    mouse_cursor_remove();
    mouse_present=0;
}
#else
static void mouse_initialize(void){}
static void mouse_poll(ta_u32 clock){(void)clock;}
static void mouse_shutdown(void){mouse_cursor_remove();mouse_present=0;}
#endif

int main(int argc,char **argv)
{
    int i,key;
    ta_u32 then,now,elapsed;
    unsigned next_index;
    for(i=1;i<argc;i++){
        const char *s=argv[i];
        if(same(s,"/HELP")||same(s,"-H")||same(s,"/?")){usage();return 0;}
        if(same(s,"/TXT")||same(s,"-T")||same(s,"/TEXT")){text_mode=1;continue;}
        if(same(s,"/GUI")||same(s,"-G")){text_mode=0;continue;}
        if(same(s,"/LOOP")||same(s,"-L")){loop_mode=1;continue;}
        if(same(s,"/NOMOUSE")){mouse_enabled=0;continue;}
        if(same(s,"/SPK4")){ta_set_speaker(1);continue;}
        if(same(s,"/NOSPK4")){ta_set_speaker(0);continue;}
        if(same(s,"/DRUM16")){ta.drum_mode=TA_DRUM_ON;continue;}
        if(same(s,"/NODRUM16")){ta.drum_mode=TA_DRUM_OFF;continue;}
        if(same(s,"/AUTODRUM16")){ta.drum_mode=TA_DRUM_AUTO;continue;}
        if(strlen(s)>=5 && s[0]=='/' && toupper(s[1])=='V' &&
           toupper(s[2])=='O' && toupper(s[3])=='L' && s[4]==':'){
            char *end;
            long volume=strtol(s+5,&end,10);
            if(end==s+5 || *end || volume<0 || volume>15){
                puts("Volume must be 0..15.");return 1;
            }
            ta_set_volume((unsigned)volume);continue;
        }
        if(s[0]=='-'||s[0]=='/'){printf("Unknown option: %s\n",s);usage();return 1;}
        if(song_count>=MAX_SONGS){puts("Maximum 64 playlist entries.");return 1;}
        if(strlen(s)>=PATHLEN){puts("Filename too long (63 characters).");return 1;}
        strcpy(songs[song_count++],s);
    }
    if(song_count==0){
        if(!playlist_find_current_directory()){
            puts("No .MID files found in the current directory.");
            usage();
            return 1;
        }
        printf("Found %u MIDI file(s) in current directory.\n",song_count);
        if(playlist_truncated)
            puts("Playlist is limited to 64 songs; extra files were skipped.");
    }
    if(!start_song(0))return 1;
    if(!text_mode){
        set_mode(9);
        draw_all();
        mouse_initialize();
        /* Visible driver-status indicator (no need to guess if detected). */
        mouse_cursor_remove();
        box(217,7,70,8,1);
        label(220,7,mouse_present?"MOUSE OK":"NO MOUSE",
              mouse_present?10:14,8);
        mouse_cursor_draw();
    }else usage();
    timer_start();
    then=get_clock_q8();
    while(!program_exit){
        now=get_clock_q8();
        /* BIOS time wraps at midnight. Ignore the unusual wrap sample. */
        elapsed=(now>=then)?now-then:0;
        then=now;
        if(elapsed){
            if(elapsed>12800UL)elapsed=12800UL;
            /* Schedule events in <= 6.9ms slices, even during dense chords. */
            while(elapsed){
                ta_u16 slice=(ta_u16)(elapsed>32UL?32UL:elapsed);
                int was_playing=ta.playing;
                elapsed-=slice;
                if(ta.playing && !ta.paused){
                    song_tick_part+=slice;
                    if(song_tick_part>=256U){
                        song_ticks++;
                        song_tick_part-=256U;
                    }
                }
                ta_advance(slice);
                if(was_playing && !ta.playing && !stopped){
                    if(song_current+1<song_count || loop_mode){
                        next_index=(song_current+1)%song_count;
                        start_song(next_index);
                    }else{
                        stopped=1;ui_dirty|=UI_STATE|UI_BUTTONS|UI_PROGRESS|UI_METERS;
                    }
                }
            }
            if(text_mode){
                if(song_ticks-last_refresh>=18UL){
                    printf("%02lu:%02lu %s\r",song_ticks/1080UL,
                           (song_ticks/18UL)%60UL,songs[song_current]);
                    fflush(stdout);
                    last_refresh=song_ticks;
                }
            }else if(ui_dirty || song_ticks<last_refresh
                         || song_ticks-last_refresh>=5UL){
                draw_dirty();  /* max ~3.6Hz; only changed rectangles */
                last_refresh=song_ticks;
            }
        }
        if(!text_mode){
            mouse_poll(now);
            if(ui_dirty){
                draw_dirty();
                last_refresh=song_ticks;
            }
        }
        if(key_ready()){
            key=next_key();
            if(key==0 || key==0xe0){(void)next_key();continue;}
            input_key(key);
            if(!text_mode && ui_dirty) {
                draw_dirty();  /* responsive even when paused */
                last_refresh=song_ticks;
            }
        }
#ifndef __WATCOMC__
        /* Host compile/run is only for testability; no real BIOS timer. */
        if(fake_clock>200UL)program_exit=1;
#endif
    }
    mouse_shutdown();
    timer_stop();
    ta_stop();
    ta_pc_speaker(0);
    set_mode(3);
    if(text_mode)puts("\nTandyAMP stopped.");
    return 0;
}

