# 210 — DOS/32A 加载器 fatal 4005 深挖：`-os` LE 镜像被拒绝

> **状态**: 未完结（类级定性已定，记录级未定位）
> **版本**: 0.4.031 落地缓解，0.4.032 补记脚本标注与本文
> **交接**: 2026-11-13（0.4.032）暂停深挖，接手请先读 §十 交接状态
> **关联**: `CHANGELOG.md` c108/c109、devdocs/195 §四 P4、devdocs/196 §六.5、`core/Makefile` `SIZE_OPT`
> **性质**: 第三方加载器（Open Watcom 绑定的 `dos32a.exe`）与 `wlink -os` 输出的兼容缺陷；本仓库内不可修加载器，只能绕开

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

## 九、验收缺口

- [x] 场景 `outlist` 全量显式标注（0.4.032：`nbook001/003/004/006` 补 `outlist`；002 已是 outlist、005 为 onlist；`sceneconf` 无第三字段的 normal 场景已清零）
- [ ] 0.4.032 后全量 `pytest` 复跑（本轮在 bump 后被打断，未执行；0.4.031 基线 931 passed, 2 skipped）
- [ ] 记录级定位（§七 1–2）
- [ ] `-os` 局部恢复可行性（§七 3）
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

1. `python -m pytest -q` 全量复跑（唯一未跑的收口项）。
2. 记录级定位：按 §七 写正确的 LE fixup 解码器，**先用可启动的 `-od` 样本校准逐页对齐**，再解 `/tmp/engine_os.exe` 比对。
3. 剧情实机冒烟（Scene 菜单 1 项 / 播放 / `scene(end)` 回鉴赏 / Back 回 special）。

**接手命令**

```bash
./makegame.sh build demo-a2 && ./makegame.sh make demo-a2   # 重建 + 注入
python -m pytest -q                                          # 全量守卫
./makegame.sh test demo-a2 --serial                          # 开机冒烟（看串口非空、无 4005）
```

**硬约束**：改 `core/Makefile` 任何编译旗标后必须 `rm -rf core/build` 全量重编；任何体积/布局变化后必须跑一次开机冒烟。
