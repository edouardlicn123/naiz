/*
 * serial.c — uPD8251 串口驱动（COM1, 9600 8N1）
 *
 * Delay loop counts (busy-read SERIAL_STATUS to pace emulator/hardware).
 */
#define SERIAL_DELAY_INTER_BYTE 200
#define SERIAL_DELAY_RX_POLL    100

/*
 * PC-98 第一个串口（COM1）使用 uPD8251 USART 芯片，
 * 端口映射：
 *   0x30 = 数据寄存器（SERIAL_DATA）
 *   0x32 = 命令/状态/模式寄存器（SERIAL_STATUS/CMD/MODE，同一端口不同上下文）
 *
 * 本模块仅供调试日志输出使用，采用 fire-and-forget 方式（不检查 TX 就绪）
 * 并在字节间插入短延迟以保证模拟器不会因输出过快而丢数据。
 */
#include "pc98.h"

static int serial_ready;  /* 0=not ready, 1=initialized */

/*
 * Serial single-byte output.
 *
 * Writes a byte directly to the data port. Silently drops if uninitialized.
 * Does not check TXRDY — fire-and-forget is reliable enough under emulation.
 *
 * @param c  Character to send
 */
static void serial_outb(unsigned char c)
{
    if (!serial_ready) return;
    outb(SERIAL_DATA, c);
}

/*
 * Initialize the uPD8251 serial port.
 *
 * Reset sequence (per uPD8251 datasheet):
 *   1. Write 3x 0x00 to enter ready state
 *   2. Write reset command (SERIAL_CMD_RESET = 0x40)
 *   3. Write mode register (9600 8N1)
 *   4. Write command register (enable TX/RX, set RTS/DTR)
 *
 * After setup: 9600 baud, 8 data bits, no parity, 1 stop bit.
 */
void serial_init(void)
{
    serial_ready = 0;

    /* uPD8251 reset sequence: 3x dummy writes + software reset. */
    outb(SERIAL_CMD, 0x00);
    outb(SERIAL_CMD, 0x00);
    outb(SERIAL_CMD, 0x00);
    outb(SERIAL_CMD, SERIAL_CMD_RESET);
    /* Set mode: 9600 8N1. */
    outb(SERIAL_CMD, SERIAL_MODE_8N1);
    /* Enable TX, RX, RTS, DTR. */
    outb(SERIAL_CMD, SERIAL_CMD_TXEN | SERIAL_CMD_RXEN | SERIAL_CMD_RTS | SERIAL_CMD_DTR);

    serial_ready = 1;
}

/*
 * Serial string output (auto \r\n pairing with inter-byte delay).
 *
 * Auto-prepends '\r' before '\n'; preserves existing "\r\n" sequences.
 * Inserts a short delay after each byte by reading SERIAL_STATUS
 * to prevent TX FIFO overflow on emulator/hardware.
 *
 * @param s  NUL-terminated string
 */
void serial_puts(const char *s)
{
    int i;
    if (!serial_ready) return;
    while (*s) {
        if (*s == '\r' && *(s + 1) == '\n') {
            /* Send CR-LF sequence as-is. */
            serial_outb('\r');
            serial_outb('\n');
            s += 2;
            for (i = 0; i < SERIAL_DELAY_INTER_BYTE; i++) inb(SERIAL_STATUS);
            continue;
        }
        if (*s == '\n') {
            serial_outb('\r');
            for (i = 0; i < SERIAL_DELAY_INTER_BYTE; i++) inb(SERIAL_STATUS);
        }
        serial_outb(*s);
        s++;
        /* Inter-byte delay: read status port N times. */
        for (i = 0; i < SERIAL_DELAY_INTER_BYTE; i++) inb(SERIAL_STATUS);
    }
}


