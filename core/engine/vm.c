/*
 * vm.c — VM runtime state ownership for the NB script engine.
 * Owns vm_flags (VM state bits) and delay_frames (frame delay counter).
 * All external reads/writes go through the accessors declared in vm.h.
 */
#include "vm.h"
#include "hal.h"

/* Maximum delay clamp: 1 hour.  Guards against a stray huge argument. */
#define DELAY_MS_MAX  3600000UL

/* VM state flags — read/written only through the vm_* accessors. */
static volatile unsigned char vm_flags = VMFLAG_PROCESS;

/* Delay deadline (wall-clock ms).  delay_active=0 means no delay pending. */
static unsigned long delay_deadline_ms = 0;
static int           delay_active_flag = 0;

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

/* Reset the pending delay (called by nb_init). */
void vm_delay_reset(void)
{
    delay_active_flag = 0;
}

/* Arm a delay of the given duration in milliseconds (used by cmd_delay). */
void vm_set_delay(unsigned long ms)
{
    unsigned long now;
    if (ms > DELAY_MS_MAX)
        ms = DELAY_MS_MAX;
    now = hal_wallclock_smooth_ms();
    delay_deadline_ms = now + ms;
    delay_active_flag = 1;
}

/* Check the delay deadline once per main-loop frame.
 * Returns 1 on the frame the deadline passes (the caller should re-request
 * VM processing).  Time-based rather than frame-based: the pump can run
 * far above the display rate when VSYNC is not emulated, which made
 * frame-counted delays expire almost instantly. */
int vm_delay_tick(void)
{
    if (!delay_active_flag)
        return 0;
    if (hal_wallclock_smooth_ms() < delay_deadline_ms)
        return 0;
    delay_active_flag = 0;
    return 1;
}

/* Non-zero while a delay is still pending. */
int vm_delay_active(void)
{
    return delay_active_flag;
}
