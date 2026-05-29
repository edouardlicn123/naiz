/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#ifndef PC98_EGC_H
#define PC98_EGC_H

#define EGC_PATTERNSOURCE_PATREG   0x0000
#define EGC_PATTERNSOURCE_BGCOLOUR 0x2000
#define EGC_PATTERNSOURCE_FGCOLOUR 0x4000

#define EGC_READ_SINGLEPLANE 0x0000
#define EGC_WRITE_NOMODIFY   0x0000
#define EGC_WRITE_ROPSHIFT   0x0800
#define EGC_WRITE_PATSHIFT   0x1000
#define EGC_SOURCE_VRAM      0x0000
#define EGC_SOURCE_CPU       0x0400
#define EGC_PATSET_NONE      0x0000
#define EGC_PATSET_SOURCE    0x0100
#define EGC_PATSET_VRAM      0x0200

#define EGC_ROP_0   0x0000
#define EGC_ROP_1   0x00FF
#define EGC_ROP_NOP 0x00CC
#define EGC_ROP_SRC 0x00F0
#define EGC_ROP_DST 0x00CC
#define EGC_ROP_PAT 0x00AA
#define EGC_ROP(r)  ((r) & 0x00FF)

#define EGC_BLOCKTRANSFER_FORWARD  0x0000
#define EGC_BLOCKTRANSFER_BACKWARD 0x1000
#define EGC_BITADDRESS_DEST(n) (((n) & 0xF) << 4)
#define EGC_BITADDRESS_SRC(n)  ((n) & 0xF)

static inline void egc_set_plane_access(unsigned short mask)
{
    mask = ~mask;
    __asm volatile ("movw $0x04A0, %%dx\n\tout %w0, %%dx\n\t" : : "a" (mask) : "%dx");
}

static inline void egc_set_pattern_and_read_src(unsigned short mode)
{
    mode |= 0x00FF;
    __asm volatile ("movw $0x04A2, %%dx\n\tout %w0, %%dx\n\t" : : "a" (mode) : "%dx");
}

static inline void egc_set_read_write_mode(unsigned short mode)
{
    __asm volatile ("movw $0x04A4, %%dx\n\tout %w0, %%dx\n\t" : : "a" (mode) : "%dx");
}

static inline void egc_set_fg_colour(unsigned short col)
{
    __asm volatile ("movw $0x04A6, %%dx\n\tout %w0, %%dx\n\t" : : "a" (col) : "%dx");
}

static inline void egc_set_mask(unsigned short mask)
{
    __asm volatile ("movw $0x04A8, %%dx\n\tout %w0, %%dx\n\t" : : "a" (mask) : "%dx");
}

static inline void egc_set_bg_colour(unsigned short col)
{
    __asm volatile ("movw $0x04AA, %%dx\n\tout %w0, %%dx\n\t" : : "a" (col) : "%dx");
}

static inline void egc_set_bit_addr_dir(unsigned short mode)
{
    __asm volatile ("movw $0x04AC, %%dx\n\tout %w0, %%dx\n\t" : : "a" (mode) : "%dx");
}

static inline void egc_set_bit_length(unsigned short len)
{
    len--;
    __asm volatile ("movw $0x04AE, %%dx\n\tout %w0, %%dx\n\t" : : "a" (len) : "%dx");
}

void egc_clear_screen(void);
void egc_clear_lines(unsigned short start_line, unsigned short num_lines);
void egc_set_to_bg_clear_mode(void);
void egc_set_to_mono_draw_mode(void);
void egc_set_to_vram_blit(void);
void egc_enable(void);
void egc_operation_done(void);
void egc_disable(void);

#endif
