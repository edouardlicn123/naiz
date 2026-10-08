/*
 * fmseq.c — MIDI -> OPNA voice allocator (devdocs/123 §四 M2).
 *
 * Pure library: no ports, deterministic, host-testable.  Consumes MidEvent
 * streams (core/lib/midi.h, times in ms) and emits YM2608 register writes
 * through FmseqSink.  The engine wires the sink to hal_fm_* and the tests
 * record the writes.
 *
 * Register layout facts used here (docs/refdocs/F03 §3.2/§3.3/§3.8 + NP2kai
 * sound/opna.c and psggenc.c):
 *   - FM op registers: base 0x30/0x40/0x50/0x60/0x70/0x80 with per-op offset
 *     3*(r&1) + 8*(r>>1) for register slot r; channel striding +ch%3.
 *   - SSG lives at FM addresses 0x00..0x0D in bank 0: 0-5 tone periods,
 *     6 noise period, 7 mixer, 8-10 amplitudes (bit4 = 0 for fixed vol).
 *   - $28 keyon: value = keymask<<4 | chselect, bank 0 (all channels).
 */
#include <stddef.h>

#include "fmseq.h"
#include "midi.h"

#define FMSEQ_SSG_DECAY_PER_SEC  384   /* 8-bit SSG amplitude units/sec */
#define FMSEQ_CLOCK              7987200.0
#define FMSEQ_SSG_DIV            16.0   /* SSG tone = clock/4/16/period */
#define FMSEQ_ATT_MAX            15     /* velocity -> TL attenuation cap */
#define FMSEQ_DRUM_FAMILY_TONE   0      /* kick/toms -> SSG0 */
#define FMSEQ_DRUM_FAMILY_SNARE  1      /* snare/rim/clap -> SSG1 */
#define FMSEQ_DRUM_FAMILY_HAT    2      /* hats/cymbals/other -> SSG2 */

typedef struct SsgVoice {
    FmseqVoice v;
    uint8_t mode;          /* FMSEQ_SSG_* */
    uint8_t noise_period;  /* reg6 value when noise enabled */
} SsgVoice;

struct Fmseq {
    const MidEvent *events;
    int count;
    int cursor;
    const FmopnPatch *patches;
    int patch_count;
    const uint8_t *gm_map;
    FmseqUnmapped unmapped;
    void *ctx;
    FmseqVoice fm[FMSEQ_MELODY_FM_CH];
    SsgVoice  ssg[FMSEQ_PERCUSSION_SSG_CH];
    uint8_t sustain[FMSEQ_MIDI_CHANNELS];
    uint16_t bend[FMSEQ_MIDI_CHANNELS];   /* 0..16383, centre 8192 */
    uint8_t program[FMSEQ_MIDI_CHANNELS]; /* last program per MIDI channel */
    uint32_t last_age;
    uint64_t last_tick;
};

/* --- helpers -------------------------------------------------------------- */

static void w(const FmseqSink *sink, int bank, uint8_t reg, uint8_t val)
{
    sink->write(sink->ctx, bank, reg, val);
}

/* Register address of op slot r (register slot) for class base (0x30..0x80). */
static void fm_op_addr(int ch, int r, uint8_t base, int *bank, uint8_t *addr)
{
    uint8_t reg = (uint8_t)(base + 3 * (r & 1) + 8 * (r >> 1));
    fmopn_op_addr(ch, reg, bank, addr);
}

/* SSG tone period for a frequency (clamped to the 12-bit period range). */
static int period_of_freq(double freq)
{
    double p;

    if (freq <= 0.0)
        freq = 1.0;
    p = (FMSEQ_CLOCK / 4.0) / FMSEQ_SSG_DIV / freq;
    if (p < 1.0)
        return 1;
    if (p > (double)FMOPN_SSG_PERIOD_MAX)
        return FMOPN_SSG_PERIOD_MAX;
    return (int)(p + 0.5);
}

/* GM percussion key -> (ssg channel, mode, noise period). */
static void percussion_class(int note, int *ssg_ch, uint8_t *mode,
                             uint8_t *noise_period)
{
    /* kick (35,36) and toms (41,43,45,47,48,50) -> SSG0 tone only. */
    if (note == FMSEQ_KICK_LOW || note == FMSEQ_KICK_HIGH ||
        (note >= 41 && note <= 50 && note != 42 && note != 44 && note != 46)) {
        *ssg_ch = FMSEQ_DRUM_FAMILY_TONE;
        *mode = FMSEQ_SSG_TONE;
        *noise_period = 0;
        return;
    }
    /* snare (38,40), cowbell (56), rim/clap (76,77) -> SSG1 tone + noise. */
    if (note == FMSEQ_SNARE_LO || note == FMSEQ_SNARE_HI ||
        note == 56 || note == 76 || note == 77) {
        *ssg_ch = FMSEQ_DRUM_FAMILY_SNARE;
        *mode = FMSEQ_SSG_TONE_NOISE;
        *noise_period = 0x09;   /* shared noise clock, muted-period body */
        return;
    }
    /* everything else (42,44,46,49,51,52,55,57,59,...) -> SSG2 noise. */
    *ssg_ch = FMSEQ_DRUM_FAMILY_HAT;
    *mode = FMSEQ_SSG_NOISE;
    *noise_period = 0x02;
}

/* Restore the SSG mixer reg from the current three voice states. */
static void ssg_write_mixer(Fmseq *seq, const FmseqSink *sink)
{
    uint8_t m = 0x3F;   /* every source muted until a voice needs it */
    int i;

    for (i = 0; i < FMSEQ_PERCUSSION_SSG_CH; i++) {
        if (!seq->ssg[i].v.active)
            continue;
        if (seq->ssg[i].mode == FMSEQ_SSG_TONE ||
            seq->ssg[i].mode == FMSEQ_SSG_TONE_NOISE)
            m &= (uint8_t)~(1u << i);
        if (seq->ssg[i].mode == FMSEQ_SSG_NOISE ||
            seq->ssg[i].mode == FMSEQ_SSG_TONE_NOISE)
            m &= (uint8_t)~(1u << (3 + i));
    }
    w(sink, 0, 0x07, m);
}

/* --- FM melodic voices ---------------------------------------------------- */

static void fm_send_keyoff(Fmseq *seq, const FmseqSink *sink, int ch)
{
    (void)seq;
    w(sink, 0, 0x28, fmopn_keyon_value(ch, 0));
}

/* Key the channel off and free the voice (release tail runs on the chip). */
static void fm_release(Fmseq *seq, const FmseqSink *sink, int ch)
{
    fm_send_keyoff(seq, sink, ch);
    seq->fm[ch].active = 0;
    seq->fm[ch].sustain_pending = 0;
}

/* Resolve the patch family for a MIDI channel (gm_map or family 0). */
static int fm_family(Fmseq *seq, int midi_ch)
{
    int fam = 0;
    const uint8_t *gm = seq->gm_map;

    if (gm)
        fam = gm[seq->program[midi_ch] % 128];
    if (fam < 0 || fam >= seq->patch_count) {
        if (seq->unmapped)
            seq->unmapped(seq->ctx, midi_ch, seq->program[midi_ch] % 128, 0);
        fam = 0;
    }
    return fam;
}

static void fm_write_patch(Fmseq *seq, const FmseqSink *sink, int ch,
                           const FmopnPatch *p, int vel, int block, int fnum)
{
    int r, bank;
    uint8_t addr, tl, att;

    att = (uint8_t)(((127 - vel) >> 3) & FMSEQ_ATT_MAX);
    for (r = 0; r < FMOPN_OPS_PER_VOICE; r++) {
        tl = (uint8_t)(fmopn_op_tl(p, r) + att);
        if (tl > 127)
            tl = 127;
        fm_op_addr(ch, r, 0x30, &bank, &addr);
        w(sink, bank, addr, fmopn_op_dt_mul(p, r));
        fm_op_addr(ch, r, 0x40, &bank, &addr);
        w(sink, bank, addr, tl);
        fm_op_addr(ch, r, 0x50, &bank, &addr);
        w(sink, bank, addr, fmopn_op_ks_ar(p, r));
        fm_op_addr(ch, r, 0x60, &bank, &addr);
        w(sink, bank, addr, fmopn_op_am_d1r(p, r));
        fm_op_addr(ch, r, 0x70, &bank, &addr);
        w(sink, bank, addr, fmopn_op_d2r(p, r));
        fm_op_addr(ch, r, 0x80, &bank, &addr);
        w(sink, bank, addr, fmopn_op_sl_rr(p, r));
    }
    fmopn_ch_addr(ch, 0xB0, &bank, &addr);
    w(sink, bank, addr, fmopn_patch_fb_alg(p));
    fmopn_ch_addr(ch, 0xB4, &bank, &addr);
    w(sink, bank, addr, fmopn_patch_pan(p));
    fmopn_ch_addr(ch, 0xA4, &bank, &addr);
    w(sink, bank, addr, (uint8_t)((block << 3) | (fnum >> 8)));
    fmopn_ch_addr(ch, 0xA0, &bank, &addr);
    w(sink, bank, addr, (uint8_t)(fnum & 0xFF));
}

static void fm_note_on(Fmseq *seq, const FmseqSink *sink, int midi_ch,
                       int note, int vel)
{
    int i, best = -1;
    uint32_t oldest_age;
    int block, fnum, family;
    const FmopnPatch *p;

    /* Allocator: a free voice, then a pedal-pending one, then the oldest. */
    for (i = 0; i < FMSEQ_MELODY_FM_CH; i++) {
        if (!seq->fm[i].active) {
            best = i;
            break;
        }
    }
    if (best < 0) {
        for (i = 0; i < FMSEQ_MELODY_FM_CH; i++) {
            if (seq->fm[i].sustain_pending) {
                best = i;
                break;
            }
        }
    }
    if (best < 0) {
        oldest_age = seq->fm[0].age;
        best = 0;
        for (i = 1; i < FMSEQ_MELODY_FM_CH; i++) {
            if (seq->fm[i].age < oldest_age) {
                oldest_age = seq->fm[i].age;
                best = i;
            }
        }
    }

    if (seq->fm[best].active)
        fm_send_keyoff(seq, sink, best);   /* force-steal: cut the old note */

    family = fm_family(seq, midi_ch);
    p = &seq->patches[family];
    fmopn_note_ratio(note, &block, &fnum);
    if (seq->bend[midi_ch] != 8192)
        fmopn_bend_ratio(seq->bend[midi_ch], &block, &fnum);
    fm_write_patch(seq, sink, best, p, vel, block, fnum);
    w(sink, 0, 0x28, fmopn_keyon_value(best, 0x0F));

    seq->fm[best].active = 1;
    seq->fm[best].midi_ch = (uint8_t)midi_ch;
    seq->fm[best].midi_note = (uint8_t)note;
    seq->fm[best].vel = (uint8_t)vel;
    seq->fm[best].family = (uint8_t)family;
    seq->fm[best].block = block;
    seq->fm[best].fnum = fnum;
    seq->fm[best].sustain_pending = 0;
    seq->fm[best].age = ++seq->last_age;
}

static void fm_note_off(Fmseq *seq, const FmseqSink *sink, int midi_ch,
                        int note)
{
    int i;

    for (i = 0; i < FMSEQ_MELODY_FM_CH; i++) {
        if (seq->fm[i].active && seq->fm[i].midi_ch == midi_ch &&
            seq->fm[i].midi_note == note) {
            if (seq->sustain[midi_ch]) {
                seq->fm[i].sustain_pending = 1;   /* hold until pedal up */
            } else {
                fm_release(seq, sink, i);
            }
            return;
        }
    }
}

static void fm_pedal_breathe(Fmseq *seq, const FmseqSink *sink)
{
    int i;

    for (i = 0; i < FMSEQ_MELODY_FM_CH; i++) {
        if (seq->fm[i].sustain_pending)
            fm_release(seq, sink, i);
    }
}

/* --- SSG percussion voices ------------------------------------------------ */

static void ssg_note_on(Fmseq *seq, const FmseqSink *sink, int midi_ch,
                        int note, int vel)
{
    int ssg_ch;
    uint8_t mode, noise_period, amp;
    int period, blk, fn;
    double freq;

    percussion_class(note, &ssg_ch, &mode, &noise_period);
    period = 1;
    if (mode != FMSEQ_SSG_NOISE) {
        fmopn_note_ratio(note, &blk, &fn);
        if (seq->bend[FMSEQ_PERCUSSION_MIDI_CH] != 8192)
            fmopn_bend_ratio(seq->bend[FMSEQ_PERCUSSION_MIDI_CH], &blk, &fn);
        freq = ((double)((long)fn << blk)) * FMSEQ_CLOCK / 150994944.0;
        period = period_of_freq(freq);
        w(sink, 0, (uint8_t)(ssg_ch * 2), fmopn_ssg_period_fine(period));
        w(sink, 0, (uint8_t)(ssg_ch * 2 + 1),
          fmopn_ssg_period_coarse(period));
    }
    if (mode == FMSEQ_SSG_NOISE || mode == FMSEQ_SSG_TONE_NOISE)
        w(sink, 0, 0x06, noise_period);

    seq->ssg[ssg_ch].v.active = 1;
    seq->ssg[ssg_ch].v.midi_ch = (uint8_t)midi_ch;
    seq->ssg[ssg_ch].v.midi_note = (uint8_t)note;
    seq->ssg[ssg_ch].v.vel = (uint8_t)vel;
    seq->ssg[ssg_ch].mode = mode;
    seq->ssg[ssg_ch].v.ssg_vol8 = (uint8_t)(((int)vel * 255) >> 7);
    seq->ssg[ssg_ch].v.sustain_pending = 0;
    seq->ssg[ssg_ch].v.age = ++seq->last_age;

    ssg_write_mixer(seq, sink);
    amp = (uint8_t)(seq->ssg[ssg_ch].v.ssg_vol8 >> 4);
    w(sink, 0, (uint8_t)(8 + ssg_ch), amp);
}

static void ssg_note_off(Fmseq *seq, const FmseqSink *sink, int midi_ch,
                         int note)
{
    int i;

    for (i = 0; i < FMSEQ_PERCUSSION_SSG_CH; i++) {
        if (seq->ssg[i].v.active && seq->ssg[i].v.midi_ch == midi_ch &&
            seq->ssg[i].v.midi_note == note) {
            seq->ssg[i].v.active = 0;
            ssg_write_mixer(seq, sink);
            w(sink, 0, (uint8_t)(8 + i), 0);   /* cut amplitude */
            return;
        }
    }
}

static void ssg_decay(Fmseq *seq, const FmseqSink *sink, uint32_t dt_ms)
{
    int i;
    uint32_t drop;

    if (dt_ms == 0)
        return;
    drop = (FMSEQ_SSG_DECAY_PER_SEC * dt_ms) / 1000;
    for (i = 0; i < FMSEQ_PERCUSSION_SSG_CH; i++) {
        if (!seq->ssg[i].v.active)
            continue;
        if (seq->ssg[i].v.ssg_vol8 > drop) {
            seq->ssg[i].v.ssg_vol8 = (uint8_t)
                ((int)seq->ssg[i].v.ssg_vol8 - (int)drop);
            w(sink, 0, (uint8_t)(8 + i),
              (uint8_t)(seq->ssg[i].v.ssg_vol8 >> 4));
        } else {
            seq->ssg[i].v.active = 0;
            seq->ssg[i].v.ssg_vol8 = 0;
            w(sink, 0, (uint8_t)(8 + i), 0);
            ssg_write_mixer(seq, sink);
        }
    }
}
/* --- event dispatch ------------------------------------------------------ */

/* Pitch bend for one MIDI channel: rewrite every sounding voice's pitch. */
static void fm_apply_bend(Fmseq *seq, const FmseqSink *sink, int midi_ch)
{
    int i, blk, fn;
    int bank;
    uint8_t addr;

    for (i = 0; i < FMSEQ_MELODY_FM_CH; i++) {
        if (seq->fm[i].active && seq->fm[i].midi_ch == midi_ch) {
            fmopn_note_ratio(seq->fm[i].midi_note, &blk, &fn);
            if (seq->bend[midi_ch] != 8192)
                fmopn_bend_ratio(seq->bend[midi_ch], &blk, &fn);
            if (blk != seq->fm[i].block || fn != seq->fm[i].fnum) {
                seq->fm[i].block = blk;
                seq->fm[i].fnum = fn;
                fmopn_ch_addr(i, 0xA4, &bank, &addr);
                w(sink, bank, addr,
                  (uint8_t)((blk << 3) | (fn >> 8)));
                fmopn_ch_addr(i, 0xA0, &bank, &addr);
                w(sink, bank, addr, (uint8_t)(fn & 0xFF));
            }
        }
    }
    if (midi_ch == FMSEQ_PERCUSSION_MIDI_CH) {
        for (i = 0; i < FMSEQ_PERCUSSION_SSG_CH; i++) {
            if (seq->ssg[i].v.active && seq->ssg[i].mode == FMSEQ_SSG_TONE) {
                int period;
                double freq;
                fmopn_note_ratio(seq->ssg[i].v.midi_note, &blk, &fn);
                if (seq->bend[midi_ch] != 8192)
                    fmopn_bend_ratio(seq->bend[midi_ch], &blk, &fn);
                freq = ((double)((long)fn << blk)) * FMSEQ_CLOCK /
                       150994944.0;
                period = period_of_freq(freq);
                w(sink, 0, (uint8_t)(i * 2), fmopn_ssg_period_fine(period));
                w(sink, 0, (uint8_t)(i * 2 + 1),
                  fmopn_ssg_period_coarse(period));
            }
        }
    }
}

static void dispatch(Fmseq *seq, const FmseqSink *sink, const MidEvent *ev)
{
    uint8_t st = (uint8_t)(ev->b0 & 0xF0);
    uint8_t ch = (uint8_t)(ev->b0 & 0x0F);
    int note, vel;

    switch (st) {
    case 0x80:                          /* note off */
        fm_note_off(seq, sink, ch, ev->b1);
        break;
    case 0x90:                          /* note on / note off by velocity */
        note = ev->b1;
        vel = ev->b2;
        if (vel > 0) {
            if (vel > 127)                  /* malformed file: clamp 7-bit */
                vel = 127;
            if (ch == FMSEQ_PERCUSSION_MIDI_CH)
                ssg_note_on(seq, sink, ch, note, vel);
            else
                fm_note_on(seq, sink, ch, note, vel);
        } else {
            if (ch == FMSEQ_PERCUSSION_MIDI_CH)
                ssg_note_off(seq, sink, ch, note);
            else
                fm_note_off(seq, sink, ch, note);
        }
        break;
    case 0xB0:                          /* CC: only sustain is tracked */
        if (ev->b1 == 64) {
            uint8_t was = seq->sustain[ch];
            seq->sustain[ch] = (uint8_t)(ev->b2 >= 64);
            if (was && !seq->sustain[ch])
                fm_pedal_breathe(seq, sink);
        }
        break;
    case 0xC0:                          /* program change */
        seq->program[ch] = ev->b1;
        break;
    case 0xE0:                          /* pitch bend 0..16383 */
        seq->bend[ch] = (uint16_t)((ev->b2 << 7) | ev->b1);
        fm_apply_bend(seq, sink, ch);
        break;
    default:                            /* 0xA0/0xD0 poly/channel pressure */
        break;
    }
}

/* --- public API ---------------------------------------------------------- */

size_t fmseq_size(void)
{
    return sizeof(struct Fmseq);
}

void fmseq_init(Fmseq *seq, const FmopnPatch *patches, int patch_count,
                const uint8_t *gm_map, FmseqUnmapped unmapped, void *ctx)
{
    int i;

    seq->events = NULL;
    seq->count = 0;
    seq->cursor = 0;
    seq->patches = patches;
    seq->patch_count = patch_count;
    seq->gm_map = gm_map;
    seq->unmapped = unmapped;
    seq->ctx = ctx;
    seq->last_age = 0;
    seq->last_tick = 0;
    for (i = 0; i < FMSEQ_MIDI_CHANNELS; i++) {
        seq->sustain[i] = 0;
        seq->bend[i] = 8192;
        seq->program[i] = 0;
    }
    for (i = 0; i < FMSEQ_MELODY_FM_CH; i++)
        seq->fm[i].active = 0;
    for (i = 0; i < FMSEQ_PERCUSSION_SSG_CH; i++) {
        seq->ssg[i].v.active = 0;
        seq->ssg[i].mode = FMSEQ_SSG_TONE;
    }
}

void fmseq_events(Fmseq *seq, const MidEvent *events, int count)
{
    seq->events = events;
    seq->count = count;
    seq->cursor = 0;
    seq->last_tick = 0;   /* next pump starts from a quiet decay baseline */
}

void fmseq_pump(Fmseq *seq, const FmseqSink *sink, uint64_t now_ms)
{
    uint64_t dt;

    if (seq->last_tick == 0 || now_ms < seq->last_tick) {
        seq->last_tick = now_ms;        /* first call / clock wrap: no decay */
        dt = 0;
    } else {
        dt = now_ms - seq->last_tick;
        seq->last_tick = now_ms;
    }

    while (seq->cursor < seq->count &&
           seq->events[seq->cursor].tick_ms <= now_ms) {
        dispatch(seq, sink, &seq->events[seq->cursor]);
        seq->cursor++;
    }

    if (dt > 0)
        ssg_decay(seq, sink, (uint32_t)(dt > 0xFFFFFFFFu ? 0xFFFFFFFFu : dt));
}

void fmseq_stop(Fmseq *seq, const FmseqSink *sink)
{
    int i;

    for (i = 0; i < FMSEQ_MELODY_FM_CH; i++) {
        if (seq->fm[i].active) {
            w(sink, 0, 0x28, fmopn_keyon_value(i, 0));
            seq->fm[i].active = 0;
            seq->fm[i].sustain_pending = 0;
        }
    }
    for (i = 0; i < FMSEQ_PERCUSSION_SSG_CH; i++) {
        w(sink, 0, (uint8_t)(8 + i), 0);
        seq->ssg[i].v.active = 0;
    }
    ssg_write_mixer(seq, sink);
    seq->cursor = 0;
    seq->last_tick = 0;
    seq->last_age = 0;
}

int fmseq_fm_voices(const Fmseq *seq)
{
    int i, n = 0;

    for (i = 0; i < FMSEQ_MELODY_FM_CH; i++)
        if (seq->fm[i].active)
            n++;
    return n;
}

int fmseq_finished(const Fmseq *seq)
{
    return seq->cursor >= seq->count;
}
