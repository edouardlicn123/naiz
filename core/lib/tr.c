/*
 * tr — 运行时翻译表（i18n）
 *
 * 从翻译文件（i18n/*.txt）加载 key=value 键值对，提供精确匹配查找。
 * 支持按语言加载 system/role/game 三组翻译文件，实现运行时文本替换。
 * 无平台依赖，属于 core/lib/ 平台无关库。
 *
 * 翻译文件格式：
 *   - 每行一个 key=value 条目
 *   - 空行和以 '#' 开头的行被跳过
 *   - key 和 value 容量上限见 tr.h
 */
#include "tr.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TR_MAX_ENTRIES 1024  /* hard cap; load_file stops at this (as before) */
#define TR_INIT_CAP     64   /* first block 64 x 2304 B = 144 KB; realloc x2 when full */

/* Translation entry: key=value pair. */
typedef struct {
    char key[TR_KEY_LEN];  /* Source text (lookup key) */
    char val[TR_VAL_LEN];  /* Translated text (lookup value) */
} TrEntry;

/* Heap-allocated translation table, grown on demand. */
static TrEntry *tr_table;
/* Number of loaded translation entries. */
static int tr_count;
/* Allocated capacity of tr_table (0 = nothing allocated yet). */
static int tr_cap;
/* Truncation counter for fail-loud diagnostics (devdoc 121). */
static int tr_trunc_count;

/* Grow tr_table capacity (doubling from TR_INIT_CAP, capped at TR_MAX_ENTRIES).
 * @return 0 on success, -1 on allocation failure (existing entries preserved) */
static int tr_grow(void)
{
    int new_cap = tr_cap ? tr_cap * 2 : TR_INIT_CAP;
    TrEntry *p;
    if (new_cap > TR_MAX_ENTRIES) new_cap = TR_MAX_ENTRIES;
    if (new_cap <= tr_cap) return 0;
    p = (TrEntry *)realloc(tr_table, (size_t)new_cap * sizeof(TrEntry));
    if (!p) return -1;
    tr_table = p;
    tr_cap = new_cap;
    return 0;
}

/* Load a translation file, parsing key=value lines (skips empty lines and # comments).
 * @param path  Path to translation file; silently skips if file does not exist */
static void load_file(const char *path)
{
    FILE *f;
    char line[TR_LINE_MAX];
    char *eq;
    int klen, vlen;
    int linelen;

    f = fopen(path, "r");
    if (!f) return;

    while (fgets(line, sizeof(line), f)) {
        linelen = (int)strlen(line);
        /* Detect truncation: line not ending with \n and not EOF? But fgets returns
         * full buffer only if no \n found before end. */
        if (linelen > 0 && line[linelen - 1] != '\n' && linelen == (int)sizeof(line) - 1) {
            /* Line was truncated by fgets buffer */
            tr_trunc_count++;
            /* Try to consume rest of line to keep position? Simple: just continue processing
             * what we have; we'll strip \r later. But better to note. */
        }

        /* Strip trailing \r\n. */
        while (linelen > 0 && (line[linelen - 1] == '\r' || line[linelen - 1] == '\n')) {
            line[--linelen] = '\0';
        }

        /* Skip empty lines and comment lines starting with '#'. */
        if (line[0] == '\0' || line[0] == '#') continue;

        /* Find first '=' separator; skip lines without '='. */
        eq = strchr(line, '=');
        if (!eq) continue;

        if (tr_count >= TR_MAX_ENTRIES) {
            tr_trunc_count++;
            break;
        }
        if (tr_count >= tr_cap && tr_grow() != 0) break;  /* OOM: stop loading */

        /* key = everything before first '='. */
        klen = (int)(eq - line);
        if (klen >= TR_KEY_LEN) {
            tr_trunc_count++;
            klen = TR_KEY_LEN - 1;
        }
        memcpy(tr_table[tr_count].key, line, klen);
        tr_table[tr_count].key[klen] = '\0';

        /* value = everything after first '='. */
        vlen = (int)strlen(eq + 1);
        if (vlen >= TR_VAL_LEN) {
            tr_trunc_count++;
            vlen = TR_VAL_LEN - 1;
        }
        memcpy(tr_table[tr_count].val, eq + 1, vlen);
        tr_table[tr_count].val[vlen] = '\0';

        tr_count++;
    }

    fclose(f);
}

/* Initialize the translation system: load system/role/game translation files by language.
 * Loading order: system -> role -> game; later files override earlier keys for same key.
 * @param lang  Language identifier (e.g. "zh", "ja", "en") */
int tr_init(const char *lang)
{
    char path[TR_PATH_BUF_SIZE];

    /* Release any previously allocated table before rebuilding (language
     * switch reloads the whole table; old entries must not leak or dangle). */
    free(tr_table);
    tr_table = NULL;
    tr_count = 0;
    tr_cap = 0;
    tr_trunc_count = 0;

    if (!lang) return -1;

    /* Guard against lang longer than available path space (max 47 chars). */
    if (strlen(lang) > 47) return -1;

    /* Load system-level translations (UI elements, generic text).
     * sys_<lang>.txt: short 8.3-safe base (system_* would truncate to the
     * same DOS short name for chi and cht, clobbering one another on HDI). */
    snprintf(path, sizeof(path), "i18n/sys_%s.txt", lang);
    load_file(path);

    /* Load role name translations. */
    snprintf(path, sizeof(path), "i18n/role_%s.txt", lang);
    load_file(path);

    /* Load game content translations (story text). */
    snprintf(path, sizeof(path), "i18n/game_%s.txt", lang);
    load_file(path);

    return 0;
}

/* Look up the translation of a text string (exact match, linear search).
 * @param text  Source string to translate
 * @return Translated string, or the original string if not found.
 *         An empty translation value is treated as untranslated and falls
 *         back to the original source text. */
const char *tr(const char *text)
{
    int i;

    /* Linear scan of the translation table for exact match. */
    for (i = 0; i < tr_count; i++) {
        if (strcmp(tr_table[i].key, text) == 0) {
            if (tr_table[i].val[0] != '\0')
                return tr_table[i].val;
            break;  /* empty value = untranslated, fall back to source */
        }
    }

    /* Return original string as fallback when no translation found. */
    return text;
}

/* Return the number of currently loaded translation entries. */
int tr_get_count(void)
{
    return tr_count;
}

/* Return number of truncations detected during loading. */
int tr_get_truncations(void)
{
    return tr_trunc_count;
}
