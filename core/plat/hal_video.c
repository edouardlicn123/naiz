/*
 * hal_video.c — HAL video forwarding for PC-98.
 *
 * Implements the video abstractions declared in hal.h by delegating
 * to the internal video driver (video.h). Engine code must not
 * reference video.h directly; porting to a new platform only requires
 * swapping the delegation targets in plat/.
 *
 * See: docs/ — HAL architecture design
 */
#include "hal.h"
#include "video.h"

void hal_video_init(void)             { video_init(); }
void hal_video_exit(void)             { video_exit(); }
void hal_video_check_palette(void)    { video_check_palette(); }
