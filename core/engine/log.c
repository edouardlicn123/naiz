#include <stdint.h>
#include <stdarg.h>
#include "hal.h"

#define LOG_BUF_SIZE 256

static int log_fd = -1;
static char log_buf[LOG_BUF_SIZE];
static unsigned char log_buf_pos = 0;

static unsigned char screen_row = 0;
static unsigned char screen_col = 0;
static unsigned char screen_inited = 0;
static unsigned char serial_enabled = 0;

#define SCREEN_ATTR 0x07

static void log_write_screen_len(const char *s, unsigned short len)
{
    unsigned short i;
    for (i = 0; i < len; i++)
    {
        unsigned char c = (unsigned char)s[i];
        if (c == '\r')
        {
            screen_col = 0;
        }
        else if (c == '\n')
        {
            screen_row++;
            screen_col = 0;
        }
        else if (c == '\t')
        {
            do {
                hal_video_write_text_char(screen_row, screen_col, ' ', SCREEN_ATTR);
                screen_col++;
            } while (screen_col % 8 != 0 && screen_col < 80);
        }
        else
        {
            hal_video_write_text_char(screen_row, screen_col, c, SCREEN_ATTR);
            screen_col++;
        }
        if (screen_col >= 80)
        {
            screen_col = 0;
            screen_row++;
        }
        while (screen_row >= 25)
        {
            hal_video_scroll_text();
            screen_row = 24;
        }
    }
}

void log_open(const char *path)
{
    log_fd = hal_file_open(path, 1);
    screen_row = 0;
    screen_col = 0;
    screen_inited = 1;
    hal_video_clear_text();
}

void log_enable_serial(int port, unsigned long baud)
{
    hal_serial_init(port, baud);
    serial_enabled = 1;
}

static void flush(void)
{
    if (log_buf_pos == 0) return;
    if (log_fd >= 0)
        hal_file_write(log_fd, log_buf, log_buf_pos);
    log_buf_pos = 0;
}

static void buf_write(const char *buf, unsigned short len)
{
    if (log_fd < 0) return;
    unsigned short i;
    for (i = 0; i < len; i++)
    {
        log_buf[log_buf_pos++] = buf[i];
        if (log_buf_pos >= LOG_BUF_SIZE)
            flush();
    }
    if (screen_inited)
        log_write_screen_len(buf, len);
    if (serial_enabled)
        hal_serial_write(buf);
}

void log_flush(void)
{
    flush();
}

void log_write(const char *s)
{
    unsigned short len = 0;
    while (s[len]) len++;
    buf_write(s, len);
}

void log_nl(void)
{
    buf_write("\r\n", 2);
}

void log_write_dec(unsigned short val)
{
    char buf[6];
    unsigned char i = 0;
    if (val == 0)
    {
        buf[0] = '0';
        buf_write(buf, 1);
        return;
    }
    char rev[6];
    unsigned char rlen = 0;
    while (val)
    {
        rev[rlen++] = (char)('0' + (val % 10));
        val /= 10;
    }
    while (rlen--)
        buf[i++] = rev[rlen];
    buf_write(buf, i);
}

void log_write_datetime(void)
{
    unsigned short cx, dx;
    __asm volatile (
        "mov $0x2A, %%ah\n\t"
        "int $0x21\n\t"
        : "=c" (cx), "=d" (dx)
        : : "%ax");
    unsigned short year = cx;
    unsigned char month = dx >> 8;
    unsigned char day = dx & 0xFF;
    log_write_dec(year);
    buf_write("-", 1);
    if (month < 10) buf_write("0", 1);
    log_write_dec(month);
    buf_write("-", 1);
    if (day < 10) buf_write("0", 1);
    log_write_dec(day);
    buf_write(" ", 1);
    __asm volatile (
        "mov $0x2C, %%ah\n\t"
        "int $0x21\n\t"
        : "=c" (cx), "=d" (dx)
        : : "%ax");
    unsigned char hour = cx >> 8;
    unsigned char minute = cx & 0xFF;
    unsigned char second = dx >> 8;
    if (hour < 10) buf_write("0", 1);
    log_write_dec(hour);
    buf_write(":", 1);
    if (minute < 10) buf_write("0", 1);
    log_write_dec(minute);
    buf_write(":", 1);
    if (second < 10) buf_write("0", 1);
    log_write_dec(second);
}

void log_printf(const char *fmt, ...)
{
    va_list args;
    va_start(args, fmt);
    char out[LOG_BUF_SIZE];
    unsigned short pos = 0;
    while (*fmt && pos < LOG_BUF_SIZE - 1)
    {
        if (*fmt == '%')
        {
            fmt++;
            switch (*fmt)
            {
                case 's':
                {
                    const char *s = va_arg(args, const char *);
                    while (*s && pos < LOG_BUF_SIZE - 1)
                        out[pos++] = *s++;
                    break;
                }
                case 'd':
                {
                    unsigned int val = va_arg(args, unsigned int);
                    if (val == 0)
                    {
                        out[pos++] = '0';
                    }
                    else
                    {
                        char rev[5];
                        unsigned char rlen = 0;
                        while (val)
                        {
                            rev[rlen++] = (char)('0' + (val % 10));
                            val /= 10;
                        }
                        while (rlen-- && pos < LOG_BUF_SIZE - 1)
                            out[pos++] = rev[rlen];
                    }
                    break;
                }
                case 'x':
                {
                    unsigned int val = va_arg(args, unsigned int);
                    char rev[4];
                    unsigned char rlen = 0;
                    unsigned char started = 0;
                    for (unsigned char i = 0; i < 4; i++)
                    {
                        unsigned char nib = (unsigned char)((val >> (12 - i * 4)) & 0xF);
                        if (nib || started || i == 3)
                        {
                            started = 1;
                            rev[rlen++] = nib <= 9 ? (char)('0' + nib) : (char)('A' + nib - 10);
                        }
                    }
                    for (unsigned char i = 0; i < rlen && pos < LOG_BUF_SIZE - 1; i++)
                        out[pos++] = rev[i];
                    break;
                }
                case 'c':
                {
                    char c = (char)va_arg(args, int);
                    out[pos++] = c;
                    break;
                }
                case '%':
                    out[pos++] = '%';
                    break;
            }
            fmt++;
        }
        else
        {
            out[pos++] = *fmt++;
        }
    }
    va_end(args);
    buf_write(out, pos);
}

void log_close(void)
{
    flush();
    if (log_fd >= 0)
    {
        hal_file_close(log_fd);
        log_fd = -1;
    }
}
