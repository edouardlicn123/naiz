/*
 * vm.c — VM runtime state ownership for the NB script engine.
 * Owns vm_flags (VM state bits) and delay_frames (frame delay counter).
 * All external reads/writes go through the accessors declared in vm.h.
 */
#include "vm.h"

/* Maximum delay frame clamp (non-AUTOEXIT only). */
#define DELAY_FRAMES_MAX  3600

/* VM state flags — read/written only through the vm_* accessors. */
static volatile unsigned char vm_flags = VMFLAG_PROCESS;

/* Frame delay counter — decremented via vm_delay_tick() (main loop). */
static int delay_frames = 0;

/* Request VM processing on the next main-loop iteration. */
void vm_request_process(void)
{
    vm_flags |= VMFLAG_PROCESS;
}

/* Set the VM error flag. */
void vm_set_error(void)
{
    vm_flags |= VMFLAG_ERROR;
}

/* Set the final-end (exit engine) flag. */
void vm_set_finalend(void)
{
    vm_flags |= VMFLAG_FINALEND;
}

/* Request a scene change; also requests processing. */
void vm_request_scene_change(void)
{
    vm_flags |= VMFLAG_SCENE_CHANGED | VMFLAG_PROCESS;
}

/* Clear the scene-change flag after it is handled. */
void vm_clear_scene_change(void)
{
    vm_flags &= (unsigned char)~VMFLAG_SCENE_CHANGED;
}

/* Pause processing (clear VMFLAG_PROCESS); used by dialog paging. */
void vm_pause_process(void)
{
    vm_flags &= (unsigned char)~VMFLAG_PROCESS;
}

/* Clear the error flag after it is handled. */
void vm_clear_error(void)
{
    vm_flags &= (unsigned char)~VMFLAG_ERROR;
}

/* Return the current VM state flags. */
unsigned char vm_get_flags(void)
{
    return vm_flags;
}

/* Reset the frame-delay counter (called by nb_init). */
void vm_delay_reset(void)
{
    delay_frames = 0;
}

/* Set the frame-delay counter to the given value (used by cmd_delay). */
void vm_set_delay(int frames)
{
    delay_frames = frames;
}

/* Tick the frame-delay counter once per main-loop frame.
 * Clamps to DELAY_FRAMES_MAX, then decrements.  Returns 1 when the counter
 * just reached zero (the caller should re-request VM processing). */
int vm_delay_tick(void)
{
    if (delay_frames <= 0)
        return 0;
    if (delay_frames > DELAY_FRAMES_MAX)
        delay_frames = DELAY_FRAMES_MAX;
    delay_frames--;
    return delay_frames == 0;
}

/* Non-zero while a frame delay is still counting down. */
int vm_delay_active(void)
{
    return delay_frames > 0;
}
