/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#ifndef MEMALLOC_H
#define MEMALLOC_H

__far void *mem_alloc(unsigned long bytes);
int mem_free(const __far void *ptr);

#endif
