/*
 * keyboard.h — PC-98 键盘驱动内部接口
 *
 * 仅供 plat/ 层实现使用（keyboard.c, hal_kbd.c）。
 * engine 层必须通过 hal.h（hal_kbd_*()）访问键盘 API。
 *
 * 扫描码常量 KC_* 定义在 hal.h 中（跨层共享）。
 * 本头文件提供函数原型和 KBD_WAIT_MAX_ITER（plat 内部用）。
 *
 * 编译守卫：plat/ 实现文件通过 -DHAL_BUILD_ALLOWED 放行。
 */
#ifndef KEYBOARD_H
#define KEYBOARD_H

#ifndef HAL_BUILD_ALLOWED
#error "keyboard.h is for plat/ implementation only. Engine code must use hal.h (hal_kbd_*() API)."
#endif

/*
 * Global timeout constant for all keyboard busy-wait loops.
 * At ~50μs per iteration (NP2kai full-speed) this is ~2.5 seconds.
 * New busy-wait loops must reference this constant, not hard-code values.
 */
#ifndef KBD_WAIT_MAX_ITER
#define KBD_WAIT_MAX_ITER  50000
#endif

/*
 * Frame-drop counter for nb_load(). When >0, kbd_update()
 * drains BIOS events without adding them to the local buffer.
 * Used to suppress auto-repeat codes immediately after scene transitions.
 */
void kbd_set_ignore_frames(int frames);

void  kbd_init(void);
int   kbd_is_down(unsigned char scancode);
void  kbd_update(void);
void  kbd_flush(void);
void  kbd_wait_any(void);
void  kbd_drain_advance(void);

#endif
