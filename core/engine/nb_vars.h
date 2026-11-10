#ifndef NB_VARS_H
#define NB_VARS_H

#include "nb_var_table.h"

void nb_var_init(void);
int  nb_var_get(int idx);
void nb_var_set(int idx, int val);
void nb_var_add(int idx, int delta);
int  nb_var_lookup(const char *id);

/* For future save/load system */
const int *nb_var_get_state(void);
void       nb_var_set_state(const int *state);

/* String variables (devdoc 205 §5).  idx is the same index used by the int
 * API; for an int variable every string accessor is a safe no-op (slot -1,
 * get returns "").  The slot lookup is file-private. */
const char *nb_var_get_str(int idx);
void        nb_var_set_str(int idx, const char *val);
const char *nb_var_default_str(int idx);

/* Save/load: NB_STRVAR_SLOTS rows of NB_VAR_STR_MAX bytes.  An empty stored
 * row means "never set" and restores the definition default. */
const char (*nb_var_get_str_state(void))[NB_VAR_STR_MAX];
void        nb_var_set_str_state(const char (*state)[NB_VAR_STR_MAX]);

#endif
