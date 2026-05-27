/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 *
 * LZ4 block decompression — C wrapper for Trixter's 8086 assembly routine.
 * 汇编核心：lz48086.asm (Trixter/Hornet, 2013, MIT via adaptation)
 */

#ifndef LZ4_H
#define LZ4_H

int lz4_decompress(const unsigned char __far *src,
                   unsigned char __far *dst,
                   unsigned int dst_size);

#endif
