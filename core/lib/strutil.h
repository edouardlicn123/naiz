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

/* Count UTF-8 codepoints in s: a byte that is not a continuation byte
 * (0x80-0xBF) starts a codepoint.  Invalid sequences count as one codepoint
 * each, so malformed input can never make the count exceed the byte length. */
int utf8_len_cps(const char *s);

/* Byte length implied by a UTF-8 leading byte (1..4); invalid bytes count
 * as 1.  Callers that cut a string mid-sequence use it to back off to the
 * last complete codepoint boundary. */
int utf8_cp_len(unsigned char c);

/* Truncate s in place at a UTF-8 codepoint boundary so it keeps at most
 * max_cps codepoints and at most max_bytes bytes (NUL excluded).  A partial
 * multibyte sequence is never left behind. */
void utf8_truncate_cps(char *s, int max_cps, int max_bytes);

#endif
