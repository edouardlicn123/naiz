/*
 * VM runtime shared interface — shared by main.c, nb.c, scene_layers.c.
 * Extracted from the old scene.h after removing the binary opcode VM (scene.c).
 */
#ifndef VM_H
#define VM_H

/* VM state flags — shared by main.c (main loop) and nb.c (NB interpreter).
 * Read externally via vm_get_flags(); write via vm_* setters.  The backing
 * variables are static in vm.c; delay state is queried via vm_delay_active(). */

/* Maximum delay frame clamp (non-AUTOEXIT only). */
#define DELAY_FRAMES_MAX  3600

/* VM flag bits */
#define VMFLAG_Z              0x01
#define VMFLAG_N              0x02
#define VMFLAG_SCENE_CHANGED  0x10
#define VMFLAG_ERROR          0x20
#define VMFLAG_FINALEND       0x40
#define VMFLAG_PROCESS        0x80

/* nb_process() return status bits */
#define SCENE_STATUS_FINALEND  0x4000
#define SCENE_STATUS_ERROR     0x8000

/*=== Accessors ============================================================*/

/* Request VM processing on the next main-loop iteration. */
void vm_request_process(void);
/* Set the VM error flag. */
void vm_set_error(void);
/* Set the final-end (exit engine) flag. */
void vm_set_finalend(void);
/* Request a scene change; also requests processing. */
void vm_request_scene_change(void);
/* Clear the scene-change flag after it is handled. */
void vm_clear_scene_change(void);
/* Pause processing (clear VMFLAG_PROCESS); used by dialog paging. */
void vm_pause_process(void);
/* Clear the error flag after it is handled. */
void vm_clear_error(void);
/* Return the current VM state flags. */
unsigned char vm_get_flags(void);
/* Reset the frame-delay counter (called by nb_init). */
void vm_delay_reset(void);
/* Set the frame-delay counter to the given value (used by cmd_delay). */
void vm_set_delay(int frames);
/* Tick the frame-delay counter once per main-loop frame; returns 1 when it
 * just reached zero (caller re-requests VM processing). */
int  vm_delay_tick(void);
/* Non-zero while a frame delay is still counting down. */
int  vm_delay_active(void);

#endif
