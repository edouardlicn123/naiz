#ifndef NB_VARS_H
#define NB_VARS_H

void nb_var_init(void);
int  nb_var_get(int idx);
void nb_var_set(int idx, int val);
void nb_var_add(int idx, int delta);
int  nb_var_lookup(const char *id);


/* For future save/load system */
const int *nb_var_get_state(void);
void       nb_var_set_state(const int *state);

#endif
