/*
 * mouse.h — PC-98 鼠标驱动内部接口
 *
 * 仅供 plat/ 层实现使用（mouse.c, hal_mouse.c）。
 * engine 层必须通过 hal.h（hal_mouse_*()）访问鼠标 API。
 *
 * 按钮常量 HAL_MOUSE_LBUTTON / HAL_MOUSE_RBUTTON 定义在 hal.h 中。
 *
 * 编译守卫：plat/ 实现文件通过 -DHAL_BUILD_ALLOWED 放行。
 */
#ifndef MOUSE_H
#define MOUSE_H

#ifndef HAL_BUILD_ALLOWED
#error "mouse.h is for plat/ implementation only. Engine code must use hal.h (hal_mouse_*() API)."
#endif

/* Button constants (also available as HAL_MOUSE_LBUTTON/RBUTTON in hal.h) */
#define MOUSE_LBUTTON  0
#define MOUSE_RBUTTON  1

void mouse_init(void);
void mouse_update(void);
int  mouse_get_x(void);
int  mouse_get_y(void);
int  mouse_was_clicked(int btn);
void mouse_flush(void);
void mouse_set_pos(int x, int y);
void mouse_drain(void);
void mouse_recenter_if_idle(void);
/* Driver ready + available (feeds the cursor presentation driver). */
int  mouse_available(void);
/* Raw display coordinates (cursor visual). */
int  mouse_get_display_x(void);
int  mouse_get_display_y(void);

#endif
