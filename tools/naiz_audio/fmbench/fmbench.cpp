/*
 * fmbench.cpp — offline YM2608 (OPNA) FM render oracle (devdocs/136 P1a).
 *
 * Host-side developer tool: renders a 32-byte .fmp patch plus a note list to a
 * WAV file using the vendored BSD-licensed ymfm YM2608 core.  It mirrors the
 * Naiz engine's register sequencing exactly (core/lib/fmopn.c + fmseq.c +
 * hal_audio.c hal_fm_init) so its output can be compared apples-to-apples with
 * what the engine produces on the target.
 *
 * This binary is NEVER linked into engine.exe and never runs on the PC-98.
 *
 * Build: make  (see Makefile).  Usage:
 *   fmbench <patch.fmp> <out.wav> [options]
 *     --clock N          master clock in Hz (default 7987200, PC-98 OPNA)
 *     --fidelity min|med|max   ymfm output fidelity (default min)
 *     --note N           single engine-faithful note (MIDI number)
 *     --vel N            note velocity 1..127 (default 96)
 *     --dur MS           note duration (default 1000)
 *     --bend N           pitch bend 0..16383, 8192 centred (default 8192)
 *     --tail MS          silence rendered after the last note-off (default 200)
 *     --events FILE      whitespace-separated events instead of a single note:
 *                          note vel start_ms dur_ms bend   (one per line, # = comment)
 *     --no-lfo           do not prime $22 (LFO disabled)
 *     --raw-note         skip velocity TL attenuation (pure patch tone)
 *     --legato-ms N      tie events whose start is within N ms of the previous
 *                          note-off (skip keyoff+keyon, retune pitch only, so
 *                          the phase is not reset); <0/omitted = disabled
 *
 * Output WAV is 32-bit signed int PCM, stereo (L = ymfm data[0], R = data[1]),
 * at the chip's native sample rate; no normalisation or clipping is applied so
 * relative levels stay meaningful.
 */
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <string>
#include <vector>

#include "ymfm_opn.h"

namespace {

/* ymfm's interface hooks all have standalone-safe defaults; nothing to add. */
struct BenchIntf : public ymfm::ymfm_interface {};

struct Event {
    int  note;
    int  vel;
    long start_ms;
    long dur_ms;
    int  bend;
};

/* --- OPNA register model (mirror of core/lib/fmopn.c + fmseq.c) ---------- */

/* Algorithm-operator index -> chip register slot (mirrors fmopn_op_slot). */
const int OP_SLOT[4] = { 0, 2, 1, 3 };

int file_slot(int regslot)
{
    for (int k = 0; k < 4; k++)
        if (OP_SLOT[k] == regslot)
            return k;
    return 0;
}

uint8_t op_byte(const uint8_t *p, int regslot, int field)
{
    return p[file_slot(regslot) * 6 + field];
}

/* MIDI note -> chip block/fnum (mirror of fmopn_note_ratio). */
void note_ratio(int note, int *block, int *fnum)
{
    if (note < 0) note = 0;
    if (note > 127) note = 127;
    double freq = 440.0 * std::pow(2.0, (note - 69) / 12.0);
    double full = freq * 36864.0 / 975.0;
    int b = 0;
    while (full > 1023.0 && b < 7) { full *= 0.5; b++; }
    int fn = (int)(full + 0.5);
    if (fn > 1023) fn = 1023;
    *block = b;
    *fnum = fn;
}

/* Pitch bend applied to an existing block/fnum (mirror of fmopn_bend_ratio). */
void bend_ratio(int bend, int *block, int *fnum)
{
    if (bend < 0) bend = 0;
    if (bend > 16383) bend = 16383;
    long fh = ((long)(*fnum)) << (*block);
    double freq = (double)fh * 975.0 / 36864.0;
    long factor = 4096L + ((bend - 8192L) * 502L) / 8192L;
    if (factor < 0) factor = 0;
    freq = freq * (double)factor / 4096.0;
    double full = freq * 36864.0 / 975.0;
    int b = 0;
    while (full > 1023.0 && b < 7) { full *= 0.5; b++; }
    int fn = (int)(full + 0.5);
    if (fn > 1023) fn = 1023;
    *block = b;
    *fnum = fn;
}

/* bank 0 -> address/data ports 0/1; bank 1 -> ports 2/3 (hal_fm_write_reg). */
void w(ymfm::ym2608 &chip, int bank, uint8_t reg, uint8_t val)
{
    if (bank == 0) {
        chip.write(0, reg);
        chip.write(1, val);
    } else {
        chip.write(2, reg);
        chip.write(3, val);
    }
}

/* Write every patch register (mirror of fm_write_patch).  vel_atten=0 gives
 * the raw patch tone.  Does NOT touch $28, so the EG/phase are left alone. */
void write_patch_regs(ymfm::ym2608 &chip, const uint8_t *p, int vel,
                      int block, int fnum, int vel_atten)
{
    uint8_t att = vel_atten ? (uint8_t)(((127 - vel) >> 3) & 0x0F) : 0;

    for (int r = 0; r < 4; r++) {
        uint8_t tl = (uint8_t)(op_byte(p, r, 1) + att);
        if (tl > 127) tl = 127;
        w(chip, 0, (uint8_t)(0x30 + 4 * r), op_byte(p, r, 0));  /* DT/MUL */
        w(chip, 0, (uint8_t)(0x40 + 4 * r), tl);                /* TL      */
        w(chip, 0, (uint8_t)(0x50 + 4 * r), op_byte(p, r, 2));  /* KS/AR   */
        w(chip, 0, (uint8_t)(0x60 + 4 * r), op_byte(p, r, 3));  /* AM/D1R  */
        w(chip, 0, (uint8_t)(0x70 + 4 * r), op_byte(p, r, 4));  /* D2R     */
        w(chip, 0, (uint8_t)(0x80 + 4 * r), op_byte(p, r, 5));  /* SL/RR   */
    }
    w(chip, 0, 0xB0, p[24]);                                    /* FB/ALG  */
    /* $B4 = pan(bits7-6) | AMS(bits5-4) | PMS(bits2-0); byte25 already is. */
    w(chip, 0, 0xB4, (uint8_t)(p[25]));
    /* ymfm's OPN phase step is (fnum<<1<<block)>>2 == fnum<<(block-1), which
     * is exactly the Yamaha OPNA formula f=(fnum<<(block-1))*clock/(144*2^20)
     * (devdocs/138).  The engine now emits the same encoding (A4 = block5/
     * fnum520), so no pitch compensation is needed. */
    w(chip, 0, 0xA4, (uint8_t)((block << 3) | (fnum >> 8)));
    w(chip, 0, 0xA0, (uint8_t)(fnum & 0xFF));
}

/* Write every patch register then key on voice 0 (mirror of fm_write_patch +
 * the $28 keyon in fm_note_on).  vel_atten=0 gives the raw patch tone. */
void write_patch_and_keyon(ymfm::ym2608 &chip, const uint8_t *p, int vel,
                           int block, int fnum, int vel_atten)
{
    write_patch_regs(chip, p, vel, block, fnum, vel_atten);
    w(chip, 0, 0x28, 0xF0);                                     /* keyon ch0 */
}

void keyoff(ymfm::ym2608 &chip)
{
    w(chip, 0, 0x28, 0x00);
}

/* --- WAV writer: 32-bit signed PCM, stereo -------------------------------- */

void put32(FILE *f, uint32_t v)
{
    uint8_t b[4] = { (uint8_t)v, (uint8_t)(v >> 8), (uint8_t)(v >> 16),
                     (uint8_t)(v >> 24) };
    fwrite(b, 1, 4, f);
}

void put16(FILE *f, uint16_t v)
{
    uint8_t b[2] = { (uint8_t)v, (uint8_t)(v >> 8) };
    fwrite(b, 1, 2, f);
}

bool write_wav32(const char *path, uint32_t rate, const std::vector<int32_t> &s)
{
    FILE *f = fopen(path, "wb");
    if (!f) {
        fprintf(stderr, "fmbench: cannot open %s\n", path);
        return false;
    }
    uint32_t data_bytes = (uint32_t)(s.size() * 4);
    uint32_t byte_rate = rate * 2 * 4;
    fwrite("RIFF", 1, 4, f);
    put32(f, 36 + data_bytes);
    fwrite("WAVE", 1, 4, f);
    fwrite("fmt ", 1, 4, f);
    put32(f, 16);
    put16(f, 1);            /* PCM */
    put16(f, 2);            /* stereo */
    put32(f, rate);
    put32(f, byte_rate);
    put16(f, (uint16_t)(2 * 4));  /* block align */
    put16(f, 32);           /* bits per sample */
    fwrite("data", 1, 4, f);
    put32(f, data_bytes);
    fwrite(s.data(), 4, s.size(), f);
    fclose(f);
    return true;
}

void usage(const char *argv0)
{
    fprintf(stderr,
            "usage: %s <patch.fmp> <out.wav> [--clock N] [--fidelity min|med|max]\n"
            "          [--note N] [--vel N] [--dur MS] [--bend N] [--tail MS]\n"
            "          [--events FILE] [--no-lfo] [--raw-note] [--legato-ms N]\n", argv0);
}

}  // namespace

int main(int argc, char **argv)
{
    if (argc < 3) { usage(argv[0]); return 2; }

    const char *patch_path = argv[1];
    const char *out_path = argv[2];
    uint32_t clock = 7987200;
    ymfm::opn_fidelity fidelity = ymfm::OPN_FIDELITY_MIN;
    long tail_ms = 200;
    bool lfo = true;
    bool vel_atten = true;
    bool have_single = false;
    long legato_ms = -1;   /* <0 = disabled: always keyoff/keyon between events */
    Event single = { 60, 96, 0, 1000, 8192 };
    const char *events_path = nullptr;

    for (int i = 3; i < argc; i++) {
        std::string a = argv[i];
        auto next = [&](const char *what) -> const char * {
            if (i + 1 >= argc) { fprintf(stderr, "fmbench: %s needs a value\n", what); exit(2); }
            return argv[++i];
        };
        if (a == "--clock") clock = (uint32_t)strtoul(next("--clock"), nullptr, 0);
        else if (a == "--fidelity") {
            std::string v = next("--fidelity");
            if (v == "min") fidelity = ymfm::OPN_FIDELITY_MIN;
            else if (v == "med") fidelity = ymfm::OPN_FIDELITY_MED;
            else if (v == "max") fidelity = ymfm::OPN_FIDELITY_MAX;
            else { fprintf(stderr, "fmbench: bad fidelity %s\n", v.c_str()); return 2; }
        }
        else if (a == "--note") { single.note = atoi(next("--note")); have_single = true; }
        else if (a == "--vel") { single.vel = atoi(next("--vel")); have_single = true; }
        else if (a == "--dur") { single.dur_ms = atol(next("--dur")); have_single = true; }
        else if (a == "--bend") { single.bend = atoi(next("--bend")); have_single = true; }
        else if (a == "--tail") tail_ms = atol(next("--tail"));
        else if (a == "--events") events_path = next("--events");
        else if (a == "--no-lfo") lfo = false;
        else if (a == "--raw-note") vel_atten = false;
        else if (a == "--legato-ms") legato_ms = atol(next("--legato-ms"));
        else { fprintf(stderr, "fmbench: unknown option %s\n", a.c_str()); usage(argv[0]); return 2; }
    }

    uint8_t patch[32];
    FILE *pf = fopen(patch_path, "rb");
    if (!pf) { fprintf(stderr, "fmbench: cannot open patch %s\n", patch_path); return 1; }
    size_t got = fread(patch, 1, sizeof(patch), pf);
    fclose(pf);
    if (got != sizeof(patch)) {
        fprintf(stderr, "fmbench: patch %s is %zu bytes, expected 32\n", patch_path, got);
        return 1;
    }

    std::vector<Event> events;
    if (events_path) {
        FILE *ef = fopen(events_path, "r");
        if (!ef) { fprintf(stderr, "fmbench: cannot open events %s\n", events_path); return 1; }
        char line[256];
        while (fgets(line, sizeof(line), ef)) {
            char *c = strchr(line, '#');
            if (c) *c = '\0';
            Event e = { 60, 96, 0, 1000, 8192 };
            int n = sscanf(line, "%d %d %ld %ld %d", &e.note, &e.vel,
                           &e.start_ms, &e.dur_ms, &e.bend);
            if (n >= 4)
                events.push_back(e);
        }
        fclose(ef);
    } else {
        (void)have_single;
        events.push_back(single);
    }
    if (events.empty()) { fprintf(stderr, "fmbench: no events\n"); return 2; }

    BenchIntf intf;
    ymfm::ym2608 chip(intf);
    chip.set_fidelity(fidelity);
    chip.reset();

    uint32_t rate = chip.sample_rate(clock);
    if (rate == 0) { fprintf(stderr, "fmbench: zero sample rate\n"); return 1; }

    /* hal_fm_init: prime the chip-wide LFO ($22 = enable | rate 2). */
    if (lfo)
        w(chip, 0, 0x22, (uint8_t)(0x08 | 2));

    std::vector<int32_t> out;
    ymfm::ym2608::output_data outbuf;
    long pos = 0;   /* samples generated so far */

    auto gen = [&](long n) {
        for (long i = 0; i < n; i++) {
            chip.generate(&outbuf);
            out.push_back(outbuf.data[0]);
            out.push_back(outbuf.data[ymfm::ym2608::OUTPUTS > 1 ? 1 : 0]);
        }
    };
    auto ms_to_samples = [&](long ms) -> long {
        if (ms <= 0) return 0;
        return (long)((double)ms * (double)rate / 1000.0 + 0.5);
    };

    /* A legato tie: event i is joined to i-1 when it starts within legato_ms
     * of i-1's note-off and the voice is still sounding.  Tied events skip
     * both the keyoff and the $28 keyon (retune only), so the OPN phase is
     * not reset -- mirroring a "no re-key" transition in the engine. */
    auto tied = [&](size_t i) -> bool {
        if (legato_ms < 0 || i == 0)
            return false;
        long gap = events[i].start_ms
                 - (events[i - 1].start_ms + events[i - 1].dur_ms);
        return gap <= legato_ms;
    };

    for (size_t i = 0; i < events.size(); i++) {
        const Event &e = events[i];
        long start = ms_to_samples(e.start_ms);
        if (start < pos) start = pos;         /* events must be sequential */
        gen(start - pos);
        pos = start;

        int block, fnum;
        note_ratio(e.note, &block, &fnum);
        if (e.bend != 8192)
            bend_ratio(e.bend, &block, &fnum);
        if (tied(i))
            write_patch_regs(chip, patch, e.vel, block, fnum, vel_atten ? 1 : 0);
        else
            write_patch_and_keyon(chip, patch, e.vel, block, fnum, vel_atten ? 1 : 0);

        long dur = ms_to_samples(e.dur_ms);
        gen(dur);
        pos += dur;

        if (i + 1 >= events.size() || !tied(i + 1))
            keyoff(chip);
    }
    gen(ms_to_samples(tail_ms));

    if (!write_wav32(out_path, rate, out))
        return 1;

    fprintf(stdout, "rate=%u samples=%zu events=%zu\n",
            rate, out.size() / 2, events.size());
    return 0;
}
