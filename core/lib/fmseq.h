/*
 * fmseq.h — MIDI -> OPNA voice allocator (devdocs/123 §四 M2).
 *
 * Pure library (core/lib): zero outb(), host-testable.  Consumes the
 * time-ordered MidEvent stream from midi.c and turns it into FM/SSG voice
 * state, emitting register writes through an injectable sink so the engine
 * can point it at hal_fm_* and tests can record the writes.
 *
 * Voice policy (devdocs/123 §8.2, user-decided):
 *   - MIDI channels other than 10 (0-based 9) are melodic -> 6 FM voices.
 *   - GM channel 10 is percussion -> 3 SSG voices: kick/toms -> SSG0
 *     tone; snare/rim/clap -> SSG1 tone+noise; hats/cymbals + everything
 *     else -> SSG2 noise-only.
 *   - Patch family of a MIDI channel comes from the GM program via
 *     gm_map[program]; NULL maps every program to family 0.  Programs out
 *     of [0, patch_count) trigger the unmapped callback and fall back to
 *     family 0 (the callback is the engine's fail-loud log point).
 *   - Note steal: a free voice, then a pedal-pending one, then the oldest
 *     (a forced steal keyoffs first so no stuck key bit survives).
 *   - v1 simplifications (documented in devdocs/123): CC7 ignored; bend is
 *     a linear +-2-semitone approximation; every note-on re-writes the whole
 *     patch; SSG drums get a software volume decay driven here (the SSG has
 *     no 4-operator envelope to do the tail).
 */
#ifndef LIB_FMSEQ_H
#define LIB_FMSEQ_H

#include <stddef.h>
#include <stdint.h>
#include "fmopn.h"
#include "midi.h"

#define FMSEQ_MELODY_FM_CH     6            /* FM voices for melodic notes */
#define FMSEQ_PERCUSSION_SSG_CH 3           /* SSG voices for GM ch 10 */
#define FMSEQ_MIDI_CHANNELS    16
#define FMSEQ_PERCUSSION_MIDI_CH 9          /* 0-based GM channel 10 */

/* SSG voice modes (per voice, mapped onto SSG registers). */
#define FMSEQ_SSG_TONE      0               /* tone output (kick/toms) */
#define FMSEQ_SSG_NOISE     1               /* noise only (hats/cymbals) */
#define FMSEQ_SSG_TONE_NOISE 2              /* tone + noise (snare body) */

/* Standard-velocity note values used to classify GM drum kit keys. */
#define FMSEQ_KICK_LOW      35
#define FMSEQ_KICK_HIGH     36
#define FMSEQ_SNARE_LO      38
#define FMSEQ_SNARE_HI      40
#define FMSEQ_SSG2_FALLBACK 42              /* hats/cymbals + anything else */

typedef struct {
    uint8_t active;         /* has a sounding note (keyon held / decay) */
    uint8_t midi_ch;
    uint8_t midi_note;
    uint8_t vel;
    uint8_t family;         /* patch table index */
    uint8_t sustain_pending;/* note-off absorbed by the pedal */
    int      block, fnum;   /* FM: chip block/fnum; SSG tone voice: period */
    uint8_t  ssg_vol8;      /* 8-bit software amplitude for SSG decay */
    uint32_t age;           /* allocation order for FIFO steal */
} FmseqVoice;

typedef struct Fmseq Fmseq;

/* Register write sink.  bank 0 -> ordinary port (0x188/0x18A), bank 1 ->
 * extended (0x18C/0x18E).  fmseq never touches ports itself. */
typedef struct {
    void *ctx;
    void (*write)(void *ctx, int bank, uint8_t reg, uint8_t val);
} FmseqSink;

/* Called when a GM program change maps to no patch family; ctx is the
 * engine's context, default_family is what fmseq will actually use. */
typedef void (*FmseqUnmapped)(void *ctx, int midi_ch, int program,
                              int default_family);

/* --- lifecycle ------------------------------------------------------------ */

/* Size of the opaque Fmseq struct, so host tests can allocate it exactly. */
size_t fmseq_size(void);

/* Initialise with the patch family table.  patches is not owned; it must
 * outlive the sequence.  gm_map is a 128-entry GM program -> family table
 * (NULL: everything maps to family 0). */
void fmseq_init(Fmseq *seq, const FmopnPatch *patches, int patch_count,
                const uint8_t *gm_map, FmseqUnmapped unmapped, void *ctx);

/* Load the event stream to replay.  count == 0 clears it.  The caller keeps
 * ownership and must keep the array alive while fmseq_pump is fed. */
void fmseq_events(Fmseq *seq, const MidEvent *events, int count);

/* Pump up to wall-clock now_ms: dispatch all events with tick_ms <= now_ms,
 * then decay the SSG percussion voices for the elapsed time.  now_ms must be
 * monotonic across calls (the engine feeds hal_wallclock_smooth_ms,
 * devdocs/107). */
void fmseq_pump(Fmseq *seq, const FmseqSink *sink, uint64_t now_ms);

/* Silence everything: keyoff every voice, clear sustain, rewind the event
 * cursor so a later fmseq_pump replays from the start point of the last
 * seek. */
void fmseq_stop(Fmseq *seq, const FmseqSink *sink);

/* --- introspection (tests + engine diagnostics) -------------------------- */

/* Number of currently sounding FM voices. */
int fmseq_fm_voices(const Fmseq *seq);

/* 1 once the whole loaded event stream has been dispatched.  The engine
 * uses this as its loop point: rewind to the start of the last seek. */
int fmseq_finished(const Fmseq *seq);

#endif /* LIB_FMSEQ_H */
