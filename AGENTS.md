# Naiz — AI 编程规则

> **当前版本**: `0.2.114`（`projects/demo-a2/config.toml`）
>
> **Bug 修复状态**: 已完成 7 轮穷举静态分析 + 针对性修复（R1–R7），另完成整合修复（Bug-1/Bug-2/i18n 管线/工具链去重）与**查 bug 系统升级**（Tier1 + Tier2，R8）与**拆分整合重构**（R9）与**日志/审计范围增强**（R10）与**cg 双形态语法**（R11）与**对象/参数括号规范化**（R12）与**全项目查 bug（R13）**与**再次全项目查 bug（R14）**与**针对漏网 bug 的 Tier3 规则扩充（R15）**与**拆分/封装机会落库（R16）**与**背景CG换图自动复位对话框（R17）**与**运行目检修复：伪透明恢复+cg 换图自动关框（R20）**与**layer_sprite 小封装（R21）**与**菜单 P0 改进（R22）**与**菜单 UI 图层化 menu_layer（R23）**与**语言全路径收口 nb_set_lang（R24）**与**i18n 8.3 短名化（R25）**与**存档/读档错误提示 i18n+可读性（R26）**与**菜单标题字模 RAM 目标修正（R27）**与**对话框内保存菜单剧情字残留（R28）**与**全项目整合机会审计与落地（R29）**与**整合机会规则落地（R30）**与**CG 画廊四项显示修复（0.2.109）**与**画廊背景 cover 占满屏幕（0.2.110）**与**记忆体/剧本 TOC 化调研与设计（devdoc 100）**与**归档打包侧 TOC 化落地（P4，0.2.111–0.2.112）**与**归档读取侧 TOC 化 P1+P2（farchive + image.c 按需读，0.2.113）**。
> - 归档读取侧 TOC 化 P1+P2（devdoc 100，0.2.113）: **共享读取库 `core/lib/farchive.{c,h}`**——纯 lib 零平台依赖零日志（沿用 naiz_file/tr/font 静默先例，失败以返回码上抛、引擎调用方 hal_log），`farchive_open`(TOC 常驻≤8192、truncated 标志)/`close`/`lookup_id`/`read_alloc`(绝对偏移+file_size 双夹逼、size=0 空洞返 NULL、malloc 失败/seek/fread 错误均返 NULL)；**image.c 整档→按需**——删 `file_read_all` 整档常驻 + `g_image_data/size/count/toc_off`/`image_get_entry`/`TOC_ENTRY_SIZE`，改 `g_image_arc`(FArchive) + 单槽 `g_blob`（`g_blob_id` 判重缓存）；`image_load` miss 路径改 `farchive_read_alloc` 瞬时读（decode 后 free，mag_decode 失败也 free 防泄漏），`image_init` 调色板一致性校验逐项瞬时读（原 `g_image_data+offset` 直读），`image_raw_blob` 借用期由「至下次 init/close」收缩为「至下次 raw_blob/init/close」——核对唯一借用方 nb_anim.c:319 先 `anim_stop_internal()`(置 `a->blob=NULL`) 再取新 blob，播放期无竞争者，单槽安全；**C14 合规**：farchive 为 lib 层无 hal.h（LIB_CFLAGS `-Ilib` 隔离），引擎侧 image_init 已 hal_log，C1/C2 两候选(`goto fail`/`return -1` 防御)登记 verify=ok；**gate 裁剪**：`lookup_name`/`read_buf` 预留给 P3 SCENE.DAT（0 调用者被 symbol_audit B 节拦）；B90 图片管理节/B92 playanima 容器直读行同步；pytest 374 passed、make 0 err/0 warn、fullaudit 6/6 全绿、bump 0.2.113
> - 归档读取侧 TOC 化 P3（devdoc 100，0.2.114）: **nb.c 接 SCENE.DAT**——`farchive_lookup_name`/`read_buf`/`name_match`(8.3 大小写不敏感)按 devdoc 回加；`g_scene_arc`/`g_scene_arc_open` 状态 + helper `nb_scene_archive_read`(lookup→read_buf 有界拷贝 cap-1 留 NUL、size≥cap 置 truncated、未命中返 -1)；`nb_init` 于 logo.nb 前 `farchive_open("SCENE.DAT",8192)` 成功置标志、失败 hal_log 警告继续；`nb_load` 重构为**归档优先/散文件回退单尾段**——归档命中整段拷贝进 nb.buf + NUL 收尾 + `num_lines='\n' 计数 + (前缀非空且末字节≠'\n' 时 +1)`（与 fgets 路径精确等价：nb_get_line 按 '\n' 分段、末行无换行也计 1，随机多组 LF/无\n 边界已推演验证）+ truncated 打 WARN（对齐现状文案），未命中走原 `fopen（"r"→文本模式）`+fgets 循环原样保留、失败路径零改动；**CRLF 防御落地**（devdoc §9.4）：pack_scenes 检测到 `\r` 即 WARN + 归一化 LF（归档读取仅认 '\n'；DOS 文本模式散文件路径本就剥 \r），测试 +1 例（CRLF→LF 字节断言）；B92 §3 数据文件/管线两行更新、B90 farchive 行补 lookup_name/read_buf；pytest 375 passed、make 0 err/0 warn、fullaudit 6/6 全绿、bump 0.2.114
> - 归档打包侧 TOC 化落地（devdoc 100 P4，0.2.111–0.2.112）: 将 devdoc 100 归档方案**打包侧先行**——①**共享写包** `tools/naiz_lib/toc_archive.py::make_toc_archive()`（IMAGE.DAT/SCENE.DAT 共用布局：uint32 count + count×20B TOC {name[12],off,size} + 数据，复用 image_dat 常量）；`pack_images.py` 写出块重构为调用它（字节等价，映像输出 680442 B/21 项不变）②**场景归档** `pack_scenes()`（build_game.py）：`scene/*.nb` → `games/<game>/SCENE.DAT`（8.3 base 截断后判短名互异防 R25 类相撞、跳过 0 字节残留、单脚本 <32 KiB NB_BUF_SIZE、增量写出），`deploy_runtime` 接入；引擎读取顺延 devdoc 100 P1–P3 ③**散文件自动净化** `_prune_stale_scenes()`：删除 games/ 根目录不在当前 scene 源集合的 `.nb`，并与拷贝循环"跳过 0 字节源文件+WARN"配合，**games/*.nb ≡ scene/*.nb 非空子集**——demo-a2 历史残留 nbook005-020.nb/nopbook.nb 共 16 个 0 字节文件被清，下次 make 从基座重建 HDI 自动净化（inject.py 每次 copy2 干净基座）④**测试** `tools/tests/test_toc_archive.py`（字节向量/往返/旧 writer 字节一致回归/>12 名拒绝/collision/32K/增量/prune 5 例）；B90/B92 §3 更新；pytest 374 passed、make 0 err/0 warn、fullaudit 全绿、HDI --list-files 确认无残留
> - CG 画廊背景 cover（0.2.110）: 画廊背景需**保证长宽比的前提下占满屏幕**——`mag_convert.py resize_to_screen` 增 `cover` 模式（scale=max 后**中心裁剪**到目标屏）、`convert_file`/CLI `--cover`/`build_game.py` images.map 行内选项透传，images.map gallery 资产加 `--cover` 重转；与 0.2.109 的 `cover` 无关（同属显示修复）；pytest/fullaudit 全绿
> - CG 画廊四项显示修复（0.2.109）: 目检 CG 画廊（`cmd_cgvmenu`，nb_cggallery.c）四项显示缺陷——①背景显示异常：画廊首次进入 Previews 墙背景绘错（gallery 资产路径未入库/取错），注册 `gallery` 资产（images.map + ASSETS.DB id=15）并让 `gallery_exit_preview` 换回 `gallery`；②画廊内背景经 `.mag` 调色板**索引覆盖**保留位（248-255/7/15 被图像调色板冲成黑/白、按钮/文字/焦点色错乱）：`nb_cggallery.c` 所有绘制颜色改保留索引（蓝 255/黑 254/白 250/黄 251），进出画廊 `palette_save/set/restore`，预览底图索引裁剪（PR 区 clip 覆盖二次采样边界）；③标题不居中/下移：`draw_title_large` 居中改用 `text_width` 计算、GAL_ORIGIN_Y 32→44；④预览叠加残留：当前帧不归零，进出画廊用 `erase_to_base` 擦三段（标题带/墙带/预览带）；menu_layer opaque 全屏会话；pytest 334+、make 0 err/0 warn、fullaudit 全绿
> - R30（整合机会规则落地，0.2.108）: R29 §8.3 建议落地——①**新增 4 条 C 规则**（39→43）：**C32**（AUTO）`strncpy()` 仅允许在 `core/lib/strutil.c` 内出现（R29④ str_copy 单一事实源回归守卫）；**C33**（HEUR）相邻 `layer_dialog_show();`+`dialog_layer_blit();` 对（`layer_dialog_clear()` 函数体内除外）→ 改用 `layer_dialog_clear()`；**C34**（HEUR）同文件重复静态数组初始化表（归一化内容 ≥2 处）→ 并单一事实源（slot_y/slot_ys 类）；**C35**（HEUR）同文件常量算术表达式重复（≥1 操作数为宏、≥3 处）→ 建议具名宏/常量（LAYER_DIALOG_CONTENT_* 类）②**symbol_audit `--gate`**：A/B 节任一输出即 exit 1（tools/diag/symbol_audit.py main 增 `--gate`，section_a/b 返回计数），`start.sh` fullaudit 第 5 步改 `-s A,B --gate`（此前只 `-s A` 且恒 exit 0、B 节死导出从未纳入判据）；`start.sh audit` 本色不带 gate ③规则基线登记：C35 首扫 10 候选全部核实为良性（缓冲尺寸/右边缘/掩码，layer_debug/layer_dialog/layer_sprite/nb_cggallery/nb_save_dialog/render/render_text/render_vram/settings_menu/keyboard），预存 C8/C9 5 候选核实良性，`--note` verify=ok 清零 open；pytest 362 passed、make 0 err/0 warn、fullaudit 全绿
> - R29（全项目整合机会审计与落地，0.2.107）: devdocs/99 全量整合审计——按"重复必须收敛单一事实源、惯用式必须收口、死代码必须删净"三原则落地 7 组改动：①**死导出清零**（`symbol_audit` A/B 归零）：删 `layer_dialog_restore`（R28 后 0 调用方，R28 记账"保留供外部"裁定作废）、`menu_layer_is_open`/`menu_layer_pixels`（menu_layer.c，内部无依赖）、`layer_bg_snapshot_valid`（layer_internal.h，内部 :41 用静态 `snapshot_valid` 不经过函数）②**内容几何单一事实源**：scene_layers.h 新增 `LAYER_DIALOG_CONTENT_X/W/Y/H` 宏，替换 13+7 处 `X+INDENT`/`W-INDENT-RIGHT` 表达式（nb_save_dialog×6、nb_question×4、layer_dialog×4、nb_saveload+1）+ nb_save_dialog 两处 content_x/y/w/h 四元组 ③**nb_saveload 槽位内聚**：`slot_y[4]`(:98) 与 `slot_ys[4]`(:315) 并一份文件级 `slot_y[SLOTS_PER_PAGE]`；新增 `SLOTS_PER_PAGE`/`slot_abs(page,row)` helper 替换 9 处 `page*4+…` 与 `(SAVE_SLOTS+3)/4`、缓存数组维数 ④**干净盒正式收口**：`dlg_clean_box` static helper（R28）→ 提升为公共 `layer_dialog_clear()`（=show+blit，layer_dialog.c），nb_question:116-117 两行合一并顺带消 2 行 ⑤**标题双分支去重**（nb_saveload:112-126 if/else 尾段相同 `draw_title_large` → `drawn` 标志单调用）⑥**`str_copy(dst,n,src)` 新 lib 封装**（core/lib/strutil.c/h）：收口 26 处 `strncpy+NUL` 惯用式（11 文件）；行为差异=不零填充余量字节，逐站核过无依赖；⑦**菜单退出序列统一**：nb_menu 两处与 nb_cggallery 退出改为 `close(1)→flush→restore_palette`（对齐 nb_saveload），三个菜单出口补契约注释（settings 不触碰——palette 未改属正常差异）；B90/B93 同步；pytest 358 passed、make 0 err/0 warn、fullaudit 6/6 全绿、HDI 引擎 md5 一致；检讨：可整合内容大多不属 39 条"单点错误"型规则能力范围（见 devdocs/99 §8，建议"高重复表达式阈值"HEUR 规则 + symbol_audit A/B 纳入 fullaudit 判据）
> - R28（对话框内保存菜单剧情字残留，0.2.106）: 目检对话框内 12 槽保存菜单（`save_dialog_menu`，nb_save_dialog.c）——打开与进入 confirm 时**剧情文字（角色名行+正文）透出、悬留**。根因=**`layer_dialog_restore()` 语义误用**：它只是 `dialog_layer_blit()`（把**含当前页剧情文字**的 480×115 合成原样盖回 VRAM，layer_dialog.c:301-304），被保存菜单当成"清空"用；`save_dlg_draw_slots` 的 `fill_dialog_bg` 只覆盖 `TEXT_Y`(28) 起的正文区（y308+），**角色名行 y286-300 从未被覆盖而残留**；`save_dlg_draw_confirm` 再 restore 把剧情文字全量盖回后 Prompt/槽位信息/Yes-No 直接叠画其上**不垫背景**→剧情正文从菜单字下透出。修复：抽静态 helper `dlg_clean_box()`= `layer_dialog_show()`+`dialog_layer_blit()`（合成重画干净框、无文字，即 nb_dialog.c:54,68 / nb_question.c:116,117 既有"新开一页"模式）替换两处 `layer_dialog_restore()`（入口 :58 与 confirm 入口 :237）；菜单进出两态底子均为干净盒，出口重建剧情页逻辑零改动；HDI 注入引擎 md5 与构建一致、fullaudit 6/6 全绿（续：R29 将 `layer_dialog_restore` 删除、static helper 提升为公共 `layer_dialog_clear`）
> - R26（存档/读档错误提示 i18n+可读性，0.2.104）: 目检发现 `show_error_msg` 4 处硬编码英文（`nb_saveload.c:280/376` "No save data."、`:217/319` "Load failed."）未走 `tr()` 且不在 `SYSTEM_UI_KEYS`——i18n 管线不感知、CJK 语料缺字，同时以菜单「聚焦选中」黄（MENU_PAL_YELLOW）绘在自以为黑的盒上辨识度差、盒顶端 4px 压到页面指示器 `1/5` 与第三槽行。修复：①`show_error_msg` 文案改 `tr(msg)`、绘白底黑字（`fill_rect` 用 `PAL_WHITE`）；**文字黑必须用保留索引 `PAL_CURSOR_BLACK`(254)**——目检反证过两轮：先用调色板索引 0 误以为黑，但菜单/背景图调色板中 0 实际是白，白底白字不可读；`palette_reset_reserved` 仅保证 7/15/254 三色，黑字只能取 254（palette.c:54 断言驱动）；②三处 `(260,298)` toast 下移至 `(260,346)`——彻底避开槽行文本(≤294)/页面指示器(≤344)/Back(x 区间不含)/确认键(仅在 confirm 态)；confirm-fail 处（`LAYER_DIALOG_X+INDENT+168, TEXT_Y-10`，对话框白底内 toast）保持原位；③`SYSTEM_UI_KEYS` 增补 "No save data."/"Load failed."（对齐 "No CGs available." 先例），9 语言 `sys_<lang>.txt` 提供译文（简 暂无存档数据/加载失败、繁 暫無存檔資料/載入失敗、日 セーブデータがありません/ロードに失敗しました、韩 저장된 데이터가 없습니다/로드 실패、法/德/意/西/葡各一）；④**盒宽动态化**——固定 120px 盒裁掉超长译文（白日文 224px/韩 192/西 184/德意 152-160/法 144/葡 136，仅简繁 96 装得下），`show_error_msg` 改 `text_width()`（render.h:78 已导出、UTF-8 感知、CJK16/ASCII8）+ `tw+24` 内边距 + 最小 120 + `LAYER_SCREEN_W` 越屏左移 clamp + `draw_text` 裁窗同步 `x+w-12`；HDI 复读确认 4 语言 CJK 字库新字形齐备（CHI 106→112、CHT 106→111、JPN 117→122、KOR 211→216 codepoints）；pytest 358 passed、make 0 err/0 warn、fullaudit 全绿
> - R23（菜单 UI 图层化 menu_layer，0.2.093）: 菜单按键 UI 图层化为**自包含可复用封装 `menu_layer`**（新 `menu_layer.c/.h`，`scene_layers.h` 引入；头部契约注释含最小接入示例）——①**渲染目标化**：`render_set_target(buf,w,h,stride,offx,offy)`/`render_set_target_vram()` 全局切换，`render.c` fill_rect/fill_rect_pattern/vram_pset_addr 增 RAM 分支（屏幕 clip+buffer 双重 C6 钳制），ui.c emboss 零改动自动跟随；②**透明 blit 原语** `render_blit_transparent()`（逐像素跳透明索引，VRAM_SET_BANK 宏分段）；③**menu_layer API 全套**：`open(x,y,w,h,transparent)`（clamp 屏幕、重复 open=重建、OOM 返 -1 调用方降级直绘 VRAM+C14 日志）/`begin_draw`（重接双 target）/`commit`/`blit`/`blit_rect`（自动求交幂等）/`close(restore)`（幂等置 NULL）/`is_open`/`pixels`/`erase_to_base`/`blit_sprite`（RAM 直拷，层未开降级 vram_blit_sprite）；**opaque**=base 快照（vram_read×2）+blit 含底+close(1) 整底还原，**transparent**=composite 填 PAL_TRANSPARENT 镂空、无 base、close 恒不还原；④**四菜单全部接入**（均全屏 opaque）：主菜单 menu_show（open→全量→blit，焦点移动增量会话 begin_draw→commit→blit_rect）、加载 nb_saveload（draw 包裹层化+标题 sprite 走 blit_sprite）、设置 settings_menu（删 bg_lang_name/ind/start_ind 三快照数组改 erase_to_base 语义）、画廊 nb_cggallery（preview 进出 close(0)→layer_bg_change 全屏→重新 open+draw_grid）；内容禁用调色板索引 15；pytest 334 passed、make 0 err/0 warn、fullaudit 全绿
> - R27（菜单标题字模 RAM 目标修正，0.2.105）: 目检「读取」菜单标题异常——R23 菜单图层化（全屏 opaque `menu_layer_open(0,0,640,400,0)`）后帧内容入层缓冲、commit 整块 `vram_write` 盖回，但 **`draw_title_large` 的 2x 缩放字模路径（`draw_glyph_scaled`/`draw_cjk_scaled`，render_text.c）只直写 VRAM、无 `text_tgt_buf` RAM 分支**（R19 阶段 A 仅给 `draw_glyph_internal` 分流，1x 与 2x 路径分叉泄漏）→ 标题先直绘 VRAM、紧接 opaque blit 用缓冲（标题区=基底背景像素）整块覆盖 → 标题被抹、显示异常。西文黑体标题走 `menu_layer_blit_sprite` 入缓冲故无征兆，**CJK 语言 100% 触发**（读/存 LOAD/SAVE 文字标题 + CG 画廊 "CG GALLERY" 同为文字路径同样中招）。修复：两缩放函数位循环前经新 helper `title_pset(px,py,color)` 落点——`text_tgt_buf` 非空时屏幕坐标→缓冲坐标（`-offx/-offy`）越界剪裁后写缓冲、返回 1；否则返回 0 走原 VRAM 路径（层退化直绘/VN 场景零行为变化）；2×2 块四像素统一经 helper。pytest 358 passed、make 0 err/0 warn、fullaudit 全绿
> - R25（i18n 8.3 短名化，0.2.100）: 「繁体字占空位」最后一根实锤——**HDI 注入 8.3 截名相撞**：`system_chi.txt`/`system_cht.txt` 基名 10 字符，`to_dos_name` 双截成 `SYSTEM_C.TXT`，注入时后写覆盖先写者，幸存内容与运行语言脱钩→简体字库配繁体文案，「開/載」空位、「始/入」正常（与 R24 的语言→字形路径无关，是部署管线文件命名缺陷）。修复：①系统表文件名全链路 `system_<lang>.txt`→`sys_<lang>.txt`（基名≤7 互异）：tr.c `i18n/sys_%s.txt`、i18n_gen 输出基名、gen_cjk_font.collect_cps 前缀 `("sys","role","game")`、项目与 games 部署 i18n 9 文件重命名、settings.txt/B92 注释同步（role_*/game_* 基名恰 8 字符不受截断影响）②**防呆**：`inject_common` 抽 `_check_dos_collision()` 覆盖**根目录+子目录**整批校验（此前子目录循环漏检，正是故障通道），碰撞即 RuntimeError 硬失败③**新测试** `tools/tests/test_dos_shortname.py`：注入校验函数、每项目 i18n 短名互异/基名≤8、system_ 遗留清零、scene 脚本 8.3（引擎启动文件 `startsetting`→`startset.nb`、`loadscene`→`loadscen.nb` 并同步 main.c/nb_mainmenu.c 字面量，validator 命令名不变）；AGENTS.md §十一 新增「游戏运行文件命名（8.3 强制）」硬性规则；pytest 358 passed、make 0 err/0 warn、fullaudit 全绿
> - R24（语言全路径收口 nb_set_lang，0.2.099）: 简体修复后繁体仍报"部分文字缺失（占空位）"——静态穷举确认非字库覆盖（4 CJK system 译文 100% 命中各 CJK_*.DAT）非绘制路径（draw_text/draw_title_large 均已 CJK 化）；根因=**语言→字形脱钩**：CJK 字库仅 `cmd_startsetting`（nb_mainmenu.c）一条路径跟随语言变更，而**读档路径 `save_apply`（save.c）调 `nb_set_lang(s->lang)` 只重载翻译表不重载字库**，存档语言与当前字库部分重叠即"有的可见、有的占空位"（continue/读档可达）。修复：`nb_set_lang()` 收口为语言驱动渲染态**唯一事实源**（strncpy→tr_init+eng 回退→`cjk_load_for_lang(nb.lang)`→`text_set_blackletter(settings_blackdialog && !nb_lang_is_cjk())`），`nb_init` 手写语言块替换为 `nb_set_lang(settings_get_lang())`、`cmd_startsetting` 语言变更分支删冗余 cjk+blackletter 行（nb.c 增 #include "cjk.h"，nb_mainmenu.c 删未用 cjk.h）——启动/书内设置/continue/读档四条路径全部收敛；pytest 351 passed、make 0 err/0 warn、fullaudit 全绿
> - R22（菜单 P0 改进，0.2.092）: 多图层落地后的菜单清点（plans/menu-p0-improvements.md），4 项行为等价改动——①**删死代码 `layer_get_bounds`+`LayerBounds`**（0 调用方，SPRITE/ANIM 分支残留 Option X 的 clip y<280 语义，与 R20 全高绘制冲突，误导维护；连带修 scene_layers.h 两处过时注释）②**`nb_saveload.c` 页级槽位缓存**：`slot_label_cache[4][128]`+`slot_exists_cache[4]` 按 `slot_cache_page` 键翻页失效，焦点/confirm 每帧不再 4×`slot_info` 读盘解析，save_game_slot 后失效重建 ③**`nb_cggallery.c` 解锁位图缓存**：`gal_unlock_cache[CG_COUNT]` 每次进入 cmd_cgvmenu 重建一次，cell/preview 不再每帧读 SYSTEM.SAV ④**`nb_question.c` 抽 `apply_option()`**：鼠标/键盘两路变量应用（lookup+`=`/`-`/`+`+INT_MIN 守卫）合一，-18 行；pytest 334 passed、make 0 err/0 warn、fullaudit 全绿
> - R21（layer_sprite 小封装，0.2.091）: 最新 symbol_audit（20260910）A/B 节全空、E 节大簇裁决不拆（layer_dialog 内聚单模块/hal_mouse HAL 薄接口/accessor 簇平坦/bg·sprite·vars 已是拆分产物，与 R9/R16 先例一致）——仅执行 3 项行为等价微重构：①抽 `sprite_blit_full()` 收口 show/replace/redraw 三处 `image_load→vram_blit_sprite→mag_release` 重复；②face/replace 的 alloc 分支改走既有 `sprite_entry_update`（删手写 4 字段赋值）；③`layer_sprite_hide` 删与 `layer_bg_restore_rect` 内部快照守卫重复的外层预查；face/clip/NAIZ_DEBUG 探针逻辑零改动；pytest 334 passed、make 0 err/0 warn、fullaudit 全绿
> - R20（运行目检修复：伪透明恢复 + cg 换图自动关框，0.2.090）: 目检推翻 devdoc 96 两项裁定——①**撤销 Option X 立绘裁剪**（对话框开启时精灵不再整层剪到 y<280；show/replace/redraw 恢复全高绘制、与对话框矩形相交，z 序=立绘在下、对话框合成在上）；伪透明经新**活动底 `dialog_occluder`**（480×115=under_dialog 纯底+立绘框内像素，与 dialog_layer 同生灭）恢复：`dialog_seed_base()`/recompose 改从 occluder 取底，PAT75 dither 孔透出立绘腿；`layer_sprite_sync_dialog_base()` 于每次精灵变更（show/replace/redraw/hide/hide_all）与开框时重建 occluder（reset 纯底→逐 active 精灵 RAM 落底→recompose 框+当前页盖回）；face 保留上半身 clip 不碰腿；replace/hide 的背景还原仍 clip_dialog=1 不盖框；`layer_bg_change` 经 redraw 尾 sync 自动重建底；动画帧不触对话框区无需复位；menu/option/save overlay 退出后洞仍透立绘。②**反转裁决 A 对 cg**——`cmd_cg` 资产分支恢复 `layer_dialog_hide()`+`nb_dialog_reset()`（`cg(){key}`=全屏事件并自动收起对话框、清空当前对白，下一句台词重新开框；`bg{}` 仍跨图存活，`cg(hidedialog)` 保留为显式收口指令）；`docs/B92` cg 两行语义更新、`docs/B90` 登记 occluder 三接口；pytest 334 passed、make 0 err/0 warn、fullaudit 全绿
> - R19（对话框图层化四阶段落地，0.2.089）: 按 devdoc 96 分阶段完成——**阶段 A**（render_text.c `draw_glyph_internal` 末级写分流 RAM/VRAM，`text_set_target()`/`text_set_target_vram()`，`dialog_paint_box` 收 layer_dialog.c static）；**阶段 B**（layer_dialog.c 复合缓冲 480×115=框+当前页文字，删防腐账本 `dialog_snapshot`/`dialog_snapshot_valid`/`dialog_dirty`/`layer_dialog_snap`/`layer_dialog_mark_dirty`，`layer_dialog_refresh`/`restore` 归一为 `dialog_layer_blit`，`layer_dialog_show` 每页重画框清上一页文字，`nb_question.c` 开框后补 blit）；**阶段 C**（layer_bg.c 重写：`under_dialog` 改名保留换源直取 MagImage RAM**零 VRAM 回读**，删旧 `layer_capture_bg`/`layer_capture_bg_dialog_from_bg`，`layer_capture_bg_dialog_from_image` 行内拷贝钳制修 C9 越行 memcpy；`layer_bg_change` = blit+capture+redraw+recompose 尾 blit；删 `layer_dialog_clear`；Option X 收口——dialog 开启时精灵**整层剪裁 y<280**（show/replace/face/redraw/hide-restore 一律不碰对话框矩形，精灵变更零 dialog blit）、`layer_dialog_hide` 关闭时精灵**全身重绘**（裁决 B）；C28 行跨距读仍由 src_row-src_y 与 img_h 夹逼）；**阶段 D**（回退 R17：删 `cmd_bg`/`cmd_cg` 资产分支的 auto `nb_dialog_reset()`，`bg(){x}`/`cg(){x}` 换图后对话框**跨图存活**——`layer_bg_change` 的 recompose 分支重种 under_dialog 并经 `dialog_layer_store_render` 渲染投影（角色名/正文/偏移，dialog_show 与存档还原时写入）用 `layer_dialog_render_page` 重绘框+当前页文字，裁决 A 达成**框+当前页文字完整存活**；`bg(hidedialog)`/`cg(hidedialog)` 恢复为**必需**的收起指令；`nb_save_dialog.c` 读档恢复文字收口到 `layer_dialog_render_page`+投影+blit（菜单为暂态 VRAM 覆盖，缓冲为持久态），删 `layer_dialog_target` 死导出；`docs/B92` 两行语义回退、`docs/B90` 符号表更新；R18 移除的 demo-a2 `.nb` 尾随行按新语义不再还原）；pytest 334 passed、make 0 err/0 warn、fullaudit 全绿
> - R18（范例脚本清理，0.2.088）: R17 已使 `bg(){x}`/`cg(){x}` 自身完成对话框全套复位——删除 demo-a2 `nbook001.nb` 中 `cg(){cg01}` 后的尾随 `cg(hidedialog)` 空转行（全项目 `.nb` 仅此一处），范例不再示范冗余写法；`bg(hidedialog)`/`cg(hidedialog)` 指令本体保留（语法/校验器/引擎零改动）
> - R17（背景/CG 换图自动复位对话框，0.2.087）: `bg(){key}`/`cg(){key}` 全屏 blit 覆盖对话框区后,`layer_capture_bg→layer_dialog_clear` 仅复位图层状态、NB 翻页状态残留,脚本被迫尾随 `hidedialog` 且其 55KB 还原写属自写自读冗余——①`cmd_bg`/`cmd_cg` 资产分支补 `nb_dialog_reset()`(show 命令自身完成全套复位);②`layer_dialog_hide()` 加 `!dialog_drawn` 早退(layer_dialog.c:192,对话框未绘制时跳过 55KB 冗余写入,并修"对话框关闭态下精灵被纯背景误盖"潜在 bug,char(hideall) 可达);③`bg(hidedialog)`/`cg(hidedialog)` **保留为可选独立指令**(语法/校验器/脚本零改动),show 后尾随降为无害空转;`docs/B92` 两处语义补注;make 0 err/0 warn、pytest 全绿、fullaudit 全绿(detail: devdocs/95)
> - R15（Tier3 规则扩充，0.2.085）: `test_bug_corpus.py` 原语料仅固化 R1-R8 真 bug——实测 R13/R14 共 8 个修复 bug **无一命中既有 35 条规则**（覆盖缺口实证）。新增 4 条 HEUR 规则固化：**C26** 所有权分离 free（mag_release 池 struct 逃逸 is_pool 守卫）/ **C27** 计数派生负下标（cmd_char `argv[argc-1]` 无 `argc<1` 守卫）/ **C28** 行跨距读无高度边界（cine 对话框 OOB，`img_w` 齐全但无 `img_h` 夹逼）/ **C29** 结构体指针仅起始越界检查（mag `off_img` 缺 `sizeof` 项）；另 `rules_c.py` 手动清单增 **C30** 对话框/sprite 背景恢复（layer_sprite_hide 幽灵）/ **C31** 菜单画廊焦点重绘（Back 残留）。四条规则均：旧形态命中、修复形态静默、全库 0 误报；语料 +4（8 个 R13/R14 bug 全部入册，规则退化即失败）、单元测试 test_c26–test_c29；规则总数 35→39、pytest 334 passed、fullaudit 全绿
> - R14（再次全项目查 bug，0.2.084）: ①**调色板轨 cine + 对话框堆 OOB 读（高）**——`layer_capture_bg_dialog_from_image` 仅对 `src_row` 做屏幕高度（400）边界检查、未对图片自身高度限定；调色板轨 cine（640×280，`atype==1`）对话框打开时 `anim_rebuild_dialog_if_open`（nb_anim.c）逐帧把对话框区（y=280..394，115 行）从 280 行图读走 → 越界读最多约 72KB 堆后；修复为函数新增 `img_h` 参数并以 `src_row-src_y`（图像行索引）与 `img_h` 夹逼，cine 图不覆盖 280 以下的区域则跳过保留原快照 ②**mag.c `off_img` 边界检查加固（低）**——`off_img` 仅判起始是否越界，struct 尾部可能溢出；令判定覆盖 `off_img+sizeof(MagImage)` ③**nb_anim.c 重复字段赋值清理（非 bug）**——`playanima` 武装状态下同一批 `a->*` 字段被赋值两次（值相同）；去除前一份冗余 ④**审计候选清零**——本轮（③）去重致 2 条行号漂移 + 12 条既有候选（layer.c:80 switch 无 default 但初值兜底 / layer_debug.c:35 fwrite 诊断导出 / nb_anim.c:477 malloc 已判空 / mp4_to_ani.py:122 与 image_dat.py:36-37 与 env_utils.py:121 惰性导入 / gen_cjk_font.py:251-268 自校验读取失败即 loud）全部 `--note` 登记 verify=ok，open 37→0；make 0 err/0 warn、pytest 322 passed、fullaudit 全绿
> - R13（全项目查 bug 修复，0.2.083）: ①**mag 池释放堆破坏（高）**——`mag_release` 对 `is_pool=1` 的图也执行 `free(img)`，而池图 struct/pixels 位于调用方 `decode_buf`（`nb_anim` 像素轨 `mag_decode_into`）内 → free 内部指针 + 与 `decode_buf` 双重释放，`playanima` 每推进一帧触发；修复为 `is_pool` 时跳过全部释放、由调用方整体释放 ②**cmd_char argv[-1] 越界读（中）**——R12 门禁下 `char()`/裸 `char`（argc=0、brace_arg=-1）时 `-1 != -1` 放行后执行 `name=argv[argc-1]`，补 `argc<1` 守卫（对齐 `cmd_bg`/`cmd_sceneconf`）③**layer_sprite_hide 幽灵残影（中）**——dialog 未绘制分支仅 deactivate 不恢复背景，`char(hideall)` 可达；补 `layer_bg_restore_rect` 恢复 ④**CG 画廊 Back 焦点残留（低）**——focus 从 Back 移回 cell 时未把 Back 从黄绘回白，补 `PAL_WHITE` 重绘 ⑤**mag.c off_img 多算 `sizeof(MagImage)`（低，潜在越界）**——struct 应紧贴 cropped 之后；令 `off_img = off_cropped + cropped_size`；均经 `--note` 登记/verify、make 0 err/0 warn、pytest 322 passed、fullaudit 全绿
> - R12（对象/参数括号规范化，0.2.082）: 将 R11 的"对象在花括号负载、括号=参数±keyword"惯例扩展到全部资源类命令——`bg(effect[,transition]){key}`（fx/transition 回位参数槽，现为占位）、`char(pos[,expr[,type]]){name}`、`bgm(){key}`/`bgm(stop)`、`sound(){key}`、`voice(){key}`、`sceneconf(){title[,type]}`（paren 别名删除，仅花括号形态）；引擎 `cmd_bg`/`cmd_char`/`cmd_sceneconf`/`cmd_bgm`/`cmd_sound`/`cmd_voice` 均以 `nb_get_last_brace_arg()==argc-1` 硬性门禁，括号承载对象形态被拒绝；`nb_validator.py` 相应 6 命令签名+判定重写；脚本全量迁移 29 处（demo-a2 bg 11/char 12 + animatest bg 3，nbook001 补 bg）；CG 画廊 `cmd_cgvmenu` 引擎直调渲染不受影响；pytest 322 passed、make 0 err/0 warn、fullaudit 全绿
> - R11（cg 双形态语法，0.2.081）: `cg(){<asset_key>}` 花括号负载展示 CG，`cg(hidedialog)` 关对话框还原背景（与 `bg(hidedialog)` 平行）；**括号位预留给未来参数、硬性拒绝 `cg(key)` 括号形态**——`nb_parse_line()` 新增 `brace_arg` 出参 + `nb.c` 文件级 `last_brace_arg` 访问器 `nb_get_last_brace_arg()`（`nb_internal.h`），`cmd_cg` 检查负载来源；根修 `layer_bg_change()` 移除 `!layer_dialog_drawn()` 门控、blit 后总是重采 `bg_dialog_snapshot`（对话框打开时展示 CG 后 hidedialog 回填旧 bg 矩形残影之根因）；`nb_validator.py` `cg` 签名改 `(0,1,'cg(){key}|cg(hidedialog)')` + 新旧形态判定；脚本 `nbook001.nb` `cg(cg01)+bg(hidedialog)` → `cg(){cg01}+cg(hidedialog)`；pytest 322 passed、fullaudit 全绿
> - R1–R2: 36 项基础修复（B1–B5, E1–E11, N1–N28）
> - R3: 13 项修复（P1–P17，含调色板泄漏、存档校验、VRAM HAL 封装等）
> - R4: 13 项修复（Q1–Q10, L1–L7，含 off-by-one、死代码、溢出等）
> - R5: 10 项修复（shell 注入+引用、offsetof、mag 解码健壮性、Python 工具链）
> - R6: 9 项修复（save.c offsetof 回归、makegame.sh argparse 空串、make_base_clean 传播、mag 颜色流、nb_vars 溢出等）
> - R7: verify CLI 修复（--note 自含 spec `REL:LINENO:VERDICT[:TEXT]`，根除多 note 共享单 --verdict 导致 verify_notes.json 数据污染）、image.c:65 补 hal_log 消除 fsize<4 静默失败、shell case 词加引号硬化（makegame.sh:165 / start.sh:271/304）、误报项 verify=ok 批量登记（S1/S5/P5/P8 共 24 条）、pending 候选计数负值 clamp
> - R8（查 bug 系统 Tier1+Tier2 升级）: Tier1=①Bug 语料回归 `test_bug_corpus.py`（R1-R7 真实 bug 固化，规则退化即失败）②verify v2 行级 STALE（note 记录核验行文本，无关编辑不再整文件失效；v1 记录 sha8 兜底兼容）③RESULT 统一"violations + 全量 Verification 两行"，state v2 存 findings 明细 ④`--since <git-ref>` 新代码聚焦门禁（仅审计变更行，新违规照样 exit 1）；Tier2=新增 C22 INT_MIN 取负 / C23 同路径双重 free / C24 memcpy 尺寸交叉核对（AUTO）+ C25 use-after-free（HEUR），规则总数 35；**C22 首跑即抓到 R7 漏网真 bug**（nb_question.c:150/185 `-opt_deltas[hit]/[sel]`，已按 INT_MIN 守卫格式修补并补 `#include <limits.h>`）；内部清理 reset 后 32 候选全部 verify=ok 归零
> - 整合修复: Bug-1（save checksum 偏移参数化）、Bug-2（venv 路径统一）、i18n 管线（tr 空值回退、nb_set_lang 重载翻译表、question/title 文本提取、i18n_gen 纳入 build）、工具链去重（B2/B3 toml 写入、B6 hdi walk 复用、B9 FONT.DAT 容器共享）、C2 text 死桩移除、C4 死常量删除、SAVETMP 死代码清理
> - R9（拆分整合重构，全机会）: A=移除 `anim_playing()` 死导出；#1=`render_internal.h` 增 `vram_fill_row`（rep stosb）/`vram_row_write`（rep movsb）static inline，消 render.c/render_vram.c/render_blit.c 三处整行拷贝副本；#2=`palette_reset_reserved()` 收口 PAL_WHITE/TRANSPARENT/CURSOR_BLACK 三色重置（nb_commands.c/nb_cg.c 各消 3 行重复）；#3=CG 画廊自 nb_mainmenu.c 拆为独立 `nb_cggallery.c`（GAL_* 常量+6 static 辅助+`cmd_cgvmenu`）；#5=`slot_info` 头部解析收口到 `save_io.c` 新 `save_read_header()`（offsetof+SEEK_SET 直跳，槽位查询不再手搓偏移）；#4/#7 审计判定不需拆分；make 0 error、pytest 322 passed、fullaudit 全绿；symbol_audit A/B 节均空
> - R10（日志/审计范围增强）: R9 复盘发现 `.h` 头文件完全在规则审计扫描之外（`collect_files` 只收 core/*/*.c + tools/*.py + shell）；已扩展 `tools.audit.audit.collect_files` 纳入 `core/**/*.h`（+42，files 125→167），C13(unused static)/C14(must hal_log) 对头文件门控排除（单头文件无法判定跨 .c 使用、inline helper 无日志义务）；R9 相关 3 条 open 候选（nb_anim.c:490 C1 / nb_commands.c:320 C8 / nb_commands.c:134 C9）经人工核实后 `--note` 登记 verify=ok（open 17→14）；头文件首扫 0 新候选、AUTO 违规 0；pytest 322 passed、fullaudit 全绿
> - 动画制作工具链（2026-08-21，devdoc 77/78 制作侧；2026-08-23 裸名字查库制；2026-08-24 项目化架构；同日 `.na` 分离修订，devdoc 79）: 动画项目目录 `animation/projects/<项目名>/{config.toml,scripts/,db/}`（`tools.naiz_build.anim_project` 为架构单一事实源：`load_project` 校验 config.toml `[project] name`=目录名、`iter_projects`、`scaffold`；`anima.sh init <项目>` 创建骨架）+ **动画脚本 `.na` 后缀**（专属动画脚本、与剧本脚本 `.nb` 严格分离：解析器 `parse_anim_script` 入口拒绝非 `.na`（F1 门禁），脚本放 `scripts/<名>.na`，引擎零改动；原 naizbook/*.nb 约定废止）+ 脚本解析（animaconf/frame/base/pal 裸括号语法，F1+V1–V8 校验）+ `.ANI` 容器 v1（逐帧 tick 表取代固定 fps，L1–L5 装载校验，`tools/naiz_lib/anim_container.py` 权威实现）+ `anim_register.py`/`anim_import.py`/`anima.sh`（init/register/check/build `<项目>/<脚本>`/buildall/list；无参数进多级交互菜单：项目列表→操作菜单[check 检查登记/register 同步/生成动画]→脚本子菜单→build[/--sync]；`--sync` 构建前同步登记库；`check` 只读双向对账未登记/失效行/待更新，有差异 exit 1）；帧素材放 `assets/<项目名>/anim/`，产物全局 `animation/output/`；脚本花括号内写**裸名字**（无路径无扩展名），经 `./anima.sh register <项目>` 登记进 `animation/projects/<项目>/db/<项目>.db` 名字索引库（复合主键 (name,kind)，仅存索引不存图像字节，与游戏 ASSETS.DB 独立）后由解析器查库映射到具体文件；多图 `{f1,f2}` 显式交错序列共用秒数；pixel/palette 双轨端到端冒烟；播放侧（nb_anim/打包入库三件套）顺延
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
