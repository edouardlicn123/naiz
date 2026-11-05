/*
 * frame.h — Unified per-frame heartbeat (devdoc 129)
 *
 * The engine frame model: exactly one tick per displayed frame.  The main
 * loop always ran this heartbeat, but every self-contained input loop
 * (question prompts, in-game menus, save/load, CG gallery) ran its own spin
 * loop and never pumped it — so BGM/PCM froze and the virtual clock stalled
 * for the whole time the player sat in a menu.
 *
 * engine_frame_pump() is that single heartbeat: wait for vblank, advance the
 * virtual clock exactly once, then tick animation / audio / typewriter.
 * Call it once at the top of EVERY interactive loop, then do that loop's own
 * keyboard/mouse handling.  It deliberately does not touch the keyboard or
 * mouse so each loop keeps its existing input semantics.
 *
 * The clock-advance ownership (devdoc 129) lives here: consumers such as
 * audio_tick() read the clock but never advance it, so pumping audio more
 * than once per frame (e.g. from inside a long decode) is idempotent.
 */
#ifndef FRAME_H
#define FRAME_H

void engine_frame_pump(void);

/*
 * Decode-time frame step (devdoc 131 方案 B).
 *
 * Same job as engine_frame_pump() but safe to call from inside a long
 * CPU-bound path (the MAG decode progress hook): it advances the virtual
 * clock and pumps audio only when the display has actually reached a new
 * VBLANK, so the BGM keeps flowing during a decode without the clock racing,
 * and it never blocks a full frame per decode stride.  (devdoc 131 方案 A's
 * periodic vblank yield in audio_tick was removed in devdoc 133.)
 */
void frame_decode_pump(void);

#endif
