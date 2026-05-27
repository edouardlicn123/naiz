/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#ifndef PC98_INTERRUPT_H
#define PC98_INTERRUPT_H

#define INTERRUPT_VECTOR_VSYNC   0x0A
#define INTERRUPT_VECTOR_TIMER   0x08
#define INTERRUPT_VECTOR_KEYBOARD 0x09

#define INTERRUPT_MASK_TIMER    0x01
#define INTERRUPT_MASK_KEYBOARD 0x02
#define INTERRUPT_MASK_VSYNC    0x04

static inline unsigned char pic_get_imr(void)
{
    unsigned char mask;
    __asm volatile ("inb $0x02, %%al" : "=a" (mask));
    return mask;
}

static inline void pic_set_imr(unsigned char mask)
{
    __asm volatile ("outb %%al, $0x02" : : "a" (mask));
}

static inline void pic_enable_irqs(unsigned char mask)
{
    unsigned char m = pic_get_imr();
    m &= ~mask;
    pic_set_imr(m);
}

static inline void pic_disable_irqs(unsigned char mask)
{
    unsigned char m = pic_get_imr();
    m |= mask;
    pic_set_imr(m);
}

static inline void pic_eoi(void)
{
    __asm volatile ("movb $0x20, %%al\n\toutb %%al, $0x00" : : : "%al");
}

#endif
