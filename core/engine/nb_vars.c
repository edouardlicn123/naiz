#include "nb_vars.h"
#include "nb_var_defs.h"
#include "hal.h"
#include "strutil.h"
#include <string.h>

static int var_values[NB_VAR_COUNT];
static char var_strs[NB_STRVAR_SLOTS][NB_VAR_STR_MAX];

/* Store val into idx's string slot.  An empty val restores the definition
 * default.  When reject_long is set (script/UI writes) a value longer than
 * maxlen codepoints is refused; save restores truncate instead so a legacy
 * value can never be silently dropped (devdoc 205 §5.3). */
static void strvar_store(int idx, const char *val, int reject_long)
{
    int slot = var_str_slot[idx];
    const char *src = val;
    char tmp[NB_VAR_STR_MAX];

    if (slot < 0) return;
    if (!src || src[0] == '\0') src = var_defs[idx].initial_str;
    if (reject_long && utf8_len_cps(src) > var_defs[idx].maxlen) {
        hal_logf("VAR: %s exceeds maxlen %d, value rejected\r\n",
                 var_defs[idx].id, var_defs[idx].maxlen);
        return;
    }
    str_copy(tmp, NB_VAR_STR_MAX, src);
    utf8_truncate_cps(tmp, var_defs[idx].maxlen, NB_VAR_STR_MAX - 1);
    str_copy(var_strs[slot], NB_VAR_STR_MAX, tmp);
}

void nb_var_init(void)
{
    int i;
    for (i = 0; i < NB_VAR_COUNT; i++) {
        var_values[i] = var_defs[i].initial;
        if (var_str_slot[i] >= 0)
            str_copy(var_strs[var_str_slot[i]], NB_VAR_STR_MAX,
                     var_defs[i].initial_str);
    }
}

int nb_var_get(int idx)
{
    if (idx < 0 || idx >= NB_VAR_COUNT) return 0;
    return var_values[idx];
}

void nb_var_set(int idx, int val)
{
    if (idx < 0 || idx >= NB_VAR_COUNT) return;
    if (val < var_defs[idx].min) val = var_defs[idx].min;
    if (val > var_defs[idx].max) val = var_defs[idx].max;
    var_values[idx] = val;
}

void nb_var_add(int idx, int delta)
{
    long long nv;
    int vmin, vmax;
    if (idx < 0 || idx >= NB_VAR_COUNT) return;
    vmin = var_defs[idx].min;
    vmax = var_defs[idx].max;
    /* 64-bit intermediate: immune to int overflow for any delta value,
     * including delta == INT_MIN (nb_commands 'var -' negative operation). */
    nv = (long long)var_values[idx] + (long long)delta;
    if (nv > vmax) nv = vmax;
    if (nv < vmin) nv = vmin;
    nb_var_set(idx, (int)nv);
}

/* REVIEWED: intentionally kept as public utility API (nb_vars.h) */
int nb_var_lookup(const char *id)
{
    int i;
    for (i = 0; i < NB_VAR_COUNT; i++) {
        if (strcmp(var_defs[i].id, id) == 0) return i;
    }
    return -1;
}

static int nb_var_str_slot(int idx)
{
    if (idx < 0 || idx >= NB_VAR_COUNT) return -1;
    return var_str_slot[idx];
}

const char *nb_var_get_str(int idx)
{
    int slot = nb_var_str_slot(idx);
    if (slot < 0) return "";
    return var_strs[slot];
}

void nb_var_set_str(int idx, const char *val)
{
    int slot = nb_var_str_slot(idx);
    if (slot < 0) return;
    strvar_store(idx, val, 1);
}

const char *nb_var_default_str(int idx)
{
    if (nb_var_str_slot(idx) < 0) return "";
    return var_defs[idx].initial_str;
}

const int *nb_var_get_state(void)
{
    return var_values;
}

void nb_var_set_state(const int *state)
{
    int i;
    for (i = 0; i < NB_VAR_COUNT; i++)
        var_values[i] = state[i];
}

const char (*nb_var_get_str_state(void))[NB_VAR_STR_MAX]
{
    return (const char (*)[NB_VAR_STR_MAX])var_strs;
}

void nb_var_set_str_state(const char (*state)[NB_VAR_STR_MAX])
{
    int i;
    for (i = 0; i < NB_VAR_COUNT; i++) {
        if (var_str_slot[i] >= 0)
            strvar_store(i, state[var_str_slot[i]], 0);
    }
}
