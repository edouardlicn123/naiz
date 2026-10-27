/*
 * preload_queue.c — see preload_queue.h (devdoc 177 Phase 3).
 *
 * Deliberately allocation-free: a scene preload can queue dozens of ids, and
 * on this target every byte of heap competes with the decoded images
 * themselves.  A 64-entry array of {id, prio} is ~512 B.
 */
#include "preload_queue.h"
#include "image.h"

typedef struct {
    int id;
    int prio;
} PreloadJob;

static PreloadJob g_preload[PRELOAD_QUEUE_CAP];
static int g_preload_count;

void preload_queue_init(void)
{
    g_preload_count = 0;
}

void preload_push(int id, int prio)
{
    int i, worst;

    if (id < 0)
        return;

    for (i = 0; i < g_preload_count; i++) {
        if (g_preload[i].id == id) {
            if (prio < g_preload[i].prio)
                g_preload[i].prio = prio;
            return;
        }
    }

    if (g_preload_count >= PRELOAD_QUEUE_CAP) {
        /* Full: replace the worst-priority job only if this one is better. */
        worst = 0;
        for (i = 1; i < g_preload_count; i++) {
            if (g_preload[i].prio > g_preload[worst].prio)
                worst = i;
        }
        if (prio >= g_preload[worst].prio)
            return;
        g_preload[worst].id = id;
        g_preload[worst].prio = prio;
        return;
    }

    g_preload[g_preload_count].id = id;
    g_preload[g_preload_count].prio = prio;
    g_preload_count++;
}

void preload_cancel(int id)
{
    int i;

    if (id < 0)
        return;
    for (i = 0; i < g_preload_count; i++) {
        if (g_preload[i].id == id) {
            g_preload_count--;
            g_preload[i] = g_preload[g_preload_count];
            return;
        }
    }
}

int preload_pending(void)
{
    return g_preload_count;
}

int preload_step(void)
{
    int i, best, id;

    if (g_preload_count <= 0)
        return 0;

    best = 0;
    for (i = 1; i < g_preload_count; i++) {
        if (g_preload[i].prio < g_preload[best].prio)
            best = i;
    }
    id = g_preload[best].id;

    /* Pop before decoding: a failure must not leave the job to be retried on
     * every frame (Tier 1 heap guard, devdoc 177 §F). */
    g_preload_count--;
    g_preload[best] = g_preload[g_preload_count];

    return image_prefetch((unsigned short)id) == 0;
}
