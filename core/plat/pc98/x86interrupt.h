/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#ifndef X86INTERRUPT_H
#define X86INTERRUPT_H

typedef __far void (*hal_isr_func)(void);

#define HAL_INTERRUPT_VECTOR_TABLE ((__far hal_isr_func*)0x0)

#define hal_cli() __asm ("cli")
#define hal_sti() __asm ("sti")

static inline hal_isr_func hal_get_isr(unsigned char vec)
{
    return HAL_INTERRUPT_VECTOR_TABLE[vec];
}

static inline void hal_set_isr(unsigned char vec, hal_isr_func ptr)
{
    HAL_INTERRUPT_VECTOR_TABLE[vec] = ptr;
}

#endif
