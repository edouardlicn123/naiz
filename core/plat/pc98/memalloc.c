/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#include "memalloc.h"
#include "hal.h"

__far void *mem_alloc(unsigned long bytes)
{
    return hal_mem_alloc((unsigned short)((bytes + 0xF) >> 4));
}

int mem_free(const __far void *ptr)
{
    hal_mem_free((void __far *)ptr);
    return 0;
}
