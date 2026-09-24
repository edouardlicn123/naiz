/*
 * IMAGE.DAT loader — on-demand archive reader (devdoc 100).
 *
 * Format (see farchive.h / tools/naiz_lib/toc_archive.py):
 *   uint32   count
 *   N x { char name[12], uint32 offset, uint32 size }
 *   raw MAG data concatenated
 *
 * The TOC stays resident; payloads are read from the open stream on
 * demand, so memory usage tracks the running decode set plus one raw
 * blob slot instead of the whole archive.
 *
 * After image_load(id), if img->is_sprite == 0:
 *   image_set_palette(img) is called automatically.
 * For sprites (is_sprite == 1):
 *   no palette update — share scene palette.
 */
#include "image.h"
#include "mag.h"
#include <stdlib.h>
#include <string.h>
#include "farchive.h"
#include "hal.h"
#include "image_internal.h"

/* Open IMAGE.DAT archive with TOC resident and single-blob raw access */
static FArchive g_image_arc;
/* Raw blob slot (owned): the only payload kept resident outside the cache */
static uint8_t *g_blob_buf = NULL;
static long     g_blob_len = 0;
/* Blob slot holds entry g_blob_id; -1 = empty */
static int      g_blob_id = -1;

static void image_set_palette(const MagImage *img);

/* Forward declarations */
static void image_close(void);

/*=== Public API ===========================================================*/

/* Load and initialize the IMAGE.DAT archive.
 * Parses the TOC (kept resident via FArchive), verifies palette
 * consistency across all entries, and primes the LRU cache slots.
 * Returns 0 on success, -1 on failure. */
int image_init(const char *path)
{
    if (g_image_arc.fp) {
        image_close();
    }

    if (farchive_open(&g_image_arc, path, 8192) != 0) {
        hal_log("Img: no IMAGE.DAT\r\n");
        return -1;
    }
    if (g_image_arc.truncated) {
        hal_log("WARN: IMAGE.DAT TOC truncated to 8192 entries\r\n");
    }

    hal_log("Img OK\r\n");

    /* Initialize cache slots to empty */
    image_cache_init();

    /* Verify shared-palette invariant across all entries */
    {
        int have_ref = 0;
        uint8_t ref_r[256], ref_g[256], ref_b[256];
        int warned = 0;
        int j;

        for (j = 0; j < g_image_arc.count; j++) {
            long eoffset, esize;
            uint8_t *raw;
            int nc;
            uint8_t pr[256], pg[256], pb[256];

            if (farchive_lookup_id(&g_image_arc, j, &eoffset, &esize) != 0) continue;
            if (esize <= 0) continue;

            raw = farchive_read_alloc(&g_image_arc, eoffset, esize, NULL);
            if (!raw) continue;
            nc = mag_read_palette(raw, (int)esize, pr, pg, pb);
            free(raw);
            if (nc < 0) continue;

            if (!have_ref) {
                have_ref = 1;
                memcpy(ref_r, pr, 256);
                memcpy(ref_g, pg, 256);
                memcpy(ref_b, pb, 256);
                if (ref_r[7] != 255 || ref_g[7] != 255 || ref_b[7] != 255) {
                    hal_log("WARN: IMAGE.DAT idx7 != white\r\n");
                    warned = 1;
                }
                if (ref_r[15] != 255 || ref_g[15] != 255 || ref_b[15] != 255) {
                    hal_log("WARN: IMAGE.DAT idx15 != white\r\n");
                    warned = 1;
                }
            } else {
                int k;
                for (k = 0; k < 256; k++) {
                    if (pr[k] != ref_r[k] || pg[k] != ref_g[k] || pb[k] != ref_b[k]) {
                        hal_log("WARN: IMAGE.DAT palette mismatch\r\n");
                        warned = 1;
                        break;
                    }
                }
                if (warned) break;
            }
        }

        if (have_ref && !warned) {
            hal_log("Img pal OK\r\n");
        }
    }
    return 0;
}

/* Load and decode a single image by TOC index.
 * Uses the LRU cache: on hit, returns a mag_retain'd shared pointer to the
 * cached image.  On miss, decodes, inserts into cache (cache takes ownership),
 * retains the decoded image and returns it.  Caller must mag_release() the
 * returned pointer after use. */
MagImage *image_load(unsigned short id)
{
    long offset, msize;
    MagImage *img;
    uint8_t *raw;

    if (!g_image_arc.fp || (int)id >= g_image_arc.count)
        return NULL;

    /* Check cache first */
    {
        MagImage *cached = image_cache_lookup((int)id);
        if (cached) {
            if (!cached->is_sprite) {
                image_set_palette(cached);
            }
            return cached;
        }
    }

    if (farchive_lookup_id(&g_image_arc, (int)id, &offset, &msize) != 0)
        return NULL;
    if (msize <= 0)
        return NULL;

    raw = farchive_read_alloc(&g_image_arc, offset, msize, NULL);
    if (!raw)
        return NULL;
    if (mag_decode(raw, (int)msize, &img) != 0) {
        free(raw);
        return NULL;
    }
    free(raw);

    if (!img->is_sprite) {
        image_set_palette(img);
    }

    /* Insert into cache — cache takes ownership of img (no deep copy).
     * img keeps refcount 1 (slot holds it).  Retain before returning so the
     * caller holds its own reference; caller must mag_release() after use. */
    image_cache_insert((int)id, img);
    return mag_retain(img);
}

/*=== Raw blob access ======================================================*/

/* Return a pointer to the raw archive bytes of entry id (no decode).
 * Contents live in an internal single-slot buffer: the return value is
 * valid only until the next image_raw_blob call or image_init/image_close.
 * The sole consumer (nb_anim.c playanima) stops the current animation
 * before fetching the next blob, so the borrow never dangles.  *out_size
 * (optional) receives the byte length.  Returns NULL on bad id, hole or
 * TOC corruption. */
const unsigned char *image_raw_blob(unsigned short id, long *out_size)
{
    long offset = 0;
    long msize = 0;
    uint8_t *buf;

    if (out_size)
        *out_size = 0;
    if (!g_image_arc.fp || (int)id >= g_image_arc.count)
        return NULL;

    if (farchive_lookup_id(&g_image_arc, (int)id, &offset, &msize) != 0)
        return NULL;
    if (msize <= 0)
        return NULL;

    if (g_blob_id != (int)id) {
        buf = farchive_read_alloc(&g_image_arc, offset, msize, NULL);
        if (!buf)
            return NULL;
        if (g_blob_buf)
            free(g_blob_buf);
        g_blob_buf = buf;
        g_blob_len = msize;
        g_blob_id = (int)id;
    }

    if (out_size)
        *out_size = g_blob_len;
    return g_blob_buf;
}

/* Free the IMAGE.DAT archive and reset all state. */
static void image_close(void)
{
    if (g_blob_buf) {
        free(g_blob_buf);
        g_blob_buf = NULL;
    }
    g_blob_len = 0;
    g_blob_id = -1;
    image_cache_clear();
    farchive_close(&g_image_arc);
}

/*=== Internal palette helper ==============================================*/

static void image_set_palette(const MagImage *img)
{
    int i;
    int nc;

    nc = img->num_colors;
    if (nc > 256) nc = 256;

    for (i = 0; i < nc; i++) {
        /* sprites: skip idx 7/15 to preserve engine white for transparency
         * BG images: apply full palette (including idx 7/15) */
        if (img->is_sprite && (i == 7 || i == 15)) continue;
        hal_set_palette(i, img->palette_r[i],
                        img->palette_g[i], img->palette_b[i]);
    }
}
