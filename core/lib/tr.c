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
 *   - key 和 value 均支持最多 256 字节
 */
#include "tr.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TR_MAX_ENTRIES 1024  /* hard cap; load_file stops at this (as before) */
#define TR_INIT_CAP     64   /* first block 64 x 384 B = 24 KB; realloc x2 when full */
#define TR_KEY_LEN     128   /* 键最大长度（含 NUL） */
#define TR_VAL_LEN     256   /* 值最大长度（含 NUL） */

/* Translation entry: key=value pair. */
typedef struct {
    char key[TR_KEY_LEN];  /* Source text (lookup key) */
    char val[TR_VAL_LEN];  /* Translated text (lookup value) */
} TrEntry;

/* Heap-allocated translation table, grown on demand (no static 384 KB block). */
static TrEntry *tr_table;
/* Number of loaded translation entries. */
static int tr_count;
/* Allocated capacity of tr_table (0 = nothing allocated yet). */
static int tr_cap;

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
    char line[512];
    char *eq;
    int klen, vlen;

    f = fopen(path, "r");
    if (!f) return;

    while (fgets(line, sizeof(line), f)) {
        /* Strip trailing \r\n. */
        {
            int len = (int)strlen(line);
            while (len > 0 && (line[len - 1] == '\r' || line[len - 1] == '\n')) {
                line[--len] = '\0';
            }
        }

        /* Skip empty lines and comment lines starting with '#'. */
        if (line[0] == '\0' || line[0] == '#') continue;

        /* Find first '=' separator; skip lines without '='. */
        eq = strchr(line, '=');
        if (!eq) continue;

        if (tr_count >= TR_MAX_ENTRIES) break;
        if (tr_count >= tr_cap && tr_grow() != 0) break;  /* OOM: stop loading */

        /* key = everything before first '='. */
        klen = (int)(eq - line);
        if (klen >= TR_KEY_LEN) klen = TR_KEY_LEN - 1;
        memcpy(tr_table[tr_count].key, line, klen);
        tr_table[tr_count].key[klen] = '\0';

        /* value = everything after first '='. */
        vlen = (int)strlen(eq + 1);
        if (vlen >= TR_VAL_LEN) vlen = TR_VAL_LEN - 1;
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

    if (!lang) return -1;

    /* Guard against lang longer than available path space (max 47 chars). */
    if (strlen(lang) > 47) return -1;

    /* Load system-level translations (UI elements, generic text). */
    snprintf(path, sizeof(path), "i18n/system_%s.txt", lang);
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
