#ifndef NB_DIALOG_H
#define NB_DIALOG_H

/* Show character name and text in dialog box with paging */
void dialog_show(const char *charname, const char *text);

/* Dialog state accessors (text buffer / offset / charname) */
const char *nb_dialog_get_text(void);
int         nb_dialog_get_offset(void);
const char *nb_dialog_get_charname(void);
void        nb_dialog_reset(void);

#endif
