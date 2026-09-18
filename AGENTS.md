# Naiz — AI 编程规则

> **当前版本**: `0.2.119`（`projects/demo-a2/config.toml`）
>
> **开发历史**: R1–R30、0.2.109–0.2.117 及动画工具链等全部 Bug 修复/功能演进记录已迁至根目录 [`CHANGELOG.md`](CHANGELOG.md)（最新：load 菜单翻页/confirm 残影修复 0.2.117）。
>
> **防复发机制**: 见 §十九 — 每次修改后必须对照 C16/P11/S7 等 39 条规则逐一检查。
>
> **构建验证**: `make -C core` — 0 errors, 0 warnings。Python 工具链全部 `.py` 文件语法通过（`tools/` 下 68 个含 `tools/diag/symbol_audit.py`，不含 venv）。

## 一、Git 限制

- **禁止自动 commit / push**。只在用户说"提交""推送"时才执行。

## 二、目录结构

参考数据（目录树、guildbook 更新约定）已移至 `docs/B91-构建环境与参考速查.md §1`。
要点：代码严格按 core/tools/games/docs/devdocs 归类；`devdocs/` 为历史存档禁止修改。

## 三、构建与测试

参考数据（命令职责、引擎编译、编译隔离、pytest、基座 HDI、运行时链）见 `docs/B91-构建环境与参考速查.md §2`。

核心验证命令：
```bash
make -C core               # 引擎编译（0 errors / 0 warnings）
tools/env_setup/venv/bin/python -m pytest tools/tests/   # Python 单元测试
./makegame.sh build <game>  # 数据构建（games/<game> 部署树，含字库/i18n）
./makegame.sh make <game>    # HDI 注入（承接 build 产物）
```

## 四、运行时约束

参考数据（32-bit 保护模式必须/禁止表）见 `docs/B91-构建环境与参考速查.md §3`。
核心：**32-bit 保护模式**（DOS/4GW 首选，VEM486 DPMI 备选），PC-98 平台（NP2kai IA32 核心）。

## 五、架构约束

参考数据（HAL 边界接口表、平台无关 lib 模块表）见 `docs/B91-构建环境与参考速查.md §4`。
核心：`core/engine/` 只能通过 `core/plat/hal.h` 访问硬件；`outb()`/`inb()`/`int 0x18` 只能在 `core/plat/` 中调用。

## 六、refdocs/ 分类索引

PC-98 外部知识参考文档见 `docs/refdocs/README.md`（按 A–H 类分组：系统架构/内存I/O/显示/输入/存储/声音/编程参考/PDF摘要）。

## 七、关键参考

参考数据（参考项目、开发文档、NP2kai 模拟器、调试速查）见 `docs/B91-构建环境与参考速查.md §5`。

## 八、调试速查

见 `docs/B91-构建环境与参考速查.md §5.4`。串口输出（`makegame.sh test <game> --serial`）是最可靠通道。

## 九、AI 协作原则

1. **先问再做**：不确定时提问，有更简方案主动提出
2. **至简至上**：最少量代码解决，不添加凭空想象的功能
3. **外科手术**：只改必须改的，保持现有风格一致
4. **结果导向**：定义成功标准，迭代至验证通过
5. **先读后写**：完整理解相关代码后再修改
6. **消灭静默失败**：异常/逻辑未命中时必须明确报错
7. **保持一致性**：命名、架构、意图与全局一致
8. **中文沟通**：compact 后自动切换中文
9. **英语注释**：日后所有 `.c` 和 `.py` 文件的代码注释统一用英语书写，不再使用中文注释
10. **先借后造**：开发新功能时优先检索项目内已有的可复用封装（`symbol_audit` B/D 节、B90 函数索引、`grep` 同前缀函数）；确无可用封装时，倾向制作可供后续复用的小而专的封装功能，而非内联零散逻辑

## 十、项目规则

- 代码严格按目录归类（core/tools/games/docs/devdocs）
- **所有项目统一入口为 `engine.exe`**，无 demo/其他之区分
- **每个场景切换时自动清屏为黑屏**（引擎层保证，无需脚本手动清屏）
- GPL v2 代码不得复制（传染性），优先借鉴思路
- 复制代码必须附来源项目 + GitHub + 许可证注释
- 安装失败先查 `logs/env_install.log` 末尾 200 行
- **用户要求"写 devdoc"时**：在 `devdocs/` 目录写入带数字前缀的开发文档（编号接续现有最大编号 +1，格式 `NN-描述.md`，如 `67-封装改进访问器收口与模块边界固化.md`）。devdocs/ 为历史存档，已写入的文档禁止修改；编号由工具/人工按当前最大号顺延

## 十一、显示管线约定

本节为**硬性规定**，未经明确许可不得更改。完整规范见 `docs/B02-显示管线规范.md`。

### 显示管线（固定）

```
video_init()          → PEGC MMIO + BIOS INT 18h AH=30h/40h + VRAM 清除
hal_set_palette()     → 模拟调色板端口（0xA8/0xAA/0xAC/0xAE），8-bit 值
fill_rect(0,0,640,400,0)  → 全屏黑底（VRAM Bank 切换，packed-pixel）
layer_dialog_open()   → VN 对话框黑底 + 白边（由首次 op_text 触发）
draw_text()           → 字模绘制到 VRAM 图形层
```

- 文字输出**禁止使用** `printf` / DOS 文本层——在 DOS/4GW + VEM486 DPMI 保护模式下不可见
- 只能用 `render.h` / `render.c` 提供的 VRAM 像素操作（`pset` / `fill_rect` / `draw_rect` / `draw_text` / `vram_blit` / `vram_blit_sprite` / `vram_pset_addr`）
- `font_get_glyph()` 从 `font.c` 获取 8×16 字形数据

### 引擎初始化顺序（固定）

```
hal_init()             → 串口调试通道
font_init("FONT.DAT")  → 8×16 字形加载
cjk_init("CJK.DAT")    → CJK 字形加载
kbd_init()              → 键盘中断驱动
mouse_init()            → 鼠标 8255 端口初始化（无 TSR 依赖）
video_init()             → PEGC MMIO + BIOS 模式设置 + VRAM 清除
hal_set_palette()        → 调色板（0=黑, 1=蓝, 7=白等）
fill_rect 全屏蓝底       → VRAM 初始蓝色背景
image_init("IMAGE.DAT")  → 图片归档加载
nb_init()                → NB 剧本引擎初始化（logo.nb 加载）
nb_process 循环          → NB 剧本解释器执行
for(;;)                  → idle 死循环
```

### 启动方式（固定）

- `AUTOEXEC.BAT` 启动（`engine.exe` 位于 AUTOEXEC 末行）
- **禁止使用** `INSTALL=` 方式（CONFIG.SYS 的 INSTALL= 会导致 NP2kai 黑屏）
- 所有项目入口统一为 `engine.exe`

### Sprite 对话框约束

- `layer_sprite_face()` **不得写入 y ≥ LAYER_DIALOG_Y (280) 的 VRAM 区域**。如需写入对话框区域（全身替换），必须用 `layer_sprite_replace()` 并主动调 `layer_dialog_refresh()`。
- `vram_blit_sprite()` 的 `clip_h` 参数（>0 时限定绘制行数）是保证此约束的架构级手段。新增 sprite blit 调用时必须传入正确的 `clip_h`。

### 游戏运行文件命名（8.3 强制）

**凡引擎运行期读取、注入 HDI 的文件（`projects/<game>/scene` 与 `projects/<game>/i18n` 源文件、`games/<game>` 部署产物、引擎启动帧文件等）必须满足 DOS 8.3 约束**：

- 文件名基名 ≤8 字符、扩展名 ≤3 字符；
- 同一目录下所有文件的 `to_dos_name()` 短名结果**互异**——杜绝截断同名的静默覆盖。

反例（本规则诞生的直接事故）：`system_chi.txt` 与 `system_cht.txt` 基名 10 字符，`to_dos_name` 双双截成 `SYSTEM_C.TXT`，HDI 注入后写者覆盖先写者，运行语言与幸存译文内容脱钩 → 简体字库渲染繁体文案，「開/載」占空位（R25 已改 `sys_<lang>.txt` 修复）。

**防呆**：`tools/naiz_img/inject_common._check_dos_collision()` 在根目录与子目录注入前整批校验，发现碰撞即 `RuntimeError` 硬失败（不得静默覆盖）；`tools/tests/test_dos_shortname.py` 对全部项目 i18n/scene 文件做 8.3 与短名互异回归。

**新增文件/改名的规则**：运行相关文件名一律直接取 8.3 安全基名（如 `sys_*`/`role_*`/`game_*`、`nbook*.nb`），不得依赖注入层截断来"擦边"。

### 变更规则

对以上四节（显示管线、初始化顺序、启动方式、游戏运行文件命名）的任何修改，必须先提问、得到明确许可后再执行。

## 十二、独立项目说明

naiz_midi / naiz_music 已作为独立项目移出到 `~/`。详见 `docs/B91-构建环境与参考速查.md §6`。

## 十三、Token 优化参考

- 完整函数索引与 Python 工具入口：`docs/B90-参考-函数索引.md`
- NB 脚本命令参考（唯一集中源）与关键常量：`docs/B92-NB脚本命令参考.md`
- 数据管线与格式参考：`docs/B92-NB脚本命令参考.md §3`、`docs/B04-工具链API参考.md`、`docs/B11-MAG图片加载与显示规范.md`
- 开发历史精炼总结（devdocs 00–67 历史存档替代索引）: `devdocs/0.1版开发文档总结.html`
- 错误排查：`docs/FAQ.md`
- 快速查找：`grep -n '^void \|^int \|^uint \|^static ' core/engine/*.c core/lib/*.c core/plat/*.c | grep '('`；NB dispatch 用 `grep -n 'cmd_table' core/engine/nb.c`
- 封装/拆分审计（**替代**逐个 grep 手查 public/static 与跨文件引用，单次扫描 39 源 + 36 头输出 A/B/C/D/E 五节报表）：
  `python -m tools.diag.symbol_audit`（A=static 候选，B=死导出，C=耦合/拆分视图，D=符号清单，E=拆分簇；`-s A,E` 只出指定节）
- 封装工作流：用户运行 `start.sh audit` → 审计日志存 `logs/symbol_audit_<时间戳>.log` 并同步输出终端 → AI 读取最新日志的 A/B/E 节 → 核实后执行封装/拆分
- **规则审计工作流**（§十七 固化）：用户运行 `start.sh fullaudit [--no-make]` → 6 步流水线（规则增量审计/`start.sh audit` 同款 `./start.sh fullaudit`/pytest/py_compile/`bash -n`/symbol_audit/make）整体复用 `tools.audit.audit` 引擎（sha256 增量，状态存 `audit_state.json`，文件哈希不变则 SKIP；扫描范围 `core/*/*.c` + `core/**/*.h` + `tools/**/*.py` + shell，头文件对 C13/C14 门控排除）与 `start.sh audit` 的 symbol_audit 步骤，仅 `--no-make` 跳过 make 节；全部通过后按 `pytest`/`py_compile`/`bash -n`/`symbol_audit`/`make` 顺序输出 `[✓]`。**symbol_audit 第 5 步带 `-s A,B --gate`**：A（未用 static 候选）/B（死导出）节任一输出即 exit 1 判失败（R30），`start.sh audit` 本色保持信息用途不带 gate。AI 修改源码后应主动运行 `./start.sh fullaudit` 验证无回归。AI 核验启发式候选后应主动 `--note REL:LINENO:VERDICT[:TEXT]` 登记到独立 `verify_notes.json`（带**行级**快照，被核行文本未变则无关编辑不 STALE；v1 整文件 sha8 快照兼容加载；单条也可用 `--note rel:line --verdict ok/fixed/todo`）；新代码审查用 `--since <git-ref>`（仅审计变更行，新增违规 exit 1，未变更文件保留既往记录）

### 变更后更新规约

每次修改涉及以下内容时，需同步更新对应文档：

- 增删改 C 函数 → 更新 `docs/B90-参考-函数索引.md`
- 新增/删除/修改 NB 命令 → 更新 `docs/B92-NB脚本命令参考.md`
- 新增/修改数据管线 → 更新 `docs/B92-NB脚本命令参考.md §3`
- 新增/移动 Python 工具 → 更新 `docs/B90-参考-函数索引.md`
- 新增/删除/修改构建环境/参考 → 更新 `docs/B91-构建环境与参考速查.md`
- **每轮 Bug 修复 / 功能演进完成 → 在根目录 `CHANGELOG.md` 的 `---` 分隔线下方第一条位置追加变更摘要条目**（含版本号、验证结果、`bump_version`），并同步 AGENTS.md 头部「当前版本」；R1 起全部历史均已迁入 `CHANGELOG.md`，AGENTS.md 不再承载历史摘要

## 十四、编码规约

### 输入循环
1. 入口 drain：`for(;;) { kbd_update(); … }` 前调 `kbd_drain_advance()`
2. 超时保护：忙等循环引用 `KBD_WAIT_MAX_ITER`
3. 语义查询：`kbd_is_pressed()`（非消耗）vs `kbd_is_down()`（消耗）
4. scene 切换：`nb_load()` 末用 `kbd_drain_advance()` + `kbd_ignore_frames = 2`

### 菜单 UI 渲染（两阶段绘制）
1. 入口全量绘制一次（`draw_rounded_emboss` 等昂贵原语只画一次），循环内只增量改文字颜色/指示符
2. 光标：`mouse_draw_cursor()` save/restore，禁止 `mouse_draw_cursor_ez()`
3. 全量重绘前调 `vblank_wait()`，重绘后调 `mouse_draw_cursor_force()`
4. 反例：循环内 `draw_rounded_emboss()` / `fill_rect(0,0,640,400,0)` / `slot_info()` 全量刷新
5. 参考：`nb_menu.c: menu_show()`、`nb.c: save_load_menu()`

### 系统界面 i18n（强制翻译）
1. 系统界面文字（按钮/标题/确认框/画廊/存档界面等**硬编码字符串**）一律以**英文为基准文案**，并必须经 `tr()` 渲染
2. 禁止硬编码英文直绘（`draw_text` / `draw_text_outlined` / `draw_title_large`）；例外仅限纯数字/格式串（`%d/%d`、`<` `>`、`CG %02d`）、语言自名、版本号
3. 新增 UI 字符串必须同步登记 `tools/naiz_conv/i18n_gen.py` 的 `SYSTEM_UI_KEYS`，否则 `i18n_gen` 重生成时被标 `# ORPHANED` 使译文失效
4. 必须为 `config.toml` `i18n.targets` 各语言在 `sys_<lang>.txt` 提供对应译文；空值视为未完成（运行时回退英文）
5. 含 `%d` 等格式串整句翻译（译文保留 `%d`），经 `snprintf(buf, tr(fmt), n)` 展开
6. 角色名与剧情文案的**原文基准遵循项目设定**（脚本原文 / `char_map` 规范名 / `source_lang`），其翻译照常经 `role_<lang>.txt` / `game_<lang>.txt` 提供——本节强制范围仅限**系统界面文字**（`sys_<lang>.txt`，8.3 安全基名）

### 对话框文字清除
- 标准方法：`layer_dialog_restore()`，禁止 `fill_rect` / `fill_rect_pattern` / `scene_draw_dialog()`
- 原理：快照 `dialog_snapshot[]` 按 `g_dialog_style` 恢复，无 ghost 残留

## 十五、Token 管理

- 对话超过 70% token 限制时需主动 compact

### 分析阶段
```
Output format: file:line — one-line description. No explanations, no code snippets.
```

### 验证阶段
```bash
make -C core && python -m py_compile tools/...file.py ...
```

## 十六、版本号管理

### 自增规则

- 版本格式 `X.Y.ZZZ`（如 `0.1.001`），ZZZ 为三位补零
- **自增时机**：每次 AI 修改 `.c` / `.h` / `.py` / `.nb` 等源代码文件后，需主动调用
  ```bash
  python -m tools.naiz_build.bump_version [game]
  ```
  一次调用即**作用于 `projects/` 下全部项目**：统一目标 = 所有项目当前版本的最大值 +1（`--minor` 则对最大值做 minor 归零），历史版本漂移在下次 bump 时自动自愈收敛到同一号（按行替换写回，保留全部 `#` 注释）。`[game]` 为可选兼容参数，仅校验该项目存在
- **手动编辑禁止**：`config.toml` 的 `version` 行由工具自动维护，禁止手动修改
- **所有项目版本同步**：`projects/` 下所有项目的版本号必须与引擎版本保持一致（`tools/tests/test_version_sync.py` 仓库不变量测试守护，fullaudit 的 pytest 步骤自动校验）；`bump_version` 一次调用即同步全部项目，无需逐个执行

### 编译带入

- `makegame.sh build <game>` 中 `build_game.py` 自动从 `config.toml` 读取 version
- 注入到 `settings.txt` 的 `version=` 行
- 引擎 `settings_load()` 解析后存入 `GameSettings`，`settings_get_version()` 供主菜单右上角显示
- 此环节已就绪，无需额外修改

## 十七、Bug 防复发规则（强制）

每次修改源代码文件（`.c` / `.h` / `.py` / `.sh`）后，必须按以下清单逐一检查。任何违反规则的情况必须修复才能提交。

### Bug 排查原则

发现 bug 时，先分析其**根因**（是越界/未初始化/类型错误/逻辑遗漏等），然后主动在**其他文件/模块**中搜索是否存在同一根因的同类型 bug。修复一个实例不等于根除，同类模式可能在代码库中反复出现。

### C 代码

| # | 规则 | 检查方法 | 反例 |
|---|------|----------|------|
| C1 | `malloc`/`calloc`/`realloc` 返回值必须检查 NULL | `grep -n 'malloc\|calloc\|realloc' *.c \| grep -v 'if.*== NULL\|if.*!= NULL\|if (!'` | `mag.c:219` 早期版本未检查 `calloc` |
| C2 | `fopen` 返回值必须检查，失败日志并 return | `grep -n 'fopen(' *.c` | `nb.c` 早期版本未检查 |
| C3 | `fread`/`fwrite`/`fgets` 返回值必须检查 | 同上 | `save.c` 早期版本需验证 |
| C4 | `strncpy` 后必须手动 NUL 终止 | `grep -n 'strncpy(' *.c \| grep -v 'buf\[sizeof'` | `save.c:239-242` 之前缺少 `buf[...] = '\0'` |
| C5 | `snprintf` 代替 `sprintf` | `grep -n 'sprintf(' \| grep -v 'snprintf'` | 历史代码中使用 `sprintf` |
| C6 | 数组下标/指针运算必须先验证边界 | 对照目标缓冲区大小检查所有下标 | `mag.c:301` 有符号溢出 |
| C7 | 结构体偏移量用 `offsetof` 而非硬编码 | `grep -n '^ *int.*skip\|^ *int.*off\|fseek.*[0-9]'` | `save.c:222` 使用 `sizeof` 计算而非 `offsetof` |
| C8 | 有符号整数加法前检查溢出 | 检查所有 `+` 运算，尤其是 `int + int` | `nb_vars.c:31` 有符号溢出 UB |
| C9 | `memcpy`/`memmove` 确保目标缓冲区足够 | 验证大小参数不超过目标 | `keyboard.c` 系列 |
| C10 | `switch` 必须有 `default` 分支 | `grep -n 'switch' \| awk ...` | `nb_commands.c:93` 缺少 default |
| C11 | `assert` 禁止使用（可能被 NDEBUG 禁用） | `grep -n 'assert('` | R4 中 `scene_layers.c`(→layer.c，现 layer_dialog.c/layer_sprite.c) assert 替换 |
| C12 | 函数无返回值时（`void` 函数）不能使用返回值 | 编译器警告 | — |
| C13 | `static` 函数如未使用需移除 | `grep -n '^static' *.c`，验证是否被调用 | R3-R4 移除了 4 个死函数 |
| C14 | OOM/fail 路径需有 `hal_log` 诊断 | 检查所有 error/return 前有日志 | `scene_layers.c:175`(→layer.c/layer_dialog.c) 之前无日志 |
| C15 | 文件操作 `fclose` 确保在每条提前 return 前 | 检查所有 `fopen` 后的 return | `save.c` 已修复 |
| C16 | `offsetof` 跳转距离需验证：读取位置 + skip = 目标字段 offset | 对照 struct 布局逐字段加算偏移 | `save.c:222` R6 中 `read_hdr` 多算了 4 字节 |
| C17 | `mouse_invalidate_cursor()` 前必须确保旧光标区域将被后续绘制完全覆盖；否则先用 `mouse_erase_cursor()` 显式擦除 | 检查所有 `invalidate` → `force_draw(新位置)` 模式中旧光标区域是否被覆盖 | `nb_save_dialog.c:56` R7 残影 bug — invalidate 后对话框局部重绘未覆盖旧光标 |
| C18 | 新增 shortcut/cache 路径时，必须逐一验证原慢路径的所有**外部副作用**（硬件状态、全局变量等）是否在快速路径中保留 | 对比新旧路径的每步操作，确认所有硬件写入/全局赋值在快路径中存在 | `image.c:175-178` R8 — cache 命中跳过 `image_set_palette()` 导致白底变黑 |
| C21 | `strcpy`/`strcat`/`gets` 禁止（无界拷贝）——用 `snprintf`/`strncpy` + 显式 NUL | `grep -n 'strcpy\|strcat\|gets'` | 工具化后 AUTO 黑名单（仓库现存 0 违规） |
| C22 | 有符号局部变量取负（`-v`/`0 - v`）可能越过 INT_MIN → 用 `(v == INT_MIN) ? INT_MIN : -v` 守卫 | AUTO 规则（识别函数局部声明，含 `-arr[idx]` 下标形式，排除赋值/下标/函数调用差值） | `nb_question.c:150/185` R8 — `-opt_deltas[hit]` 为 R7 同型漏网，已修补 |
| C23 | 同路径双重 free 禁止（两次 free 之间未置 NULL 且未重新 malloc，且无 return/break/continue/goto/exit 分隔成互斥路径） | AUTO 规则（互斥错误路径模式依法豁免） | R8 新增；cjk.c/font.c/mag.c "每错误路径各 free+return" 属合法豁免 |
| C24 | `memcpy` 尺寸与被拷目标字节数组维度交叉核对（字面量/`sizeof` 拷贝 vs `char a[8]` 声明） | AUTO 规则（RE_BYTE_ARRAY_DECL 匹配 char/uint8_t/int8_t/BYTE/byte 数组字面量维度；指针目标仍由 C9 启发式兜底） | R8 新增 |
| C25 | use-after-free：free 之后到块终止符（`}`/return/break/continue/goto/exit）之间若解引用（`->`/`[`/`(`）且未重赋值即违规 | HEUR 规则 | R8 新增 |
| C26 | 所有权分离 free：`if (guard) free(x->field);` 之后同路径无条件 `free(x)`，即 guard 逃逸导致 base 在错误所有权下释放 | HEUR 规则（成员 free + 未防护 base free） | R15 新增（R13 mag_release 池 struct 逃逸） |
| C27 | 计数派生负下标：`arr[count - K]` 之前的守卫须覆盖 `count < K`（`if (argc < 1)` / `argc == 0`），缺则越界读 | HEUR 规则 | R15 新增（R13 `argv[argc-1]`） |
| C28 | 行跨距读无高度边界：函数含 `width` 类跨距乘法（如 `row * img_w`）但作用域内无任何 height 提及（参/局部/宏）→ 行索引未对图像自身高度夹逼 | HEUR 规则（只认小写 height 名，`LAYER_DIALOG_H` 等全大写宏不误判） | R15 新增（R14 cine 对话框 OOB） |
| C29 | 结构体指针仅起始越界检查：guarded `(T *)(buf + off)` 的守卫只有 `off > size`、缺 `off + sizeof(T)` 项，struct 尾部可溢出 | HEUR 规则 | R15 新增（R13/R14 mag `off_img`） |
| C32 | `strncpy()` 仅允许在 `core/lib/strutil.c` 内使用（R29 收口后），其余文件一律 `str_copy()` | AUTO 规则 | R29 后续新增（str_copy 单一事实源回归守卫） |
| C33 | 相邻 `layer_dialog_show();`+`dialog_layer_blit();` 对（`layer_dialog_clear()` 函数体内除外）→ 改用 `layer_dialog_clear()` | HEUR 规则 | R29 后续新增（干净盒惯用式回归守卫） |
| C34 | 同一文件内重复的静态数组初始化表（内容归一化完全相同，≥2 处）→ 并单一事实源 | HEUR 规则 | R29 后续新增（slot_y/slot_ys 类回归守卫） |
| C35 | 同一文件内常量算术表达式重复（≥1 操作数为宏、≥3 处）→ 建议具名宏/常量 | HEUR 规则 | R29 后续新增（LAYER_DIALOG_CONTENT_* 类回归守卫） |

### Python 代码

| # | 规则 | 检查方法 | 反例 |
|---|------|----------|------|
| P1 | `except:` 必须指定异常类型 | `grep -n 'except\s*:' \| grep -v 'except.*as\|except Exception\|except OSError'` | 禁止裸 except |
| P2 | `open()` 必须使用 `with` 语句 | `grep -n "open("` | 早期代码有裸 open |
| P3 | `assert` 替换为 `if ...: raise RuntimeError()` | `grep -n 'assert '` | `gen_cjk_font.py:149` R4 修复 |
| P4 | `struct.pack_into`/`struct.unpack_from` 需验证偏移+大小不超界 | 检查 offset + size 不超过 buffer | `fat.py:96-104` off-by-one |
| P5 | 二进制数据读取后需验证长度 | 检查 read 后数据长度是否符合预期 | R2 中 fat.py 多次修复 |
| P6 | 文件路径用 `Path` 对象而非字符串拼接 | — | `build_game.py:26` 硬编码路径 |
| P7 | `subprocess.Popen`/`run` 优先用 list 形式，避免 `shell=True` | `grep -n 'shell=True\|sh -c'` | `env_build.py` f-string 注入修复 |
| P8 | 避免在函数体内 import（延迟 import 需在顶部） | 检查 import 语句位置 | `inject_common.py:294` 不在顶部的 import |
| P9 | 可变默认参数禁止（`def f(x=[])`） | `grep -n 'def.*=\[\]\|def.*={}'` | — |
| P10 | `sys.exit(string)` 需改为 `print(...); sys.exit(1)` | `grep -n 'sys.exit(' \| grep -v 'sys.exit(0)\|sys.exit(1)'` | `mag_convert.py:500` |
| P11 | 可变状态（如 `next_free`）跨函数传递时需返回更新值或用可变容器 | 检查所有 int/str 按值传递后在调用者是否被更新 | `fat_table.py:38` `alloc_next_free` 必须返回更新游标（R6 曾修复 `make_base_clean.py` 中 `next_free` 未传播的同类 bug） |
| P14 | 禁止 `eval`/`exec`/`os.system`/`os.popen`（动态代码/子 shell 转义）；`subprocess.Popen` 用 list argv 属合法 | `grep -n 'eval(\|exec(\|os.system(\|os.popen('`（排除 venv） | 工具化后 AUTO 黑名单（仓库现存 0 违规） |

### Shell 脚本

| # | 规则 | 检查方法 | 反例 |
|---|------|----------|------|
| S1 | 变量扩展全部用 `"$var"` 引用 | `grep -n '\$' *.sh \| grep -v '"\$'` | `makegame.sh:87` 未引用的 `$SERIAL` |
| S2 | 禁止 `eval` | `grep -n 'eval '` | `detect_watcom.sh:16` R5 修复 |
| S3 | 用 `command -v` 替代 `which` | `grep -n '\bwhich\b'` | `makegame.sh:33` R5 修复 |
| S4 | 用 `$(cd "$(dirname "$0")" && pwd)` 替代 `readlink -f` | `grep -n 'readlink'` | `build.sh:3` R5 修复 |
| S5 | `shift` 前确保 `$# > 0` | 检查 shift 场景 | `makegame.sh:50` 脆弱的 shift |
| S6 | 循环多字符变量时用数组而非未引用字符串 | 检查 for 循环中的未引用变量 | `detect_watcom.sh:15` R5 修复 |
| S7 | 可选 flag 用数组条件追加，避免空串位置参数 | `grep -n '"[^"]*\$[A-Z][^"]*"' *.sh \| grep -v '\[\[ \|if \|echo'` | `makegame.sh:87` R6 中 `$SERIAL` 空串被 argparse 拒绝 |

### 提交前自检命令

```bash
# C 编译
make -C core 2>&1 | grep -E 'Error|Warning'

# Python 语法
for f in $(find tools -name '*.py'); do python -m py_compile "$f" 2>&1 | grep -v 'OK'; done

# Shell 检查
shellcheck core/*.sh makegame.sh start.sh 2>&1 | grep -v 'SC'
```

### 已弃用但保留的代码

以下代码为**有意保留**的废弃代码（B5 拆分时归档 + 全项目死文件审计时确认，非遗漏）。日后代码审查中 **C13/P11 等"未使用需移除"规则不适用于它们，无需再检查是否删除**：

| 位置 | 说明 |
|------|------|
| `tools/env_setup/env_np2kai.py::cmd_build_i286` | 废弃的 i286 核心编译命令（仅 16-bit 保护模式，无法运行 32-bit DOS/4GW 引擎）。无 start.sh 入口，install_env.py 仍保留该 CLI 子命令以兼容历史用法 |
| `tools/env_setup/env_toolchains.py::_install_gcc_ia16_deepin` | 无调用。deepin 发行版专用 gcc-ia16 安装路径，暂不维护 |
| `core/plat/vram.c` | 被 `core/Makefile` `filter-out` 排除、`vram_init()`/`vram_plane()` 无任何调用方。pc98.h 注明是有意保留的 opt-in 参考实现（`VRAM_DPMI_MAP` 映射方案），供未来 DPMI VRAM 直写实验参考。删除需经用户确认 |
| `tools/naiz_screendig/`（6 文件） | 独立手工截图诊断工具（`python -m tools.naiz_screendig`），无自动化入口，仅 docs 引用；功能与 `naiz_lib/np2kai_capture` 重叠但被 docs 列为 P0 截图工具，保留 |
| `tools/diag/read_fat16.py` | FAT16 手工诊断工具（复用 `naiz_img`），仅 `docs/B90` 索引，无脚本调用；手工排查基座 HDI 时使用，保留 |
