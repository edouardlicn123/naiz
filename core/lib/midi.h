/*
 * midi.h — Minimal SMF (Standard MIDI File) parser.
 *
 * Pure library (core/lib): no platform headers, no logging.  Failures are
 * signalled via return codes and reported by engine callers.  This mirrors
 * the existing silent lib/ convention (farchive.c, tr.c, font.c).
 *
 * Scope (devdoc 101):
 *   - Reads MThd + MTrk chunks; event timing is normalized to wall-clock
 *     milliseconds using the tempo map and PPQN.
 *   - Only channel voice messages (0x80-0xEF) are kept, expanded to a
 *     uniform 3-byte form (running status applied).  Meta events are
 *     consumed (tempo / end-of-track are processed, the rest skipped);
 *     sysex blocks are skipped.
 *   - SMPTE division and format > 1 are rejected.
 *   - every read is bounded by the stream length (C6/C9).
 *
 * The returned event array is owned by the caller and released with
 * midi_free().
 */
#ifndef MIDI_H
#define MIDI_H

#include <stdint.h>

/* One replayable MIDI event, time-ordered by tick_ms.  b2 is 0 for the
 * two-data-byte voice statuses (0xCx program change / 0xDx channel
 * pressure); the driver derives the wire length from b0. */
typedef struct {
    uint32_t tick_ms;  /* absolute time in ms from track start */
    uint8_t  b0;       /* channel voice status byte */
    uint8_t  b1;       /* data byte 1 */
    uint8_t  b2;       /* data byte 2 (0 when the message is 2 bytes) */
} MidEvent;

/* Parse an SMF byte stream.
 *
 *   data / len   raw SMF bytes
 *   out_events   receives a malloc'd MidEvent array sorted by tick_ms
 *                (NULL when out_count is 0); caller releases with midi_free()
 *   out_count    receives the number of events
 *
 * Returns 0 on success, negative on error:
 *   -1  bad MThd header / truncated stream / chunk length exceeds bounds
 *   -2  unsupported: SMPTE division or format > 1
 *   -3  malformed track (bad VLV, unknown status with no running status,
 *       missing data bytes, chunk overrun, PPQN == 0)
 *   -4  out of memory or event budget exceeded
 */
int  midi_parse(const uint8_t *data, uint32_t len,
                MidEvent **out_events, int *out_count);

/* Free an event array returned by midi_parse.  NULL is safe. */
void midi_free(MidEvent *events);

#endif
