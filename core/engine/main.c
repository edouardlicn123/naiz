/*
 * Naiz Engine 主入口模块
 * — HAL / 字库 / 键盘 / 视频 / 调色板 / 图片归档初始化
 * — 玩家偏好读取 (USER.CFG) + 项目配置 (config.toml→nb_config.h)
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
#include "nb_dialog.h"
#include "nb_saveload.h"
#include "save.h"
#include "layer_debug.h"
#include "prefs.h"
#include "bootmenu.h"
#include "audio.h"
#include "frame.h"

/* Debug logging — shared macro in debug.h */
#include "debug.h"
#include "input_boundary.h"

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
#define ENGINE_EXIT(s) do { \
    NAIZ_BGM_IRQ_CLEANUP(); \
    hal_video_exit(); return (s); } while(0)

/* devdoc 164 phase 1: stop the Timer-B ISR before leaving, so no handler
 * runs after the engine tears the display down.  Compiles to nothing when
 * the interrupt pump is disabled. */
#if NAIZ_BGM_IRQ
#define NAIZ_BGM_IRQ_CLEANUP() hal_bgm_irq_shutdown()
#else
#define NAIZ_BGM_IRQ_CLEANUP() ((void)0)
#endif

/* devdoc 150 diagnostic bench: play one BGM on repeat, headlessly, so a
 * capture reflects the steady-state BGM path with no host input.  Off by
 * default; enable with -DBGM_BENCH=1 [-DBGM_BENCH_NAME=icy_garden]. */
#ifndef BGM_BENCH
#define BGM_BENCH 0
#endif
#ifndef BGM_BENCH_NAME
#define BGM_BENCH_NAME melody_town
#endif
/* Stringify so the key can be passed unquoted on the command line. */
#define NAIZ_BGM_STR2(x) #x
#define NAIZ_BGM_STR(x) NAIZ_BGM_STR2(x)
#define BGM_BENCH_KEY NAIZ_BGM_STR(BGM_BENCH_NAME)

/* devdoc 152: BGM_IDLE runs the REAL main loop (not the tight BGM_BENCH spin)
 * sitting on the first dialogue page of a gameplay scene, so a recording
 * reflects the true per-pass load (prefetch I/O + input poll).  Default 0;
 * enable with -DBGM_IDLE=1 [-DBGM_IDLE_SCENE=nbook001] (extension appended). */
#ifndef BGM_IDLE
#define BGM_IDLE 0
#endif
#ifndef BGM_IDLE_SCENE
#define BGM_IDLE_SCENE nbook001
#endif
#define BGM_IDLE_FILE NAIZ_BGM_STR(BGM_IDLE_SCENE) ".nb"

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

#if NAIZ_IRQ_PROBE
    /* devdoc 163 Phase 3 C1: 2-second GDC vsync IRQ probe (diagnostic
     * build only; compiles out by default).  Runs after video_init so the
     * GDC is initialised, and reports via serial [IRQP]. */
    hal_irq_probe_run();
    /* devdoc 164 phase 0: read-only DPMI interrupt-capability probe, to
     * decide whether the toolchain can hook a hardware IRQ at all. */
    hal_dpmi_probe_run();
#endif

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

    audio_init();

    sys_save_load();

    /* Settings: load existing or show first-launch menu */
    prefs_load();
#if !BGM_BENCH && !BGM_IDLE
    bootmenu_run();
    prefs_save();
#endif

    /* Deterministic marker for the effective boot language.  The whole point
     * of devdoc 120 was that the menu selection used to be saved but never
     * read back, and that failure is invisible on screen until you squint at
     * glyphs.  This line is the probe target for tools/diag/np2kai_ab.py
     * --expect/--forbid; do not remove it without a replacement marker. */
    hal_logf("[LANG] boot effective lang='%s' default='%s'\r\n",
             prefs_get_lang(), NAIZ_DEFAULT_LANG);

    /* CJK: load language-specific file with fallback */
    if (cjk_load_for_lang(prefs_get_lang()) != 0) {
        hal_log("CJK not found\r\n");
        ENGINE_EXIT(1);
    }

    if (nb_init() != 0) {
        hal_log("NB init fail\r\n");
        ENGINE_EXIT(1);
    }
    hal_log("NB OK\r\n");

#if BGM_IDLE
    /* devdoc 152: jump straight into a gameplay scene (its bgm(){...} starts
     * the music), then FALL THROUGH to the normal main loop below — it runs
     * to the first dialogue page and parks in the input-waiting loop, exactly
     * the "idle dialogue page" state the player reported as still fluttering. */
    hal_logf("BGM idle: %s\r\n", BGM_IDLE_FILE);
    scene_switch(BGM_IDLE_FILE, SCENE_SWITCH_INIT);
#endif

#if BGM_BENCH
    /* devdoc 150: skip the game flow and loop one BGM so a recording captures
     * the steady-state BGM path with no host input (makegame.sh test can't
     * deliver input under NP2kai's disk-audio capture). */
    hal_logf("BGM bench: %s\r\n", BGM_BENCH_KEY);
    audio_bgm_start(BGM_BENCH_KEY);
    for (;;)
        engine_frame_pump();
#endif

    /* Drain init-phase I/O deltas and recenter cursor before main loop. */
    hal_mouse_drain();
    hal_mouse_set_pos(LAYER_SCREEN_W / 2, LAYER_SCREEN_H / 2);

    {
        int st;
#ifdef AUTOEXIT
        for (;;) {
            engine_frame_pump();  /* vblank + clock + anim + audio + reveal */
            nb_prefetch_lookahead();  /* devdoc 133: warm next display images */
            hal_kbd_update();
            hal_mouse_update();
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
            engine_frame_pump();  /* vblank + clock + anim + audio + reveal */
            nb_prefetch_lookahead();  /* devdoc 133: warm next display images */
            hal_kbd_update();
            hal_mouse_update();
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
                input_drain_boundary();
                for (;;) {
                    engine_frame_pump();  /* vblank + clock + anim + audio + reveal */
                    nb_prefetch_lookahead();  /* devdoc 133: warm next display images */
                    hal_kbd_update();
                    /* A pending waitanima hold ended on its own (once playback
                     * finished): leave immediately so the script resumes. */
                    if (wait_anim && !anim_waiting())
                        break;
                    if (hal_mouse_was_clicked(HAL_MOUSE_LBUTTON)) {
                        hal_log("[INPUT] Mouse clicked\r\n");
                        if (!anim_waiting()) {  /* input swallowed during waitanima hold */
                            if (nb_dialog_reveal_active())
                                nb_dialog_reveal_finish();  /* reveal-jump, no page turn */
                            else
                                vm_request_process();
                        }
                        break;
                    }
                    if (hal_kbd_is_down(KC_F5) && !nb_is_menu_scene() && !anim_waiting()) {
                        hal_log("[INPUT] F5 -> save dialog menu\r\n");
                        if (save_request(SAVE_OP_CAPTURE_TEMP, -1) != 0) break;
                        save_request(SAVE_OP_OPEN_SAVE, -1);
                        break;
                    }
                    if (hal_kbd_is_down(KC_F6) && !nb_is_menu_scene() && !anim_waiting()) {
                        hal_log("[INPUT] F6 -> load scene\r\n");
                        if (save_request(SAVE_OP_CAPTURE_TEMP, -1) != 0) break;
                        save_request(SAVE_OP_OPEN_LOAD, -1);
                        break;
                    }
                    if (hal_kbd_is_down(KC_ESC) && !anim_waiting()) {
                        hal_log("[INPUT] ESC -> main menu\r\n");
                        hal_kbd_flush();
                        save_request(SAVE_OP_OPEN_MAINMENU, -1);
                        break;
                    }
                    if (hal_kbd_is_down(KC_F7)) {
                        hal_log("[INPUT] F7 -> dump layers\r\n");
                        layer_debug_handle("all");
                        hal_kbd_drain_advance();
                    }
                    if (hal_kbd_is_down(KC_SPACE) || hal_kbd_is_down(KC_ENTER) || hal_kbd_is_down(KC_XFER)) {
                        hal_log("[INPUT] Key confirmed\r\n");
                        if (!anim_waiting()) {  /* input swallowed during waitanima hold */
                            if (nb_dialog_reveal_active())
                                nb_dialog_reveal_finish();  /* reveal-jump, no page turn */
                            else
                                vm_request_process();
                        }
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
