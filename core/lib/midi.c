/*
 * midi.c — Minimal SMF (Standard MIDI File) parser.
 *
 * See midi.h for the contract.  Pure library (core/lib): no platform
 * headers, no logging.  All decoding is bounded by the caller-provided
 * stream length (C6/C9).
 *
 * Algorithm (devdoc 101 §4.1):
 *   - MThd: format / ntrks / division (PPQN = division & 0x7FFF; SMPTE
 *     division rejected).
 *   - MTrk: VLV delta times + events.  Channel voice messages are expanded
 *     to a uniform 3-byte form (running status applied); meta events are
 *     consumed (tempo 51/2F processed, rest skipped); sysex is skipped.
 *     All events from every track are merged and sorted by (tick, seq).
 *   - A second pass converts absolute ticks to wall-clock ms via the tempo
 *     map:  ms += (tick - prev_tick) * us_per_quarter / ppqn / 1000,
 *     switching tempo each time a tempo event is crossed.
 */
#include <stdlib.h>
#include <string.h>
#include "midi.h"
#include "endian.h"

/* VLV ceiling: a 32-bit VLV needs at most 4 bytes (4 x 7 bits). */
#define MIDI_MAX_TICK 0x0FFFFFFFUL
#define MIDI_MAX_VLV_BYTES 4
#define MIDI_DEFAULT_TEMPO_US 500000UL  /* 120 BPM */

/* Budget guards against runaway input and unbounded allocation. */
#define MIDI_MAX_EVENTS 65536
#define MIDI_MAX_TEMPOS 64

/* Read a big-endian variable-length quantity.  Returns 0 on success with
 * *val and *consumed set, -1 on out-of-range or underflow. */
static int midi_read_vlv(const uint8_t *p, uint32_t rem,
                         uint32_t *val, uint32_t *consumed)
{
    uint32_t v = 0;
    uint32_t n = 0;

    for (;;) {
        uint8_t b;
        if (n >= MIDI_MAX_VLV_BYTES || rem < 1)
            return -1;
        b = p[n];
        n++;
        v = (v << 7) | (uint32_t)(b & 0x7F);
        if (v > MIDI_MAX_TICK)
            return -1;
        rem--;
        if (!(b & 0x80))
            break;
    }
    *val = v;
    *consumed = n;
    return 0;
}

/* Raw parsed event before tick->ms conversion. */
typedef struct {
    uint32_t tick;    /* absolute tick */
    uint32_t seq;     /* insertion order, stable tie-break for qsort */
    uint8_t  b0;      /* status byte */
    uint8_t  b1;      /* data 1 */
    uint8_t  b2;      /* data 2 */
} MidiRawEvt;

typedef struct {
    uint32_t tick;    /* absolute tick of a tempo change */
    uint32_t us;      /* microseconds per quarter */
} MidiTempo;

static int cmp_evt(const void *a, const void *b)
{
    const MidiRawEvt *x = (const MidiRawEvt *)a;
    const MidiRawEvt *y = (const MidiRawEvt *)b;
    if (x->tick != y->tick)
        return (x->tick < y->tick) ? -1 : 1;
    if (x->seq != y->seq)
        return (x->seq < y->seq) ? -1 : 1;
    return 0;
}

static int cmp_tempo(const void *a, const void *b)
{
    const MidiTempo *x = (const MidiTempo *)a;
    const MidiTempo *y = (const MidiTempo *)b;
    if (x->tick != y->tick)
        return (x->tick < y->tick) ? -1 : 1;
    return 0;
}

/* Append one raw event, growing the array.  Returns 0 / -1 (OOM). */
static int evt_add(MidiRawEvt **evts, int *n, int *cap, uint32_t seq,
                   uint32_t tick, uint8_t b0, uint8_t b1, uint8_t b2)
{
    MidiRawEvt *p;

    if (*n >= MIDI_MAX_EVENTS)
        return -1;
    if (*n >= *cap) {
        int ncap = (*cap == 0) ? 256 : (*cap * 2);
        p = (MidiRawEvt *)realloc(*evts, (size_t)ncap * sizeof(MidiRawEvt));
        if (!p)
            return -1;
        *evts = p;
        *cap = ncap;
    }
    (*evts)[*n].tick = tick;
    (*evts)[*n].seq = seq;
    (*evts)[*n].b0 = b0;
    (*evts)[*n].b1 = b1;
    (*evts)[*n].b2 = b2;
    (*n)++;
    return 0;
}

/* Append one tempo change, growing the array.  Returns 0 / -1 (OOM). */
static int tempo_add(MidiTempo **tps, int *n, int *cap, uint32_t tick, uint32_t us)
{
    MidiTempo *p;

    if (*n >= MIDI_MAX_TEMPOS)
        return -1;
    if (*n >= *cap) {
        int ncap = (*cap == 0) ? 8 : (*cap * 2);
        p = (MidiTempo *)realloc(*tps, (size_t)ncap * sizeof(MidiTempo));
        if (!p)
            return -1;
        *tps = p;
        *cap = ncap;
    }
    (*tps)[*n].tick = tick;
    (*tps)[*n].us = us;
    (*n)++;
    return 0;
}

/* Parse one MTrk chunk starting at offset *pos (checked to hold the 8-byte
 * chunk header).  Adds events/tempo changes to the shared arrays.  Returns
 * 0, -1 on malformed data, -2 on budget overflow. */
static int midi_parse_track(const uint8_t *d, uint32_t len, uint32_t *pos,
                            MidiRawEvt **evts, int *evt_n, int *evt_cap,
                            MidiTempo **tps, int *tp_n, int *tp_cap,
                            uint32_t *seq)
{
    uint32_t abs_tick = 0;
    uint8_t  running = 0;
    uint32_t chunk_len;
    uint32_t end;

    if (*pos + 8 > len)
        return -1;
    if (memcmp(d + *pos, "MTrk", 4) != 0)
        return -1;
    chunk_len = read32_be(d + *pos + 4);
    *pos += 8;
    if (chunk_len > len - *pos)
        return -1;
    end = *pos + chunk_len;

    while (*pos < end) {
        uint32_t delta;
        uint32_t vb;
        uint8_t b;

        if (midi_read_vlv(d + *pos, end - *pos, &delta, &vb) < 0)
            return -1;
        *pos += vb;
        abs_tick += delta;
        if (abs_tick > MIDI_MAX_TICK)
            return -1;
        if (*pos >= end)
            return -1;

        b = d[*pos];

        if (b == 0xFF) {
            /* meta event: type, VLV length, payload */
            uint32_t mlen, mc;
            uint8_t mtype;
            *pos += 1;
            if (*pos >= end)
                return -1;
            mtype = d[*pos];
            *pos += 1;
            if (midi_read_vlv(d + *pos, end - *pos, &mlen, &mc) < 0)
                return -1;
            *pos += mc;
            if (mlen > end - *pos)
                return -1;
            if (mtype == 0x51 && mlen == 3) {
                uint32_t us = ((uint32_t)d[*pos] << 16) |
                              ((uint32_t)d[*pos + 1] << 8) |
                              (uint32_t)d[*pos + 2];
                if (tempo_add(tps, tp_n, tp_cap, abs_tick, us) < 0)
                    return -2;
            } else if (mtype == 0x2F) {
                /* end of track; skip the (normally zero) payload and bail */
                *pos = end;
                break;
            }
            *pos += mlen;
            continue;
        }

        if (b == 0xF0 || b == 0xF7) {
            /* sysex: VLV length then raw bytes, all skipped */
            uint32_t slen, sc;
            *pos += 1;
            if (midi_read_vlv(d + *pos, end - *pos, &slen, &sc) < 0)
                return -1;
            *pos += sc;
            if (slen > end - *pos)
                return -1;
            *pos += slen;
            continue;
        }

        /* channel voice message (status or running status) */
        {
            uint8_t st = b;
            int ndata;
            uint8_t b1;
            uint8_t b2 = 0;

            if (st & 0x80) {
                running = st;
                *pos += 1;
            } else if (running) {
                st = running;
            } else {
                return -1;
            }

            /* 0xCx program change / 0xDx channel pressure carry 1 byte,
             * every other voice status carries 2. */
            ndata = ((st >> 4) == 0xC || (st >> 4) == 0xD) ? 1 : 2;
            if ((uint32_t)ndata > end - *pos)
                return -1;
            b1 = d[*pos];
            if (ndata == 2)
                b2 = d[*pos + 1];
            *pos += (uint32_t)ndata;

            if (evt_add(evts, evt_n, evt_cap, (*seq)++, abs_tick,
                        st, b1, b2) < 0)
                return -2;
        }
    }
    return 0;
}

int midi_parse(const uint8_t *data, uint32_t len,
               MidEvent **out_events, int *out_count)
{
    MidiRawEvt *evts = NULL;
    MidiTempo *tps = NULL;
    MidEvent *final = NULL;
    int evt_n = 0, evt_cap = 0;
    int tp_n = 0, tp_cap = 0;
    uint32_t pos;
    uint32_t ppqn;
    uint32_t hdr_len;
    uint32_t ntrks;
    uint32_t seq = 0;
    int rc = -1;
    int i;

    if (!data || !out_events || !out_count)
        return -1;
    *out_events = NULL;
    *out_count = 0;

    if (len < 14)
        return -1;
    if (memcmp(data, "MThd", 4) != 0)
        return -1;
    hdr_len = read32_be(data + 4);
    if (hdr_len < 6)
        return -1;
    if (read16_be(data + 8) > 1)
        return -2;  /* format 2 not supported */
    ntrks = read16_be(data + 10);
    ppqn = read16_be(data + 12);
    if (ppqn & 0x8000)
        return -2;  /* SMPTE division not supported */
    ppqn &= 0x7FFF;
    if (ppqn == 0)
        return -3;

    pos = 8 + hdr_len;
    if (pos > len)
        return -1;

    for (i = 0; i < (int)ntrks; i++) {
        int t = midi_parse_track(data, len, &pos, &evts, &evt_n, &evt_cap,
                                 &tps, &tp_n, &tp_cap, &seq);
        if (t < 0) {
            rc = (t == -2) ? -4 : -3;
            goto done;
        }
    }

    if (evt_n == 0) {
        rc = 0;
        goto done;
    }

    /* Time-ordered event stream for the replay driver. */
    qsort(evts, (size_t)evt_n, sizeof(MidiRawEvt), cmp_evt);
    if (tp_n > 1)
        qsort(tps, (size_t)tp_n, sizeof(MidiTempo), cmp_tempo);

    final = (MidEvent *)malloc((size_t)evt_n * sizeof(MidEvent));
    if (!final) {
        rc = -4;
        goto done;
    }

    /* tick -> wall-clock ms via the tempo map. */
    {
        unsigned long long prev_tick = 0;
        unsigned long long ms = 0;
        unsigned int cur_us = MIDI_DEFAULT_TEMPO_US;
        int k;
        int ti = 0;

        for (k = 0; k < evt_n; k++) {
            unsigned long long ems;

            /* Catch up the tempo as long as a change precedes this event. */
            while (ti < tp_n && (unsigned long long)tps[ti].tick <=
                                (unsigned long long)evts[k].tick) {
                ms = ms + (tps[ti].tick - prev_tick) * (unsigned long long)cur_us /
                             ppqn / 1000;
                prev_tick = (unsigned long long)tps[ti].tick;
                cur_us = tps[ti].us;
                ti++;
            }
            ems = ms + (evts[k].tick - prev_tick) * (unsigned long long)cur_us /
                          ppqn / 1000;
            if (ems > 0xFFFFFFFFUL)
                ems = 0xFFFFFFFFUL;  /* clamp driver cursor range */
            final[k].tick_ms = (uint32_t)ems;
            final[k].b0 = evts[k].b0;
            final[k].b1 = evts[k].b1;
            final[k].b2 = evts[k].b2;
        }
    }

    *out_events = final;
    *out_count = evt_n;
    final = NULL;  /* ownership handed to the caller */
    rc = 0;

done:
    free(tps);
    free(evts);
    free(final);  /* no-op unless ownership was not taken */
    return rc;
}

void midi_free(MidEvent *events)
{
    free(events);
}
