/*
 * 来源项目：MHVNVisualNovelEngine
 * GitHub:   https://github.com/maxotaku11niku/MHVNVisualNovelEngine
 * 许可证：   MIT License
 */

#ifndef PC98_CHARGEN_H
#define PC98_CHARGEN_H

void chargen_get_char_data(unsigned short code, unsigned long *buffer);
void chargen_set_char_data(unsigned short code, const unsigned long *buffer);
unsigned short chargen_sjis_to_internal(unsigned short code);

#endif
