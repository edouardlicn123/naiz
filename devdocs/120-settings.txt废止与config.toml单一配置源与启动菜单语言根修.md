# 120 — settings.txt 废止与 config.toml 单一配置源（含启动菜单语言失效根修）

> **状态**：完结（实现 + 仓库级验证 + 实机 A/B 三轮全绿；**但 §6.3 记载一个本轮未覆盖的内容缺口**：`demo-a2` 中日韩剧本文本与角色名基本未翻译，故「繁体中文剧情」仍不可见——那是内容工作，不是本轮的代码缺陷）
> **日期**：2026-10-02
> **起因**：实机反馈「启动菜单选繁体中文，进入正式游戏仍是英语」。
> **接替/订正**：`devdocs/118-玩家偏好分家与音频开关音量设置场景.md`（§6.1 归属表 + §三 键集失效，追加 ERRATA）、`devdocs/119-用户偏好分家实装订正与设计门控与规格双源守恒.md`（§二 行号真值表因本次改名整体失效，追加 ERRATA）
> **关联版本**：`0.3.014`
> **根因类别**：① 实现缺陷（访问器 getter/setter 结构体不对称）② 结构性问题（项目配置经由运行时文件传递，而该文件由 build 无条件覆盖，且同一键名横跨两个归属相反的文件）

> ### 📌 本文的两套行号坐标（阅读前必读）
>
> 本次改动把 `settings.c/h` 改名为 `prefs.c/h`、`settings_menu.c/h` 改名为 `bootmenu.c/h`，因此文中出现**两种坐标系**：
>
> | 记法 | 含义 | 可解析性 |
> |---|---|---|
> | §二、§三、§2.4 叙述根因时的 `settings.c:62` / `settings_menu.c:105` | **0.3.013 重命名前的历史坐标**，用于精确指认缺陷现场，**故意不改** | 指向的文件已不存在，**不可**按现行行号校验 |
> | §九 真值表中的 `prefs.c:181` / `bootmenu.c:105` 等 | **0.3.014 现行坐标** | 与当前代码一致，由 `tools/tests/test_devdoc_refs.py` 持续断言 |
>
> 阅读根因请看历史坐标；核对当前实现请以 §九 为准。

---

## 一、症状

开机菜单（`settings_menu_run()`，ASCII 纯文本，运行于翻译表与 CJK 字库之前）选中「繁體中文」并确认进入游戏后：

- 界面全部英文；
- 串口日志 `settings_menu: selected lang=cht (Chinese (TC))` **正常打印**——选择确实被接收了；
- 重启后再进开机菜单，Language 行**又显示回 English**；
- 游戏内 `startsetting` 改语言后界面不变。

「选了没生效」+「重启后连菜单显示都回退」，两个症状叠加，指向「值写下去了但没被读回来」。

## 二、判定过程

### 2.1 先排除译文与字库缺失

| 检查 | 结果 |
|---|---|
| `games/<game>/i18n/sys_cht.txt` 等三份译文 | 全部存在（49 / 3 / 37 行） |
| `games/<game>/CJK_CHT.DAT` | 存在 |
| `sys_cht.txt` 是否空 | 非空 |

→ 译文侧无缺失。若语言真的切到 `cht`，`tr_init("cht")` 会拿到非空表。**排除**。

### 2.2 顺藤摸到访问器不对称

| 访问器 | 实际读写 |
|---|---|
| `settings_set_lang()`（`settings.c:308-312`） | 写 **`g_pref.lang`**（玩家偏好 / USER.CFG） |
| `settings_get_lang()`（`settings.c:62-65`） | 读 **`g_settings.lang`**（项目默认 / settings.txt） |

两者永不相遇。后果链：

- `main.c:94` `settings_save()` 把 `lang=cht` **正确写进** USER.CFG —— 但没有任何代码读它；
- `main.c:97` `cjk_load_for_lang(settings_get_lang())` → `eng`；
- `nb.c:171` `nb_set_lang(settings_get_lang())` → `tr_init("eng")`；
- `settings_menu.c:105` `find_lang_index()` 也读 `g_settings.lang` → **二次开机菜单显示回退**；
- `nb_mainmenu.c:116` `strcmp(old_lang, settings_get_lang())` 恒等 → 游戏内 `startsetting` 的 `nb_set_lang()` 永不触发。

### 2.3 排查「第二次 settings_load 是否是独立缺陷」

`nb_init()`（`nb.c:166`）会**再调一次** `settings_load()`，而 `settings_load()` 开头 `memset(&g_pref, 0, ...)`（`settings.c:192`）会清掉开机菜单刚写入内存的 `g_pref.lang`。乍看是第二个缺陷。

**但不是**：`main.c:94` 已先 `settings_save()` 落盘，重载时从 USER.CFG 读回同一个值。**只要修 getter，boot 路径即通**；这一行 `memset` 无需改动。（此处特意记下否决理由，避免后人手贱「顺手优化」成第二处 load 去重而引入首次启动丢选择的回归。）

### 2.4 同根因横向排查

`devdocs/118` §…（原 118 记载）已记录过**完全同型**的缺陷：`audio_get_*` 的 getter 当时读 `g_pref` 而非 `audio.c` 的真实状态。本次逐一核对 `settings.c` 全部访问器：

| 键 | getter 读 | setter 写 | 对称 |
|---|---|---|---|
| `version` / `blackletter_*` | `g_settings` | 无 setter | ✅ |
| `text_speed` | `g_pref.text_speed` | `g_pref.text_speed` | ✅ |
| `bgm` / `snd` / `vc` / `bgm_vol` / `pcm_vol` | 转发 `audio_get_*()` | 先应用再记入 `g_pref` | ✅ |
| **`lang`** | **`g_settings.lang`** | **`g_pref.lang`** | ❌ **唯一不对称** |

且 `grep settings_get_lang tools/tests/` **无任何命中** —— 没有任何测试断言 getter 的返回路径，故测试全绿也掩盖不了。这就是为什么必须补防呆。

## 三、根因

**双层。**

### 3.1 直接根因（实现缺陷）

0.3.011（devdoc 118）把玩家偏好从 `settings.txt` 分家到 `USER.CFG` 时，`settings_set_lang()` 迁到了 `g_pref`，**`settings_get_lang()` 漏改**，仍读 `g_settings.lang`。getter/setter 分家而访问器没跟上，且无测试覆盖。

### 3.2 结构根因（为什么这个缺陷会发生，且不容易被发现）

`lang` 是**唯一一个同时存在于两个文件的键**：`settings.txt` 里是「项目默认」，`USER.CFG` 里是「玩家选择」。

后果有三：

1. **setter 与 getter 各自指向一个「看起来完全合理」的字段**——写 `g_pref.lang` 对、读 `g_settings.lang` 也对，代码审查无从察觉；
2. **`test_user_cfg_settings.py` 明确豁免了 `lang`**（`PLAYER_KEYS - {"lang"}`），把同名双份键**固化成了受保护的既定设计**；
3. 玩家偏好与项目配置**归属相反**却共用一个键名，语义只存在于人的脑子里。

### 3.3 更外层的结构问题：项目配置根本不该经由运行时文件传递

`settings.txt` 由 build **无条件覆盖**，而其中 5 个键（`dlgstyle` `btnstyle` `version` `blacktitle` `blackdialog`）**没有任何运行时 setter**——它们是构建期常量，却被放进一个运行期解析的文件里，再由 build 从 `config.toml` 注入回去：

```
config.toml [project] version
  → build_game.py 注入 settings.txt
  → 运行时 fopen("settings.txt") 解析
  → settings_get_version()
```

**同一份配置在构建期与运行期各走一遍，中间隔一个文本文件**。而 `[transition]` 早已走对了路（`config.toml` → `export_config.py` → `nb_config.h` → 编译进 `engine.exe`），`projects/demo-a2/config.toml` 里甚至白纸黑字写着「构建时编译进引擎（无需 settings.txt）」——**迁移做了一半就停了**。

## 四、设计

### 4.1 目标数据流

```
config.toml  ← 唯一项目配置源（人手编辑 / bump_version）
   [project]    version
   [i18n]       source_lang | targets | default_lang
   [transition] type | frames              （已迁移，本次不动）
   [dialog]     style                      （本次迁入）
   [button]     style                      （本次迁入）
   [blackletter] title | dialog            （本次迁入）
        ↓ export_config.py（沿用 c_header.py 的 escape/preamble + naiz_lib.langdefs 校验）
   core/engine/nb_config.h  —— NAIZ_* 宏
        ↓ compile_engine()   ← build_game.py 步骤 2：导出头在 `:496` 编译之前，顺序已正确
   engine.exe

USER.CFG  ← 唯一运行时可写文件（7 键玩家偏好，build 永不触碰）
settings.txt —— 彻底消失
```

### 4.2 三条关键决策与理由

| 决策 | 理由 |
|---|---|
| **删掉 settings.txt，项目配置全部走 `nb_config.h`** | 项目配置是**构建期常量**，放进运行期文件没有语义；且该文件在 build 的无条件覆盖路径上（devdoc 118 的原始事故现场）。`[transition]` 已是先例 |
| **只留 USER.CFG 一个 `lang` 键** | 消除同名双份键这个「getter/setter 可以各自指向不同字段而看起来都合理」的温床（§3.2）。出厂默认改用**不同键名**（config.toml 字段 `default_lang` → 宏 `NAIZ_DEFAULT_LANG`），由 config.toml 单一持有 |
| **`settings.c/h` → `prefs.c/h`，符号 `settings_*` → `prefs_*`** | 瘦身后该文件只管 USER.CFG，`settings` 这个名字已不贴切；保留 `settings_` 前缀等于把「命名/归属不一致」这个本次 bug 的深层成因留在原地（AGENTS §九.7 一致性）。开机菜单 `settings_menu.c/h` → `bootmenu.c/h`，`settings_menu_run()` → `bootmenu_run()`（它属开机菜单 UI，不属偏好存储，改成 `prefs_run()` 是错的） |

### 4.3 已否决的替代方案（及否决理由）

| 备选 | 否决理由 |
|---|---|
| **把 settings.txt 的键全并进 USER.CFG** | `version` 由 `config.toml` 注入却在 UI 有**两处**显示（`nb_menu.c:273` 主菜单、`settings_menu.c:162` 开机画面）。USER.CFG 不被 build 写 → `bump_version` 后界面永远显示首次启动时的旧号，**直接破坏 AGENTS §十六 版本号管理**。`blacktitle`/`blackdialog` 同理会永久脱离 `config.toml`（改配置永久失效且无报错 = §九.6 静默失败）。要保住这两点就必须让 build 写 USER.CFG——**AGENTS §十一明令禁止**，且直接撞守卫 `test_build_never_writes_user_cfg` |
| **只留 USER.CFG 单份、丢掉出厂默认语言能力** | 项目将无法「出厂即非英语」。`[i18n] default_lang` 正是给这个能力一个家（config.toml 单一持有） |
| **保留双份键、只加守卫测试** | 能防回归，但把「同名双份键」这个结构性温床留着。本次已选择连温床一起拆 |
| **`[project] title` 顺带导出为 `NAIZ_TITLE`** | grep 确认它**当前完全没有送达运行时**（无 `NAIZ_TITLE`，引擎内也无硬编码），主菜单标题全来自 `.nb` 的 `tr()`。导出它只会把「配置存在但无消费者」固化 |
| **`dlgstyle`/`btnstyle` 并入 `[project]` 或单开 `[style]`** | 选拆 `[dialog]` + `[button]`：两者语义本就不同（对话框背景样式 / 按钮配色方案），合成一节反而模糊 |

### 4.4 已知并接受的行为

**玩家在开机菜单确认过语言后，`config.toml` 的 `default_lang` 不再影响该玩家**（`lang` 是玩家真实选择，与 `version` 性质不同），故 `default_lang` 的变更只对**新玩家**生效。这不是缺陷，是「玩家偏好优先」的正确表现。

## 五、实现清单

> 待实现后回填精确行号（§十：行号会随实现位移，写于改动之前的行号对当时成立）。

### 5.1 工具层

- `tools/naiz_build/export_config.py` — 新增 6 个宏：`NAIZ_VERSION`、`NAIZ_DLGSTYLE`、`NAIZ_BTNSTYLE`、`NAIZ_BLACKLETTER_TITLE`、`NAIZ_BLACKLETTER_DIALOG`、`NAIZ_DEFAULT_LANG`；沿用既有 `NAIZ_TRANSITION_*` 范式与 `c_header.escape()`；`default_lang` 校验 ∈ `naiz_lib.langdefs.LANG_CODE_SET` 且 ∈ `{source_lang} ∪ targets`，越界 ERROR（**不得降级为 WARN**）
- `projects/demo-a2/config.toml` — 新增 `[dialog] style` / `[button] style` / `[i18n] default_lang`（原 `scene/settings.txt` 的编码说明注释一并迁入）
- `projects/animatest/config.toml` — 同上（缺省值）
- `tools/naiz_build/build_game.py` — 删除 settings.txt 部署块与 config.toml→settings.txt inject 块
- 删除 `projects/demo-a2/scene/settings.txt`

### 5.2 引擎层

- `core/engine/settings.c/h` → `core/engine/prefs.c/h`（含 `SETTINGS_*` → `PREFS_*`、`settings_get/set/load/save_*` → `prefs_*`、`g_settings`/`GameSettings`/`SETTINGS_VERSION_MAX` 删除）
- `prefs.c` — 删除 settings.txt 解析段；项目常量改读 `NAIZ_*`；`prefs_get_lang()` 读 `g_pref.lang`（**根修**）
- `core/engine/settings_menu.c/h` → `core/engine/bootmenu.c/h`（`settings_menu_run` → `bootmenu_run`）
- 9 处 `#include "settings.h"` → `"prefs.h"`；删除 `prefs.h` 与 `bootmenu.h` 对 `bootmenu_run()` 的重复声明
- `core/Makefile` **无需改动**（`ENG_SRCS = $(wildcard engine/*.c)`）
- 注释订正：`main.c` 文件头、`nb.h` 文件头、`nb_setting.c` 文件头

### 5.3 防呆测试

- 作废：`test_user_cfg_settings.py` 的 settings.txt 部署断言与 `test_settings_txt_has_no_player_keys`、`PLAYER_KEYS - {"lang"}` 豁免；`test_audio_settings_invariants.py` 的双文件读取顺序断言与 project/player 分块
- 新增反向守卫：`build_game.py` 中旧部署/注入写法（`scene" / "settings.txt"`、`safe_copy2(settings_src`、`settings_dst`、`inject = {`）不得复现，且 `stale_settings.unlink()` 必须存在（**只许剪除，不许写**）；`projects/*/scene/settings.txt` 与已部署 `games/*/settings.txt` 必须不存在；`export_config.py` 必须导出全部 6 个宏
- **根修守卫**：`prefs_get_lang` 与 `prefs_set_lang` 函数体必须引用同一 struct 成员（同一 class 的缺陷 devdoc 118 已犯过一次，不许犯第二次）
- 重指：`test_devdoc_refs.py` 全部 `("settings.c"/"settings.h", N)` → `("prefs.c"/"prefs.h", N)` 并重校；`("build_game.py", 320)` 删除

## 六、验证

### 6.1 静态与仓库级

| 项 | 结果 |
|---|---|
| `make -C core` + `core/*.err` 全空 | 0 errors, 0 warnings（**须查 `.err`，见 §7.6**） |
| `pytest tools/tests/` | **604 passed, 1 skipped**（含 c46 新增 i18n/字库/版本守卫） |
| `./start.sh fullaudit --no-make` | 7 步全 `[✓]`（规则增量 / pytest / nb_validator / py_compile / bash -n / symbol_audit `--gate`） |
| `export_config.py` 负例 | `default_lang` 无译文、非法语言码 `zh`、`button.style=9` 均 ERROR + exit 1 |
| `./makegame.sh build demo-a2 && make demo-a2` | 部署树**无 `settings.txt`**；`nb_config.h` 为 `NAIZ_VERSION "0.3.014"` / `NAIZ_DLGSTYLE 5` / `NAIZ_BTNSTYLE 2` / `NAIZ_DEFAULT_LANG "eng"` |

**守卫自证**（AGENTS §九.6：假通过比失败更危险）：把 `prefs_get_lang()` 改回读另一个 struct 成员后，`test_audio_settings_invariants.py` 立即 2 red —— 守卫确实在测目标物。

### 6.2 实机（NP2kai + 串口 + XTEST）

`np2kai_ab.py` 原先**无法对启动期标记下断言**：`--target` / `--forbid` 都从 `--advance-to` 的匹配结束处起算，而语言标记在 `nb_init start` 之前发出，落在窗口之外；`--clicks 0` 又必然触发 `INPUT_NOT_SAMPLED`（§八 五禁之四：没发过输入就不该有判定）。故新增 `--boot-expect` / `--boot-forbid` / `--boot-only`（启动期断言，跳过 3–6 阶段），并在 `nb_set_lang()` 加上确定性标记（`prefs_get_lang()` 在真实游戏路径上的**唯一**消费者）。

| 轮次 | 前提 | 串口日志 | 判定 |
|---|---|---|---|
| A（getter 路径） | `USER.CFG` 预置 `lang=cht` | `bootmenu: enter (default lang=cht)` → `nb_set_lang lang='cht'` | **PASS**，exit 0 |
| B（setter 路径） | 无 `USER.CFG`，菜单内 Right×3 选 `cht` | `enter (default lang=eng)` → `selected lang=Chinese (TC) (cht)` → `nb_set_lang lang='cht'` | **PASS**，exit 0 |
| C（**反向对照**） | 故意把 getter 改回读另一份 | `enter (default lang=eng)` → `nb_set_lang lang='eng'` | **BUG_SIGNATURE_PRESENT**，exit 1 |

C 轮复现的正是原始症状（`USER.CFG` 写着 `cht`，菜单却显示 `eng`），证明 A/B 两轮不是恒真断言。

顺带修掉 `np2kai_ab.py` 两个真实缺陷：`--forbid` 声明为可选却无条件传给 `_wait_for`，省略时 `TypeError` 直接崩掉整个探针；`_report` 在 `--boot-only` 下格式化 `None` 正则会再崩一次。

### 6.3 ⚠ 未被本次修复覆盖的问题：`demo-a2` 的中日韩剧本文本根本没翻

**本轮修的是「语言选择不生效」，不是「没有译文」。** 二者是独立缺陷，A/B 全 PASS 之后仍会看到英文剧情：

| 文件 | 总键数 | 译文为空 |
|---|---|---|
| `game_jpn.txt` / `game_chi.txt` / `game_cht.txt` | 37 | **36** |
| `role_jpn.txt` / `role_chi.txt` / `role_cht.txt` | 3 | **3** |
| `game_kor.txt` | 37 | 12 |
| `sys_*.txt`（系统界面） | 49 | 0（已全译） |

`tr()` 对空译文的处理是**回落源串**（`core/lib/tr.c:168`，`break` 处注释即 `empty value = untranslated, fall back to source`），所以修好配置后：开机菜单与设置界面**确实是繁体中文**，但**剧情台词与角色名仍是英文**。

**结论**：0.3.014 交付的是「语言选择生效」+「配置单一源」；「繁体中文剧本文本」是**内容缺口**，需要单独补 `projects/demo-a2/i18n/game_cht.txt` 等文件。**在补齐之前，用户看到的现象只是从「菜单也是英文」变成「菜单中文、剧情英文」，不能算原问题彻底解决。**

## 七、踩坑清单

1. **不要在开机菜单之后再去「优化」第二次 `settings_load()`**（`nb.c:166`）。它的 `memset(&g_pref)` 看着像 bug，实际被 `main.c:94` 的落盘顺序救了；去掉它或调换顺序会引入「首次启动丢选择」。
2. **`test_devdoc_refs.py` 的 `STALE_QUOTED_REFS` 白名单里存着 `settings.c:80` 这类「指向空行」的变异目标**（devdoc 119 §五 的设计：故意指向错值以证明 118 已漂移）。改名后这些条目必须一并重指到 `prefs.c`，**且不能「顺手修正」它们指向的行**——它们存在的意义就是记录「118/119 的行号已漂移」这个事实。
3. **devdoc 119 §二的行号真值表整体建立在 `settings.c` 上**，本次改名使其全部失效 → 已按 §十 对 119 追加 ERRATA。真值表的替代品在本文件 §九。
4. **`[project] title` 是个「看起来该生效其实完全没生效」的字段**，grep 时容易误以为已被导出。
5. **wcl386 的诊断不在 stdout，而在 `core/<unit>.err`。** 本轮一度用 `make -C core 2>&1 | grep -ciE 'error|warning'` 判「0 错 0 警」并写进本节——**该构建实际带着 `W131: No prototype found for 'bootmenu_run'`**（`nb_mainmenu.c` 调用 `bootmenu_run()` 却缺 `bootmenu.h`，是本轮改名造成的；改名前它从别处拿到了原型，改名后原型丢了）。stdout 只有命令行，grep 必然输出 0，等于**伪造了本项唯一要证明的东西**。正确判据是 `find core -maxdepth 1 -name '*.err' -size +0`（应无输出），已写入 AGENTS.md §三与 §十七自检命令，并新增 `tools/tests/test_build_diagnostics.py` 常态化守卫（同时断言 `engine.exe` 不比源文件旧，避免「压根没编译」导致守卫空转）。**与 §八 五禁之一同源：把没测到的东西当成测过了。**
6. **改引擎后只 `build` 不 `make` 会跑旧引擎，而旧引擎的日志一切正常**（AGENTS §八 五禁之二）。本类改动的验收点恰好在 `engine.exe` 里（version 来自编译期宏），只 build 的 HDI 会显示旧版本号——这次会「假通过」得特别有说服力。5. **wcl386 的诊断不在 stdout，而在 `core/<unit>.err`。** 本轮一度用 `make -C core 2>&1 | grep -ciE 'error|warning'` 判「0 错 0 警」并写进本节——**该构建实际带着 `W131: No prototype found for 'bootmenu_run'`**（`nb_mainmenu.c` 调用 `bootmenu_run()` 却缺 `bootmenu.h`，是本轮改名造成的）。stdout 只有命令行，grep 必然输出 0，等于**伪造了本项唯一要证明的东西**。正确判据是 `find core -maxdepth 1 -name '*.err' -size +0`（应无输出），已写入 AGENTS.md §三与 §十七自检命令，并新增 `tools/tests/test_build_diagnostics.py` 常态化守卫（同时断言 `engine.exe` 不比源文件旧，避免「没编译」导致守卫空转）。**这与 §8 五禁之一同源：把没测到的东西当成测过了。**

## 八、文档订正（§十 四步）

| 步 | 对象 | 内容 |
|---|---|---|
| 1 | devdoc 118 | 追加 `⚠ ERRATA（0.3.014）`：§6.1 归属表「以及 `lang` 的项目默认」与 §三 `:60` 键集已失效；本文件/符号改名 |
| 1 | devdoc 119 | 追加 `⚠ ERRATA（0.3.014）`：§二 行号真值表因改名整体失效 |
| 2 | 本文件 | 承载订正后的完整记录 |
| 3 | `CHANGELOG.md` | `c45` 条目 + 订正标记 + 版本索引首行 |
| 4 | `AGENTS.md` §十一 + `docs/B91` §2 + `docs/B90` | 就地订正（`settings.txt` 行删除、改述 config.toml 单一源） |
## 九、行号真值表（0.3.014 现行坐标）

> 本文 §二/§三 的历史坐标已随改名作废；此表为**唯一现行真值源**，由
> `tools/tests/test_devdoc_refs.py` 逐行断言「该行非空且含所声称的符号」。

### 9.1 引擎层

| 声称位置 | 该行内容 | 符号 |
|---|---|---|
| `core/engine/prefs.c:57` | `const char *prefs_get_lang(void)` | 玩家语言 getter（读 `g_pref.lang`，空则 `NAIZ_DEFAULT_LANG`） |
| `core/engine/prefs.c:269` | `void prefs_set_lang(const char *lang)` | setter，**与上一行同源**（根修点） |
| `core/engine/prefs.c:181` | `int prefs_load(void)` | 载入入口，`memset(&g_pref, 0, ...)` 后只解析 `USER.CFG` |
| `core/engine/prefs.c:195` | `f = fopen("USER.CFG", "r")` | 读取 |
| `core/engine/prefs.c:242` | `int prefs_save(void)` | 保存入口 |
| `core/engine/prefs.c:244` | `FILE *f = fopen("USER.CFG", "w")` | **全系统唯一的运行时写入点** |
| `core/engine/prefs.c:187` | `g_pref.text_speed = TEXT_SPEED_DEFAULT;` | 缺文件时的出厂缺省 |
| `core/engine/prefs.c:33` | `"Instant", "16/s", ...` | 速度梯标签 |
| `core/engine/prefs.h:75` | `const char *prefs_get_version(void)` | 版本走 `NAIZ_VERSION` 编译期宏 |
| `core/engine/bootmenu.c:103` | `static int find_lang_index(void)` | 回退到 `NAIZ_DEFAULT_LANG`（原读 `g_settings.lang`） |
| `core/engine/bootmenu.c:200` | `void bootmenu_run(void)` | 开机菜单主体 |
| `core/engine/bootmenu.c:286` | `prefs_set_lang(LANG_CODES[lang_idx]);` | 玩家选择的唯一写入点 |
| `core/engine/main.c:94` | `prefs_save()` | 菜单选择先落盘，再加载 CJK |
| `core/engine/main.c:105` | `cjk_load_for_lang(prefs_get_lang())` | 按生效语言加载 CJK 字库 |
| `core/engine/nb.c:171` | `nb_set_lang(prefs_get_lang())` | 运行时消费点 |
| `core/engine/nb.c:337` | `NB_DEBUG("[LANG] nb_set_lang lang='%s'\r\n", lang);` | **实机探针断言点**：`prefs_get_lang()` 在真实游戏路径上的唯一消费者 |
| `core/engine/main.c:101` | `hal_logf("[LANG] boot effective lang='%s' default='%s'\r\n", ...)` | 开机菜单决定的确定性标记 |
| `core/engine/nb_mainmenu.c:117` | `strcmp(old_lang, prefs_get_lang())` | 游戏内改语言的同步判据 |
| `core/engine/nb_menu.c:273` | `draw_text(prefs_get_version(), ...)` | 主菜单版本号 |

### 9.2 工具层

| 声称位置 | 该行内容 | 符号 |
|---|---|---|
| `tools/naiz_build/build_game.py:325` | `stale_settings.unlink()` | 剪除部署树里的死文件 |
| `tools/naiz_build/build_game.py:466` | `[... export_config.py ...]` | 导出头 |
| `tools/naiz_build/build_game.py:470` | `compile_engine()` | **导出头必须先于编译**（顺序即不变量） |
