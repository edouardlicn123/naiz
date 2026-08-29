/*
 * NB 脚本解释器公共接口 (Naiz Book)
 * NB: 基于文本的脚本系统，替代 scene.c 的二进制 VM
 * 提供 nb_init/nb_process 供 main.c 主循环调用
 * 参考: devdocs/0.1版开发文档总结.html#doc-21
 */
#ifndef NB_H
#define NB_H

/*
 * 初始化 NB 脚本引擎
 * 加载 settings.txt → tr_init 翻译表 → 加载 logo.nb
 * 返回值: 0=成功
 */
int  nb_init(void);

/*
 * 执行 NB 脚本的一帧处理
 * 循环执行: 读取下一行 → 解析命令 → 通过 cmd_table 分派
 * 支持分页对话框续显 (dialog_state.text_offset)
 * 返回值: 0=正常, SCENE_STATUS_FINALEND=退出, SCENE_STATUS_ERROR=出错
 */
int  nb_process(void);

/*
 * 加载并切换到指定场景脚本（供 main loop / NB 命令处理器 / 存档模块调用）。
 * 内部触发 VMFLAG_SCENE_CHANGED 让主循环完成场景切换。
 */
void nb_load(const char *filename);

/*
 * 当前场景是否为菜单场景（mainmenu/loadscene/scenes/setting/logo/op）。
 * 菜单场景中禁用 F5/F6 存档热键。
 * 返回值: 1=菜单场景
 */
int nb_is_menu_scene(void);

/*
 * 复制当前解释器状态（filename/lang/chapter_title）到调用者缓冲区。
 * 每个缓冲区的 size 必须包含结尾 NUL 字节；拷贝保证 NUL 终止。
 */
void nb_get_state(char *filename, int fn_size,
                  char *lang, int lang_size,
                  char *title, int title_size);

/*
 * 从存档快照恢复运行时语言。
 */
void nb_set_lang(const char *lang);

#endif
