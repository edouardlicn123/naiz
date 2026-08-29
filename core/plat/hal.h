/*
 * hal.h — 硬件抽象层（HAL）接口
 *
 * 引擎的 platform 无关代码通过此接口访问平台特定的硬件功能。
 * 每个支持的平台提供一组实现文件（如 PC-98 的 hal_pc98.c / hal_kbd.c /
 * hal_mouse.c / hal_video.c）。
 *
 * 当前定义的接口：
 *   基础:
 *   - hal_init()         平台初始化（串口、中断等）
 *   - hal_log()          调试日志输出
 *   - hal_set_palette()  调色板 RGB 写入
 *   - hal_read_palette() 调色板 RGB 读取
 *   显示:
 *   - hal_video_init()   视频模式设置
 *   - hal_video_exit()   视频模式恢复
 *   - hal_vblank_wait()  垂直同步等待
 *   键盘:
 *   - hal_kbd_init()     键盘初始化
 *   - hal_kbd_update()   每帧轮询
 *   - hal_kbd_is_down()    消耗性查询
 *   - hal_kbd_flush()      清空缓冲
 *   - hal_kbd_drain_advance() 确认键释放等待
 *   - hal_kbd_wait_any()     任意键等待
 *   - hal_kbd_set_ignore_frames() 帧忽略设置
 *   鼠标:
 *   - hal_mouse_init()     鼠标初始化
 *   - hal_mouse_update()   每帧轮询
 *   - hal_mouse_get_x/y()  坐标查询
 *   - hal_mouse_was_clicked() 按钮状态
 *   - hal_mouse_flush/drain() 缓冲操作
 *   - hal_mouse_set_pos()   位置设置
 *   - hal_mouse_draw_cursor() 光标绘制
 *   音频:
 *   - hal_bgm_play/stop()   BGM 控制
 *   - hal_sound_play()      音效
 *   - hal_voice_play()      语音
 *
 * 约束（详见 AGENTS.md §5.1）：
 *   - core/engine/ 中的引擎代码只能通过此头文件访问硬件
 *   - outb()/inb() 等端口 I/O 只能在 core/plat/ 中调用
 *   - 不允许在引擎代码中直接解引用 MMIO 地址
 *
 * 键盘扫描码常量（KC_*）与鼠标按钮常量在此处定义，供 engine 层使用。
 * 平台实现（keyboard.c/mouse.c）也使用同一套常量。
 */
#ifndef HAL_H
#define HAL_H

#include <stdint.h>

/*
 * 平台初始化
 *
 * 在引擎启动早期调用一次。PC-98 实现初始化 uPD8251 串口作为
 * 调试输出通道。其他平台实现应在此完成必要的早期硬件设置。
 *
 * 在所有其他 HAL 函数之前调用。
 */
void hal_init(void);

/*
 * 调试字符串输出
 *
 * 在 DOS/4GW 保护模式下，标准 printf() 不可用（DOS 文本层被
 * 图形模式覆盖），串口是唯一可靠的输出通道。
 *
 * @param s  以 NUL 结尾的字符串
 */
void hal_log(const char *s);

/*
 * 设置调色板索引的 RGB 值
 *
 * 各分量使用 8-bit 精度（0-255）。PC-98 PEGC 模式下通过
 * GDC 端口 0xA8-0xAE 写入。
 *
 * @param idx  调色板索引（0-255）
 * @param r    红色分量
 * @param g    绿色分量
 * @param b    蓝色分量
 */
void hal_set_palette(int idx, uint8_t r, uint8_t g, uint8_t b);

/*
 * 读取调色板索引的 RGB 值
 *
 * 读取索引 idx 对应的 R/G/B 分量，通过输出参数返回。
 *
 * @param idx  调色板索引（0-255）
 * @param r    输出红色分量
 * @param g    输出绿色分量
 * @param b    输出蓝色分量
 */
void hal_read_palette(int idx, uint8_t *r, uint8_t *g, uint8_t *b);

/*
 * 等待垂直回扫（VBLANK）
 *
 * 轮询 GDC 状态端口直到 VSYNC 开始。
 * 为免撕裂的 VRAM 操作提供 ~16ms 安全窗口。
 */
void hal_vblank_wait(void);

/*
 * 读取墙钟毫秒数（DOS INT 21h AH=2Ch，10ms 分辨率）
 *
 * 用于与帧节拍解耦的时间基动画步进。午夜回绕由调用方处理。
 */
unsigned long hal_wallclock_ms(void);

/*
 * 音频播放（stub）
 *
 * 当前为空实现，仅通过 hal_log() 输出命令和 key。
 * 后端实现计划见 devdocs/0.1版开发文档总结.html#doc-41。
 */
void hal_bgm_play(const char *key);
void hal_bgm_stop(void);
void hal_sound_play(const char *key);
void hal_sound_stop(void);
void hal_voice_play(const char *key);
void hal_voice_stop(void);

/*============================================================================
 * 键盘扫描码常量（PC-98 硬件标准）
 *============================================================================
 * 与 NP2kai keystat.tbl 定义的编码一致。
 * engine 层代码通过这些常量调用 hal_kbd_*() 函数。
 */
#define HAL_KBD_WAIT_MAX_ITER  50000

/* 字母数字键 —— 扫描码 0x00-0x0E */
#define KC_ESC      0x00
#define KC_1        0x01
#define KC_2        0x02
#define KC_3        0x03
#define KC_4        0x04
#define KC_5        0x05
#define KC_6        0x06
#define KC_7        0x07
#define KC_8        0x08
#define KC_9        0x09
#define KC_0        0x0A
#define KC_MINUS    0x0B
#define KC_HAT      0x0C
#define KC_YEN      0x0D
#define KC_BS       0x0E
#define KC_TAB      0x0F
#define KC_Q        0x10
#define KC_W        0x11
#define KC_E        0x12
#define KC_R        0x13
#define KC_T        0x14
#define KC_Y        0x15
#define KC_U        0x16
#define KC_I        0x17
#define KC_O        0x18
#define KC_P        0x19
#define KC_AT       0x1A
#define KC_LBRACKET 0x1B
#define KC_RETURN   0x1C
#define KC_ENTER    0x1C
#define KC_A        0x1D
#define KC_S        0x1E
#define KC_D        0x1F
#define KC_F        0x20
#define KC_G        0x21
#define KC_H        0x22
#define KC_J        0x23
#define KC_K        0x24
#define KC_L        0x25
#define KC_SEMI     0x26
#define KC_COLON    0x27
#define KC_RBRACKET 0x28
#define KC_Z        0x29
#define KC_X        0x2A
#define KC_C        0x2B
#define KC_V        0x2C
#define KC_B        0x2D
#define KC_N        0x2E
#define KC_M        0x2F
#define KC_COMMA    0x30
#define KC_DOT      0x31
#define KC_SLASH    0x32
#define KC_UNDER    0x33
#define KC_SPACE    0x34
#define KC_XFER     0x35
#define KC_RLUP     0x36
#define KC_RLDN     0x37
#define KC_INS      0x38
#define KC_DEL      0x39
#define KC_UP       0x3A
#define KC_LEFT     0x3B
#define KC_RIGHT    0x3C
#define KC_DOWN     0x3D
#define KC_HOME     0x3E
#define KC_HELP     0x3F
#define KC_NP_MINUS 0x40
#define KC_NP_SLASH 0x41
#define KC_NP_7     0x42
#define KC_NP_8     0x43
#define KC_NP_9     0x44
#define KC_NP_STAR  0x45
#define KC_NP_4     0x46
#define KC_NP_5     0x47
#define KC_NP_6     0x48
#define KC_NP_PLUS  0x49
#define KC_NP_1     0x4A
#define KC_NP_2     0x4B
#define KC_NP_3     0x4C
#define KC_NP_EQU   0x4D
#define KC_NP_0     0x4E
#define KC_NP_COMMA 0x4F
#define KC_NP_DOT   0x50
#define KC_NFER     0x51
#define KC_VF1      0x52
#define KC_VF2      0x53
#define KC_VF3      0x54
#define KC_VF4      0x55
#define KC_VF5      0x56
#define KC_STOP     0x60
#define KC_COPY     0x61
#define KC_F1       0x62
#define KC_F2       0x63
#define KC_F3       0x64
#define KC_F4       0x65
#define KC_F5       0x66
#define KC_F6       0x67
#define KC_F7       0x68
#define KC_F8       0x69
#define KC_F9       0x6A
#define KC_F10      0x6B
/* 修饰键 */
#define KC_SHIFT    0x70
#define KC_CAPS     0x71
#define KC_KANA     0x72
#define KC_GRPH     0x73
#define KC_ALT      0x73
#define KC_CTRL     0x74

/* 鼠标按钮常量 */
#define HAL_MOUSE_LBUTTON  0
#define HAL_MOUSE_RBUTTON  1

/*============================================================================
 * 键盘 HAL 接口
 *============================================================================
 * 函数签名与 keyboard.h 相同。
 */
void hal_kbd_init(void);
void hal_kbd_update(void);
int  hal_kbd_is_down(unsigned char scancode);
void hal_kbd_flush(void);
void hal_kbd_drain_advance(void);
void hal_kbd_wait_any(void);
void hal_kbd_set_ignore_frames(int n);

/*============================================================================
 * 鼠标 HAL 接口
 *============================================================================
 * 光标绘制函数在阶段二之后移至 engine 层 cursor.c。
 */
void hal_mouse_init(void);
void hal_mouse_update(void);
int  hal_mouse_get_x(void);
int  hal_mouse_get_y(void);
int  hal_mouse_was_clicked(int btn);
void hal_mouse_set_pos(int x, int y);
void hal_mouse_flush(void);
void hal_mouse_drain(void);
void hal_mouse_invalidate_cursor(void);
void hal_mouse_erase_cursor(void);
void hal_mouse_draw_cursor(void);
void hal_mouse_draw_cursor_force(void);
void hal_mouse_recenter_if_idle(void);
int  hal_mouse_available(void);
int  hal_mouse_get_display_x(void);
int  hal_mouse_get_display_y(void);

/*============================================================================
 * 视频 HAL 接口
 *============================================================================
 */
void hal_video_init(void);
void hal_video_exit(void);
void hal_video_check_palette(void);

/*============================================================================
 * VRAM 访问接口
 *
 * PC-98 PEGC 256-color mode: VRAM is 640x400 bytes (256KB total), accessed
 * through a 32KB bank window at 0xA8000. Bank selection via port 0xE0004.
 *
 * These functions abstract the banked VRAM access so engine rendering code
 * does not directly reference hardware addresses (see AGENTS.md §5.1).
 *============================================================================
 */

/* VRAM bank size in bytes (32KB = 32768). */
#define VRAM_BANK_SZ       32768

/* Select VRAM bank 0-7 for the window at 0xA8000. */
void hal_vram_bank_select(int bank);

/* Return pointer to the VRAM window base. */
volatile uint8_t *hal_vram_get_window(void);

#endif
