#include "nb_vars.h"
#include "nb_var_defs.h"
#include <string.h>

static int var_values[NB_VAR_COUNT];

void nb_var_init(void)
{
    int i;
    for (i = 0; i < NB_VAR_COUNT; i++)
        var_values[i] = var_defs[i].initial;
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
