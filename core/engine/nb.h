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
 * 场景切换单入口（阶段 2 G）：统一接管「音频停止 + nb_load」
 * （黑屏 / 键盘排空 / 显示重置在 nb_load -> scene_end 内完成）。
 * 所有场景切换（脚本 scene 命令、main loop 热键、存档应用、菜单跳转、
 * 引擎启动）都必须经此入口，不得直接调 nb_load。
 * reason 为 SceneSwitchReason 枚举值，仅作语义记录。
 */
typedef enum {
    SCENE_SWITCH_INIT = 0,    /* 引擎启动 -> logo */
    SCENE_SWITCH_SCRIPT = 1,  /* 脚本 scene 命令 */
    SCENE_SWITCH_HOTKEY = 2,  /* main loop F5/F6/ESC */
    SCENE_SWITCH_APPLY = 3,   /* 存档应用（load） */
    SCENE_SWITCH_MENU = 4     /* 菜单跳转（mainmenu/cgview/loadscen/back） */
} SceneSwitchReason;

void scene_switch(const char *filename, int reason);

/*
 * 当前场景是否为菜单场景（mainmenu/loadscen/scenes/setting/logo/op）。
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
