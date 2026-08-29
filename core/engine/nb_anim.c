/*
 * nb_anim.c -- ANI animation playback for the NB script engine.
 *
 * Plays .ANI containers (NAIZ_ANIM v1) stored in IMAGE.DAT as raw entries.
 * Layout authority: tools/naiz_lib/anim_container.py; command spec: devdoc 80.
 *
 * Grammar:
 *   playanima{name}                    play once, container ticks pace frames
 *   playanima(once[,sec]){name}        explicit once / fixed total duration
 *   playanima(loop[,sec]){name}        loop until stopanima / scene change;
 *                                      sec = total budget per pass, resets on wrap
 *   waitanima{}                        pause script until playback finishes
 *   stopanima{}                        stop immediately
 *
 * Frames are decoded straight from the resident container bytes via
 * mag_decode (never through image_cache, never via image_load).
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nb_anim.h"
#include "render.h"
#include "image.h"
#include "scene_layers.h"
#include "layer_internal.h"
#include "hal.h"
#include "cursor.h"
#include "vm.h"
#include "debug.h"
#include "nb_asset_table.h"
#include "nb_internal.h"

/*==== Container layout constants (mirrors anim_container.py) ==============*/
#define ANI_HDR_SIZE      28L
#define ANI_OFF_VERSION   4   /* u16, must be 1 */
#define ANI_OFF_TYPE      6   /* u8  */
#define ANI_OFF_TRACK     7   /* u8  */
#define ANI_OFF_RESERVED1 9   /* u8, must be 0 */
#define ANI_OFF_NFRAMES   10  /* u16 */
#define ANI_OFF_W         12  /* u16 */
#define ANI_OFF_H         14  /* u16 */
#define ANI_OFF_PALSZ     16  /* u32 */
#define ANI_OFF_NBLOB     20  /* u32 */
#define ANI_PALETTE_BYTES 768
#define ANI_MAX_FRAMES    4096

/* Fullscreen/cine route S sizes fixed by devdoc 80 (V8 on import side) */
#define ANI_FS_W  640
#define ANI_FS_H  400
#define ANI_CINE_H 280

static AnimState g_anim;

/*==== Byte readers (alignment-safe little-endian) =========================*/

static unsigned short rd16(const unsigned char *p)
{
    return (unsigned short)((unsigned short)p[0] | ((unsigned short)p[1] << 8));
}

static unsigned long rd32(const unsigned char *p)
{
    return (unsigned long)p[0] | ((unsigned long)p[1] << 8) |
           ((unsigned long)p[2] << 16) | ((unsigned long)p[3] << 24);
}

/*==== Internal helpers ====================================================*/

/* Single termination exit for every path (finished / stopanima / replaced /
 * bg or scene implicit stop). Wakes the script loop when a waitanima pause
 * is pending. No-op when nothing is active. */
static void anim_stop_internal(void)
{
    AnimState *a = &g_anim;

    if (!a->active)
        return;

    if (a->img) {
        mag_release(a->img);
        a->img = NULL;
    }
    /* blob/offs/ticks/pals point into the resident IMAGE.DAT buffer */

    a->active = 0;
    layer_set_active(LAYER_Z_ANIM, 0);
    a->wait = 0;
    a->loop = 0;
    a->tick_armed = 0;
    a->type = -1;
    a->track = -1;
    a->nframes = 0;
    a->frame = 0;
    a->tick = 0;
    a->duration_ticks = 0;
    a->duration_total = 0;
    a->base_blitted = 0;
    a->blob = NULL;
    a->offs = NULL;
    a->ticks = NULL;
    a->pals = NULL;
    a->data_end = 0;
    a->last_ms = 0;
    a->ms_frac = 0;
    memset(a->prev_pal_r, 0xFF, sizeof(a->prev_pal_r));
    memset(a->prev_pal_g, 0xFF, sizeof(a->prev_pal_g));
    memset(a->prev_pal_b, 0xFF, sizeof(a->prev_pal_b));
    if (a->decode_buf) { free(a->decode_buf); a->decode_buf = NULL; }
    a->decode_buf_size = 0;

    vm_request_process();
}

/* Decode container frame `frame` into a fresh MagImage. Returns NULL on any
 * failure (caller logs and stops). Blob size = gap to next offset; last blob
 * ends where the palette table starts (palette track) resp. at file end.
 * When a->decode_buf is available, uses mag_decode_into to avoid per-frame
 * malloc/free (OPT-11). */
static MagImage *anim_decode_frame(AnimState *a, int frame)
{
    MagImage *img = NULL;
    long off, off_end;
    int blob_size;

    if (!a->blob || !a->offs || frame < 0 || frame >= a->nframes)
        return NULL;
    off = (long)rd32(a->offs + (long)frame * 4L);
    if (frame + 1 < a->nframes)
        off_end = (long)rd32(a->offs + (long)(frame + 1) * 4L);
    else
        off_end = a->data_end;
    if (off <= 0 || off_end <= off || off_end > a->data_end)
        return NULL;
    blob_size = (int)(off_end - off);
    if (a->decode_buf && a->decode_buf_size > 0) {
        if (mag_decode_into(a->blob + off, blob_size,
                            a->decode_buf, a->decode_buf_size, &img) != 0)
            return NULL;
    } else {
        if (mag_decode(a->blob + off, blob_size, &img) != 0)
            return NULL;
    }
    return img;
}

/* Per-frame tick count from the container tick table (L5 guarantees >= 1). */
static int anim_frame_ticks(const AnimState *a)
{
    int t;

    if (!a->ticks || a->frame < 0 || a->frame >= a->nframes)
        return 1;
    t = (int)rd16(a->ticks + (long)a->frame * 2);
    return (t >= 1) ? t : 1;
}

/* Recapture the dialog-area snapshot after pixels under an open dialog were
 * overwritten, so later dialog restore composites over live animation pixels
 * instead of stale pre-animation background (devdoc 77 4.7 flow).
 * OPT-10: copies directly from the MagImage RAM buffer (just decoded),
 * avoiding a 55KB VRAM readback per frame. */
static void anim_rebuild_dialog_if_open(const MagImage *img, int blit_x, int blit_y)
{
    if (layer_dialog_drawn() && img && img->pixels)
        layer_capture_bg_dialog_from_image(img->pixels, img->width, blit_x, blit_y);
}

/* Palette indices protected during cine playback — must not be overwritten
 * when the dialog is visible, otherwise colours shift even though pixels
 * are untouched.  Index 0 (screen base black) is included so the border
 * strips outside the dialog box stay black after each palette remap.
 * O(1) lookup via static table (initialized once). */
static uint8_t prot_pal[256];
static void anim_init_protected_pal(void)
{
    memset(prot_pal, 0, sizeof(prot_pal));
    prot_pal[0] = 1;                 /* screen base black, border fill */
    prot_pal[PAL_WHITE] = 1;         /* border, text */
    prot_pal[PAL_TRANSPARENT] = 1;   /* transparency sentinel */
    prot_pal[PAL_DIALOG_FILL] = 1;   /* dialog background */
    prot_pal[BTN_FILL_IDX] = 1;      /* button fill */
    prot_pal[MENU_PAL_WHITE] = 1;    /* unselected option text */
    prot_pal[MENU_PAL_YELLOW] = 1;   /* highlighted option text */
    prot_pal[BTN_HIGHLIGHT_IDX] = 1; /* button highlight */
    prot_pal[BTN_SHADOW_IDX] = 1;    /* button shadow */
    prot_pal[PAL_CURSOR_BLACK] = 1;  /* cursor outline */
}

/* Fill the border strips outside the dialog box (left: x=0..79,
 * right: x=560..639, both y=280..399) with index 0 (black).
 * Called after each cine palette remap so the strips stay black
 * regardless of how the cine rewrites the global palette. */
static void anim_fill_dialog_border(void)
{
    fill_rect(0, LAYER_DIALOG_Y,
              LAYER_DIALOG_X, LAYER_SCREEN_H - LAYER_DIALOG_Y, 0);
    fill_rect(LAYER_DIALOG_X + LAYER_DIALOG_W, LAYER_DIALOG_Y,
              LAYER_SCREEN_W - LAYER_DIALOG_X - LAYER_DIALOG_W,
              LAYER_SCREEN_H - LAYER_DIALOG_Y, 0);
}

/* Draw current frame. PIXEL: full-frame blit (fullscreen additionally
 * rebuilds the dialog snapshot). PALETTE: blit base once, then apply the
 * per-frame 768-byte table. Cine is 640x280 at (0,0): never reaches the
 * dialog area by construction.  When the dialog is open, protected palette
 * indices (0/7/15/248-254) are skipped and border strips are refilled
 * black to preserve dialog colours regardless of global palette remaps.
 * OPT-14: dialog_drawn cached before palette loops to avoid repeated calls. */
static void anim_draw_frame(AnimState *a)
{
    const unsigned char *pal;
    int i, dlg_on;

    /* OPT-14: cache once — avoids repeated layer_dialog_drawn() overhead
     * inside the palette loops and branch below. */
    dlg_on = layer_dialog_drawn();

    if (a->track == 0) {
        /* Program the frame's own palette first: pixel-track frames come
         * straight from mag_decode (never image_load), so unlike cmd_bg
         * nobody else applies their palette. Without this, indices render
         * through whatever palette the previous background left behind
         * (observed: dark-blue frames rendering near-black).
         * Dirty-diff: skip entries whose RGB hasn't changed. */
        for (i = 0; i < a->img->num_colors && i < 256; i++) {
            uint8_t r = a->img->palette_r[i];
            uint8_t g = a->img->palette_g[i];
            uint8_t b = a->img->palette_b[i];
            if (dlg_on && prot_pal[i])
                continue;
            if (r == a->prev_pal_r[i] && g == a->prev_pal_g[i] && b == a->prev_pal_b[i])
                continue;
            hal_set_palette(i, r, g, b);
            a->prev_pal_r[i] = r;
            a->prev_pal_g[i] = g;
            a->prev_pal_b[i] = b;
        }
        if (dlg_on)
            anim_fill_dialog_border();
        if (dlg_on && a->type == 0)
            vram_blit_sprite(a->img, 0, 0, PAL_NO_TRANSPARENCY, 0, LAYER_DIALOG_Y);
        else
            vram_blit(a->img, 0, 0);
        cursor_refresh();
        if (a->type == 0)
            anim_rebuild_dialog_if_open(a->img, 0, 0);
        return;
    }

    if (!a->base_blitted && a->img) {
        if (dlg_on)
            vram_blit_sprite(a->img, 0, 0, PAL_NO_TRANSPARENCY, 0, LAYER_DIALOG_Y);
        else
            vram_blit(a->img, 0, 0);
        cursor_refresh();
        a->base_blitted = 1;
        anim_rebuild_dialog_if_open(a->img, 0, 0);
    }
    if (!a->pals)
        return;
    pal = a->pals + (long)a->frame * ANI_PALETTE_BYTES;
    if (!dlg_on) {
        for (i = 0; i < 256; i++) {
            uint8_t r = pal[i * 3];
            uint8_t g = pal[i * 3 + 1];
            uint8_t b = pal[i * 3 + 2];
            if (r == a->prev_pal_r[i] && g == a->prev_pal_g[i] && b == a->prev_pal_b[i])
                continue;
            hal_set_palette(i, r, g, b);
            a->prev_pal_r[i] = r;
            a->prev_pal_g[i] = g;
            a->prev_pal_b[i] = b;
        }
    } else {
        for (i = 0; i < 256; i++) {
            uint8_t r = pal[i * 3];
            uint8_t g = pal[i * 3 + 1];
            uint8_t b = pal[i * 3 + 2];
            if (prot_pal[i])
                continue;
            if (r == a->prev_pal_r[i] && g == a->prev_pal_g[i] && b == a->prev_pal_b[i])
                continue;
            hal_set_palette(i, r, g, b);
            a->prev_pal_r[i] = r;
            a->prev_pal_g[i] = g;
            a->prev_pal_b[i] = b;
        }
    }
    if (dlg_on)
        anim_fill_dialog_border();
}

/*==== Command handlers ====================================================*/

void cmd_playanima(int argc, const char **argv, const char *cmd_name)
{
    AnimState *a = &g_anim;
    const struct { const char *name; int id; } *p;
    const unsigned char *blob;
    const unsigned char *offs_base;
    long blob_len = 0;
    long table_end;
    long data_end;
    long prev_off;

    const char *kw, *name;
    int atype, atrack, nframes, w, h, i;
    unsigned long palsz_ul, nblob_ul, o;
    int id = -1;
    int mode = 0;          /* 0=once, 1=loop */
    int has_dur = 0;
    int dur_ticks = 0;
    double sec = 0.0;


    (void)cmd_name;

    /* Grammar (nb_parse_line yields argv[argc-1] == brace payload):
     *   argc==1: name                          -> once
     *   argc==2: once|loop, name               -> mode, container pacing
     *   argc==3: once|loop, sec, name          -> mode + duration budget
     * Anything else is rejected with the received content logged (D7). */
    kw = (argc >= 1) ? argv[0] : "";
    name = (argc >= 1) ? argv[argc - 1] : "";
    anim_init_protected_pal();
    if (argc == 1) {
        mode = 0;
    } else if (argc == 2 && (strcmp(kw, "once") == 0 || strcmp(kw, "loop") == 0)) {
        mode = (strcmp(kw, "loop") == 0) ? 1 : 0;
    } else if (argc == 3 && (strcmp(kw, "once") == 0 || strcmp(kw, "loop") == 0)) {
        mode = (strcmp(kw, "loop") == 0) ? 1 : 0;
        sec = atof(argv[1]);
        if (!(sec > 0.0)) {
            NB_DEBUG("playanima: bad duration '%s', must be > 0 seconds\r\n", argv[1]);
            return;
        }
        has_dur = 1;
        /* ceil(sec*60) without math.h: near-integer addend keeps exact values stable */
        dur_ticks = (int)(sec * 60.0 + 0.999999);
        if (dur_ticks < 1)
            dur_ticks = 1;
    } else {
        NB_DEBUG("playanima: rejected argc=%d argv0='%s' (usage: playanima(once|loop[,sec]){name})\r\n",
                 argc, kw);
        return;
    }

    /* Implicitly replace any currently playing animation */
    anim_stop_internal();

    /* Resolve name -> asset id via generated table (ASSETS.DB type='ANI') */
    for (p = anim_map; p->name != NULL; p++) {
        if (strcmp(p->name, name) == 0) {
            id = p->id;
            break;
        }
    }
    if (id < 0 || id > 65535) {
        NB_DEBUG("playanima: animation '%s' not found in anim_map\r\n", name);
        return;
    }

    blob = image_raw_blob((unsigned short)id, &blob_len);

    if (!blob || blob_len < ANI_HDR_SIZE) {
        NB_DEBUG("playanima: cannot fetch container '%s' (id=%d len=%ld)\r\n", name, id, blob_len);
        return;
    }

    /* L1: magic "ANIZ" + version */
    if (blob[0] != 'A' || blob[1] != 'N' || blob[2] != 'I' || blob[3] != 'Z') {
        NB_DEBUG("playanima: container '%s' bad magic\r\n", name);
        return;
    }
    if (rd16(blob + ANI_OFF_VERSION) != 1) {
        NB_DEBUG("playanima: container '%s' unsupported version %u\r\n", name,
                 (unsigned)rd16(blob + ANI_OFF_VERSION));
        return;
    }

    atype = blob[ANI_OFF_TYPE];
    atrack = blob[ANI_OFF_TRACK];
    nframes = (int)rd16(blob + ANI_OFF_NFRAMES);
    w = (int)rd16(blob + ANI_OFF_W);
    h = (int)rd16(blob + ANI_OFF_H);
    palsz_ul = rd32(blob + ANI_OFF_PALSZ);
    nblob_ul = rd32(blob + ANI_OFF_NBLOB);

    /* L2 */
    if (atype > 1 || atrack > 1) {
        NB_DEBUG("playanima: container '%s' bad type %d track %d\r\n", name, atype, atrack);
        return;
    }
    if (blob[ANI_OFF_RESERVED1] != 0) {
        NB_DEBUG("playanima: container '%s' reserved1 must be 0\r\n", name);
        return;
    }

    /* L3 */
    if (nframes < 1 || nframes > ANI_MAX_FRAMES) {
        NB_DEBUG("playanima: container '%s' nframes=%d out of range\r\n", name, nframes);
        return;
    }
    if (atrack == 0) {
        if (nblob_ul != (unsigned long)nframes) {
            NB_DEBUG("playanima: '%s' pixel nblob %lu != nframes %d\r\n",
                     name, nblob_ul, nframes);
            return;
        }
        if (palsz_ul != 0UL) {
            NB_DEBUG("playanima: '%s' pixel palsz %lu must be 0\r\n", name, palsz_ul);
            return;
        }
    } else {
        if (nblob_ul != 1UL) {
            NB_DEBUG("playanima: '%s' palette nblob %lu must be 1\r\n", name, nblob_ul);
            return;
        }
        if (palsz_ul != (unsigned long)nframes * ANI_PALETTE_BYTES) {
            NB_DEBUG("playanima: '%s' palsz %lu != nframes*%d\r\n",
                     name, palsz_ul, ANI_PALETTE_BYTES);
            return;
        }
    }

    /* L4: tables must fit; palette table sits at file end */
    table_end = ANI_HDR_SIZE + (long)nblob_ul * 4L + (long)nframes * 2L;
    if (blob_len < table_end || (long)palsz_ul > blob_len ||
        blob_len < table_end + (long)palsz_ul) {
        NB_DEBUG("playanima: container '%s' truncated (len=%ld need>=%ld)\r\n",
                 name, blob_len, table_end + (long)palsz_ul);
        return;
    }

    /* Route S size check (devdoc 80): fullscreen 640x400, cine 640x280 */
    if ((atype == 0 && (w != ANI_FS_W || h != ANI_FS_H)) ||
        (atype == 1 && (w != ANI_FS_W || h != ANI_CINE_H))) {
        NB_DEBUG("playanima: '%s' size %dx%d violates route S (%dx%d/%dx%d)\r\n",
                 name, w, h, ANI_FS_W, ANI_FS_H, ANI_FS_W, ANI_CINE_H);
        return;
    }

    offs_base = blob + ANI_HDR_SIZE;
    data_end = (atrack == 1) ? (blob_len - (long)palsz_ul) : blob_len;

    /* L4 offsets: strictly increasing, inside [table_end, data_end] */
    prev_off = -1;
    for (i = 0; i < (int)nblob_ul; i++) {
        o = rd32(offs_base + (long)i * 4L);
        if ((long)o <= prev_off || (long)o < table_end || (long)o > data_end) {
            NB_DEBUG("playanima: '%s' bad offset[%d]=%lu\r\n", name, i, o);
            return;
        }
        prev_off = (long)o;
    }

    /* L5: every tick entry must be >= 1 */
    for (i = 0; i < nframes; i++) {
        if ((int)rd16(offs_base + (long)nblob_ul * 4L + (long)i * 2L) < 1) {
            NB_DEBUG("playanima: '%s' tick[%d] < 1\r\n", name, i);
            return;
        }
    }

    /* Arm state, then decode frame 0 before going active so a decode failure
     * never leaves a half-initialized animation behind. */
    a->blob = blob;
    a->offs = offs_base;
    a->ticks = offs_base + (long)nblob_ul * 4L;
    a->pals = (atrack == 1) ? (blob + (blob_len - (long)palsz_ul)) : NULL;
    a->data_end = data_end;
    a->type = atype;
    a->track = atrack;
    a->nframes = nframes;
    a->frame = 0;
    a->loop = mode;
    a->tick = anim_frame_ticks(a);
    a->duration_ticks = has_dur ? dur_ticks : 0;
    a->duration_total = has_dur ? dur_ticks : 0;
    a->base_blitted = 0;

    /* OPT-11: allocate decode work buffer for pixel-track animations.
     * All frames share the same dimensions, so one allocation serves all.
     * Worst case pool: output(w*h) + action(w/4) + final(w*h) + crop(w*h) + struct */
    if (atrack == 0) {
        int pool_8bpp = w * h + w / 4 + 64;
        int pool_4bpp = w * h + w / 4 + w * h + w * h + 256;
        int pool = (pool_8bpp > pool_4bpp ? pool_8bpp : pool_4bpp) + (int)sizeof(MagImage) + 256;
        a->decode_buf = (uint8_t *)malloc(pool);
        if (a->decode_buf) {
            a->decode_buf_size = pool;
        } else {
            a->decode_buf_size = 0;
            hal_log("anim: decode buf OOM, falling back to per-frame alloc\r\n");
        }
    }
    a->blob = blob;
    a->offs = offs_base;
    a->ticks = offs_base + (long)nblob_ul * 4L;
    a->pals = (atrack == 1) ? (blob + (blob_len - (long)palsz_ul)) : NULL;
    a->data_end = data_end;
    a->type = atype;
    a->track = atrack;
    a->nframes = nframes;
    a->frame = 0;
    a->loop = mode;
    a->tick = anim_frame_ticks(a);
    a->duration_ticks = has_dur ? dur_ticks : 0;
    a->duration_total = has_dur ? dur_ticks : 0;
    a->base_blitted = 0;
    a->img = anim_decode_frame(a, 0);

    if (!a->img) {
        NB_DEBUG("playanima: frame 0 decode failed for '%s'\r\n", name);
        anim_stop_internal();
        return;
    }

    a->active = 1;
    layer_set_active(LAYER_Z_ANIM, 1);
    vblank_wait();
    anim_draw_frame(a);

    NB_DEBUG("playanima: started '%s' %s%s%s %s/%s %dx%d frames=%d\r\n",
             name,
             has_dur ? "dur=" : "", has_dur ? argv[1] : "", has_dur ? "s " : "",
             atype == 0 ? "fullscreen" : "cine",
             atrack == 0 ? "pixel" : "palette",
             w, h, nframes);
}

void cmd_waitanima(int argc, const char **argv, const char *cmd_name)
{
    AnimState *a = &g_anim;

    (void)argv;
    (void)cmd_name;

    if (argc != 0)
        NB_DEBUG("waitanima: unexpected %d arg(s) ignored\r\n", argc);
    if (!a->active) {
        hal_log("waitanima: no active animation, passing through\r\n");
        return;
    }
    if (a->loop)
        NB_DEBUG("waitanima: loop animation never finishes by itself; "
                 "blocked until stopanima\r\n");
    a->wait = 1;
    vm_pause_process();
}

void cmd_stopanima(int argc, const char **argv, const char *cmd_name)
{
    (void)argv;
    (void)cmd_name;

    if (argc != 0)
        NB_DEBUG("stopanima: unexpected %d arg(s) ignored\r\n", argc);
    anim_stop_internal();
    hal_log("stopanima: stopped\r\n");
}

/*==== Public API ==========================================================*/

int anim_waiting(void)
{
    return (g_anim.active && g_anim.wait) ? 1 : 0;
}

int anim_playing(void)
{
    return g_anim.active;
}

void anim_stop(void)
{
    anim_stop_internal();
}

int anim_tick(void)
{
    AnimState *a = &g_anim;
    MagImage *ni;
    unsigned long now, delta;
    int steps, i;

    if (!a->active)
        return 0;

    /*
     * Time-based stepping: convert elapsed wall time into nominal tick
     * units (60 ticks/s) so playback duration tracks real seconds no
     * matter how slow the host loop runs (under NP2kai the pass rate is
     * ~20Hz, far below the historical 60Hz assumption).
     * OPT-13: integer fixed-point (10-bit fraction) replaces double.
     * 1 tick = 1000/60 ms; in fixed-point: tick_fp = 1024*1000/60 = 17067.
     * ms_frac += delta_ms * 61; steps = ms_frac / 1024.
     *
     * Calibration: the first call after arm records the baseline timestamp
     * via tick_armed (not last_ms==0, which is ambiguous when PIT returns 0).
     * When the PIT is unavailable (hal_wallclock_ms()==0), we fall back to
     * a fixed 16ms per call so the animation never freezes.
     */
    now = hal_wallclock_ms();
    if (!a->tick_armed) {
        a->last_ms = now;
        a->tick_armed = 1;
        return a->img != NULL;     /* calibration pass, no advancement */
    }
    if (now == 0) {
        /* PIT unavailable: assume one tick per call (60Hz pace).
         * 1024 = 1 tick in 10-bit fixed-point (1024/61 ≈ 16.787ms). */
        a->ms_frac += 1024UL;
    } else if (now < a->last_ms) {
        /* Midnight / counter wrap: recalibrate */
        a->last_ms = now;
        return a->img != NULL;
    } else {
        delta = now - a->last_ms;
        a->last_ms = now;
        a->ms_frac += delta * 61;  /* 61 ≈ 1024*60/1000 */
    }
    steps = (int)(a->ms_frac / 1024);
    if (steps <= 0)
        return a->img != NULL;     /* less than one tick elapsed */
    if (steps > 180)               /* clamp catch-up after long stalls */
        steps = 180;
    a->ms_frac -= (unsigned long)steps * 1024;

    for (i = 0; i < steps; i++) {
        /* Duration budget countdown overrides natural end / frame looping.
         * Expiry always terminates playback (even in loop mode): the loop
         * flag only wraps the frame sequence, sec bounds the total time. */
        if (a->duration_total > 0 && --a->duration_ticks <= 0) {
            anim_stop_internal();
            hal_log("anim: finished (duration elapsed)\r\n");
            return 0;
        }

        /* Current frame still holding */
        if (a->tick > 0) {
            a->tick--;
            continue;
        }

        /* Advance to next frame */
        a->frame++;
        if (a->frame >= a->nframes) {
            if (!a->loop) {
                anim_stop_internal();
                hal_log("anim: finished\r\n");
                return 0;
            }
            a->frame = 0;
        }

        /* Palette track: single base blob, only palette changes per frame.
         * Skip decode/replacement — a->img already holds the base image. */
        if (a->track != 1) {
            ni = anim_decode_frame(a, a->frame);
            if (!ni) {
                NB_DEBUG("anim: decode failed at frame %d, stopping\r\n", a->frame);
                anim_stop_internal();
                return 0;
            }
            if (a->img)
                mag_release(a->img);
            a->img = ni;
        }
        a->tick = anim_frame_ticks(a);
        anim_draw_frame(a);
    }

    return a->img != NULL;
}
