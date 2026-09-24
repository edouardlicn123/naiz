/*
 * keyboard.c — PC-98 键盘输入驱动
 *
 * 直接从 BIOS 键盘缓冲区读取扫描码，而非通过 INT 18h 或 USART I/O。
 *
 * 原理：
 *   PC-98 上 INT 09h（键盘 IRQ 处理）将 MAKE 码存入 BIOS 键盘缓冲区
 *   （物理内存 0x0502-0x0521）。DOS/4GW DPMI 保护模式下物理地址 0x0000
 *   被映射到线性地址 0x0000（平坦数据段），因此可直接解引用指针读取。
 *
 * 为何不用 INT 18h 调用 int386()？
 *   DPMI 不能可靠地将 INT 18h CRT BIOS 键盘调用转发到实模式处理函数。
 *
 * 为何不用 USART 端口直接轮询（0x41/0x43）？
 *   IRQ1 中断应答周期会在轮询代码读取之前消耗 USART 的字节，
 *   此时 RxRDY 已被清除，因而无法读到。
 *
 * 参考：docs/refdocs/ — PC-98 键盘控制器规范
 */
#include "keyboard.h"
#include <string.h>
#include "hal.h"

#ifdef KBD_DEBUG
#define KBD_LOG(...) do { \
    char _buf[128]; \
    int _n = snprintf(_buf, sizeof(_buf), "[KBD] "); \
    snprintf(_buf + _n, sizeof(_buf) - _n, __VA_ARGS__); \
    hal_log(_buf); \
} while (0)
#else
#define KBD_LOG(...) ((void)0)
#endif

#define KBD_BUF_SIZE     64
#define KBD_DELAY_ITER   50000  /* ~50ms busy-wait delay in wait_release */

/*
 * BIOS 键盘缓冲区内存布局
 * 地址基于段 0（线性地址），由 PC-98 的 INT 09h 处理函数维护：
 *   - 每个按键占 2 字节（低字节 = 字符码，高字节 = 扫描码）
 *   - HEAD/TAIL 为环形缓冲区的读写指针
 *   - COUNT 记录当前缓冲按键数
 */
#define BIOS_BUF_START   0x0502UL   /* 缓冲区起始，16 项 × 2 字节 = 32 字节 */
#define BIOS_BUF_END     0x0522UL   /* 缓冲区结束（末尾之后） */
#define BIOS_HEAD        0x0524UL   /* word: 下一个读取偏移 */
#define BIOS_TAIL        0x0526UL   /* word: 下一个写入偏移 */
#define BIOS_COUNT       0x0528UL   /* byte: 缓冲区内按键数量 */

static unsigned char kbd_buf[KBD_BUF_SIZE];
static int          kbd_buf_len;

/* Frame-drop counter: when >0, kbd_update() drains BIOS events without
 * adding them to the local buffer. Used after scene transitions to
 * suppress auto-repeat codes that arrive immediately after kbd_flush. */
static int kbd_ignore_frames;

void kbd_set_ignore_frames(int frames) { kbd_ignore_frames = frames; }

/*
 * Reset BIOS keyboard buffer pointers and counters, clearing the BIOS queue.
 *
 * Resets HEAD/TAIL to BIOS_BUF_START and COUNT to zero,
 * discarding all accumulated key events. Used after scene transitions
 * or when waiting for key release to clear auto-repeat codes.
 */
static void kbd_bios_reset(void)
{
    volatile unsigned char *mem = (unsigned char *)0UL;
    mem[BIOS_COUNT]    = 0;
    /* HEAD = BIOS_BUF_START（小端写入） */
    mem[BIOS_HEAD]     = (unsigned char)(BIOS_BUF_START & 0xFF);
    mem[BIOS_HEAD + 1] = (unsigned char)((BIOS_BUF_START >> 8) & 0xFF);
    /* TAIL = BIOS_BUF_START */
    mem[BIOS_TAIL]     = (unsigned char)(BIOS_BUF_START & 0xFF);
    mem[BIOS_TAIL + 1] = (unsigned char)((BIOS_BUF_START >> 8) & 0xFF);
}

/*
 * Initialize the keyboard subsystem.
 *
 * Only clears the local key buffer. The BIOS-side buffer is maintained
 * automatically by the PC-98 firmware INT 09h handler.
 *
 * Should be called once early in engine startup.
 */
void kbd_init(void)
{
    kbd_buf_len = 0;
}

/*
 * Drain BIOS keyboard events into the local FIFO.
 *
 * Reads scan codes from the BIOS keyboard buffer into the local kbd_buf
 * for querying via kbd_is_down. Call once per frame
 * before processing input.
 *
 * Separates MAKE (bit 7=0) from BREAK (bit 7=1):
 *   - MAKE:  append to kbd_buf
 *   - BREAK: do NOT append to kbd_buf
 *
 * The local buffer holds 16 entries. If too many keys arrive in one frame
 * (fast typing / auto-repeat), both local and BIOS buffers are forcibly
 * cleared to prevent ring-buffer wraparound.
 */
void kbd_update(void)
{
    volatile unsigned char *mem = (unsigned char *)0UL;
    unsigned char count;
    unsigned int head;
    unsigned char sc;

    /* Frame-drop: drain BIOS events but discard them. */
    if (kbd_ignore_frames > 0) {
        kbd_ignore_frames--;
        count = mem[BIOS_COUNT];
        if (count > 0) {
            KBD_LOG("ignore: draining %d BIOS events\r\n", count);
            while (count--) {
                head = (unsigned int)mem[BIOS_HEAD]
                     | ((unsigned int)mem[BIOS_HEAD + 1] << 8);
                sc = mem[head + 1];
                head += 2;
                if (head >= BIOS_BUF_END)
                    head = BIOS_BUF_START;
                mem[BIOS_HEAD] = (unsigned char)(head & 0xFF);
                mem[BIOS_HEAD + 1] = (unsigned char)((head >> 8) & 0xFF);
            }
            mem[BIOS_COUNT] = 0;
        }
        return;
    }

    /* Process all available BIOS events until queue is empty.
     * When local buffer is full, drop oldest event to make room
     * (memmove by one slot). */
    {
        int overflow = 0;
        while (1) {
            count = mem[BIOS_COUNT];
            if (count == 0)
                break;

            head = (unsigned int)mem[BIOS_HEAD]
                 | ((unsigned int)mem[BIOS_HEAD + 1] << 8);

            sc = mem[head + 1];

            if (sc & 0x80) {
                KBD_LOG("BREAK sc=0x%02X\r\n", sc & 0x7F);
            } else {
                KBD_LOG("MAKE  sc=0x%02X\r\n", sc);
                if (kbd_buf_len < KBD_BUF_SIZE) {
                    kbd_buf[kbd_buf_len++] = sc;
                } else {
                    if (!overflow) {
                        hal_log("WARN: kbd_buf overflow\r\n");
                        overflow = 1;
                    }
                    memmove(kbd_buf, kbd_buf + 1, KBD_BUF_SIZE - 1);
                    kbd_buf[KBD_BUF_SIZE - 1] = sc;
                }
            }

            head += 2;
            if (head >= BIOS_BUF_END)
                head = BIOS_BUF_START;
            mem[BIOS_HEAD]     = (unsigned char)(head & 0xFF);
            mem[BIOS_HEAD + 1] = (unsigned char)((head >> 8) & 0xFF);
            mem[BIOS_COUNT]    = count - 1;
        }
    }
}

/*
 * Check if a scan code was just pressed (consuming query).
 *
 * Searches the local buffer for the target scan code, removes it
 * (via array compaction), and returns 1. Returns 0 if not found.
 * Implements edge-triggered key detection.
 *
 * This is the VN engine's primary input function — each key press
 * triggers exactly once.
 *
 * @param sc  Target scan code
 * @return    1 if the key was just pressed (event consumed), 0 otherwise
 */
int kbd_is_down(unsigned char sc)
{
    int i;
    for (i = 0; i < kbd_buf_len; i++) {
        if (kbd_buf[i] == sc) {
            memmove(kbd_buf + i, kbd_buf + i + 1, kbd_buf_len - i - 1);
            kbd_buf_len--;
            KBD_LOG("consume sc=0x%02X (remaining=%d)\r\n", sc, kbd_buf_len);
            return 1;
        }
    }
    return 0;
}

/*
 * Flush all key buffers, discarding accumulated events before scene transitions.
 *
 * Clears both local kbd_buf, BIOS keyboard buffer, and the kbd_held[] state.
 * Also resets kbd_ignore_frames (flush means "ready now", no frame-drop needed).
 */
void kbd_flush(void)
{
    kbd_buf_len = 0;
    kbd_ignore_frames = 0;
    kbd_bios_reset();
    KBD_LOG("flush\r\n");
}

/*
 * Read-only check if a MAKE entry for the given scan code exists in the BIOS buffer.
 *
 * Does not consume events; only scans the ring buffer.
 * Used by kbd_wait_release to check if a key is still held.
 *
 * @param sc  Target scan code
 * @return    1 if matching entry found, 0 otherwise
 */
static int kbd_bios_has_make(unsigned char sc)
{
    volatile unsigned char *mem = (unsigned char *)0UL;
    unsigned int head;
    unsigned char count = mem[BIOS_COUNT];
    if (count == 0)
        return 0;
    head = (unsigned int)mem[BIOS_HEAD]
         | ((unsigned int)mem[BIOS_HEAD + 1] << 8);
    while (count--) {
        if (mem[head + 1] == sc)
            return 1;
        head += 2;
        if (head >= BIOS_BUF_END)
            head = BIOS_BUF_START;
    }
    return 0;
}

/*
 * Busy-wait until a key is physically released, clearing auto-repeat codes.
 *
 * Under auto-repeat, the BIOS buffer is continuously filled with MAKE codes.
 * This function repeatedly resets the BIOS buffer with ~50ms delays
 * until the key is physically released, preventing stale MAKE codes
 * from leaking into subsequent key-wait loops.
 *
 * Protected by KBD_WAIT_MAX_ITER timeout (~2.5 seconds).
 *
 * Special case: when waiting for non-Enter keys, if Enter is detected as
 * pressed, it also satisfies the release condition (escape hatch to prevent
 * Space auto-repeat from hanging the caller).
 *
 * @param sc  Target scan code to wait for release
 */
static void kbd_wait_release(unsigned char sc)
{
    volatile unsigned char *mem = (unsigned char *)0UL;
    int timeout = KBD_WAIT_MAX_ITER / 1000;
    if (timeout < 1) timeout = 1;
    KBD_LOG("wait_release(sc=0x%02X) begin\r\n", sc);
    do {
        if (--timeout <= 0) {
            KBD_LOG("wait_release(sc=0x%02X) timeout\r\n", sc);
            break;
        }
        kbd_bios_reset();
        {
            volatile int d;
            for (d = 0; d < KBD_DELAY_ITER; d++) {
                (void)mem[BIOS_COUNT];
            }
        }
        kbd_bios_reset();
        if (sc == KC_ENTER) {
            if (!kbd_bios_has_make(KC_ENTER)) break;
        } else {
            int has_sc  = kbd_bios_has_make(sc);
            int has_ent = kbd_bios_has_make(KC_ENTER);
            if (!has_sc || has_ent) break;
        }
    } while (1);
    KBD_LOG("wait_release(sc=0x%02X) done\r\n", sc);
}

/*
 * Busy-wait until any key is pressed (5M loop timeout).
 *
 * Polls the BIOS keyboard buffer COUNT until non-zero or timeout.
 * Consumes one key event before returning. Used for "press any key"
 * prompts.
 *
 * Timeout protection: returns automatically after 5M iterations to
 * prevent deadlock if the emulator freezes.
 */
void kbd_wait_any(void)
{
    volatile unsigned char *mem = (unsigned char *)0UL;
    unsigned int head;
    volatile int timeout = KBD_WAIT_MAX_ITER * 100;

    while (mem[BIOS_COUNT] == 0 && --timeout > 0) {}
    if (timeout == 0) return;

    head = (unsigned int)mem[BIOS_HEAD]
         | ((unsigned int)mem[BIOS_HEAD + 1] << 8);
    head += 2;
    if (head >= BIOS_BUF_END)
        head = BIOS_BUF_START;
    mem[BIOS_HEAD]     = (unsigned char)(head & 0xFF);
    mem[BIOS_HEAD + 1] = (unsigned char)((head >> 8) & 0xFF);
    mem[BIOS_COUNT]    = mem[BIOS_COUNT] - 1;
}

/*
 * Wait until all confirm keys (Space/Enter/XFER) are physically released.
 * Calls kbd_wait_release for each with built-in timeout protection.
 * Should be called at the entrance of blocking input loops to prevent
 * stale auto-repeat codes from leaking across scene transitions.
 */
void kbd_drain_advance(void)
{
    kbd_wait_release(KC_SPACE);
    kbd_wait_release(KC_ENTER);
    kbd_wait_release(KC_XFER);
}
