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
#endif

#define MAX_SONGS 8
#define PATHLEN 64
#define SCREEN_W 320
#define SCREEN_H 200
#define VRAM_BANK 8192U
#define VRAM_STRIDE 160U

static char songs[MAX_SONGS][PATHLEN];
static unsigned song_count=0, song_current=0;
static int text_mode=0, loop_mode=0, show_equalizer=0;
static int stopped=0, program_exit=0, fast_redraw=1;
static ta_u32 song_ticks=0, last_refresh=0;

#ifdef __WATCOMC__
static unsigned char far * const vram=(unsigned char far *)MK_FP(0xB800,0);
static volatile ta_u32 far * const bios_tick=(volatile ta_u32 far*)MK_FP(0x40,0x6c);
static void put_sound(ta_u8 value){outp(0xc0,value);}
static ta_u32 get_ticks(void){return *bios_tick;}
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
static void put_sound(ta_u8 value){(void)value;}
static ta_u32 get_ticks(void){return fake_clock++;}
static void set_mode(unsigned char mode){(void)mode;}
static int key_ready(void){return 0;}
static int next_key(void){return 'q';}
#endif

void ta_psg_tone(int slot,ta_u16 divider,ta_u8 attenuation)
{
    ta_u8 latch,volume;
    if(slot<0||slot>=3)return;
    if(divider<1)divider=1;
    if(divider>1023)divider=1023;
    if(attenuation>15)attenuation=15;
    latch=(ta_u8)(0x80+(slot<<5));
    volume=(ta_u8)(0x90+(slot<<5));
    put_sound((ta_u8)(latch|(divider&15)));
    put_sound((ta_u8)((divider>>4)&63));
    put_sound((ta_u8)(volume|attenuation));
}
void ta_psg_silence(void)
{
    put_sound(0x9f);
    put_sound(0xbf);
    put_sound(0xdf);
    put_sound(0xff);
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
        for(col=left;col+1<right;col+=2)vram[offset+(col>>1)]=both;
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
static void draw_base(void)
{
    unsigned i;
    box(0,0,320,200,8);
    frame(1,1,318,98,8);
    header(3,"TANDYAMP 3-VOICE MIDI");
    frame(7,19,109,44,0);
    frame(123,19,189,44,0);
    box(8,67,302,3,0);
    box(8,67,1,3,14);
    for(i=0;i<7;i++){
        frame(7+i*37,74,33,20,7);
    }
    label(17,80,"PREV",0,4);
    label(54,80,"PLAY",0,4);
    label(90,80,"PAUSE",0,5);
    label(132,80,"STOP",0,4);
    label(170,80,"NEXT",0,4);
    label(207,80,"EQ",0,2);
    label(244,80,"LOOP",0,4);
    frame(1,101,318,97,8);
    header(102,show_equalizer?"TANDYAMP VISUALIZER":"TANDYAMP PLAYLIST");
    label(8,188,"SPACE PAUSE  N NEXT  P PREV  E EQ  Q QUIT",7,49);
}
static void draw_playlist(void)
{
    unsigned i,start;
    char n[5];
    box(3,116,314,70,0);
    if(!song_count){
        label(10,134,"PASS A MIDI FILE ON COMMAND LINE",10,43);
        return;
    }
    start=song_current>4?song_current-4:0;
    for(i=start;i<song_count && i<start+7;i++){
        unsigned y=118+(i-start)*10;
        ta_u8 col=(i==song_current)?14:10;
        if(i==song_current)box(5,y-1,306,9,1);
        sprintf(n,"%u.",i+1);
        label(10,y,n,col,3);
        label(29,y,leaf(songs[i]),col,43);
    }
}
static void draw_visualizer(void)
{
    unsigned x,i,row;
    box(3,116,314,70,0);
    for(i=0;i<3;i++){
        unsigned barx=26+i*95, height=6;
        TAVoice *v=&ta.voices[i];
        char buf[15];
        if(ta.playing && !ta.paused && v->note>=0)
            height=10+((unsigned)v->note%6U)*7U;
        box(barx,125,38,51,8);
        box(barx,176-height,38,height,10);
        for(row=131;row<177;row+=9)box(barx,row,38,1,0);
        sprintf(buf,"CH%u",i+1);
        label(barx,177,buf,14,3);
    }
    label(9,118,"THREE-VOICE LEVELS - NOT AUDIO EQ",7,49);
}
static void draw_status(void)
{
    char tm[25],filename[64];
    unsigned i;
    ta_u32 secs=song_ticks/18UL;
    if(text_mode)return;
    box(12,24,100,34,0);
    sprintf(tm,"%02lu:%02lu",secs/60UL,secs%60UL);
    label(20,28,tm,10,8);
    label(19,47,ta.playing?(ta.paused?"PAUSED":"PLAYING"):"STOPPED",14,12);
    box(129,24,179,35,0);
    if(song_count){
        strncpy(filename,leaf(songs[song_current]),30);
        filename[30]=0;
    } else strcpy(filename,"NO MIDI FILE");
    label(135,25,filename,10,29);
    label(135,39,ta.playing?"TANDY 3CH  MIDI  16 COLORS":"READY",7,29);
    box(10,68,298,1,8);
    if(ta.loaded && ta.playing){
        /* No duration scan yet. Pulsing activity segment; not a seek bar. */
        i=(unsigned)((song_ticks>>1)%286UL);
        box(10+i,68,12,1,14);
    }
    if(show_equalizer)draw_visualizer();
}
static void draw_all(void)
{
    if(text_mode)return;
    draw_base();
    if(show_equalizer)draw_visualizer();
    else draw_playlist();
    draw_status();
}
static int same(const char *a,const char *b)
{
    while(*a&&*b){
        if(toupper((unsigned char)*a)!=toupper((unsigned char)*b))return 0;
        a++;b++;
    }
    return !*a&&!*b;
}
static void usage(void)
{
    puts("TandyAMP v0.1 -- Tandy 1000 EX three-voice MIDI player");
    puts("Usage: TANDYAMP [options] FILE.MID [NEXT.MID ...]");
    puts("Options: /TXT     text-only player (no Tandy graphics)");
    puts("         /GUI     Tandy 320x200 16-color display (default)");
    puts("         /LOOP    repeat entire playlist");
    puts("         /HELP    this help");
    puts("Keys: SPACE pause/resume, S stop, R replay, N next, P previous");
    puts("      E visualizer/playlist, L loop toggle, Q or ESC quit");
    puts("Supports MIDI format 0 and 1, 12 tracks, files <= 28 KB.");
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
    stopped=0;
    if(text_mode)printf("Playing %u/%u: %s\n",song_current+1,song_count,songs[song_current]);
    fast_redraw=1;
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
    case 'Q':case 27:program_exit=1;break;
    case ' ':ta_pause();fast_redraw=1;break;
    case 'S':ta_stop();stopped=1;fast_redraw=1;break;
    case 'R':if(song_count)start_song(song_current);break;
    case 'N':next_song(0);break;
    case 'P':next_song(1);break;
    case 'L':loop_mode=!loop_mode;fast_redraw=1;break;
    case 'E':show_equalizer=!show_equalizer;fast_redraw=1;break;
    }
}
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
        if(s[0]=='-'||s[0]=='/'){printf("Unknown option: %s\n",s);usage();return 1;}
        if(song_count>=MAX_SONGS){puts("Maximum 8 playlist entries.");return 1;}
        if(strlen(s)>=PATHLEN){puts("Filename too long (63 characters).");return 1;}
        strcpy(songs[song_count++],s);
    }
    if(song_count==0){usage();return 0;}
    if(!start_song(0))return 1;
    if(!text_mode){
        set_mode(9);
        draw_all();
    }else usage();
    then=get_ticks();
    while(!program_exit){
        now=get_ticks();
        elapsed=now-then;
        if(elapsed){
            if(elapsed>50UL)elapsed=50UL;
            then=now;
            while(elapsed--){
                int was_playing=ta.playing;
                if(ta.playing && !ta.paused)song_ticks++;
                ta_tick();
                if(was_playing && !ta.playing && !stopped){
                    if(song_current+1<song_count || loop_mode){
                        next_index=(song_current+1)%song_count;
                        start_song(next_index);
                    }else{
                        stopped=1;fast_redraw=1;
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
            }else if(fast_redraw || song_ticks-last_refresh>=5UL){
                if(fast_redraw){draw_all();fast_redraw=0;}
                else draw_status();
                last_refresh=song_ticks;
            }
        }
        if(key_ready()){
            key=next_key();
            if(key==0 || key==0xe0){(void)next_key();continue;}
            input_key(key);
        }
#ifndef __WATCOMC__
        /* Host compile/run is only for testability; no real BIOS timer. */
        if(fake_clock>200UL)program_exit=1;
#endif
    }
    ta_stop();
    set_mode(3);
    if(text_mode)puts("\nTandyAMP stopped.");
    return 0;
}
