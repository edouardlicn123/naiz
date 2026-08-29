/*
 * video.h — PC-98 视频子系统内部接口
 *
 * 仅供 plat/ 层实现使用（video.c, hal_video.c）。
 * engine 层必须通过 hal.h（hal_video_*()）访问视频 API。
 *
 * 编译守卫：plat/ 实现文件通过 -DHAL_BUILD_ALLOWED 放行。
 */
#ifndef VIDEO_H
#define VIDEO_H

#ifndef HAL_BUILD_ALLOWED
#error "video.h is for plat/ implementation only. Engine code must use hal.h (hal_video_*() API)."
#endif

void video_init(void);
void video_exit(void);
void video_check_palette(void);

#endif
