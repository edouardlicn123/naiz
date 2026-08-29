/*
 * Naiz Engine 主入口模块
 * — HAL / 字库 / 键盘 / 视频 / 调色板 / 图片归档初始化
 * — 运行时配置读取 (settings.txt)
 * — AUTOEXEC.BAT 启动入口
 * — 主循环: kbd_update → delay → NB 解释器 / scene VM → cursor draw
 * — 初始化顺序有硬性要求，见 AGENTS.md §十一
 */
#include <stdio.h>
#include <string.h>
#include "vm.h"
#include "font.h"
#include "cjk.h"
#include "render.h"
#include "image.h"
#include "hal.h"
#include "nb.h"
#include "nb_anim.h"   /* ANI animation support */
#include "nb_saveload.h"
#include "save.h"
#include "layer_debug.h"
#include "settings.h"
#include "settings_menu.h"

/* Debug logging — shared macro in debug.h */
#include "debug.h"

/*
 * Engine main entry — initialization + main loop.
 * Init order (fixed, do not change):
 *   hal_init -> font_init -> cjk_init -> kbd_init -> video_init
 *   -> palette init -> fill_rect(black) -> palette self-check
 *   -> image_init -> nb_init
 * Two main loop modes:
 *   AUTOEXIT: auto-run until end (testing)
 *   Non-AUTOEXIT: advance text with Space/Enter/XFER
 * @return 0 on normal exit, 1 on error
 */
#define ENGINE_EXIT(s) do { hal_video_exit(); return (s); } while(0)

int main(void)
{

    
    hal_init();
    hal_log("Naiz engine\r\n");

    if (font_init("FONT.DAT") != 0) {
        hal_log("FONT.DAT not found\r\n");
        ENGINE_EXIT(1);
    }
    font_load_alt("BLACK.DAT");   /* non-fatal: alt table optional */
    hal_kbd_init();
    hal_mouse_init();
    hal_log("Init OK\r\n");

    hal_video_init();
    hal_log("Vid OK\r\n");

    /* palette[0]=black first + fill_rect(black) as redundant safety net. */
    hal_set_palette(0, 0x00, 0x00, 0x00);
    fill_rect(0, 0, LAYER_SCREEN_W, LAYER_SCREEN_H, 0);
    hal_log("VRAM OK\r\n");
    hal_set_palette(PAL_BLUE, 0x00, 0x00, 0xFF);
    hal_set_palette(PAL_GREEN, 0x00, 0xFF, 0x00);
    hal_set_palette(PAL_RED, 0xFF, 0x00, 0x00);
    hal_set_palette(PAL_WHITE, 0xFF, 0xFF, 0xFF);
    hal_set_palette(PAL_TRANSPARENT, 0xFF, 0xFF, 0xFF);
    hal_set_palette(PAL_DIALOG_FILL, 0x00, 0x00, 0x00);
    hal_set_palette(PAL_CURSOR_BLACK, 0x00, 0x00, 0x00);

    /* Self-check: read back palette entries to verify 256c I/O path. */
    hal_video_check_palette();
    hal_log("Pal OK\r\n");

    /* Background is drawn by scene bgload opcode. */

    if (image_init("IMAGE.DAT") != 0) {
        hal_log("Img FAIL\r\n");
        ENGINE_EXIT(1);
    } else
        hal_log("Img OK\r\n");

    sys_save_load();

    /* Settings: load existing or show first-launch menu */
    settings_load();
    settings_menu_run();
    settings_save();

    /* CJK: load language-specific file with fallback */
    if (cjk_load_for_lang(settings_get_lang()) != 0) {
        hal_log("CJK not found\r\n");
        ENGINE_EXIT(1);
    }

    if (nb_init() != 0) {
        hal_log("NB init fail\r\n");
        ENGINE_EXIT(1);
    }
    hal_log("NB OK\r\n");

    /* Drain init-phase I/O deltas and recenter cursor before main loop. */
    hal_mouse_drain();
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);

    {
        int st;
#ifdef AUTOEXIT
        for (;;) {
            vblank_wait();  /* 60Hz heartbeat: paces anim_tick/vm_delay/input */
            hal_kbd_update();
            hal_mouse_update();
            anim_tick();  /* advance animation frame */
            /* Headless build: keep processing each frame regardless of any
             * dialog/wait that cleared VMFLAG_PROCESS. */
            vm_request_process();
            st = nb_process();
            if (st & SCENE_STATUS_FINALEND) { hal_log("End\r\n"); ENGINE_EXIT(0); }
            if (st & SCENE_STATUS_ERROR)    { hal_log("Err\r\n"); ENGINE_EXIT(1); }
            hal_mouse_draw_cursor();
        }
#else
        for (;;) {
            vblank_wait();  /* 60Hz heartbeat: paces anim_tick/vm_delay/input */
            hal_kbd_update();
            hal_mouse_update();
            anim_tick();  /* advance animation frame */
            if (vm_delay_tick())
                vm_request_process();
            if (!anim_waiting())
                st = nb_process();
            if (st & SCENE_STATUS_FINALEND) { hal_log("End\r\n"); ENGINE_EXIT(0); }
            if (st & SCENE_STATUS_ERROR)    { hal_log("Err\r\n"); ENGINE_EXIT(1); }
            hal_mouse_draw_cursor();
            hal_mouse_drain();
            /* NOTE: no per-pass NB_DEBUG here (same serial-throttle reason as
             * nb_process entry) — idle passes must stay cheap at 60Hz. */
            if (!vm_delay_active() && !(vm_get_flags() & VMFLAG_PROCESS)) {
                int wait_anim = anim_waiting();
                NB_DEBUG("[MAIN] Entering input waiting\r\n");
                hal_kbd_drain_advance();
                for (;;) {
                    vblank_wait();  /* 60Hz heartbeat (same pace as outer loop) */
                    hal_kbd_update();
                    anim_tick();  /* keep any active animation playing while waiting */
                    /* A pending waitanima hold ended on its own (once playback
                     * finished): leave immediately so the script resumes. */
                    if (wait_anim && !anim_waiting())
                        break;
                    if (hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
                        hal_log("[INPUT] Mouse clicked\r\n");
                        if (!anim_waiting())  /* input swallowed during waitanima hold */
                            vm_request_process();
                        break;
                    }
                    if (hal_kbd_is_down(KC_F5) && !nb_is_menu_scene() && !anim_waiting()) {
                        hal_log("[INPUT] F5 -> save dialog menu\r\n");
                        if (save_game_temp() != 0) break;
                        save_dialog_menu();
                        break;
                    }
                    if (hal_kbd_is_down(KC_F6) && !nb_is_menu_scene() && !anim_waiting()) {
                        hal_log("[INPUT] F6 -> load scene\r\n");
                        if (save_game_temp() != 0) break;
                        nb_load("loadscene.nb");
                        break;
                    }
                    if (hal_kbd_is_down(KC_ESC) && !anim_waiting()) {
                        hal_log("[INPUT] ESC -> main menu\r\n");
                        hal_kbd_flush();
                        nb_load("mainmenu.nb");
                        break;
                    }
                    if (hal_kbd_is_down(KC_F7)) {
                        hal_log("[INPUT] F7 -> dump layers\r\n");
                        layer_debug_handle("all");
                        hal_kbd_drain_advance();
                    }
                    if (hal_kbd_is_down(KC_SPACE) || hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_XFER)) {
                        hal_log("[INPUT] Key confirmed\r\n");
                        if (!anim_waiting())  /* input swallowed during waitanima hold */
                            vm_request_process();
                        break;
                    }
                    hal_mouse_update();
                    hal_mouse_draw_cursor();
                }
                hal_mouse_flush();
            }
        }
#endif
    }
}
