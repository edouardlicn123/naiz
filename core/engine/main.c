#include <stdint.h>
#include "hal.h"
#include "log.h"
#include "pc98_egc.h"
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

static void draw_band(int y, int color)
{
    egc_set_bg_colour(color);
    egc_clear_lines(y, 8);
}

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

    free_scene_engine();
    free_graphics_system();

    return 0;
}
