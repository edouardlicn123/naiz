#include <stdint.h>
#include "hal.h"
#include "log.h"
#include "pc98_egc.h"
#include "pc98_gdc.h"
#include "pc98_keyboard.h"
#include "stdbuffer.h"
#include "rootinfo.h"
#include "palette.h"
#include "fontfile.h"
#include "textengine.h"
#include "graphics.h"
#include "scenevm.h"

static void init_display(void)
{
    gdc_set_mode1(GDC_MODE1_COLOUR | GDC_MODE1_LINEDOUBLE_OFF | GDC_MODE1_DISPLAY_ON);
    gdc_set_mode2(GDC_MODE2_16COLOURS | GDC_MODE2_EGC);
    egc_enable();
    egc_set_plane_access(0xF);
    egc_set_mask(0xFFFF);
    egc_set_bg_colour(0);
    egc_set_fg_colour(0xF);
    egc_clear_screen();
}

int main(void)
{
    log_open("ENGINE.LOG");
    log_write(".\r\n");
    log_flush();

    int hal_ok = hal_check_compatibility();
    log_write("A\r\n");
    log_flush();

    log_write("B ");
    log_write(hal_ok ? "OK\r\n" : "FAIL\r\n");
    log_flush();
    if (!hal_ok) return 1;

    log_write("C VIDEO_INIT\r\n");
    log_flush();
    init_display();

    /* DEBUG: Test VRAM and EGC directly */
    egc_set_bg_colour(0x1); /* Blue band */
    egc_clear_lines(10, 20);
    egc_set_bg_colour(0xC); /* Red band */
    egc_clear_lines(40, 20);
    egc_set_bg_colour(0);   /* Reset to black */
    egc_set_to_mono_draw_mode();
    wait_vsync();
    /* END DEBUG */

    log_write("ROOTINFO\r\n");
    log_flush();
    int err = read_root_info();
    if (err) { log_write("ERR: rootinfo\r\n"); return err; }

    init_font_file();

    /* DEBUG: Test text rendering */
    write_string("DEBUG: ABC abc 123 !@#", 0, 16, FORMAT_COLOUR_SET(0xF), 0);
    write_string("The quick brown fox jumps over the lazy dog.", 0, 32, FORMAT_COLOUR_SET(0x7), 0);
    write_string("0123456789 + - * / < > , . ' ; : [ ]", 0, 48, FORMAT_COLOUR_SET(0xE), 0);
    wait_vsync();
    /* END DEBUG */

    log_write("INIT_LANG\r\n");
    log_flush();
    err = init_language(0);
    log_write("LANG_DONE\r\n");
    log_flush();
    if (err) { log_write("ERR: lang\r\n"); return err; }

    log_write("PRE_GFX\r\n");
    log_flush();
    log_write("GRAPHICS\r\n");
    log_flush();
    err = init_graphics_system();
    log_write("GFX_DONE\r\n");
    log_flush();
    if (err) { log_write("ERR: gfx\r\n"); return err; }

    log_write("PRE_TEXT\r\n");
    log_flush();
    log_write("DOTEXT\r\n");
    log_flush();
    log_write("TEXT\r\n");
    log_flush();
    err = setup_text_info();
    log_write("TEXT_DONE\r\n");
    log_flush();
    if (err) { log_write("ERR: text\r\n"); return err; }

    Rect2Int tb = {{0, 304}, {640, 96}};
    register_text_box(&tb);
    text_box_inner_bounds = (Rect2Int){{8, 312}, {624, 80}};

    Rect2Int cnb = {{16, 272}, {128, 32}};
    register_char_name_box(&cnb);
    char_name_box_inner_bounds = (Rect2Int){{24, 280}, {112, 16}};

    Rect2Int cb = {{128, 80}, {384, 64}};
    register_choice_box(&cb);
    choice_box_inner_bounds = (Rect2Int){{136, 88}, {368, 48}};

    text_box_img_info = &textbox_info;
    char_name_box_img_info = &charnamebox_info;
    choice_box_img_info = &choicebox_info;

    log_write("SCENE\r\n");
    err = setup_scene_engine();
    if (err) { log_write("ERR: scene\r\n"); return err; }

    log_write("MAIN_LOOP\r\n");

    int finish = 0;
    while (!finish)
    {
        scene_async_action_process();

        unsigned char skip = 0;
        update_prev_key_status();
        if (KEY_STATUS[0x1C >> 3] & (1 << (0x1C & 7))) skip = 1;

        if (scene_info.cur_scene != 0xFFFF &&
            (return_status & (SCENE_STATUS_RENDERTEXT | SCENE_STATUS_WIPETEXT)))
        {
            int done = string_write_animation_frame(skip);
            if (done) end_user_wait();
        }

        if (return_status & SCENE_STATUS_MAKING_CHOICE)
        {
            if (KEY_STATUS[0x48 >> 3] & (1 << (0x48 & 7))) switch_choice(SELECT_UP);
            if (KEY_STATUS[0x50 >> 3] & (1 << (0x50 & 7))) switch_choice(SELECT_DOWN);
            if (skip) commit_choice();
        }

        int st = scene_data_process();
        if (st & SCENE_STATUS_FINALEND) finish = 1;
        if (st & SCENE_STATUS_ERROR)
        {
            log_write("ERR: scene\r\n");
            finish = 1;
        }

        wait_vsync();
    }

    log_write("F DONE ");
    log_write_datetime();
    log_write("\r\n");
    log_close();

    free_scene_engine();
    free_graphics_system();

    return 0;
}
