/*
 * IMAGE.DAT loader — MMAP-style archive for MAG images.
 *
 * Format:
 *   uint32   count        number of archived files
 *   N x {    TOC entry:
 *     char  name[12]      8.3 filename (debug)
 *     uint32 offset       byte offset to MAG data
 *     uint32 size         MAG data size in bytes
 *   }
 *   raw MAG concatenation
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
#include "endian.h"
#include "hal.h"
#include "naiz_file.h"
#include "image_internal.h"

/* MMAP buffer: entire IMAGE.DAT loaded into memory */
static uint8_t *g_image_data = NULL;
/* Total file size in bytes */
static long     g_image_size = 0;
/* Number of archived images */
static int      g_image_count = 0;
/* Offset to the first TOC entry (right after the 4-byte count) */
static long     g_image_toc_off = 4;

static void image_set_palette(const MagImage *img);

#define TOC_ENTRY_SIZE 20  /* name[12] + offset[4] + size[4] */

/* Forward declarations */
static int image_get_entry(long entry_off, long *out_offset, long *out_size);
static void image_close(void);

/*=== Public API ===========================================================*/

/* Load and initialize the IMAGE.DAT archive.
 * Reads the entire file into g_image_data, parses the TOC count,
 * and validates palette consistency across all entries.
 * Returns 0 on success, -1 on failure. */
int image_init(const char *path)
{
    long fsize;
    uint32_t tmp_count;

    if (g_image_data) {
        image_close();
    }

    g_image_data = (uint8_t *)file_read_all(path, &fsize);
    if (!g_image_data) {
        hal_log("Img: no IMAGE.DAT\r\n");
        return -1;
    }

    if (fsize < 4) {
        hal_log("WARN: IMAGE.DAT too small\r\n");
        free(g_image_data);
        g_image_data = NULL;
        return -1;
    }
    g_image_size = fsize;

    /* Parse TOC */
    tmp_count = read32_le(g_image_data);
    if (tmp_count > 8192) {
        tmp_count = 8192;
        hal_log("WARN: IMAGE.DAT TOC truncated to 8192 entries\r\n");
    }
    g_image_count = (int)tmp_count;
    g_image_toc_off = 4;

    hal_log("Img OK\r\n");

    /* Initialize cache slots to empty */
    image_cache_init();

    /* Verify shared-palette invariant across all entries */
    {
        int have_ref = 0;
        uint8_t ref_r[256], ref_g[256], ref_b[256];
        int warned = 0;
        int j;

        for (j = 0; j < g_image_count; j++) {
            long eoff, eoffset, esize;
            int nc;
            uint8_t pr[256], pg[256], pb[256];

            eoff = g_image_toc_off + (long)j * TOC_ENTRY_SIZE;
            if (image_get_entry(eoff, &eoffset, &esize) != 0) continue;
            if (esize == 0) continue;
            if (eoffset < 0 || (unsigned long)eoffset + (unsigned long)esize > (unsigned long)g_image_size) continue; /* bounds check */

            nc = mag_read_palette(g_image_data + eoffset, (int)esize, pr, pg, pb);
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
    long offset, msize, entry_off;
    MagImage *img;
    uint8_t *raw;

    if (!g_image_data || (int)id >= g_image_count)
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

    entry_off = g_image_toc_off + (long)id * TOC_ENTRY_SIZE;
    if (image_get_entry(entry_off, &offset, &msize) != 0)
        return NULL;

    if (offset < 0 || msize < 0) return NULL;
    if ((unsigned long)offset + (unsigned long)msize > (unsigned long)g_image_size)
        return NULL;

    raw = g_image_data + offset;
    if (mag_decode(raw, (int)msize, &img) != 0)
        return NULL;

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
 * Valid until the next image_init/image_close; *out_size (optional)
 * receives the byte length. Returns NULL on bad id or TOC corruption. */
const unsigned char *image_raw_blob(unsigned short id, long *out_size)
{
    long entry_off;
    long offset = 0;
    long msize = 0;

    if (out_size)
        *out_size = 0;
    if (!g_image_data || (int)id >= g_image_count)
        return NULL;

    entry_off = g_image_toc_off + (long)id * TOC_ENTRY_SIZE;
    if (image_get_entry(entry_off, &offset, &msize) != 0)
        return NULL;
    if (offset < 0 || msize <= 0)
        return NULL;
    if ((unsigned long)offset + (unsigned long)msize > (unsigned long)g_image_size)
        return NULL;

    if (out_size)
        *out_size = msize;
    return g_image_data + offset;
}

/* Free the IMAGE.DAT archive and reset all state. */
static void image_close(void)
{
    if (g_image_data) {
        free(g_image_data);
        g_image_data = NULL;
    }
    image_cache_clear();
    g_image_size = 0;
    g_image_count = 0;
    g_image_toc_off = 4;
}

/*=== Internal helpers ======================================================*/

/* Read TOC entry offset and size at entry_off, return 0 on success. */
static int image_get_entry(long entry_off, long *out_offset, long *out_size)
{
    if (entry_off < 0 || entry_off + TOC_ENTRY_SIZE > g_image_size)
        return -1;
    *out_offset = (long)read32_le(g_image_data + entry_off + 12);
    *out_size   = (long)read32_le(g_image_data + entry_off + 16);
    return 0;
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
