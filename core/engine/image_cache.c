/*
 * image_cache.c — LRU cache for decoded MAG images.
 *
 * Split from image.c: cache policy (slot count, LRU scoring, copy-in/copy-out
 * semantics) evolves independently of IMAGE.DAT TOC parsing and decoding.
 * Depends only on mag.h — touches no archive globals.
 *
 * Ownership model (refcount-based, no deep copies):
 *   - Each slot holds exactly one reference to its decoded MagImage.
 *   - lookup() hit: returns mag_retain'd shared pointer (caller must release).
 *   - insert(): cache takes ownership of img — no deep copy; caller must NOT
 *     release img after insert (caller transfers its reference to the cache).
 *   - evict/clear: slot mag_release() drops the cache's reference.
 * Caller discipline: every mag_retain (from lookup) must be paired with
 * mag_release after use; the borrow never dangles because the slot keeps
 * a live reference until evict, and evict only drops that reference.
 */
#include <stdlib.h>
#include "image_internal.h"
#include "mag.h"

/* devdoc 177: 8 -> 32 so a scene preload can stage every bg/char/cg of the
 * incoming script while the transition covers the screen.  The slot array is
 * pointer-sized entries only; the decoded images themselves are what cost
 * heap, and preload only keeps what the script actually references. */
#define IMAGE_CACHE_SLOTS 32

/* Hit floor for a prefetched image.  Eviction picks the lowest-hits slot, so a
 * just-prefetched image (hits 0) would be the first thrown away before its
 * script command ran; the pin lifts it above the freshly-loaded slots until it
 * is used (devdoc 133 方案 D). */
#define IMAGE_CACHE_PREFETCH_HITS 4

typedef struct {
    int       id;            /* asset_id, -1 = empty */
    MagImage *img;           /* decoded image */
    int       hits;          /* access count for LRU eviction */
    int       ready;         /* devdoc 177: slot holds a complete image */
} ImageCacheSlot;

static ImageCacheSlot g_image_cache[IMAGE_CACHE_SLOTS];

/* Initialize all cache slots to empty. */
void image_cache_init(void)
{
    int i;
    for (i = 0; i < IMAGE_CACHE_SLOTS; i++) {
        g_image_cache[i].id = -1;
        g_image_cache[i].img = NULL;
        g_image_cache[i].hits = 0;
        g_image_cache[i].ready = 0;
    }
}

/* Free all cached images and reset the slots. */
void image_cache_clear(void)
{
    int i;
    for (i = 0; i < IMAGE_CACHE_SLOTS; i++) {
        if (g_image_cache[i].img) {
            mag_release(g_image_cache[i].img);
            g_image_cache[i].img = NULL;
        }
        g_image_cache[i].id = -1;
        g_image_cache[i].hits = 0;
        g_image_cache[i].ready = 0;
    }
}

/* Look up an image by id.  On hit returns a mag_retain'd shared pointer to
 * the cached image (caller must mag_release it), NULL on miss. */
MagImage *image_cache_lookup(int id)
{
    int i;
    if (id < 0) return NULL;
    for (i = 0; i < IMAGE_CACHE_SLOTS; i++) {
        if (g_image_cache[i].id == id) {
            /* devdoc 177: a slot is only legal to hand out once its image is
             * complete; a resident-but-not-ready slot is a miss. */
            if (!g_image_cache[i].ready)
                return NULL;
            g_image_cache[i].hits++;
            return mag_retain(g_image_cache[i].img);
        }
    }
    return NULL;
}

/* Insert a decoded image into the cache.  The cache takes ownership of img
 * (stores the pointer directly, no deep copy) — the caller must NOT call
 * mag_release on img afterwards.  Evicts the least-recently-used slot when
 * the cache is full.  @param id  Asset identifier  @param img  Decoded
 * MagImage whose ownership transfers to the cache */
void image_cache_insert(int id, MagImage *img)
{
    int i, evict;
    if (!img) return;
    /* Check if already in cache (shouldn't happen if lookup was called
     * first, but safe) */
    for (i = 0; i < IMAGE_CACHE_SLOTS; i++) {
        if (g_image_cache[i].id == id) {
            mag_release(g_image_cache[i].img);
            g_image_cache[i].img = img;
            g_image_cache[i].hits = 0;
            g_image_cache[i].ready = 1;
            return;
        }
    }
    /* Find empty slot or evict LRU */
    evict = 0;
    for (i = 0; i < IMAGE_CACHE_SLOTS; i++) {
        if (g_image_cache[i].id < 0) {
            evict = i;
            break;
        }
        if (g_image_cache[i].hits < g_image_cache[evict].hits)
            evict = i;
    }
    /* Evict old entry */
    if (g_image_cache[evict].img) {
        mag_release(g_image_cache[evict].img);
    }
    g_image_cache[evict].id = id;
    g_image_cache[evict].img = img;
    g_image_cache[evict].hits = 0;
    g_image_cache[evict].ready = 1;
}

/* devdoc 177: flip a resident slot to ready.  image_cache_insert() already
 * sets it (the cache only ever receives whole decoded images); this entry
 * point exists so a producer that stages a slot in two steps can publish it
 * explicitly, and it is a no-op for a missing id. */
void image_cache_mark_ready(int id)
{
    int i;
    if (id < 0) return;
    for (i = 0; i < IMAGE_CACHE_SLOTS; i++) {
        if (g_image_cache[i].id == id &&
            g_image_cache[i].img != NULL) {
            g_image_cache[i].ready = 1;
            return;
        }
    }
}

/* Non-zero when id is cached and complete (devdoc 177). */
int image_cache_is_ready(int id)
{
    int i;
    if (id < 0) return 0;
    for (i = 0; i < IMAGE_CACHE_SLOTS; i++) {
        if (g_image_cache[i].id == id)
            return g_image_cache[i].ready;
    }
    return 0;
}

/* Lift a slot's hit floor so a prefetched image survives until it is used.
 * See image_internal.h; no-op when the id is not cached. */
void image_cache_pin(int id)
{
    int i;
    if (id < 0) return;
    for (i = 0; i < IMAGE_CACHE_SLOTS; i++) {
        if (g_image_cache[i].id == id) {
            if (g_image_cache[i].hits < IMAGE_CACHE_PREFETCH_HITS)
                g_image_cache[i].hits = IMAGE_CACHE_PREFETCH_HITS;
            return;
        }
    }
}
