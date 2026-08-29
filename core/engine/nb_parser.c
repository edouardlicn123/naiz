/*
 * nb_parser.c — NB script line parser (tokenizer).
 *
 * Split from nb.c: pure string parsing of one script line into a command
 * name and argument pointer array.  No render/hal/layer dependencies.
 */
#include <string.h>
#include "nb_internal.h"/*
 * Parse one NB script line.
 * Formats: cmd(arg1, arg2, ...){text}  or  cmd(arg1, arg2, ...)  or  cmd{text}
 * @param line     Input line (modified: strings NUL-terminated in-place)
 * @param cmd      Output command name buffer
 * @param cmd_size cmd buffer size
 * @param args     Output argument pointer array
 * @param max_args args array max length
 * @return Number of arguments (excluding command name)
 */
int nb_parse_line(char *line, char *cmd, int cmd_size,
                  const char **args, int max_args)
{
    int argc = 0;
    char *p = line;

    while (*p == ' ' || *p == '\t') p++;

    /* extract command name */
    {
        int i = 0;
        while (*p && *p != '(' && *p != '{' && *p != ' ' && *p != '\t'
               && i < cmd_size - 1) {
            cmd[i++] = *p++;
        }
        cmd[i] = '\0';
    }

    if (*p == '(') {
        /* parenthesized args: cmd(arg1, arg2, ...) */
        p++;
        /* Stop at '{' too: after consuming ')' the cursor may sit on the
         * brace payload opener — those bytes belong to the brace argument,
         * not to another paren arg. */
        while (*p && *p != ')' && *p != '{' && argc < max_args) {
            while (*p == ' ' || *p == '\t') p++;  /* skip leading whitespace */
            args[argc] = p;
            argc++;
            while (*p && *p != ',' && *p != ')') p++;
            if (*p == ',') { *((char *)p) = '\0'; p++; }
            if (*p == ')') { *((char *)p) = '\0'; p++; }
        }
        /* sync past closing paren even if args were truncated */
        if (argc >= max_args) {
            while (*p && *p != ')' && *p != '{') p++;
            if (*p == ')') p++;
        } else if (*p == ')') {
            p++;  /* advance past closing paren (critical for cmd(){text}) */
        }
    }
    /*
     * text arg: cmd(){text} or cmd{text}
     * Empty parens () produce argc=0 (the ) handler advances p past the
     * paren and into {text}), so cmd(){Hello} → argc=1, argv=["Hello"].
     * This is correct: the empty paren adds no argv entry.
     */
    if (*p == '{' && argc < max_args) {
        p++;
        if (*p) {
            args[argc] = p;
            argc++;
        }
        /* find closing } */
        while (*p && *p != '}') p++;
        if (*p == '}') *((char *)p) = '\0';
    }

    return argc;
}

/*
 * Extract line line_num from nb.buf.
 * Walks '\n' delimiters to locate the target line.
 * @param line_num  Line number (0-based)
 * @param out       Output buffer
 * @param out_size  Output buffer size
 */
void nb_get_line(int line_num, char *out, int out_size)
{
    const char *p = nb_get_buffer();
    int i;

    for (i = 0; i < line_num && *p; i++) {
        while (*p && *p != '\n') p++;
        if (*p == '\n') p++;
    }

    {
        int len = 0;
        while (*p && *p != '\n' && len < out_size - 1) {
            out[len++] = *p++;
        }
        out[len] = '\0';
    }
}

/*
 * Parse one NB script line using ';' as the top-level argument delimiter.
 *
 * Used for multi-segment commands (question/scene) where each ';'-separated
 * segment is itself comma-delimited (consumed later via nb_next_field).
 * Commas are left intact — only ';' terminates an arg.  The command name is
 * not extracted here; the caller already parsed it via nb_parse_line.
 *
 * @param line     Input line (modified: segments NUL-terminated in-place)
 * @param args     Output argument pointer array
 * @param max_args args array max length
 * @return Number of arguments, or -1 when the line has no parenthesized
 *         argument list (caller keeps its prior parse result)
 */
int nb_parse_line_semi(char *line, const char **args, int max_args)
{
    char *paren_open, *paren_close, *sp;
    int argc = 0;

    /* Command name is not re-extracted here; the caller already has it from
     * nb_parse_line.  Locate the parenthesized argument list. */
    paren_open = strchr(line, '(');
    paren_close = strrchr(line, ')');
    if (!paren_open || !paren_close || paren_close <= paren_open)
        return -1;

    /* NUL-terminate at the closing paren so the last segment ends cleanly. */
    *paren_close = '\0';

    sp = paren_open + 1;
    while (*sp && argc < max_args) {
        while (*sp == ' ' || *sp == '\t') sp++;
        if (!*sp) break;
        args[argc] = sp;
        argc++;
        while (*sp && *sp != ';') sp++;
        if (*sp == ';') { *sp = '\0'; sp++; }
    }

    return argc;
}
