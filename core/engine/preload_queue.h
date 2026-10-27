/*
 * preload_queue.h — Scene-asset preload queue (devdoc 177 Phase 3).
 *
 * nb_load() queues the display assets the incoming script will need
 * (bg / cg / char); engine_frame_pump() pops at most one per frame and decodes
 * it into the image cache while the screen is still covered by the transition.
 *
 * The queue is a fixed array of ids + priorities (no buffers, no allocation):
 * devdoc 177 §C measured that reserving a decode buffer per slot would cost
 * ~16 MB of heap, so preload only warms the existing LRU cache through
 * image_prefetch().  Memory stays bounded by the cache itself.
 */
#ifndef PRELOAD_QUEUE_H
#define PRELOAD_QUEUE_H

/* Capacity for one scene's deduplicated display assets.  Overflow drops the
 * lowest-priority job (the highest prio number) rather than failing. */
#define PRELOAD_QUEUE_CAP 64

/* Priority bands (lower = decoded first). */
#define PRELOAD_PRIO_BG   0   /* backgrounds and CGs: the next screen */
#define PRELOAD_PRIO_CHAR 1   /* standing portraits */

/* Drop every queued job.  Called when a new scene preload starts. */
void preload_queue_init(void);

/* Queue one asset id.  Duplicate ids coalesce (the better priority wins);
 * when the queue is full this job replaces the worst one only if it is better.
 * Negative ids are ignored. */
void preload_push(int id, int prio);

/* Remove id from the queue.  image_load() calls this when it decodes the same
 * id synchronously, so the frame pump does not decode it twice. */
void preload_cancel(int id);

/* Number of queued jobs. */
int preload_pending(void);

/* Decode the highest-priority job into the image cache.
 * Returns 1 when a job was consumed and decoded, 0 when the queue is empty or
 * the decode failed.  A failed job is dropped, never retried (devdoc 177
 * Tier 1 heap guard); the caller must not consume a second job that frame. */
int preload_step(void);

#endif
