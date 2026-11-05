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

/* Convert a script asset key to the compact 8.3 TOC name stored in packed
 * archives (AUDIO.DAT): uppercase, base before the last '.', capped at 8
 * characters, no trailing padding — the engine-side mirror of the toolchain
 * to_dos_name()[0].rstrip().  dst capacity must be at least 9 bytes.  Returns
 * dst. */
char *str_toc8(char *dst, size_t n, const char *src);

#endif
