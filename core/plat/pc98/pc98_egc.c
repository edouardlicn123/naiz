/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#include "pc98_egc.h"
#include "pc98_grcg.h"
#include "pc98_gdc.h"
#include "x86strops.h"

void egc_set_to_bg_clear_mode(void)
{
    egc_set_pattern_and_read_src(EGC_PATTERNSOURCE_BGCOLOUR);
    egc_set_read_write_mode(EGC_WRITE_PATSHIFT | EGC_SOURCE_CPU);
    egc_set_bit_addr_dir(EGC_BLOCKTRANSFER_FORWARD);
}

void egc_set_to_mono_draw_mode(void)
{
    egc_set_pattern_and_read_src(EGC_PATTERNSOURCE_FGCOLOUR);
    egc_set_read_write_mode(EGC_WRITE_ROPSHIFT | EGC_SOURCE_CPU
        | EGC_ROP((EGC_ROP_SRC & EGC_ROP_PAT) | ((~EGC_ROP_SRC) & EGC_ROP_DST)));
    egc_set_bit_addr_dir(EGC_BLOCKTRANSFER_FORWARD);
}

void egc_set_to_vram_blit(void)
{
    egc_set_pattern_and_read_src(EGC_PATTERNSOURCE_PATREG);
    egc_set_read_write_mode(EGC_WRITE_PATSHIFT | EGC_SOURCE_VRAM | EGC_PATSET_SOURCE);
    egc_set_bit_addr_dir(EGC_BLOCKTRANSFER_FORWARD);
}

void egc_clear_screen(void)
{
    egc_set_plane_access(0xF);
    egc_set_mask(0xFFFF);
    egc_set_to_bg_clear_mode();
    egc_set_bit_length(2048);
    hal_memset16_far(0xFFFF, GDC_PLANES, 16000);
}

void egc_clear_lines(unsigned short start_line, unsigned short num_lines)
{
    egc_set_plane_access(0xF);
    egc_set_mask(0xFFFF);
    egc_set_to_bg_clear_mode();
    egc_set_bit_length(2048);
    hal_memset16_far(0xFFFF, GDC_PLANES + start_line * 80, 40 * num_lines);
}

void egc_enable(void)
{
    grcg_enable();
    gdc_set_mode2(GDC_MODE2_MODIFY);
    gdc_set_mode2(GDC_MODE2_EGC);
    gdc_set_mode2(GDC_MODE2_NOMODIFY);
}

void egc_disable(void)
{
    gdc_set_mode2(GDC_MODE2_MODIFY);
    gdc_set_mode2(GDC_MODE2_GRCG);
    gdc_set_mode2(GDC_MODE2_NOMODIFY);
    grcg_disable();
}
