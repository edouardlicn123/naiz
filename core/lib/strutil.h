/*
 * strutil.h — Bounded string helpers (platform-independent).
 */
#ifndef STRUTIL_H
#define STRUTIL_H

#include <stddef.h>

/* Copy src into dst (capacity n bytes including the NUL terminator),
 * always NUL-terminating dst.  When n == 0 nothing is written.  The trailing
 * bytes of dst beyond the terminator are NOT zero-filled (unlike strncpy).
 * Returns dst. */
char *str_copy(char *dst, size_t n, const char *src);

#endif
