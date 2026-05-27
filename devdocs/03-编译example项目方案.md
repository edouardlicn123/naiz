# 编译 example 项目方案 — 数据编译与集成验证

## 目标

在 NP2kai 上成功运行 `projects/example/` 的场景，验证各 Phase 产出能正确联动。

## 本文档的角色

本文档是**集成验证总纲**，不重复各 Phase 的实现细节。每个 Phase 的具体实施步骤见对应文档：

| 阶段 | 文档 | 产出 |
|------|------|------|
| 数据编译（Phase A） | 本文档 §A | `out/ROOTINFO.DAT` 等运行时数据 |
| 引擎基础 | `04-Phase1-引擎基础.md` | `engine.exe` + NP2kai Hello World |
| 核心引擎系统 | `05-Phase2-核心引擎系统.md` | 完整场景运行 |
| 音频系统 | `06-Phase3-音频系统.md` | BGM + SE 播放 |
| Python 工具链 | `07-Phase4-工具链.md` | 自研数据编译工具 |
| 开发工具 | `08-Phase5-开发工具.md` | 脚本编辑器 GUI |
| 跨平台移植 | `09-Phase6-跨平台移植.md` | SDL2 后端 |

## Phase A — 数据编译

用 MHVN98 原工具链（临时过渡）编译 example 素材，产出引擎要加载的运行时格式。

### A1：安装宿主依赖

```bash
sudo apt install build-essential liblz4-dev
```

### A2：编译 MHVN98 工具链

```bash
mkdir -p tools/mhvn_build

# mhvnscas — 场景脚本编译器
make -C ref_projects/MHVNVisualNovelEngine/MHVNSCAS
cp ref_projects/MHVNVisualNovelEngine/MHVNSCAS/bin/mhvnscas tools/mhvn_build/

# mhvntxar — 文本存档编译器
make -C ref_projects/MHVNVisualNovelEngine/MHVNTXAR
cp ref_projects/MHVNVisualNovelEngine/MHVNTXAR/bin/mhvntxar tools/mhvn_build/

# mhvnimgp — 图像打包器
make -C ref_projects/MHVNVisualNovelEngine/MHVNIMGP
cp ref_projects/MHVNVisualNovelEngine/MHVNIMGP/bin/mhvnimgp tools/mhvn_build/

# mhvnlink — 数据链接器
make -C ref_projects/MHVNVisualNovelEngine/MHVNLINK
cp ref_projects/MHVNVisualNovelEngine/MHVNLINK/bin/mhvnlink tools/mhvn_build/
```

### A3：编译 example 数据

```bash
cd projects/example
PATH="../../tools/mhvn_build:$PATH" make
```

产出 `out/` 目录：

| 文件 | 说明 |
|------|------|
| `ROOTINFO.DAT` | 引擎配置 |
| `SCENE.DAT` | 场景字节码（LZ4 压缩） |
| `EN_GB.otxa` | 英文文本存档 |
| `JA_JP.otxa` | 日文文本存档 |
| `BGIMAGE.DAT` | 背景图像 |
| `SPRITE.DAT` | 精灵数据 |
| `SYSTEM.DAT` | 系统数据 |

**里程碑 M0**：`ls out/ROOTINFO.DAT` 存在。

## 集成验证流程

每个里程碑都依赖前置 Phase 完成，回到本文档验证整体集成。

| 里程碑 | 依赖 Phase | 验证方式 |
|--------|-----------|----------|
| M0 | Phase A | `ls out/ROOTINFO.DAT` |
| M1 | Phase 1 | NP2kai 显示 Hello World |
| M2 | Phase 2 | 完整场景（背景 + 对话 + 选项 + 分支） |
| M3 | Phase 3 | 场景中有 BGM/SE |
| M4 | Phase 4 | 用自研工具链重复 A2-A3，产出一致 |
| M5 | Phase 5 | 脚本编辑器修改 → 重新编译 → NP2kai 运行 |
| M6 | Phase 6 | 同一场景在 SDL2 窗口上运行 |

### 验证步骤

每个里程碑验证时：

```
1. 确认前置 Phase 所有 checkboxes 已完成
2. 确认 out/ 数据已用最新数据编译
3. 将 engine.exe + out/ 复制到 NP2kai 虚拟磁盘
4. 启动 NP2kai，观察行为是否符合预期
```

## 依赖关系图

```
tools/mhvn_build/          core/engine.exe
    ├── mhvnscas                ↑
    ├── mhvntxar           Phase 1~3 逐步构建
    ├── mhvnimgp
    └── mhvnlink

projects/example/
    ├── *.sca ──→ mhvnscas ──→ SCENE.DAT
    ├── *.txt ──→ mhvntxar ──→ *.otxa
    └── images/ ─→ mhvnimgp ─→ BGIMAGE.DAT
                    └── mhvnlink ─→ out/ (含 ROOTINFO.DAT)
                                    │
                    engine.exe ←────┘
```
