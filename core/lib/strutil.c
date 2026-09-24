/*
 * strutil.c — Bounded string helpers.
 *
 * str_copy wraps the common "strncpy + manual NUL" idiom so call sites never
 * repeat the terminator chore and never shrink the destination by one.
 */
#include "strutil.h"
#include <string.h>

char *str_copy(char *dst, size_t n, const char *src)
{
    if (dst && n > 0) {
        strncpy(dst, src, n - 1);
        dst[n - 1] = '\0';
    }
    return dst;
}
