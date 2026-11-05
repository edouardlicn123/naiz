#ifndef NB_DIALOG_H
#define NB_DIALOG_H

/* Show character name and text in dialog box with paging.
 * Renders one page and advances the paging offset; does NOT pause the VM
 * (stage 2 B) — nb_process() yields while nb_dialog_pending() and advances
 * pages on wake. */
void dialog_show(const char *charname, const char *text);

/* Dialog state accessors (text buffer / offset / charname) */
const char *nb_dialog_get_text(void);
int         nb_dialog_get_offset(void);
const char *nb_dialog_get_charname(void);
void        nb_dialog_reset(void);

/* 1 while a dialog page is live on screen (waiting for page-advance or
 * dismissal input).  The interpreter/VM must yield while it is set. */
int         nb_dialog_pending(void);
/* Consume the dismissal of the last displayed page (clears the pending flag;
 * called by nb_process() after the final page was read). */
void        nb_dialog_dismiss(void);

/* Typewriter reveal (devdoc 105) — the body of the current page is shown
 * progressively. Call nb_dialog_reveal_tick() every frame from the main
 * loop (alongside anim_tick/audio_tick); suspend the page-advance inputs
 * while nb_dialog_reveal_active() and translate a confirm into
 * nb_dialog_reveal_finish() (jump, no page turn). */
void        nb_dialog_reveal_tick(void);
int         nb_dialog_reveal_active(void);
void        nb_dialog_reveal_finish(void);

#endif
