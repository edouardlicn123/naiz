#ifndef HAL_H
#define HAL_H

void hal_video_init(void);
void hal_video_set_palette(int idx, unsigned char r, unsigned char g, unsigned char b);
void hal_video_fill_rect(int x, int y, int w, int h, int color);
void hal_video_vsync_wait(void);
void hal_video_clear_screen(void);
void hal_video_write_text_char(int row, int col, unsigned char ch, unsigned char attr);
void hal_video_scroll_text(void);
void hal_video_clear_text(void);
void hal_video_deinit(void);

void hal_input_init(void);
int  hal_input_poll(void);
int  hal_input_state(int scancode);

int  hal_file_open(const char *path, unsigned char mode);
int  hal_file_read(int fd, void *buf, int count);
int  hal_file_write(int fd, void const *buf, int count);
int  hal_file_read_far(int fd, unsigned short seg, unsigned short off, int count);
int  hal_file_write_far(int fd, unsigned short seg, unsigned short off, int count);
int  hal_file_close(int fd);
int  hal_file_seek(int fd, unsigned char method, unsigned long len, unsigned long *newpos);

void __far *hal_mem_alloc(unsigned short segments);
void  hal_mem_free(void __far *ptr);

void hal_interrupt_set(unsigned char vector, void (*handler)(void));
void hal_interrupt_get(unsigned char vector, void (**handler)(void));

void hal_vsync_enable(void);
void hal_vsync_disable(void);
int  hal_vsync_count(void);

int hal_check_compatibility(void);

int  hal_serial_init(int port, unsigned long baud);
void hal_serial_write_char(unsigned char c);
void hal_serial_write(const char *s);

#endif
