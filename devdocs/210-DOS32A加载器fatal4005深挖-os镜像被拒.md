# 210 — DOS/32A 加载器 fatal 4005 深挖：`-os` LE 镜像被拒绝

> **状态**: 已破案（0.4.033，c111）：4005 = **装载地址敏感**——AUTOEXEC 是否含 `SET DOS16M=1`
> 平移了 ENGINE.EXE 的 DOS 装载地址，恰落在 DOS/32A fixup 处理的坏地址上。见 §十一。
> 记录级"逐条拒收"定性仍被推翻（11.2–11.3 成立）；11.4 的初版结论已被对照实验修正。
> **版本**: 0.4.031 落地缓解，0.4.032 补记脚本标注与本文
> **交接**: 2026-11-13（0.4.032）暂停深挖，接手请先读 §十 交接状态
> **关联**: `CHANGELOG.md` c108/c109、devdocs/195 §四 P4、devdocs/196 §六.5、`core/Makefile` `SIZE_OPT`
> **性质**: DOS/32A 9.12 加载器 fixup 处理的**装载地址敏感**缺陷；本仓库内不可修加载器，通过 AUTOEXEC `SET DOS16M=1` 平移装载地址绕开

## 一、症状

0.4.030 把 `projects/demo-a2/scene/nbook002.nb` 的 `sceneconf()` 从 `onlist` 改成 `outlist`
（生成表 `SCENE_MENU_COUNT` 由 2 变 1）后重新构建，模拟器启动到加载 `ENGINE.EXE` 时直接报：

```
unrecognized fixup data in application
```

（完整形态为 DOS/32A `fatal (4005)`。）

**关键特征：串口零输出。** 引擎的 `hal_init()` 是串口调试通道的建立点，`logs/serial_demo-a2.log`
为空即可判定：**扩展器在把控制权交给程序之前就退出了**，任何引擎代码都没执行。此后所有
「功能/脚本/资源」方向的怀疑都可以先搁置。

## 二、证据链（逐项排除）

| 序号 | 假设 | 检验方法 | 结果 |
|---|---|---|---|
| E1 | `.nb` 语法错误 | `./makegame.sh build demo-a2` 全流程 | 通过；`nb_scene_menu.h` 生成 `SCENE_MENU_COUNT 1`、仅 `nbook005.nb` 一行，行字段 4 个齐全 |
| E2 | HDI 注入截断/写坏 | 用 `tools/naiz_img` 读 `disks/demo-a2.hdi` 内 `ENGINE.EXE`，与 `games/demo-a2/engine.exe` 逐字节比对 | 完全一致（245232 B），排除注入路径 |
| E3 | 增量编译残留（新旧目标文件混用） | `rm -rf core/build` 后全量重编 `-os` | 产物仍为 245232 B（布局确定性），启动仍 4005 → 排除混用 |
| E4 | LE 头结构损坏 | 按 MZ `e_lfanew` 定位 LE，逐字段解析 | 结构自洽，见 §三 |
| E5 | 优化级是变量 | 同一棵树分别编 `-os` / `-od`（仅该旗标不同），各实机启动一次 | `-os` 必 4005；`-od` 必正常启动（各 2 次，含一次全量重编） |

结论：失败物是**按 `-os` 编出来的那份 LE 镜像**，不是脚本、不是盘、不是残留对象。

## 三、LE 头自检（`-os` 镜像，demo-a2）

以 MZ 头 `e_lfanew` 指向 `LE` 签名，按 LE 头字段读取：

| 字段 | 值 | 判读 |
|---|---|---|
| `byte_order` / `word_order` | 0 / 0 | 小端，合法 |
| `cpu_type` / `os_type` | 2 / 1 | 386 / OS/2 子集，合法 |
| `module_pages` | 46 | — |
| `page_size` / `last_page_size` | 4096 / 2640 | 45×4096+2640 = 186960 |
| 数据页偏移 | `0xe3a0` = 58272 | 文件长 245232 − 186960 = **恰好吻合** |
| `object_count` | 2 | code / data，Watcom 32-bit flat 典型 |
| fixup 段大小 | 30294 | = 修页表 47×4 + 修记录 30106 |
| 修页表条目 | 47（= pages+1） | 单调不减，末项 30105 ≈ 记录跨度 30106 |

对照物：`games/animatest/engine.exe`（224508 B、42 页、fixup 段 25514）结构同型且可启动；
`-od` 版 demo-a2（311812 B、62 页）同样同型且可启动。

**所以不是坏了，是加载器不收。** 头部、页表、修页表、数据页偏移全部自洽。

## 四、已知同型记录（不是新问题）

- devdocs/195 §四 P4：`-l=dos32a` + `-os` 曾出现 `fatal (4005)`；`-od` 正常；**LE fixup 数据本身
  经逐页校验是合法的**。
- devdocs/196 §六.5：明确写下「能不能启动依赖布局，**任何体积变化后都要跑开机冒烟**」。

即 2026-11-02 已经踩过一次，当时以「mag 单独 `-od`」收口，未解决机制本身。本次是同一机制的
再次触发：`nbook002` 改 `outlist` 让生成表缩小 1 条记录，镜像布局随之位移，跨过了可加载/不可加载的分界。

## 五、当前结论与未解问题

**已定（类级）**：DOS/32A 的 fixup 解释器拒收 `-os` 产物中的某一条/某几条 fixup 记录；
该记录是 wlink 在 `-os` 布局下产生的。`-od` 布局下不出现或落在加载器可接受范围内。

**未定（记录级）**：具体是第几页、第几条记录、哪个字段。原因是 LE fixup 记录为**变长编码**
（源偏移 16/32 位、source list、target type 1/2 混排），本轮的快速解码器（固定 7 字节）在
**包括已知可启动镜像在内**的所有样本上都对不齐页表边界（17–37 页失配），故其输出的「越界」
报告全部作废，不构成证据。

**为什么可以接受未定**：`dos32a.exe` 是工具链里唯一一份加载器（27504 B，版本串为字面
`x.x.x`），仓库内既不能替换也不能修改。即使定位到具体记录，可做的动作也只有「绕开」
（调整布局 / 换优化级 / 单独改某个目标文件的优化级），无法修根。

## 六、已落地的缓解

`core/Makefile` 第 59 行新增、第 70 行接入：

```make
SIZE_OPT = $(if $(filter dos32a,$(EXTENDER)),-od,-os)
BASE    = -bt=dos $(EXT_LINK) -zq $(SIZE_OPT) -s ... $(EXT_DEFS) $(EXTRA_DEFS)
```

- `EXTENDER=dos32a`（openpack 交付链，`build.sh open`）→ `-od`；
- `EXTENDER=dos4g`（cmpack 对照链）→ `-os`，历史交付形态不动。
- 代价：openpack 产物 245232 → 311812 B，且关闭优化（运行更慢，正确性优先）。
- `mag.c` 原有的 `LIB_CFLAGS:-os=-od` 替换在新旗标下自然保持 `-od`，行为不变。

**操作规则（必须遵守）**：
1. 任何改动 `BASE` 内编译旗标之后，必须 `rm -rf core/build` 再全量重编——make 不跟踪旗标，
   否则复用旧旗标的目标文件（同 AGENTS §八 六禁之六）。
2. 任何会让镜像体积/布局变化的改动（增删源文件、改常量表、改优化级）之后，**必须跑一次
   开机冒烟**（`makegame.sh build && make && test --serial`，串口非空且无 4005）。

## 七、下一步深挖方案（若要记录级定位）

1. **写规范的 LE fixup 解码器**（一次性脚本，不进仓库运行路径）：
   - 逐条消费变长记录：type 字节（bit4=32 位源偏移、bit5=源偏移表、bit6=16:16 指针）、
     源偏移、target flags（bit3=16 位目标偏移、bit4=32 位、bit5=ordinal、bit6=internal）、
     目标对象号/序号、目标偏移、source list（count + DWORD 数组）。
   - **校准判据**：解码必须逐页精确结束于下一页的起始偏移（等于修页表下一项）。任一页
     对不齐就是解码器错，不得出结论。
2. 用校准后的解码器解 `-od`（可启动）与 `-os`（崩溃）两份，逐页 diff：记录数、源偏移、
   目标偏移、类型分布。
3. 若锁定可疑对象/文件，用「其余 `-os`、单文件 `-od`」做定向重编 + 开机冒烟验证；
   成功即把该文件加入 per-file `-od` 例外表（如 `mag.c` 现例），其余恢复 `-os`。
4. 若 diff 无差异（纯布局阈值效应），则放弃恢复 `-os`，保留全局 `-od`。

## 八、踩坑清单

1. **串口空 = 加载期失败**，不要先怀疑脚本/资源；先看 `logs/serial_*.log` 是否为空。
2. **HDI 内的 exe 必须与部署树逐字节比对**再下「注入没问题」的结论——不能只看大小。
3. **LE 头自洽 ≠ 可加载**：修页表单调、数据页偏移吻合都可能成立，加载器仍可拒收。
4. **不要用固定长度假设解 fixup 记录**：先用已知可启动镜像校准，否则得到的「越界」全是假的
   （本轮已踩：对可启动镜像同样报越界）。
5. **改编译旗标必须清 `core/build`**；只用 `build` 不 `make` 跑的是旧 HDI（AGENTS §八 六禁之二）。
6. **每次体积/布局变化后跑开机冒烟**：这是 196 §六.5 留下的一条，本次因未执行而直到用户实机才发现。
7. **fatal 4005 是"表象错误码"**：`apply_fixups` 在循环顶部预置 `_err_code=4005`，循环内任何
   `file_errorm` 退出都按 4005 报出（v9.12 `loader.asm`）。见到 4005 不要直接解读为"fixup 记录
   内容非法"，先用 §十一 的复现三连验证可复现性。
8. **容器缺 devpts 时 `makegame test --serial` 必挂**（`OSError: out of pty devices`）。挂载
   devpts 不跨命令持久，替代方案：`tools/diag/np2kai_smoke_fifo.py`（现已用 PTY 串口，容器内
   退化为 `naiz_screendig` 抓屏；FIFO 在本机 wxnp21kai 上不转发串口，勿改回）。注意模拟器进程
   **必须与抓屏在同一条命令内**完成启动→等待→抓屏（后台进程不跨命令存活）；
   抓屏产物在沙箱外的 /tmp，需立即复制进项目目录。
9. **诊断新工具速记**：`tmp_le/sim_loader.py`（对任意 wlink LE 镜像跑 v9.12 加载器全检查，含
   fixup 记录逐条解析）、`tmp_le/dos32a-git/`（v9.12 官方源码，取自 GitHub DosWorld/dos32a，
   codeload.zip 可下，narechk 原站已死且被代理挡）。

## 九、验收缺口

- [x] 场景 `outlist` 全量显式标注（0.4.032：`nbook001/003/004/006` 补 `outlist`；002 已是 outlist、005 为 onlist；`sceneconf` 无第三字段的 normal 场景已清零）
- [x] 0.4.032 后全量 `pytest` 复跑（2026-11-13 深挖轮：**931 passed, 2 skipped**）
- [x] 记录级定位（§七 1–2）：解码器已校准，但结论是**否定**的——不存在"被拒的记录"，见 §十一
- [x] `-os` 全量恢复（§七 3）：`SIZE_OPT = -os`（0.4.033）+ `SET DOS16M=1` 两条链无条件写入（§11.5），实机冒烟通过
- [ ] 实机剧情冒烟：Scene 菜单应只剩 005 一项，进入可播放、`scene(end)` 回鉴赏

## 十、交接状态（2026-11-13，0.4.032 暂停）

**已完成**

- `core/Makefile` 第 59 行 `SIZE_OPT`（dos32a→`-od`，dos4g→`-os`），第 70 行 `BASE` 接入；全量重编后实机启动正常。
- 六个 normal 场景全部显式标注：`nbook001/002/003/004/006` = `outlist`，`nbook005` = `onlist`；生成表 `SCENE_MENU_COUNT 1`，仅 `nbook005.nb`。
- 本文（210）与 `CHANGELOG.md` c108/c109、`docs/B91 §2.2` 已同步。

**当前产物与现场**

| 项 | 路径 | 尺寸 / 时间 | 说明 |
|---|---|---|---|
| 部署引擎 | `games/demo-a2/engine.exe` | 311812 B / 11-13 16:25 | `-od`，可启动 |
| 构建产物 | `core/engine32a.exe` | 311812 B / 11-13 16:25 | 与部署件同源 |
| **失败样本** | `/tmp/engine_os.exe` | 245232 B / 11-13 16:09 | `-os` 版，启动即 4005；**`/tmp` 可能被清理，长期保留请另存** |

**最后一次实机验证**：0.4.032 `build + make + test --serial`，串口依次输出
`aiz engine` / `Init OK` / `Vid OK` / `VRAM OK` / `Pal chk OK`，无 4005（`WARN: INT 18h AH=30h/40h returned non-zero` 为既有非致命告警）。

**未做（接手执行）**

1. ~~`python -m pytest -q` 全量复跑~~ —— 已做（0.4.032 补记轮：931 passed, 2 skipped）。
2. ~~记录级定位~~ —— 已做且结论为否定（不存在被拒记录），见 §十一。
3. 剧情实机冒烟（Scene 菜单 1 项 / 播放 / `scene(end)` 回鉴赏 / Back 回 special）——待人工执行。

**接手命令**

```bash
./makegame.sh build demo-a2 && ./makegame.sh make demo-a2   # 重建 + 注入
python -m pytest -q                                          # 全量守卫
./makegame.sh test demo-a2 --serial                          # 开机冒烟（看串口非空、无 4005）
```

**硬约束**：改 `core/Makefile` 任何编译旗标后必须 `rm -rf core/build` 全量重编；任何体积/布局变化后必须跑一次开机冒烟。

## 十一、2026-11-13 深挖后续：记录级定性被推翻（§五/§七.2 翻案）

本轮拿到了 DOS/32A v9.12 官方源码并做了逐指令对照 + 决定性实验，结论与 §五 相反。

### 11.1 源码级事实（DosWorld/dos32a @ GitHub，v9.12）

`src/dos32a/loader.asm` 中 fatal 4005 的**全部**触发点只有四处，全在 `apply_fixups`：

1. `test cx,0F20h` —— SRC/FLAGS 的源列表/导入标志置位；
2. 对象号越界（`(objnum-1)*16 > (nobjects-1)*16` 时 `jc`）；
3. fixup 类型码 > 8；
4. 类型 1/4（`fix_invalid`）。

关键点：`_err_code` 在 `apply_fixups` 循环**顶部预置为 4005**，循环内任何 `file_errorm`（包括上述检查）都按 4005 报出。其余错误各有专名（4001 对象过多 / 4004 内存不足 / 4006 16 位溢出 / 3002 文件错 / 3005 no-fixups 标志）。

### 11.2 记录编码对照（校准解码器 vs 源码）

实测 Watcom 记录布局 `type(1)+flags(1)+src16(2)+obj(1)+tgt(2/4)` 与 loader 读取方式**完全一致**：
- `cx = word@[0]`（低字节=类型，高字节=flags）、`src16 = word@[2]`、objnum 字节 `@[4]`（flags bit6=0x40 时为双字节）；
- flags bit4（0x10）= loader 里的 "Alias" 位，仅决定 target 是 2 还是 4 字节，**不触发 0x0F20 掩码**；
- 逐字节消费步长 7/9 字节与校准解码器一致。

### 11.3 仿真结果（`tmp_le/sim_loader.py`，逐检查忠实复刻 loader.asm）

| 镜像 | 模块标志/对象/页表/fixup 全部检查 | 结果 |
|---|---|---|
| engine_os.exe（-os，3953 条） | 全部通过 | **无任何 4005 触发条件** |
| engine_od.exe（-od，4066 条） | 全部通过 | 同上 |
| engine_animatest.exe（3395 条） | 全部通过 | 同上 |

另有辅助确认：
- 反汇编内嵌 stub（`objdump` @ 0x54C1 起）：`mov [err],4005h` / `test cx,0F20h` / `test cx,4000h` / `test cx,1000h` / `cmp cl,07h` 与源码逐条对应，stub 即 v9.12 同源代码；
- fixup 目标地址（页基址+源偏移）全部 < 对象 vsize，无越界写；两镜像各有 2 条 src=-1/-2 的跨页伪记录（0xFFFF/0xFFFE），`-od`/animatest 同样存在且可启动，非分界。

**结论 A：不存在"某条 fixup 记录被拒收"**。§五 的"加载器解释器拒收 -os 产物中的某条记录"定性错误；§七.2 记录级 diff 无 smoking gun 可找。

### 11.4 决定性实验（初版结论有误，被 11.5 对照实验修正）

- 用 `EXTENDER=dos32a SIZE_OPT=-os TARGET=engine_os.exe make`（干净全量重编）重建失败样本（245232 B，md5 `49fdfcf8…`）；
- 经 `tools.naiz_img.inject` 注入新建 HDI，NP2kai 实机启动：引擎设置菜单正常显示；
- **但该实验被污染**：手动调 inject 时未设 `NAIZ_PACK`，`_is_open_pack()` 走默认分支 → AUTOEXEC 含 `SET DOS16M=1`。初版"启动成功"与随后一次"4005 复现"实为**仅差 AUTOEXEC 一行的两份 HDI**，见 11.5。原失败样本 `/tmp/engine_os.exe` 已丢失，md5 无从比对。

### 11.5 真正根因：装载地址敏感（0.4.033，c111 破案）

对照实验矩阵（同一 -os 引擎 245232 B，各样本间 md5 差异 ≤ 3 字节模块名，代码段全同）：

| # | 引擎 md5 | HDI 构建方式 | AUTOEXEC | 结果 |
|---|---|---|---|---|
| 1 | `49fdfcf8` | 手动 inject（NAIZ_PACK 未设） | 含 `SET DOS16M=1` | **启动到标题画面** |
| 2 | `e56f3238` | `makegame make`（openpack） | 无 DOS16M | **fatal 4005** |
| 3 | `e56f3238` | 手动 inject（同 #2 引擎字节） | 含 `SET DOS16M=1` | **启动到标题画面** |
| 4 | `e56f3238` | `makegame make` + `NAIZ_AE_PAD=1`（加一行 7 字节 REM） | 无 DOS16M 有 REM | **启动** |

关键事实：

- `SET DOS16M=1` **本身 DOS/32A 不读**（v9.12 源码全文零引用）；它的真实作用是**增大 AUTOEXEC/环境块 → 平移 ENGINE.EXE 的 DOS 装载地址**。
- `NAIZ_AE_PAD=1`（196 §4.4 的诊断旋钮，纯 REM 填充）同样消除 4005 → **因果因子是装载地址平移，不是变量内容**。
- `inject_common.generate_autoexec` 原来写 `if not _is_open_pack()`，把该行只给商业链 → openpack（DOS/32A）链的装载地址恰落在坏地址 → 4005。0.4.030 原始发作（场景表改一条记录即发作）同为布局敏感的体现。
- DOS/32A 9.12 loader 的 fixup 处理存在装载地址相关缺陷（指令级机理未再深挖——加载器不可修，只能绕开；如要深挖从 `apply_fixups` 的 `gs:[esi]` 段界限/缓冲区布局入手）。

**修复（0.4.033，c111）**：

1. `core/Makefile`：`SIZE_OPT = -os` 全链恢复——**立绘切换性能恢复**（-od 期间 blit 热循环无优化慢约 4 倍，GCC 等效基准 -O0 vs -Os）；
2. `tools/naiz_img/inject_common.py`：`SET DOS16M=1` 改为**两条链无条件写入**（对 DOS/4GW 是必需开关，对 DOS/32A 是无害的地址平移）；
3. 全量重编 + 注入 + 实机冒烟：0.4.033 标题画面正常；`pytest` 931 passed, 2 skipped。

**风险与守则**：

- 4005 与装载地址耦合，**任何改变 AUTOEXEC 字节数或镜像布局的改动**理论上都可能再触发。改旗标/布局后 `rm -rf core/build` 全量重编 + 开机冒烟（守则不变）；若再现 4005，**先 `NAIZ_AE_PAD=0..4` 扫装载地址偏移**即可判定是否地址敏感，不必再怀疑 fixup 记录。
- 抓屏冒烟两条教训：① 手动 inject 与 `makegame make` 的 AUTOEXEC **不同**（`NAIZ_PACK` 分支），对照实验必须用同一条注入路径；② 判定启动成功前必须 kill_stale + 同命令内启动并抓屏，防残留窗口假阳性。

**新工具**：`tmp_le/sim_loader.py`（LE 加载器仿真，已随 c5187e6 出库、当前不可复跑）；`tools/diag/np2kai_smoke_fifo.py`（无 pty 环境冒烟替代）。剧情实机冒烟（§九 第 4 项）由用户人工执行。

### 11.7 2026-11-16 复发（接 212）

0.4.033 落地后，vclock 等改动把镜像从 245232 推到 245500 B，**同一枚 `-os` 引擎在 `SET DOS16M=1`
已在位的情况下再次 fatal 4005**（串口 0 字节）；`NAIZ_AE_PAD=1..4` 均能启动。即 §11.5 的「写一行
撑大 AUTOEXEC」只是过拟合到当时的装载地址，镜像一变即失效。0.4.034 起改为 openpack 链生产
AUTOEXEC 固定垫行 `REM naiz ae pad`，详见 `devdocs/212-DOS32A装载地址敏感复发与AUTOEXEC垫行兜底.md`
（判定矩阵、守则、方案 C 计划）。**本文 §11.5 的机理描述仍成立，但其「修复」表述已被 212 取代。**

**硬约束**：改 `core/Makefile` 任何编译旗标后必须 `rm -rf core/build` 全量重编；任何体积/布局变化后必须跑一次开机冒烟。
