#include <stdint.h>
#include "hal.h"
#include "log.h"
#include "pc98_egc.h"
#include "pc98_grcg.h"
#include "pc98_gdc.h"
#include "pc98_keyboard.h"
#include "x86segments.h"
#include "x86strops.h"
#include "stdbuffer.h"
#include "rootinfo.h"
#include "palette.h"
#include "fontfile.h"
#include "textengine.h"
#include "graphics.h"
#include "scenevm.h"

extern unsigned char prev_key_status[16];
extern unsigned char key_change_status[16];

#define ASYNC_USER 0x80

static int key_pressed(unsigned char scancode)
{
    int byte = scancode >> 3;
    int bit = scancode & 7;
    return (key_change_status[byte] >> bit) & 1;
}

int main(void)
{
    log_open("ENGINE.LOG");
    log_write("Naiz engine starting\r\n");
    log_flush();

    if (!hal_check_compatibility())
    {
        log_write("Compatibility check failed\r\n");
        return 0xFF;
    }

    hal_video_init();
    gdc_start_text();
    log_write("Video init done\r\n");
    log_flush();

    if (read_root_info() != 0)
    {
        log_write("Failed to read ROOTINFO.DAT\r\n");
        return 0xFF;
    }
    init_language(root_info.cur_lang);
    log_write("Rootinfo loaded\r\n");

    init_font_file();
    log_write("Font loaded\r\n");

    set_default_palette();

    {
        Rect2Int text_r = { { 20, 330 }, { 600, 60 } };
        Rect2Int name_r = { { 20, 310 }, { 200, 20 } };
        Rect2Int choice_r = { { 200, 150 }, { 240, 80 } };

        text_box_img_info = register_text_box(&text_r);
        text_box_inner_bounds.pos.x = text_r.pos.x + 8;
        text_box_inner_bounds.pos.y = text_r.pos.y + 8;
        text_box_inner_bounds.size.x = text_r.size.x - 16;
        text_box_inner_bounds.size.y = text_r.size.y - 16;

        char_name_box_img_info = register_char_name_box(&name_r);
        char_name_box_inner_bounds.pos.x = name_r.pos.x + 8;
        char_name_box_inner_bounds.pos.y = name_r.pos.y + 8;
        char_name_box_inner_bounds.size.x = name_r.size.x - 16;
        char_name_box_inner_bounds.size.y = name_r.size.y - 16;

        choice_box_img_info = register_choice_box(&choice_r);
        choice_box_inner_bounds.pos.x = choice_r.pos.x + 8;
        choice_box_inner_bounds.pos.y = choice_r.pos.y + 8;
        choice_box_inner_bounds.size.x = choice_r.size.x - 16;
        choice_box_inner_bounds.size.y = choice_r.size.y - 16;
    }

    if (init_graphics_system() != 0)
    {
        log_write("Failed to init graphics system\r\n");
        return 0xFF;
    }
    log_write("Graphics init done\r\n");

    if (setup_text_info() != 0)
    {
        log_write("Failed to setup text info\r\n");
        return 0xFF;
    }
    log_write("Text info loaded\r\n");

    if (setup_scene_engine() != 0)
    {
        log_write("Failed to setup scene engine\r\n");
        return 0xFF;
    }
    log_write("Scene loaded, entering loop\r\n");

    int text_active = 0;
    int text_full = 0;

    for (;;)
    {
        hal_video_vsync_wait();
        update_prev_key_status();

        int st = scene_data_process();

        if (st & SCENE_STATUS_FINALEND) break;
        if (st & SCENE_STATUS_ERROR)
        {
            log_write("Scene error\r\n");
            break;
        }

        if (st & SCENE_STATUS_RENDERTEXT)
        {
            text_active = 1;
            text_full = 0;
        }

        if (text_active)
        {
            if (string_write_animation_frame(0) != 0)
            {
                text_active = 0;
                text_full = 1;
            }
        }

        if (st & SCENE_STATUS_MAKING_CHOICE)
        {
            if (key_pressed(KC_UP)) switch_choice(SELECT_UP);
            if (key_pressed(KC_DOWN)) switch_choice(SELECT_DOWN);
            if (key_pressed(KC_ENTER) || key_pressed(KC_SPACE)) commit_choice();
        }

        if ((cur_async_actions & ASYNC_USER) && !(st & SCENE_STATUS_MAKING_CHOICE))
        {
            if (!text_active && text_full)
            {
                if (key_pressed(KC_ENTER) || key_pressed(KC_SPACE))
                {
                    end_user_wait();
                    control_process(1);
                    text_full = 0;
                }
            }
        }

        scene_async_action_process();
        do_draw_requests();
    }

    free_scene_engine();
    free_graphics_system();
    log_write("Shutdown\r\n");
    log_flush();
    log_close();
    return 0;
}
