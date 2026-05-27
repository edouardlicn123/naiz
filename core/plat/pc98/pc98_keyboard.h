/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#ifndef PC98_KEYBOARD_H
#define PC98_KEYBOARD_H

#define KEY_STATUS  ((volatile unsigned __far char*)0x052A)

#define KEY_MOD   (*((volatile unsigned __far char*)0x053A))
#define KEY_MOD_SHIFT 0x01
#define KEY_MOD_CAPS  0x02
#define KEY_MOD_KANA  0x04
#define KEY_MOD_GRPH  0x08
#define KEY_MOD_CTRL  0x10

#define KC_ESC  0x00
#define KC_ENTER 0x1C
#define KC_SPACE 0x34

void update_prev_key_status(void);
void wait_vsync(void);

#endif
