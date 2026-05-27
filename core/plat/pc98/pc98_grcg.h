/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#ifndef PC98_GRCG_H
#define PC98_GRCG_H

#define GRCG_MODE_TDW      0x00
#define GRCG_MODE_RMW      0x40
#define GRCG_DISABLE       0x00
#define GRCG_ENABLE        0x80
#define GRCG_PLANEMASK(m)  (0x0F & (~(m)))

static inline void grcg_write_mode(unsigned char mode)
{
    __asm volatile ("outb %%al, $0x7C" : : "a" (mode));
}

static inline void grcg_enable(void)
{
    grcg_write_mode(GRCG_ENABLE);
}

static inline void grcg_disable(void)
{
    grcg_write_mode(GRCG_DISABLE);
}

static inline void grcg_set_tile_regs(unsigned char t0, unsigned char t1, unsigned char t2, unsigned char t3)
{
    __asm volatile ("out %%al, $0x7E" : : "a" (t0));
    __asm volatile ("out %%al, $0x7E" : : "a" (t1));
    __asm volatile ("out %%al, $0x7E" : : "a" (t2));
    __asm volatile ("out %%al, $0x7E" : : "a" (t3));
}

static inline void grcg_set_tiles_to_colour(unsigned char col)
{
    unsigned char t0 = (col & 0x01) ? 0xFF : 0x00;
    unsigned char t1 = (col & 0x02) ? 0xFF : 0x00;
    unsigned char t2 = (col & 0x04) ? 0xFF : 0x00;
    unsigned char t3 = (col & 0x08) ? 0xFF : 0x00;
    grcg_set_tile_regs(t0, t1, t2, t3);
}

#endif
