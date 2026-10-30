# devdoc 185：Naiz 部署双管线——开源资源包与开源基座（可选择，不取代）

**日期**：2026-10-28
**状态**：规划阶段，未开始实施（本文档不含代码）
**与 devdoc 178 关系**：178 是"替换什么"（组件级规划），本文是"怎么并存"（管线级架构）。178 的阶段产物直接成为本管线的资源与配置来源。
**设计前提**（用户明确的两条现状约束）：
1. 商业资源走 GitHub repo（naiz_cmpack Releases）+ start.sh 下载——开源方案照搬这套思路
2. 维持"~45M 基座镜像 → 注入游戏包 → 测试运行"的工作流不变

---

## 一、现状盘点（本方案的对齐基线）

| 环节 | 现有实现 | 关键位置 |
|---|---|---|
| 资源分发 | `start.sh commercial` 子命令，`COMMERCIAL_DOWNLOADS` 数组（描述\|URL\|sha256）→ 下载 `tools_commercial.zip`（GitHub Releases `edouardlicn123/naiz_cmpack` v1.1）→ 解压到项目根 | [start.sh:152-199](file:///home/edo/naiz/start.sh#L152-L199) |
| 路径常量 | `COMMERCIAL_DIR` / `COMMERCIAL_BASE_HDI` / `COMMERCIAL_DOS_DIR` | [naiz_lib/\_\_init\_\_.py:12-21](file:///home/edo/naiz/tools/naiz_lib/__init__.py#L12-L21) |
| 基座镜像 | `tools_commercial/base_msdos5_scsi_48m_clean.hdi`（MS-DOS 5.0，48MB，FAT16，SCSI，只读母版，每次复制后增量编辑） | B06 规范 §基座 |
| 系统文件部署 | build_game.py 从 `COMMERCIAL_DOS_DIR` 部署 DOS4GW/VEM486/CTMOUSE | [build_game.py:354](file:///home/edo/naiz/tools/naiz_build/build_game.py#L354) |
| 注入工具 | `tools/naiz_img/inject.py`，**`-b/--base` 已支持基座覆盖**，默认值来自 naiz_lib | [inject.py:41](file:///home/edo/naiz/tools/naiz_img/inject.py#L41) |
| DOS 配置注入 | inject_common.py 硬编码生成 CONFIG.SYS（`DEVICE=A:\VEM486.EXE /U`）与 AUTOEXEC.BAT | [inject_common.py:26-42](file:///home/edo/naiz/tools/naiz_img/inject_common.py#L26-L42) |
| git 忽略 | `.gitignore` 忽略 `tools_commercial/` 与 `tools_commercial.zip` | [.gitignore:36-37](file:///home/edo/naiz/.gitignore#L36-L37) |

**关键利好**：注入工具已经参数化基座（`-b`），双管线在镜像层的切换成本天然很低。

---

## 二、总体架构：一条管线开关，两套资源，同一套工具

```
                         ┌─────────────────────────────────────┐
                         │  chain = commercial（默认，现状零改动）│
  start.sh ── 资源准备 ──┤  tools_commercial/（naiz_cmpack）     │
                         └─────────────────────────────────────┘
                         ┌─────────────────────────────────────┐
                         │  chain = oss（新增，opt-in）           │
                         │  tools_oss/（naiz_osspack，公开 repo） │
                         └─────────────────────────────────────┘
                                        ↓ 同一套工具，仅资源来源不同
        naiz_lib 路径解析（按 chain 选 *_DIR / *_BASE_HDI）
                                        ↓
        build_game.py 部署对应 runtime 文件清单
                                        ↓
        core Makefile 按链出对应 stub 的 engine.exe
                                        ↓
        inject.py -b <对应基座> → CONFIG.SYS/AUTOEXEC 按管线模板
                                        ↓
        NP2kai 测试（流程完全不变）
```

**不取代的保证**：所有现有函数/常量默认值继续指向 commercial 路径；`chain` 不设置时走的代码路径与今天逐字节相同。oss 分支全部是"新增分支 + 新增常量 + 新增模板"，不改商业分支的任何既有取值。

---

## 三、资源层：naiz_osspack 公开仓库（对标 naiz_cmpack）

### 3.1 结构设计

| 项 | naiz_cmpack（商业，现状） | naiz_osspack（开源，新增） |
|---|---|---|
| 可见性 | 按现状（release 下载） | **公开 repo**——内容全部可再分发 |
| 分发物 | tools_commercial.zip | tools_oss.zip |
| 解压位置 | `./tools_commercial/` | `./tools_oss/` |
| 内部结构 | dos_system/ + base_msdos5_scsi_48m_clean.hdi + pc9821bios/ | dos_system/ + base_freedos98_scsi_48m_clean.hdi + licenses/ |
| start.sh 入口 | `commercial` 子命令 + `COMMERCIAL_DOWNLOADS` 数组 | 新增 `oss` 子命令 + `OSS_DOWNLOADS` 数组（同一格式：描述\|URL\|sha256） |

### 3.2 dos_system/ 内容清单（对应 178 的替换表）

| 文件 | 来源（已克隆在 /media/edo/data/source） | 许可 | 备注 |
|---|---|---|---|
| KERNEL.SYS | lpproj/fdkernel（nec98test，fdkernel_dbcs bin 包）或 tori kernel 2035a | GPL v2 | 首选 lpproj 版（活跃、DBCS） |
| COMMAND.COM | lpproj FreeCOM DBCS | GPL 等 | freecom_dbcswip bin 包 |
| FDXMS.SYS | tori fdxms（2004/9/10） | **待确认**（zip 内 readme） | tori 版对 PC-98 布局验证最充分 |
| HIMEMX98.EXE | lpproj/himemx.nec v3.34 | GPL | FDXMS 的备选 |
| EMM386.EXE | tori emm386（2005/2/23）或 lpproj/emm386.nec v2.26 | **待确认** / GPL | 178 阶段 2 的胜出者 |
| CTMOUSE.COM | FDOS/mouse CuteMouse 2.1 | GPL v2 | 与商业链同文件，可复用 |

### 3.3 许可合规要点

- GPL 组件（kernel/FreeCOM/CTMOUSE/HIMEMX）：分发二进制须**附带许可文本 + 源码获取途径**。我们若不修改，`licenses/` 里放 LICENSE 文件 + upstream URL 即满足 GPL 的"源码可达"要求
- tori 组件（fdxms/emm386）分发条款必须在打包前确认——若不允许再分发，则 naiz_osspack 不内置，改为 start.sh oss 下载时**直链 tori 原站**（与 COMMERCIAL_DOWNLOADS 数组同构，多一条直链下载项即可）
- 引擎侧：CauseWay 是 Public Domain，无义务；Naiz 引擎本身的许可按用户意愿另行处理（不在本方案范围）

---

## 四、镜像层：开源版 48MB 基座（维持注入思路）

目标产物：`tools_oss/base_freedos98_scsi_48m_clean.hdi`——**与商业基座同规格**（48MB / FAT16 / SCSI / 同分区几何），使现有注入工具与测试流程零适配。

### 路线 A（推荐）：现有基座原地换血

1. 复制 `base_msdos5_scsi_48m_clean.hdi` → 新母版
2. 用现有 naiz_img FAT 编辑能力：删除 MS-DOS 系统文件（IO.SYS/MSDOS.SYS/COMMAND.COM），写入 FreeDOS(98) KERNEL.SYS/COMMAND.COM/驱动
3. 重写引导扇区为 FreeDOS(98) 引导代码（SYS 工具或手工写 VBR）
4. 预写按 178 §5.2.1 胜出配置的 CONFIG.SYS / AUTOEXEC.BAT
5. NP2kai 裸启动验证（进 DOS 提示符 + `MEM` 输出正确）

- 优点：几何/引导链（SCSI）与商业基座完全一致，注入侧零适配；48MB 体积不变
- 风险：FreeDOS(98) 对该镜像的 SCSI HDD 引导兼容性——lpproj 官方 fd98_hd_250m 本身就是 HDI 硬盘引导形态，可行性高，但需实测

### 路线 B（fallback）：lpproj fd98_hd_250m 裁剪到 48MB

- 优点：官方已验证可引导
- 缺点：HDI 几何/分区表需要收缩改造，工具侧假定的 48M 布局要适配，工作量大

**结论**：先 A 后 B。A 失败才走 B。

---

## 五、构建与注入层：chain 开关

### 5.1 开关形态（实施时二选一，倾向前者）

- 环境变量 `NAIZ_DOS_CHAIN=commercial|oss`（缺省 commercial）
- 或 makegame.sh / build_game.py / inject.py 增加 `--chain` 参数贯通传递

### 5.2 受影响的注入点（全部是"按 chain 分支"，非重写）

| 位置 | 商业分支（现状不动） | oss 分支 |
|---|---|---|
| naiz_lib 常量 | `COMMERCIAL_*`（现状） | 新增 `OSS_DIR` / `OSS_BASE_HDI` / `OSS_DOS_DIR` |
| build_game.py 部署清单 | `("DOS4GW.EXE","VEM486.EXE","CTMOUSE.COM")` | `("KERNEL.SYS","COMMAND.COM","FDXMS.SYS","EMM386.EXE","CTMOUSE.COM",...)` |
| core Makefile 链接 | `-l=dos4g`（现状） | `-l=causeway`（178 阶段 1 的改动，以链接变量/第二目标形式并存，**不删 dos4g 目标**） |
| inject_common.py CONFIG.SYS | `DEVICE=A:\VEM486.EXE /U` 模板 | 178 §5.2.1 胜出配置模板 |
| inject_common.py AUTOEXEC | `SET DOS16M=1 + CTMOUSE + engine.exe` | 去掉 DOS16M，其余同构 |
| inject.py 基座 | DEFAULT_BASE（商业） | `-b tools_oss/base_freedos98_...hdi`（参数已存在，无需改） |

### 5.3 engine.exe 双 stub 并存

商业链与开源链的 engine.exe 不通用（stub 不同）。实施形态建议：Makefile 以链接变量区分，产出两个产物（如 engine.exe = dos4g、engine_cw.exe = causeway），makegame.sh 按 chain 选用。**商业测试的现有产物命名不变**。

---

## 六、降级场景：半开源管线

若 178 阶段 2 全败（无 VEM486 替代）：

- naiz_osspack 的 dos_system/ 不含 VEM486（闭源不可再分发）
- oss 管线的 runtime 清单里 VEM486 仍从 `tools_commercial/dos_system/` 取——即 chain=oss 时**允许跨包引用这一个文件**
- 用户侧表现：装 oss 管线仍需商业包里的 VEM486.EXE 一个文件；管线架构与开关不受影响
- 此场景写入 naiz_osspack README 明示

---

## 七、实施阶段（不含代码）

| 阶段 | 内容 | 前置 | 产出 |
|---|---|---|---|
| **O1** | naiz_osspack 仓库筹备（结构 + licenses/ + 许可确认，尤其 tori 组件）+ start.sh 增 oss 子命令 | 无 | 可下载的空/半满包 |
| **O2** | 开源基座制作（路线 A）+ 裸启动验证 | 178 阶段 2 的胜出 CONFIG.SYS | base_freedos98_scsi_48m_clean.hdi |
| **O3** | chain 开关贯通（naiz_lib 常量 → build_game 清单 → Makefile 双 stub → inject 模板） | O1、O2；引擎侧依赖 178 阶段 1（CauseWay） | `--chain oss` 端到端可跑 |
| **O4** | 端到端测试：注入游戏 → bootmenu → BGM（含 176 ISR 剖面复测）→ transition → image_load | O3 | 测试记录 |
| **O5** | tools_oss.zip 打包上 Release + sha256 固化进 start.sh + README（含许可清单与半开源说明） | O4 通过 | 正式发布 |

**并行关系**：O1 与 178 阶段 1（CauseWay 切换）完全独立可并行；O2 依赖 178 阶段 2 的配置结论；O3/O4/O5 串行。

---

## 八、风险汇总

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| tori 组件（fdxms/emm386）再分发条款不允许 | 中 | oss 包缺核心驱动 | 换 lpproj 系（GPL）或 start.sh 直链 tori 原站 |
| FreeDOS(98) 在 48M SCSI 基座上引导失败 | 低-中 | 路线 A 失败 | 路线 B 裁剪官方 250M HDI；或复用 lpproj 官方引导结构改造 |
| GPL 合规疏漏 | 低 | 法律瑕疵 | licenses/ 目录制度化：每个二进制对应 LICENSE + upstream URL，O1 阶段完成 |
| 双 stub engine 产物混淆导致 HDI 塞错引擎 | 低 | 测试假象 | makegame.sh 按 chain 强制校验 exe 的 stub 签名（现有 B05 已有 LE 头检查惯例） |
| VEM486 无替代（178 阶段 2 全败） | 中 | oss 管线半开源 | 见第六节，架构不受影响 |

---

## 九、与现有文档的关系

- devdoc 178：组件替换规划——其阶段 1/2/3 的产出分别是本方案 O3（stub）、O2（CONFIG.SYS）、O3（清单）的输入
- B06-HDI 注入规范：需在实施 O3 时补"开源基座"章节（基座路径、CONFIG.SYS 模板差异）——届时更新，不在本规划内提前写
- A01 §`-b/--base`：已参数化，本方案直接受益，无需改动

---

## 十、实施注记（2026-10-28 首批落地）

| 规划项 | 实际落地 | 差异说明 |
|---|---|---|
| 资源仓库 | **naiz-openpack**（github.com/edouardlicn123/naiz-openpack，已本地提交 85eeda6，待用户推送） | 命名从 naiz_osspack 改为 naiz-openpack |
| 资源目录 | `tools_open/`（对应 `tools_commercial/`），zip 内带顶层目录 | 命名从 tools_oss 改为 tools_open |
| 打包脚本 | naiz-openpack `make_openpack.sh` → `~/tools_open.zip` + SHA256 | 首包 312KB，SHA256 `984bcc20…070f5`，待用户上传 Release |
| start.sh 下载项 | **待办**——等用户提供 Release URL 后写入 `OSS_DOWNLOADS`（同 `COMMERCIAL_DOWNLOADS` 结构） | |
| 自动选择 | **已落地（目录级）**：[naiz_lib/\_\_init\_\_.py](file:///home/edo/naiz/tools/naiz_lib/__init__.py) 新增 `TOOLS_OPEN_DIR`/`OPEN_DOS_DIR`/`OPEN_BASE_HDI` + `resolve_dos_dir()`/`resolve_base_hdi()`；[build_game.py:352](file:///home/edo/naiz/tools/naiz_build/build_game.py#L352)、[inject_common.py:21](file:///home/edo/naiz/tools/naiz_img/inject_common.py#L21)、[read_fat16.py:16](file:///home/edo/naiz/tools/diag/read_fat16.py#L16) 已接入；`.gitignore` 已加 `tools_open/` | 优先 tools_open，目录/文件不存在则回退 tools_commercial；BIOS 目录仍固定商业源 |
| 首包内容 | dos_system/ 11 文件：KERNEL.SYS（lpproj）+ KWC8632.SYS + KERNEL35A.SYS（tori 对照）+ COMMAND.COM（FreeCOM DBCS）+ FDXMS.SYS（tori）+ HIMEMX.EXE（lpproj）+ EMM386.EXE（tori）+ CTMOUSE.COM（2.1b4）+ MEM.EXE + COUNTRY.SYS + SYS.COM；licenses/ 逐组件许可 + SOURCES.md 对照表 | CTMOUSE.COM 2.1b4 已获得（FreeDOS 1.4 仓库 icm 镜像），上游为 CTMOUSE.EXE 改名（MZ 头判别） |
| 基座镜像 | 未制作（O2，依赖 178 阶段 2 结论） | `OPEN_BASE_HDI` 常量已就位，镜像放入 tools_open/ 根即自动生效 |
