# 87 — CJK 按语言加载与游戏前设置菜单

> 日期：2026-08-27
> 前置：devdoc 84-86（显示层架构）
> 版本起点：0.2.065

---

## 一、问题陈述

### 1.1 CJK.DAT 内存占用过高

CJK.DAT 是引擎最大的堆分配，占 4MB 机器的 24.8%：

| 指标 | 值 |
|------|-----|
| 文件大小 | 1,016 KB |
| 字形数 | 32,515 |
| 占 4MB 比例 | 24.8% |

### 1.2 内存分布

| Unicode 范围 | 字形数 | 大小 | 占比 |
|-------------|--------|------|------|
| Basic Latin (U+0020-007E) | 95 | 3 KB | 0.3% |
| CJK Symbols (U+3000-303F) | 64 | 2 KB | 0.2% |
| Hiragana (U+3040-309F) | 96 | 3 KB | 0.3% |
| Katakana (U+30A0-30FF) | 96 | 3 KB | 0.3% |
| CJK Ideographs (U+4E00-9FFF) | 20,992 | 656 KB | 64.6% |
| Hangul (U+AC00-D7A3) | 11,172 | 349 KB | 34.3% |

### 1.3 核心思路

根据用户选择的语言，只加载对应的 Unicode 范围。默认英语无需 CJK。

---

## 二、支持的语言

### 2.1 语言列表

| 语言 | 按钮文字 | lang 值 | CJK 文件 | 大小 |
|------|---------|--------|---------|------|
| English | English | eng | CJK_EN.DAT | ~3 KB |
| Japanese | Japanese | jpn | CJK_JP.DAT | ~680 KB |
| Chinese (Simplified) | Chinese (SC) | chi | CJK_CN.DAT | ~674 KB |
| Chinese (Traditional) | Chinese (TC) | cht | CJK_CT.DAT | ~674 KB |
| Korean | Korean | kor | CJK_KR.DAT | ~1,016 KB |
| French | French | fre | CJK_FR.DAT | ~5 KB |
| German | German | ger | CJK_DE.DAT | ~5 KB |
| Italian | Italian | ita | CJK_IT.DAT | ~5 KB |
| Spanish | Spanish | spa | CJK_ES.DAT | ~5 KB |
| Portuguese | Portuguese | por | CJK_PT.DAT | ~5 KB |

### 2.2 各文件包含的 Unicode 范围

| 文件 | 范围 | 字形数 |
|------|------|--------|
| CJK_EN.DAT | Basic Latin | 95 |
| CJK_FR.DAT | Basic Latin + Extended Latin (U+00C0-00FF) | 159 |
| CJK_DE.DAT | Basic Latin + Extended Latin | 159 |
| CJK_IT.DAT | Basic Latin + Extended Latin | 159 |
| CJK_ES.DAT | Basic Latin + Extended Latin | 159 |
| CJK_PT.DAT | Basic Latin + Extended Latin | 159 |
| CJK_JP.DAT | Basic Latin + CJK Symbols + Hiragana + Katakana + Ideographs | ~21,343 |
| CJK_CN.DAT | Basic Latin + CJK Symbols + Ideographs | ~21,151 |
| CJK_CT.DAT | Basic Latin + CJK Symbols + Ideographs | ~21,151 |
| CJK_KR.DAT | Basic Latin + CJK Symbols + Ideographs + Hangul | ~32,335 |

### 2.3 内存节省

| 场景 | 原方案 | 新方案 | 节省 |
|------|--------|--------|------|
| 默认英语 | 1,016 KB | 3 KB | 1,013 KB (99.7%) |
| 选择日语 | 1,016 KB | 680 KB | 336 KB (33%) |
| 选择中文 | 1,016 KB | 674 KB | 342 KB (34%) |
| 选择韩语 | 1,016 KB | 1,016 KB | 0 KB |
| 选择欧洲语言 | 1,016 KB | 5 KB | 1,011 KB (99.5%) |

---

## 三、启动流程

### 3.1 新启动序列

```
main.c:
  hal_init()
  font_init("FONT.DAT")           ← ASCII 字形
  font_load_alt("BLACK.DAT")      ← 黑体 ASCII
  hal_kbd_init()
  hal_mouse_init()
  hal_video_init()
  hal_set_palette(...)
  fill_rect(0, 0, 640, 400, 0)   ← 全屏黑
  image_init("IMAGE.DAT")
  sys_save_load()
  settings_load()                  ← 读 settings.txt，无则默认 lang=eng

  if (首次启动 / 无 settings.txt) {
      settings_menu_run()          ← C 代码绘制英语菜单
      settings_save()              ← 保存选择
  }

  cjk_init(cjk_file_for_lang())   ← 按 lang 选择 CJK 文件
  nb_init() → logo.nb → mainmenu.nb
```

### 3.2 关键变化

| 项目 | 原流程 | 新流程 |
|------|--------|--------|
| CJK 加载时机 | settings_load 之前 | settings_load 之后 |
| CJK 文件 | 固定 "CJK.DAT" | 按 lang 动态选择 |
| 设置菜单 | 无 | 首次启动显示 |
| 菜单语言 | — | 纯英语（ASCII） |

### 3.3 首次启动 vs 后续启动

| 场景 | 行为 |
|------|------|
| 首次启动（无 settings.txt） | 显示设置菜单 → 选择语言 → 保存 → 加载 CJK → 进入游戏 |
| 后续启动（有 settings.txt） | 跳过设置菜单 → 直接加载 CJK → 进入游戏 |

---

## 四、设置菜单设计

### 4.1 菜单草图（640×400）

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│                       Naiz Settings                            │
│                                                                │
│                                                                │
│  Language     ┌───┐ ┌──────────────┐ ┌───┐                    │
│               │ < │ │   Japanese   │ │ > │                    │
│               └───┘ └──────────────┘ └───┘                    │
│                                                                │
│                                                                │
│                      ┌──────────────┐                          │
│                      │  Start Game  │                          │
│                      └──────────────┘                          │
│                                            v0.2.065           │
└────────────────────────────────────────────────────────────────┘
```

### 4.2 元素坐标

| 元素 | 位置 | 尺寸 | 说明 |
|------|------|------|------|
| 标题 "Naiz Settings" | (240, 40) | — | 无边框，draw_title_large() |
| 标签 "Language" | (80, 130) | — | 左侧，draw_text() |
| < 按钮 | (220, 126) | 40×28 | 切换语言 |
| 当前语言文字 | (270, 126) | 180×28 | 居中显示当前选择 |
| > 按钮 | (460, 126) | 40×28 | 切换语言 |
| Start Game | (240, 220) | 160×32 | 保存并进入游戏 |

### 4.3 交互逻辑

**语言切换**：

```
← → 方向键 或 点击 < > 按钮：
  English → Japanese → Chinese (SC) → Chinese (TC) → Korean →
  French → German → Italian → Spanish → Portuguese → 循环回 English
```

**当前选择加载**：

```
显示菜单时：
  lang = settings_get_lang()
  如果是首次启动（无 settings.txt）：
      lang = "eng"                  ← 默认英语
  显示当前 lang 对应的文字
```

**Start Game**：

```
点击 Start Game：
  settings_save()                   ← 写入 settings.txt
  cjk_init("CJK_{lang}.DAT")       ← 加载对应字库
  nb_init() → logo.nb → mainmenu.nb → 游戏
```

### 4.4 按钮样式

| 状态 | 背景 | 文字 |
|------|------|------|
| 未选中 | 灰色 (PAL_DIALOG_FILL=248) | 白色 (PAL_WHITE=7) |
| 选中/高亮 | 黄色 (MENU_PAL_YELLOW=251) | 黑色 (0) |

---

## 五、Extended Latin 扩展

### 5.1 范围定义

```python
# gen_cjk_font.py 新增
EXTENDED_LATIN = (0x00C0, 0x00FF)  # 64 个字形
# 覆盖：À Á Â Ã Ä Å Æ Ç È É Ê Ë Ì Í Î Ï Ð Ñ Ò Ó Ô Õ Ö Ø Ù Ú Û Ü Ý Þ ß
#       à á âã ä å æ ç è é ê ë ì í î ï ð ñ ò ó ô õ ö ø ù úû ü ý þ ÿ
```

### 5.2 语言文件生成

```python
# 欧洲语言：Basic Latin + Extended Latin
for lang in ["fre", "ger", "ita", "spa", "por"]:
    generate_cjk(
        output=f"CJK_{lang.upper()}.DAT",
        ranges=[
            (0x0020, 0x007E),  # Basic Latin
            (0x00C0, 0x00FF),  # Extended Latin
        ]
    )
```

---

## 六、改动清单

### A. `tools/naiz_font/gen_cjk_font.py` — 添加 Extended Latin 支持

```python
# 新增范围常量
EXTENDED_LATIN_START = 0x00C0
EXTENDED_LATIN_END = 0x00FF
```

### B. `tools/naiz_build/build_game.py` — 生成多语言 CJK 文件

```python
# 新增函数
def generate_language_cjk(output_dir):
    """生成所有语言版本的 CJK 文件"""
    languages = {
        "EN": [(0x0020, 0x007E)],
        "FR": [(0x0020, 0x007E), (0x00C0, 0x00FF)],
        "DE": [(0x0020, 0x007E), (0x00C0, 0x00FF)],
        "IT": [(0x0020, 0x007E), (0x00C0, 0x00FF)],
        "ES": [(0x0020, 0x007E), (0x00C0, 0x00FF)],
        "PT": [(0x0020, 0x007E), (0x00C0, 0x00FF)],
        "JP": [(0x0020, 0x007E), (0x3000, 0x303F), (0x3040, 0x309F),
               (0x30A0, 0x30FF), (0x4E00, 0x9FFF)],
        "CN": [(0x0020, 0x007E), (0x3000, 0x303F), (0x4E00, 0x9FFF)],
        "CT": [(0x0020, 0x007E), (0x3000, 0x303F), (0x4E00, 0x9FFF)],
        "KR": [(0x0020, 0x007E), (0x3000, 0x303F), (0x4E00, 0x9FFF),
               (0xAC00, 0xD7A3)],
    }
    for lang_code, ranges in languages.items():
        generate_cjk_file(
            os.path.join(output_dir, f"CJK_{lang_code}.DAT"),
            ranges
        )
```

### C. `core/engine/main.c` — 启动流程调整

```c
// 原：
cjk_init("CJK.DAT");

// 新：
settings_load();
if (settings_menu_needed())     // 首次启动
    settings_menu_run();        // 绘制菜单，用户选择，保存
cjk_init(cjk_file_for_lang()); // 按 lang 加载
```

### D. `core/engine/settings.c` — 添加 settings_save()

```c
int settings_save(void) {
    FILE *f = fopen("settings.txt", "w");
    if (!f) return -1;
    fprintf(f, "version=%s\n", g_settings.version);
    fprintf(f, "dlgstyle=%d\n", g_settings.dlgstyle);
    fprintf(f, "btnstyle=%d\n", g_settings.btnstyle);
    fprintf(f, "lang=%s\n", g_settings.lang);
    fprintf(f, "blacktitle=%d\n", g_settings.blacktitle);
    fprintf(f, "blackdialog=%d\n", g_settings.blackdialog);
    fclose(f);
    return 0;
}
```

### E. `core/engine/settings.h` — 声明

```c
int settings_save(void);
```

### F. `core/engine/settings_menu.c` — 新增设置菜单模块

~150行，实现：

```c
/* 设置菜单运行（阻塞，直到用户点击 Start Game） */
void settings_menu_run(void) {
    int lang_idx = 0;           /* 当前语言索引 */
    const char *lang_names[] = {
        "English", "Japanese", "Chinese (SC)", "Chinese (TC)", "Korean",
        "French", "German", "Italian", "Spanish", "Portuguese"
    };
    const char *lang_codes[] = {
        "eng", "jpn", "chi", "cht", "kor",
        "fre", "ger", "ita", "spa", "por"
    };
    int n_langs = 10;

    /* 从当前设置加载默认选择 */
    lang_idx = find_lang_index(settings_get_lang());

    /* 绘制菜单 */
    draw_title_large(240, 40, "Naiz Settings");
    draw_text("Language", 0, 80, 130, 200, 400, 0, PAL_WHITE);

    /* 主循环 */
    for (;;) {
        /* 绘制语言选择器 */
        draw_lang_selector(lang_names[lang_idx]);

        /* 绘制 Start Game 按钮 */
        draw_rounded_emboss(240, 220, 160, 32);
        draw_text("Start Game", 0, 270, 228, 120, 400, 0, PAL_WHITE);

        /* 输入处理 */
        if (key_left || click_left_arrow)
            lang_idx = (lang_idx - 1 + n_langs) % n_langs;
        if (key_right || click_right_arrow)
            lang_idx = (lang_idx + 1) % n_langs;
        if (key_enter || click_start_game) {
            settings_set_lang(lang_codes[lang_idx]);
            return;
        }
    }
}
```

### G. `core/engine/settings_menu.h` — 声明

```c
void settings_menu_run(void);
```

### H. `core/Makefile` — 添加 settings_menu.o

```makefile
ENGINE_OBJS += settings_menu.o
```

---

## 七、语言切换顺序

```
English (默认) → Japanese → Chinese (SC) → Chinese (TC) → Korean →
French → German → Italian → Spanish → Portuguese → 循环回 English
```

索引表：

| 索引 | 语言 | lang 值 | CJK 文件 |
|------|------|--------|---------|
| 0 | English | eng | CJK_EN.DAT |
| 1 | Japanese | jpn | CJK_JP.DAT |
| 2 | Chinese (SC) | chi | CJK_CN.DAT |
| 3 | Chinese (TC) | cht | CJK_CT.DAT |
| 4 | Korean | kor | CJK_KR.DAT |
| 5 | French | fre | CJK_FR.DAT |
| 6 | German | ger | CJK_DE.DAT |
| 7 | Italian | ita | CJK_IT.DAT |
| 8 | Spanish | spa | CJK_ES.DAT |
| 9 | Portuguese | por | CJK_PT.DAT |

---

## 八、验证计划

### 8.1 构建验证

```bash
# 确认所有 CJK 文件生成
ls -la games/*/CJK_*.DAT
# 应有 10 个文件：CJK_EN/FR/DE/IT/ES/PT/JP/CN/CT/KR.DAT
```

### 8.2 内存验证

串口输出：

```c
hal_log("cjk: loaded '%s' (%ld bytes)\r\n", filename, file_size);
```

验证：
- 首次启动：`CJK_EN.DAT` (~3 KB)
- 选择日语后重启：`CJK_JP.DAT` (~680 KB)

### 8.3 功能验证

1. **首次启动**：显示设置菜单，选择语言，点击 Start Game
2. **语言切换**：← → 切换语言，验证文字正确显示
3. **设置保存**：检查 settings.txt 内容正确
4. **重启验证**：重启后跳过设置菜单，直接进入游戏
5. **CJK 验证**：进入游戏后 CJK 文字正确显示

### 8.4 回归验证

```bash
make -C core && tools/env_setup/venv/bin/python -m pytest tools/tests/
```

---

## 九、版本变更

- 版本号：0.2.065 → 0.2.066
- 新增文件：
  - `core/engine/settings_menu.c`（~150行）
  - `core/engine/settings_menu.h`（~10行）
  - `CJK_EN.DAT`（~3 KB）
  - `CJK_JP.DAT`（~680 KB）
  - `CJK_CN.DAT`（~674 KB）
  - `CJK_CT.DAT`（~674 KB）
  - `CJK_KR.DAT`（~1,016 KB）
  - `CJK_FR.DAT`（~5 KB）
  - `CJK_DE.DAT`（~5 KB）
  - `CJK_IT.DAT`（~5 KB）
  - `CJK_ES.DAT`（~5 KB）
  - `CJK_PT.DAT`（~5 KB）
- 修改文件：
  - `core/engine/main.c`（+15行：启动流程调整）
  - `core/engine/settings.c`（+15行：settings_save 实现）
  - `core/engine/settings.h`（+1行：settings_save 声明）
  - `core/Makefile`（+1行：settings_menu.o）
  - `tools/naiz_font/gen_cjk_font.py`（+10行：Extended Latin 支持）
  - `tools/naiz_build/build_game.py`（+50行：多语言 CJK 生成）
- 无头文件依赖变更
