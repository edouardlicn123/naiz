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

int utf8_len_cps(const char *s)
{
    int n = 0;
    const unsigned char *p = (const unsigned char *)s;

    if (!p) return 0;
    while (*p) {
        if ((*p & 0xC0) != 0x80) n++;   /* leading byte of a codepoint */
        p++;
    }
    return n;
}

/* Byte length implied by a UTF-8 leading byte; invalid bytes count as 1. */
int utf8_cp_len(unsigned char c)
{
    if ((c & 0x80) == 0x00) return 1;
    if ((c & 0xE0) == 0xC0) return 2;
    if ((c & 0xF0) == 0xE0) return 3;
    if ((c & 0xF8) == 0xF0) return 4;
    return 1;
}

void utf8_truncate_cps(char *s, int max_cps, int max_bytes)
{
    int n, cps = 0, pos = 0;

    if (!s) return;
    if (max_cps < 0) max_cps = 0;
    if (max_bytes < 0) max_bytes = 0;
    n = (int)strlen(s);
    while (pos < n) {
        int len = utf8_cp_len((unsigned char)s[pos]);
        if (len > n - pos) len = n - pos;      /* malformed tail */
        if (cps + 1 > max_cps || pos + len > max_bytes) break;
        pos += len;
        cps++;
    }
    s[pos] = '\0';
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
