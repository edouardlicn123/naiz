#ifndef LOG_H
#define LOG_H

void log_open(const char *path);
void log_write(const char *s);
void log_write_dec(unsigned short val);
void log_write_datetime(void);
void log_flush(void);
void log_nl(void);
void log_printf(const char *fmt, ...);
void log_close(void);

#endif
