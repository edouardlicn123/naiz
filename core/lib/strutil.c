/*
 * strutil.c — Bounded string helpers.
 *
 * str_copy wraps the common "strncpy + manual NUL" idiom so call sites never
 * repeat the terminator chore and never shrink the destination by one.
 *
 * str_toc8 converts a script asset key to the compact 8.3 TOC name used by
 * the packed archives — the engine-side mirror of the toolchain's
 * to_dos_name(); tools/tests/test_strutil.py asserts the two agree.
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

char *str_toc8(char *dst, size_t n, const char *src)
{
    const char *last_dot;
    size_t base_len, i;

    if (!dst || n == 0)
        return dst;
    if (!src)
        src = "";

    /* Mirror of the toolchain to_dos_name() half that becomes the compact
     * TOC key: uppercase, base = text before the LAST '.', capped at 8
     * chars, no trailing padding.  Callers must pass n >= 9. */
    last_dot = strrchr(src, '.');
    base_len = last_dot ? (size_t)(last_dot - src) : strlen(src);
    if (base_len > 8)
        base_len = 8;

    for (i = 0; i < base_len && i + 1 < n; i++) {
        char c = src[i];
        if (c >= 'a' && c <= 'z')
            c = (char)(c - 'a' + 'A');
        dst[i] = c;
    }
    dst[i] = '\0';
    return dst;
}
