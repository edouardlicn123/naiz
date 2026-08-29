#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <i86.h>
#include "mouse.h"
#include "hal.h"
#include "pc98.h"

/* Mouse coordinate range */
#define MOUSE_X_MAX  639
#define MOUSE_Y_MAX  399

/* Dead zone: ignore deltas at or below this threshold */
#define MOUSE_DEAD_ZONE 2

/* Frame limit: clamp deltas exceeding this to prevent spike-induced drift */
#define MOUSE_FRAME_LIMIT 50

/* Idle detection threshold: recenter if no motion for this many frames */
#define MOUSE_IDLE_RESET 300

/* Mouse state */
static int mouse_buttons_before = 0;
static int mouse_buttons_now = 0;
static int mouse_x_now = 320;
static int mouse_y_now = 200;
static int mouse_is_initialized = 0;
static int mouse_is_available_flag = 0;

/* Click FIFO */
#define MOUSE_FIFO_SIZE 16
typedef struct {
    int button;
    int x;
    int y;
} mouse_click_t;
static mouse_click_t mouse_click_fifo[MOUSE_FIFO_SIZE];
static int mouse_fifo_head = 0;
static int mouse_fifo_tail = 0;

/* Idle tracking for recenter */
static int mouse_idle_frames = 0;

/* Direction consistency filter: require N frames of same-direction movement
 * before committing.  Noise flips sign randomly; real movement is sustained. */
#define DIR_CONFIRM_THRESHOLD 3
static int mouse_dir_conf_x = 0;
static int mouse_dir_conf_y = 0;
static int mouse_last_sign_x = 0;
static int mouse_last_sign_y = 0;
static int mouse_pending_dx = 0;
static int mouse_pending_dy = 0;

/* Game coordinates: direction-filtered, used for hit-testing.
 * Display coordinates (mouse_x_now/y_now) accumulate directly for cursor visual;
 * game coordinates only accept direction-confirmed movement, so they don't drift.
 * When display drifts too far from game, it's slowly pulled back. */
#define DRIFT_CALIB_THRESH  4
#define DRIFT_CALIB_DIV     2
static int mouse_x_game = 320;
static int mouse_y_game = 200;

/* NP2kai system port (P5 extension) — absolute coordinates via I/O ports 0x7E0-0x7E3 */
#define NP2_PORT_MODE  0x7ED   /* mode select: 1=command, 0=data */
#define NP2_PORT_DATA  0x7EF   /* string command/data port */
#define NP2_PORT_XL    0x7E0   /* read: X low byte  */
#define NP2_PORT_XH    0x7E1   /* read: X high byte */
#define NP2_PORT_YL    0x7E2   /* read: Y low byte  */
#define NP2_PORT_YH    0x7E3   /* read: Y high byte */
static int mouse_np2kai = 0;    /* 1 = NP2kai detected */
static int mouse_pos_explicit = 0; /* 1 = position was set by set_pos(); skip NP2 override once */

static int mouse_np2_detect(void)
{
    const char *cmd = "NP2";
    char resp[8];
    int i;

    /* NP2 system port protocol: switch to command mode, write cmd, switch back, read response */
    outb(NP2_PORT_MODE, 1);
    for (i = 0; cmd[i]; i++)
        outb(NP2_PORT_DATA, cmd[i]);
    outb(NP2_PORT_MODE, 0);

    memset(resp, 0, sizeof(resp));
    for (i = 0; i < (int)sizeof(resp) - 1; i++) {
        resp[i] = (char)inb(NP2_PORT_DATA);
        if (resp[i] == 0) break;
    }

    return (strcmp(resp, "NP2") == 0);
}

static void mouse_np2_getpos(int *x, int *y)
{
    *x = (int)inb(NP2_PORT_XL) | ((int)inb(NP2_PORT_XH) << 8);
    *y = (int)inb(NP2_PORT_YL) | ((int)inb(NP2_PORT_YH) << 8);
}

/* INT33 QMOUSE state */
static int mouse_int33_available = 0;
static int mouse_int33_active = 0;
static int mouse_int33_valid_count = 0;
#define INT33_VALID_REQUIRED 3

/* INT 33h call via inline asm (bypasses int386() DPMI reflection bugs) */
static void mouse_int33_asm(uint16_t ax, uint16_t bx, uint16_t cx, uint16_t dx,
                            uint16_t *out_ax, uint16_t *out_bx,
                            uint16_t *out_cx, uint16_t *out_dx)
{
    uint16_t _ax = ax, _bx = bx, _cx = cx, _dx = dx;
    _asm {
        mov  ax, word ptr _ax
        mov  bx, word ptr _bx
        mov  cx, word ptr _cx
        mov  dx, word ptr _dx
        int  33h
        mov  word ptr _ax, ax
        mov  word ptr _bx, bx
        mov  word ptr _cx, cx
        mov  word ptr _dx, dx
    }
    if (out_ax) *out_ax = _ax;
    if (out_bx) *out_bx = _bx;
    if (out_cx) *out_cx = _cx;
    if (out_dx) *out_dx = _dx;
}

/*=== 8255 handshake =======================================================*/

static void mouse_read_8255(int *dx, int *dy, int *btn)
{
    uint8_t x_low, x_high, y_low, y_high;
    uint8_t stat;

    outb(MOUSE_PORT_CTRL, MOUSE_HC | MOUSE_IN);
    stat = inb(MOUSE_PORT_DATA);
    x_low = stat & 0x0F;

    outb(MOUSE_PORT_CTRL, MOUSE_HC | MOUSE_SH | MOUSE_IN);
    x_high = inb(MOUSE_PORT_DATA) & 0x0F;

    outb(MOUSE_PORT_CTRL, MOUSE_HC | MOUSE_SX | MOUSE_IN);
    y_low = inb(MOUSE_PORT_DATA) & 0x0F;

    outb(MOUSE_PORT_CTRL, MOUSE_HC | MOUSE_SX | MOUSE_SH | MOUSE_IN);
    y_high = inb(MOUSE_PORT_DATA) & 0x0F;

    outb(MOUSE_PORT_CTRL, MOUSE_IN);

    *dx = (int8_t)((x_high << 4) | x_low);
    *dy = (int8_t)((y_high << 4) | y_low);

    /* Buttons: active low on bits 7 (left) and 6 (right) */
    {
        int left = (stat & 0x80) ? 0 : 1;
        int right = (stat & 0x40) ? 0 : 1;
        *btn = left | (right << 1);
    }
}

/*=== Init =================================================================*/

void mouse_init(void)
{
    if (mouse_is_initialized) return;

    outb(MOUSE_PORT_MODE, 0x93);
    outb(MOUSE_PORT_CTRL, MOUSE_IN);
    mouse_dir_conf_x = 0; mouse_dir_conf_y = 0;
    mouse_last_sign_x = 0; mouse_last_sign_y = 0;
    mouse_pending_dx = 0; mouse_pending_dy = 0;
    mouse_x_game = 320; mouse_y_game = 200;
    mouse_is_available_flag = 1;

    /* Detect QMOUSE via INT33 AX=0000h (returns AX != 0 if installed) */
    {
        uint16_t ax;
        mouse_int33_asm(0x0000, 0, 0, 0, &ax, NULL, NULL, NULL);
        mouse_int33_available = (ax != 0);
    }

    /* Detect NP2kai via system port "NP2" command */
    mouse_np2kai = mouse_np2_detect();
    if (mouse_np2kai) {
        hal_log("[MOUSE] NP2kai detected via system port\r\n");
    }

    mouse_is_initialized = 1;
}

/*=== Update ===============================================================*/

void mouse_update(void)
{
    int dx_raw = 0, dy_raw = 0, btn = 0;
    int dx = 0, dy = 0;
    int use_np2 = 0;
    int use_abs = 0;

    if (!mouse_is_initialized) return;

    /*=== NP2kai path (highest priority): absolute coordinates via I/O ports ===*/
    if (mouse_np2kai) {
        int nx, ny;
        {   /* 8255 still read for button state (drain deltas silently) */
            int _dxd, _dyd;
            mouse_read_8255(&_dxd, &_dyd, &btn);
        }
        mouse_np2_getpos(&nx, &ny);
#ifdef NAIZ_DEBUG
        {
            char _dbg[80];
            snprintf(_dbg, sizeof(_dbg), "[MOUSE] NP2 raw port: nx=%d ny=%d\r\n", nx, ny);
            hal_log(_dbg);
        }
#endif

        if (mouse_pos_explicit) {
            mouse_pos_explicit = 0;
        } else {
            /* Clamp NP2 absolute coords to the 640x400 screen, mirroring
             * the INT33 validity check and the 8255 clamp below. */
            if (nx < 0) nx = 0; else if (nx > 639) nx = 639;
            if (ny < 0) ny = 0; else if (ny > 399) ny = 399;
            mouse_x_now = mouse_x_game = nx;
            mouse_y_now = mouse_y_game = ny;
        }
        mouse_buttons_now = btn;
        mouse_idle_frames = 0;
        use_abs = 1;
        use_np2 = 1;
    }

    /*=== INT33 path: absolute coordinates from QMOUSE (NP2kai fallback / real PC) ===*/
    if (!use_np2 && mouse_int33_available) {
        uint16_t _ax, _bx, _cx, _dx;
        mouse_int33_asm(0x0003, 0, 0, 0, &_ax, &_bx, &_cx, &_dx);
        /* Coordinate sanity per path: INT33 rejects out-of-range |_cx,|_dx;
         * NP2 clamps above; 8255 clamps below (see each block). */
        if (_cx <= 639 && _dx <= 399 && (_bx & 0xFFF8) == 0) {
            if (mouse_int33_valid_count < INT33_VALID_REQUIRED)
                mouse_int33_valid_count++;
            if (mouse_int33_valid_count >= INT33_VALID_REQUIRED) {
                mouse_int33_active = 1;
                mouse_x_now = _cx; mouse_y_now = _dx;
                mouse_x_game = _cx; mouse_y_game = _dx;
                mouse_buttons_now = _bx & 0x07;
                mouse_idle_frames = 0;
                use_abs = 1;
                /* Drain 8255 so stale deltas don't accumulate while off */
                {
                    int _dxd, _dyd, _btnd;
                    mouse_read_8255(&_dxd, &_dyd, &_btnd);
                }
            }
        } else {
            mouse_int33_valid_count = 0;
            mouse_int33_active = 0;
        }
    }

    /*=== 8255 PPI fallback path ===*/
    if (!use_abs) {
        mouse_read_8255(&dx_raw, &dy_raw, &btn);
        mouse_buttons_now = btn;

        dx = dx_raw;
        dy = dy_raw;

        if (dx < 0 && dx_raw > -MOUSE_DEAD_ZONE) dx = 0;
        if (dx > 0 && dx_raw <  MOUSE_DEAD_ZONE) dx = 0;
        if (dy < 0 && dy_raw > -MOUSE_DEAD_ZONE) dy = 0;
        if (dy > 0 && dy_raw <  MOUSE_DEAD_ZONE) dy = 0;

        if (dx >  MOUSE_FRAME_LIMIT) dx =  MOUSE_FRAME_LIMIT;
        if (dx < -MOUSE_FRAME_LIMIT) dx = -MOUSE_FRAME_LIMIT;
        if (dy >  MOUSE_FRAME_LIMIT) dy =  MOUSE_FRAME_LIMIT;
        if (dy < -MOUSE_FRAME_LIMIT) dy = -MOUSE_FRAME_LIMIT;

        mouse_x_now += dx;
        mouse_y_now += dy;

        if (mouse_x_now < 0) mouse_x_now = 0;
        if (mouse_x_now > MOUSE_X_MAX) mouse_x_now = MOUSE_X_MAX;
        if (mouse_y_now < 0) mouse_y_now = 0;
        if (mouse_y_now > MOUSE_Y_MAX) mouse_y_now = MOUSE_Y_MAX;

        /* Game path: direction-consistency filter */
        {
            int sx = (dx > 0) ? 1 : (dx < 0) ? -1 : 0;
            int sy = (dy > 0) ? 1 : (dy < 0) ? -1 : 0;

            if (sx == 0) {
                mouse_dir_conf_x = 0;
                mouse_pending_dx = 0;
            } else if (sx == mouse_last_sign_x) {
                mouse_dir_conf_x++;
                mouse_pending_dx += dx;
            } else {
                mouse_dir_conf_x = 0;
                mouse_pending_dx = 0;
            }
            mouse_last_sign_x = sx;

            if (mouse_dir_conf_x >= DIR_CONFIRM_THRESHOLD && mouse_pending_dx != 0) {
                mouse_x_game += mouse_pending_dx;
                mouse_pending_dx = 0;
            }

            if (sy == 0) {
                mouse_dir_conf_y = 0;
                mouse_pending_dy = 0;
            } else if (sy == mouse_last_sign_y) {
                mouse_dir_conf_y++;
                mouse_pending_dy += dy;
            } else {
                mouse_dir_conf_y = 0;
                mouse_pending_dy = 0;
            }
            mouse_last_sign_y = sy;

            if (mouse_dir_conf_y >= DIR_CONFIRM_THRESHOLD && mouse_pending_dy != 0) {
                mouse_y_game += mouse_pending_dy;
                mouse_pending_dy = 0;
            }
        }

        if (mouse_x_game < 0) mouse_x_game = 0;
        if (mouse_x_game > MOUSE_X_MAX) mouse_x_game = MOUSE_X_MAX;
        if (mouse_y_game < 0) mouse_y_game = 0;
        if (mouse_y_game > MOUSE_Y_MAX) mouse_y_game = MOUSE_Y_MAX;

        /* Calibration: when idle, continuously pull display toward game coords */
        if (dx == 0 && dy == 0) {
            int dx_cal = mouse_x_game - mouse_x_now;
            int dy_cal = mouse_y_game - mouse_y_now;
            if (dx_cal >  DRIFT_CALIB_THRESH) mouse_x_now += dx_cal / DRIFT_CALIB_DIV;
            if (dx_cal < -DRIFT_CALIB_THRESH) mouse_x_now += dx_cal / DRIFT_CALIB_DIV;
            if (dy_cal >  DRIFT_CALIB_THRESH) mouse_y_now += dy_cal / DRIFT_CALIB_DIV;
            if (dy_cal < -DRIFT_CALIB_THRESH) mouse_y_now += dy_cal / DRIFT_CALIB_DIV;
        }

        if (dx == 0 && dy == 0)
            mouse_idle_frames++;
        else
            mouse_idle_frames = 0;
    }

#ifdef NAIZ_DEBUG
    {
        char _dbg[160];
        snprintf(_dbg, sizeof(_dbg),
                 "[MOUSE] g=%d/%d d=%d/%d b=%d dr=%d/%d np2=%d i33=%d/%d idle=%d\r\n",
                 mouse_x_game, mouse_y_game,
                 mouse_x_now, mouse_y_now, mouse_buttons_now,
                 dx_raw, dy_raw,
                 mouse_np2kai ? 1 : 0,
                 mouse_int33_available, mouse_int33_active,
                 mouse_idle_frames);
        hal_log(_dbg);
    }
#endif

    {   int btn_i;
        for (btn_i = 0; btn_i < 3; btn_i++) {
            if ((mouse_buttons_now & (1 << btn_i)) &&
                !(mouse_buttons_before & (1 << btn_i))) {
                if ((mouse_fifo_head + 1) % MOUSE_FIFO_SIZE != mouse_fifo_tail) {
                    mouse_click_fifo[mouse_fifo_head].button = btn_i;
                    mouse_click_fifo[mouse_fifo_head].x = mouse_x_game;
                    mouse_click_fifo[mouse_fifo_head].y = mouse_y_game;
                    mouse_fifo_head = (mouse_fifo_head + 1) % MOUSE_FIFO_SIZE;
                }
            }
        }
    }

    mouse_buttons_before = mouse_buttons_now;
}

/*=== Accessors ============================================================*/

int mouse_get_x(void) { return mouse_x_game; }
int mouse_get_y(void) { return mouse_y_game; }

/* Mouse driver initialized and available (feeds the cursor driver). */
int mouse_available(void)
{
    return mouse_is_initialized && mouse_is_available_flag;
}

/* Display coordinates (raw, uncorrected position; used for cursor visual). */
int mouse_get_display_x(void) { return mouse_x_now; }
int mouse_get_display_y(void) { return mouse_y_now; }

/*
 * Consume a single click event matching btn.
 * Advances tail past all entries up to and including the match, so
 * non-matching entries before a match are dropped.  Only HAL_MOUSE_LBUTTON
 * is used in practice, so this is correct for single-button usage;
 * for multi-button callers the entire FIFO drains on the first match.
 */
int mouse_was_clicked(int btn)
{
    int current;
    if (!mouse_is_initialized) return 0;
    current = mouse_fifo_tail;
    while (current != mouse_fifo_head) {
        if (mouse_click_fifo[current].button == btn) {
            mouse_fifo_tail = (current + 1) % MOUSE_FIFO_SIZE;
            return 1;
        }
        current = (current + 1) % MOUSE_FIFO_SIZE;
    }
    return 0;
}

void mouse_flush(void)
{
    mouse_fifo_head = 0;
    mouse_fifo_tail = 0;
}

/*=== Drain ================================================================*/

void mouse_drain(void)
{
    int dx, dy, btn;
    if (!mouse_is_initialized) return;
    mouse_read_8255(&dx, &dy, &btn);
    mouse_dir_conf_x = 0; mouse_dir_conf_y = 0;
    mouse_last_sign_x = 0; mouse_last_sign_y = 0;
    mouse_pending_dx = 0; mouse_pending_dy = 0;
    mouse_int33_valid_count = 0;
}

/*=== Recenter =============================================================*/

void mouse_recenter_if_idle(void)
{
    if (!mouse_is_initialized) return;
    if (mouse_np2kai) return; /* No drift with absolute coords */
    if (mouse_idle_frames >= MOUSE_IDLE_RESET) {
        mouse_x_now = 320;
        mouse_y_now = 200;
        mouse_x_game = 320; mouse_y_game = 200;
        mouse_flush();
        mouse_drain();
        mouse_dir_conf_x = 0; mouse_dir_conf_y = 0;
        mouse_last_sign_x = 0; mouse_last_sign_y = 0;
        mouse_pending_dx = 0; mouse_pending_dy = 0;
        mouse_idle_frames = 0;
    }
}

void mouse_set_pos(int x, int y)
{
    if (x < 0) x = 0;
    if (x > MOUSE_X_MAX) x = MOUSE_X_MAX;
    if (y < 0) y = 0;
    if (y > MOUSE_Y_MAX) y = MOUSE_Y_MAX;
    mouse_flush();
    mouse_drain();
    mouse_x_now = x;
    mouse_y_now = y;
    mouse_x_game = x; mouse_y_game = y;
    mouse_dir_conf_x = 0; mouse_dir_conf_y = 0;
    mouse_last_sign_x = 0; mouse_last_sign_y = 0;
    mouse_pending_dx = 0; mouse_pending_dy = 0;
    mouse_idle_frames = 0;
    mouse_int33_valid_count = 0;
    if (mouse_int33_active)
        mouse_int33_asm(0x0004, 0, (uint16_t)x, (uint16_t)y, NULL, NULL, NULL, NULL);
    mouse_pos_explicit = 1;
}
