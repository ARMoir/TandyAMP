/* TandyAMP screen-layout and incremental-redraw tests.
   Host-only; draws the actual C89 UI to the simulated four-bank Tandy VRAM. */
#define TANDYAMP_UI_TEST 1
#define main tandyamp_dos_main
#include "../src/main.c"
#undef main
#include <assert.h>
#include <unistd.h>

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
    static const char *reference[UI_BUTTON_COUNT]={
        "PREV","PLAY","PAUSE","STOP","NEXT",
        "VIS","LOOP","DRUM","SPK4 OFF","MUTE OFF"
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

    /* Exact 5x2 grid: no button text crosses its 58x17 inset.
       Transport row is separate from the functional mode/mute row. */
    assert(UI_BUTTON_COUNT==10U && UI_BUTTON_COLS==5U);
    assert(UI_BUTTON_WIDTH==58U && UI_BUTTON_HEIGHT==17U);
    assert(UI_BUTTON_Y==72U && button_y(5)==91U);
    assert(button_x(0)==button_x(5));
    assert(button_x(4)+UI_BUTTON_WIDTH<320U);
    for(i=0;i<UI_BUTTON_COUNT;i++){
        unsigned y=button_y(i),tx,ty;
        ta_u8 basecolor=(ta_u8)(i==1?15:0);
        x=button_x(i);
        textw=(unsigned)strlen(reference[i])*6U-1U;
        start=x+(UI_BUTTON_WIDTH-textw)/2U;
        tx=start;
        ty=y+(UI_BUTTON_HEIGHT-7U)/2U;
        assert(!strncmp(reference[i],button_labels[i],
                        strlen(button_labels[i])));
        assert(start>x+2U && start+textw<x+UI_BUTTON_WIDTH-2U);
        assert(button_at(x+UI_BUTTON_WIDTH/2U,
                         y+UI_BUTTON_HEIGHT/2U)==(int)i);
        assert(button_at(x,y)==(int)i);
        assert(button_at(x+UI_BUTTON_WIDTH-1,
                         y+UI_BUTTON_HEIGHT-1)==(int)i);
        assert(color_at(x+UI_BUTTON_WIDTH-1,ty)==0);
        if(i%UI_BUTTON_COLS<UI_BUTTON_COLS-1)
            assert(color_at(x+UI_BUTTON_WIDTH,ty)==8);
        if(i<8)
            assert(colored_pixels(tx,ty,textw,7,basecolor)>4);
        else{
            assert(colored_pixels(tx,ty,23,7,0)>4);
            assert(colored_pixels(tx+30,ty,17,7,4)>3);
        }
    }
    assert(button_at(8,80)==-1);
    assert(button_at(39,90)==-1); /* gap between rows */
    assert(button_at(300,110)==-1);
    assert(button_at(159,80)==2); /* pause */
    assert(button_at(159,99)==7); /* drum */
    assert(button_at(button_x(8)+24,button_y(8)+8)==8);
    assert(button_at(button_x(9)+24,button_y(9)+8)==9);

    /* The SPK4 button joins its peers in the second row. A toggle only
       changes its 58x17 rectangle, not the other nine buttons. */
    {
        ta_u32 clock=ta.clock_q8;
        unsigned long before=ui_pixels_written,paint;
        assert(ta.speaker_enabled==0);
        click_button(8);
        assert(ta.speaker_enabled==1 && ta.clock_q8==clock);
        draw_dirty();
        paint=ui_pixels_written-before;
        assert(paint>0 && paint<2600UL);
        assert(colored_pixels(button_x(8)+8,button_y(8)+5,23,7,15)>4);
        assert(colored_pixels(button_x(8)+38,button_y(8)+5,11,7,10)>3);
        before=ui_pixels_written;
        click_button(8);
        assert(ta.speaker_enabled==0 && ta.clock_q8==clock);
        draw_dirty();
        assert(ui_pixels_written-before<2600UL);
        assert(colored_pixels(button_x(8)+38,button_y(8)+5,17,7,4)>3);
    }
    /* MUTE is real and remembers the prior volume, not a dead filler. */
    {
        unsigned v=15U-ta.master_attenuation;
        unsigned long before=ui_pixels_written;
        assert(v>0);
        click_button(9);
        assert(ta.master_attenuation==15);
        draw_dirty();
        assert(ui_pixels_written-before<10000UL); /* includes volume text */
        assert(colored_pixels(button_x(9)+38,button_y(9)+5,11,7,14)>3);
        click_button(9);
        assert(ta.master_attenuation==15U-v);
        draw_dirty();
        assert(colored_pixels(button_x(9)+38,button_y(9)+5,17,7,4)>3);
    }
    assert(button_at(20,109)==-1);

    /* Mode indicator/button repaints don't require a full-screen redraw. */
    ta.drum_mode=TA_DRUM_ON;
    ta.drum16=1;
    ui_dirty=UI_BUTTONS|UI_TRACK;
    draw_dirty();
    assert(colored_pixels(button_x(7)+8,button_y(7)+5,30,7,15)>3);
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
    assert(delta>0 && delta<3500UL);

    /* A pause changes its indicator but never forces a full repaint. */
    ta.paused=1;
    ui_dirty=UI_STATE|UI_BUTTONS|UI_METERS|UI_PROGRESS;
    prior=ui_pixels_written;
    draw_dirty();
    delta=ui_pixels_written-prior;
    /* Cached per-button paint: pausing updates transport state only,
       not the second row or a full 320x200 frame. */
    assert(delta>0 && delta<13000UL);

    /* Volume changes while paused stay silent and repaint only track text. */
    ta.master_attenuation=0;
    input_key('-');assert(ta.master_attenuation==1);
    prior=ui_pixels_written;draw_dirty();
    assert(ui_pixels_written-prior<10000UL);
    assert(colored_pixels(250,51,42,7,7)>5);
    for(i=0;i<30;i++)input_key('-');
    assert(ta.master_attenuation==15);
    for(i=0;i<30;i++)input_key('+');
    assert(ta.master_attenuation==0);
    input_key('M');assert(ta.master_attenuation==15);
    input_key('M');assert(ta.master_attenuation==0);

    /* Pointer is a software sprite over the actual banked framebuffer.
       Moving it must restore exactly the original pixels underneath. */
    {
        static ta_u8 screenshot[32768];
        draw_dirty();
        memcpy(screenshot,host_screen,sizeof screenshot);
        mouse_present=1;
        mouse_cursor_visible=0;
        mouse_x=160;mouse_y=100;
        mouse_cursor_draw();
        assert(mouse_cursor_visible);
        assert(memcmp(screenshot,host_screen,sizeof screenshot)!=0);
        mouse_cursor_remove();
        assert(!memcmp(screenshot,host_screen,sizeof screenshot));

        mouse_move_to(159,80);
        assert(mouse_cursor_visible);
        mouse_cursor_remove();
        assert(!memcmp(screenshot,host_screen,sizeof screenshot));
        mouse_move_to(159,80);
        ui_dirty|=UI_BUTTONS;
        draw_dirty();
        assert(mouse_cursor_visible);
        mouse_cursor_remove();
        assert(!memcmp(screenshot,host_screen,sizeof screenshot));
        mouse_cursor_draw();

        /* No idle redraw, including no needless cursor erase/repaint. */
        prior=ui_pixels_written;
        draw_dirty();
        assert(ui_pixels_written==prior);

        /* Native drivers expose either 640-unit or 320-unit X values. */
        mouse_x_divisor=2;
        assert(mouse_logical_x(639)==319);
        assert(mouse_logical_x(186)==93);
        mouse_x_divisor=1;
        assert(mouse_logical_x(319)==319);
        mouse_x_divisor=2;

        /* Holding a button is one click; fast press/release counted via
           INT 33h AX=5 is not dropped between polling intervals. */
        ta.playing=1;ta.paused=0;mouse_was_down=0;
        mouse_sample(159,80,1,1,159,80);
        assert(ta.paused==1);
        mouse_sample(159,80,1,0,159,80);
        assert(ta.paused==1);
        mouse_sample(159,80,0,0,159,80);
        mouse_sample(159,80,0,1,159,80);
        assert(ta.paused==0);
        draw_dirty();

        /* Click second-row SPK4 through the serial mouse interface,
           then MUTE. The old title-bar location is no longer clickable. */
        mouse_was_down=0;
        mouse_sample(button_x(8)+17,button_y(8)+8,1,1,
                     button_x(8)+17,button_y(8)+8);
        assert(ta.speaker_enabled==1);
        draw_dirty();
        mouse_sample(button_x(8)+17,button_y(8)+8,0,0,
                     button_x(8)+17,button_y(8)+8);
        mouse_sample(button_x(8)+17,button_y(8)+8,0,1,
                     button_x(8)+17,button_y(8)+8);
        assert(ta.speaker_enabled==0);
        draw_dirty();
        mouse_sample(button_x(9)+17,button_y(9)+8,0,1,
                     button_x(9)+17,button_y(9)+8);
        assert(ta.master_attenuation==15);
        draw_dirty();
        mouse_sample(button_x(9)+17,button_y(9)+8,0,1,
                     button_x(9)+17,button_y(9)+8);
        assert(ta.master_attenuation==0);
        draw_dirty();
        mouse_cursor_remove();
        mouse_present=0;
        mouse_was_down=0;
    }

    /* Cached PSG writes: unchanged tones and volumes cause NO I/O.
       Volume-only change costs 1 byte, pitch change 2, full note 3.
       A same-mode drum retrigger MUST still reset the noise shift register. */
    {
        unsigned long writes;
        ta_psg_silence();
        test_psg_writes=0;
        ta_psg_tone(0,254,6);
        assert(test_psg_writes==3);
        writes=test_psg_writes;
        ta_psg_tone(0,254,6);
        assert(test_psg_writes==writes);
        ta_psg_tone(0,254,7);
        assert(test_psg_writes==writes+1);
        writes=test_psg_writes;
        ta_psg_tone(0,255,7);
        assert(test_psg_writes==writes+2);
        writes=test_psg_writes;
        ta_psg_noise(5,9);
        assert(test_psg_writes==writes+2);
        writes=test_psg_writes;
        ta_psg_noise(5,9);
        assert(test_psg_writes==writes+1);
        ta_psg_silence();
        writes=test_psg_writes;
        ta_psg_tone(0,254,6);
        assert(test_psg_writes==writes+3);
    }

    /* Directory playlist logic is shared with the DOS build. */
    {
        unsigned j;
        char song[16];
        static const char *order[]={"ALPHA.MID","bravo.mid","Zulu.MID"};
        song_count=0;playlist_truncated=0;
        playlist_add_sorted("Zulu.MID");
        playlist_add_sorted("ALPHA.MID");
        playlist_add_sorted("bravo.mid");
        playlist_add_sorted("README.MD");
        playlist_add_sorted("track.MID.bak");
        assert(song_count==3);
        for(j=0;j<3;j++)assert(!song_compare(songs[j],order[j]));
        for(j=0;j<70;j++){
            sprintf(song,"T%02u.MID",j);
            playlist_add_sorted(song);
        }
        assert(song_count==64 && playlist_truncated==1);
        /* Tests/make_test_mid.py created real .MID test files. */
        assert(chdir("tests")==0);
        assert(playlist_find_current_directory()>=3);
        assert(song_count<=MAX_SONGS);
        assert(!song_compare(songs[0],"bad.mid"));
        for(j=1;j<song_count;j++)
            assert(song_compare(songs[j-1],songs[j])<=0);
        assert(chdir("..")==0);
    }

    printf("PASS: auto-discovered alphabetical MIDI playlist, 64-file cap, "
           "and 10 clickable 5x2 controls including SPK4 and MUTE, title, zero-write idle, "
           "clock-only refresh, per-voice meters, software cursor restore, "
           "captured clicks, coordinate scaling and state-only repaint.\n");
    return 0;
}

