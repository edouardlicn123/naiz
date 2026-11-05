/*
 * tr.h — 运行时翻译表（i18n）接口
 *
 * 从 i18n/*.txt 文件加载 key=value 翻译键值对，提供精确匹配查找。
 * 支持 system/role/game 三组翻译文件按语言标识加载。
 */

#ifndef TR_H
#define TR_H

/* 翻译文件路径缓冲区大小（字节） */
#define TR_PATH_BUF_SIZE 64

/* 容量上限（devdoc 121：按 5 个对话框推导）
 * key 855 B→1024；value 1260 B→1280 */
#define TR_KEY_LEN 1024
#define TR_VAL_LEN 1280

/* 行缓冲（key + '=' + value + \n\0） */
#define TR_LINE_MAX (TR_KEY_LEN + TR_VAL_LEN + 4)

/* 初始化翻译系统：清空翻译表并按 lang 加载 system/role/game 三组文件 */
/* 参数 lang: 语言标识（如 "zh", "ja", "en"）; 返回值: 0=成功 */
int  tr_init(const char *lang);
/* 查询 text 对应的翻译文本，精确匹配，未找到返回原字符串 */
/* 参数 text: 源字符串; 返回值: 译文字符串（内部表指针，调用方不应释放） */
const char *tr(const char *text);
/* 返回当前已加载的翻译条目数 */
int tr_get_count(void);
/* 返回翻译加载过程中发生截断的条目数（静默→响亮） */
int tr_get_truncations(void);

#endif
