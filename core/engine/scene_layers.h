/*
 * Scene layers — sprite registry, bg snapshot, dialog state machine.
 *
 * Implements the layered rendering model:
 *   Layer 0: Background (full-screen MAG image)
 *   Layer 1: Sprites (up to 16, with mirror + face/replace semantics)
 *   Layer 2: Dialog box (VN text area, y ≥ 280)
 *
 * Architecture constraints:
 *   - face sprites must not write to y ≥ LAYER_DIALOG_Y (clip_h guard)
 *   - dialog lazy-snapshot avoids corruption from sprite overlap
 */
#ifndef SCENE_LAYERS_H
#define SCENE_LAYERS_H

#include "mag.h"


/* 最大精灵数（同时活跃） */
#define LAYER_MAX_SPRITES  16
/* 精灵区域宽度 */
#define LAYER_SPRITE_W    200
/* 精灵区域高度 */
#define LAYER_SPRITE_H    400
/* 对话框区域 */
#define LAYER_DIALOG_X    80
#define LAYER_DIALOG_Y    280                       /* 对话框首行 */
#define LAYER_DIALOG_W    480
#define LAYER_DIALOG_H    115
#define LAYER_DIALOG_BORDER  2                      /* 边框宽度 */
#define LAYER_DIALOG_INDENT  12                     /* 左侧缩进 */
#define LAYER_DIALOG_RIGHT_INDENT 12                /* 右侧缩进 */
#define LAYER_DIALOG_TEXT_Y  28                     /* 文本起始 Y */
#define LAYER_DIALOG_HEADER_Y 6                     /* 角色名起始 Y */
#define LAYER_DIALOG_BOTTOM  (LAYER_DIALOG_Y + LAYER_DIALOG_H - LAYER_DIALOG_BORDER)
/* 颜色方案数量（对话框/按钮背景色） */
#define COLOR_SCHEME_COUNT  5
/* screen dimensions in render.h (LAYER_SCREEN_W, LAYER_SCREEN_H) */

/*==== Layer Z-order (lower = drawn first, covered by higher) ==============*/
#define LAYER_Z_BG        0   /* 背景层：全屏640x400 */
#define LAYER_Z_SPRITE    1   /* 立绘层：最多16个精灵，clip_h保护对话框 */
#define LAYER_Z_ANIM      2   /* 动画层：clip_h限制在y<LAYER_DIALOG_Y */
#define LAYER_Z_DIALOG    3   /* 对话框层：(80,280) 480x115 */
#define LAYER_Z_TEXT      4   /* 文字层：在对话框内绘制文字 */
#define LAYER_Z_CURSOR    5   /* 光标层：最顶层，最后绘制 */
#define LAYER_Z_COUNT     6   /* 层总数 */

/* 层边界矩形 */
typedef struct {
    int x, y, w, h;
} LayerBounds;

/* Scene transition API lives in transition.h (transition.c). */
#include "transition.h"

/* Button system constants */
#define BTN_W           100
#define BTN_H            34
#define BTN_R            17
#define SAVE_SLOT_R       5
#define BTN_GAP          10
#define BTN_COL_GAP      14
#define BTN_FILL_IDX       249
#define BTN_HIGHLIGHT_IDX  252
#define BTN_SHADOW_IDX     253

/* Dialog/button style — encapsulated in layer_dialog.c, accessed via accessors. */

/* Dialog/palette helpers (implemented in layer_dialog.c) */
void dlg_update_palette(void);
void btn_update_palette(void);
/* Set dialog/button style (with palette update). Values clamped internally. */
void dlg_set_style(unsigned char s);
void btn_set_style(unsigned char s);
/* Return current dialog style (0-9). */
unsigned char dlg_get_style(void);

/* Fill rectangle with dialog background style (solid or dither per g_dialog_style). */
void fill_dialog_bg(int x, int y, int w, int h);

/*
 * INVARIANT: layer_sprite_face() must NOT write to y >= LAYER_DIALOG_Y.
 * Sprite draws that must affect the dialog area must use
 * layer_sprite_replace() which calls layer_dialog_refresh().
 */

/* 精灵条目：记录位置、资源 ID 和镜像状态 */
typedef struct {
    unsigned char active;   /* 是否激活 */
    int id;                 /* 精灵 ID */
    int asset_id;           /* 资源 ID */
    int x, y;               /* 屏幕坐标 */
    int mirror;             /* 水平翻转标志 */
} SpriteEntry;

/* 统一场景结束处理：失效鼠标快照 → 全屏清黑 → 重置图层 → 排空键盘
 * skip_transition: 为 1 时跳过过渡动画，直接全屏黑屏 */
void scene_end(int skip_transition);
/* 截取当前 VRAM 作为背景层 */
void layer_capture_bg(void);
/* 截取对话框区域的背景 */
void layer_capture_bg_dialog(void);
/* 从纯背景快照重建对话框背景（避免 VRAM 上对话框叠加层污染） */
void layer_capture_bg_dialog_from_bg(void);
/* 打开 VN 对话框 */
void layer_dialog_open(void);
/* 还原对话框区域的背景 */
void layer_dialog_restore(void);
/* 截取当前对话框像素用于后续还原 */
void layer_dialog_snap(void);
/* 隐藏对话框 */
void layer_dialog_hide(void);
/* 对话框是否已绘制 */
int  layer_dialog_drawn(void);

/* 显示精灵（全身），y 不受限制 */
void layer_sprite_show(int sprite_id, int asset_id, int x, int y, int mirror);
/* 换表情（仅上半身），限制 y < LAYER_DIALOG_Y */
void layer_sprite_face(int sprite_id, int asset_id, int x, int y, int mirror);
/* 替换精灵（全身 + 刷新对话框区域） */
void layer_sprite_replace(int sprite_id, int asset_id, int x, int y, int mirror);
/* 隐藏所有精灵 + 清理状态 */
void layer_sprite_hide_all(void);
/* 查询指定精灵是否存在 */
int  layer_has_sprite(int id);
/* 重绘所有激活的精灵 */
void layer_redraw_sprites(void);

/*==== Unified layer management API ========================================*/

/* 统一换背景操作（封装7步仪式：blit + 条件capture + redraw + palette + snapshot） */
void layer_bg_change(MagImage *img);
/* 统一立绘更新操作（内部自动选择 show/replace） */
void layer_sprite_update(int sprite_id, int asset_id, int x, int y, int mirror);
/* 统一对话框显示操作（内部自动选择 open/snap + restore） */
void layer_dialog_show(void);
/* 统一对话框隐藏操作（hide + redraw sprites） */
void layer_dialog_hide_clean(void);

/*==== Layer Z-order state query ===========================================*/

/* 查询某层是否活跃（有内容显示） */
int  layer_is_active(int z_order);
/* 标记某层活跃/非活跃 */
void layer_set_active(int z_order, int active);
/* 获取某层的可写区域 */
LayerBounds layer_get_bounds(int z_order);
/* 检查在指定y坐标写入某层是否安全（不破坏更高层） */
int  layer_can_blit_at(int z_order, int y);

#endif
