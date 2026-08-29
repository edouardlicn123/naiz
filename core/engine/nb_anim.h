/*
 * nb_anim.h -- ANI animation playback for the NB script engine.
 *
 * Implements the playanima / waitanima / stopanima commands (devdoc 80)
 * plus the per-frame animator hook anim_tick() called from main.c.
 * Single active animation, no queue. Loop policy lives here (player),
 * never in the container.
 */
#ifndef NB_ANIM_H
#define NB_ANIM_H

#include "mag.h"

typedef struct {
    int active;
    int wait;            /* waitanima requested: pause script processing */
    int loop;            /* loop mode (player-side policy) */
    unsigned char tick_armed; /* 1 after first anim_tick() calibration */
    int type;            /* 0=fullscreen, 1=cine */
    int track;           /* 0=pixel, 1=palette */
    int nframes;
    int frame;           /* currently displayed frame */
    int tick;            /* ticks remaining on current frame */
    int duration_ticks;  /* remaining playback budget ticks (0=container) */
    int duration_total;  /* saved budget for loop restart (0=none) */
    int base_blitted;
    MagImage *img;       /* pixel: current frame; palette: resident base image
                             (refcounted via mag_retain/release, may be NULL) */
    const unsigned char *blob;  /* container raw bytes base (IMAGE.DAT resident) */
    const unsigned char *offs;  /* container offset table base (nblob x u32 LE) */
    const unsigned char *ticks; /* container tick table base (u16 LE) */
    const unsigned char *pals;  /* palette table base, NULL on pixel track */
    long data_end;       /* end offset of frame data (before palette table) */
    unsigned long last_ms;  /* wall clock at previous tick (time-based stepping) */
    unsigned long ms_frac;  /* fractional tick accumulator (fixed-point, 10-bit fraction) */
    uint8_t prev_pal_r[256];  /* cached palette for dirty-diff */
    uint8_t prev_pal_g[256];
    uint8_t prev_pal_b[256];
    uint8_t *decode_buf;    /* pre-allocated decode work buffer (pixel-track only) */
    int decode_buf_size;    /* allocated size in bytes */
} AnimState;

/* Non-zero while a waitanima pause is in effect */
int anim_waiting(void);

/* Query whether an animation is currently playing */
int anim_playing(void);

/* Idempotent stop of any active animation (bg/scene implicit stop too) */
void anim_stop(void);

/* Advance the active animation by one 60Hz frame; call every loop pass */
int anim_tick(void);

/* Command handlers (registered in cmd_table, see nb_commands.c) */
void cmd_playanima(int argc, const char **argv, const char *cmd_name);
void cmd_waitanima(int argc, const char **argv, const char *cmd_name);
void cmd_stopanima(int argc, const char **argv, const char *cmd_name);

#endif /* NB_ANIM_H */
