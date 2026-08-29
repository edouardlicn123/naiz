/*
 * endian.h — Little-endian read helpers (inline).
 *
 * PC-98 is little-endian; data files use LE byte order.
 * These inline helpers replace hand-written byte shifts.
 */
#ifndef ENDIAN_H
#define ENDIAN_H

#include <stdint.h>

static inline uint16_t read16_le(const uint8_t *p)
{
    return (uint16_t)(p[0] | ((uint16_t)p[1] << 8));
}

static inline uint32_t read32_le(const uint8_t *p)
{
    return (uint32_t)(p[0] | ((uint32_t)p[1] << 8) |
                     ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24));
}

#endif
