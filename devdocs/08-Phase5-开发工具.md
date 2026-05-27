# Phase 5：开发工具

## 目标

提供脚本编辑器 GUI，实现可视化编辑场景脚本，并可一键编译 + 预览。

## 前置依赖

- ✅ Phase 4 完成（数据管线可用）

## 参考项目

| 项目 | 查阅内容 | 用途 |
|------|----------|------|
| xsystem35-sdl2 | GPL v2，仅参考 | 脚本编辑/预览工具设计思路 |

## 实施步骤

### Step 1：脚本编辑器 GUI

`tools/editor/` — Python GUI 应用。

功能：
- `.mhn` 脚本语法高亮
- 场景结构树形浏览（.scene / label / 指令大纲）
- 一键编译（调用 Phase 4 script_compiler + linker）
- 预览窗口：编译后自动启动 NP2kai 运行 `engine.exe` + `out/` 数据
- 变量/标志清单可视化
- 文本条目编辑（支持 UTF-8 + 格式化转义序列）

- [ ] `tools/editor/` — 语法高亮 + 编辑
- [ ] `tools/editor/` — 场景导航树
- [ ] `tools/editor/` — 编译 + NP2kai 预览集成

### Step 2：工作流验证

- 用编辑器创建/修改一个简单场景
- 编译 → 复制到 NP2kai → 运行
- **✅ M5**：不用写一行二进制即可做出简单场景

- [ ] 编辑-编译-预览全流程验证
- [ ] **✅ M5** 确认

## 产出物

```
tools/editor/            ← 脚本编辑器 GUI
```

## 验证

回到 `03-编译example项目方案.md` 确认 M5 里程碑。
