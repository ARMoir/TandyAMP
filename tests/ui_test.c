/* TandyAMP screen-layout and incremental-redraw tests.
   Host-only; draws the actual C89 UI to the simulated four-bank Tandy VRAM. */
#define TANDYAMP_UI_TEST 1
#define main tandyamp_dos_main
#include "../src/main.c"
#undef main
#include <assert.h>

static unsigned color_at(unsigned x,unsigned y)
{
    unsigned off=((y&3U)*VRAM_BANK)+((y>>2)*VRAM_STRIDE)+(x>>1);
    ta_u8 val=host_screen[off];
    return (unsigned)(x&1U?(val&15U):((val>>4)&15U));
}
static unsigned colored_pixels(unsigned x,unsigned y,unsigned w,unsigned h,
                               unsigned color)
{
    unsigned i,j,n=0;
    for(j=y;j<y+h;j++)
        for(i=x;i<x+w;i++)
            if(color_at(i,j)==color)n++;
    return n;
}
int main(void)
{
    unsigned i,x,textw,start;
    unsigned long initial,delta,prior;
    static const char *reference[7]={
        "PREV","PLAY","PAUSE","STOP","NEXT","VIS","LOOP"
    };

    /* Render the same CANYON.MID scene seen on the real hardware video. */
    song_count=1;
    strcpy(songs[0],"CANYON.MID");
    ta.loaded=1;
    ta.playing=1;
    ta.paused=0;
    ta.voices[0].note=60;
    ta.voices[0].velocity=100;
    ta.voices[1].note=64;
    ta.voices[1].velocity=90;
    ta.voices[2].note=67;
    ta.voices[2].velocity=95;
    song_ticks=0;
    draw_all();

    /* All seven 5x7 labels fit WITHIN the button's inside bevel. */
    for(i=0;i<7;i++){
        x=UI_BUTTON_X+i*UI_BUTTON_STEP;
        textw=(unsigned)strlen(reference[i])*6U-1U;
        start=x+(UI_BUTTON_WIDTH-textw)/2U;
        assert(!strcmp(reference[i],button_labels[i]));
        assert(start>x+1 && start+textw<x+UI_BUTTON_WIDTH-1);
        assert(colored_pixels(start,80,textw,7,(i==1)?15:0)>4);
        assert(color_at(x+UI_BUTTON_WIDTH-1,80)==0);
        if(i<6)assert(color_at(x+UI_BUTTON_WIDTH,80)==8);
    }
    assert(UI_BUTTON_X+6*UI_BUTTON_STEP+UI_BUTTON_WIDTH<=SCREEN_W-5);

    /* The upper-right now-playing window must not be empty. */
    assert(colored_pixels(135,38,162,7,10)>10);
    assert(colored_pixels(135,25,135,7,7)>10);
    initial=ui_pixels_written;
    assert(initial>32000UL);

    /* Redrawing unchanged state is a true zero-write operation. */
    prior=ui_pixels_written;
    draw_dirty();
    assert(ui_pixels_written==prior);

    /* One displayed second changes digits and the activity dot only,
       not an entire 320x200 framebuffer or playlist panel. */
    song_ticks=18;
    draw_dirty();
    delta=ui_pixels_written-prior;
    assert(delta>0 && delta<3000UL);
    assert(delta*12UL<initial);
    prior=ui_pixels_written;
    draw_dirty();
    assert(ui_pixels_written==prior);

    /* Changing only the lower panel is allowed once, not on every tick. */
    show_equalizer=1;
    ui_dirty=UI_PANEL|UI_BUTTONS|UI_METERS;
    draw_dirty();
    prior=ui_pixels_written;
    draw_dirty();
    assert(ui_pixels_written==prior);

    /* One voice changes; only its small meter rectangle is repainted. */
    ta.voices[1].note=76;
    ta.voices[1].velocity=110;
    draw_dirty();
    delta=ui_pixels_written-prior;
    assert(delta>0 && delta<2000UL);

    /* A pause changes its indicator but never forces a full repaint. */
    ta.paused=1;
    ui_dirty=UI_STATE|UI_BUTTONS|UI_METERS|UI_PROGRESS;
    prior=ui_pixels_written;
    draw_dirty();
    delta=ui_pixels_written-prior;
    assert(delta>0 && delta<9000UL);

    printf("PASS: 7 centered labels, song title, zero-write idle, "
           "clock-only refresh, per-voice meters, state-only repaint.\n");
    return 0;
}
