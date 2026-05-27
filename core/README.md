# MHN Engine (PC-98 Galgame Engine)

## 目录说明

- `engine/` — 跨平台核心逻辑
- `data/` — 数据格式解码器
- `plat/` — 平台抽象层 (HAL)
- `build/` — 构建输出
- `Makefile` — 构建文件（待创建）

## 文件版权注释规则

所有 `core/` 下的源文件，如果其代码**复制或改编自 ref_projects/ 中的参考项目**，必须在文件开头添加注释块：

```c
/*
 * 来源项目：<项目名称>
 * GitHub:   <GitHub URL>
 * 许可证：   <许可证类型>
 */
```

如果是独立新写的文件则无需添加。详见 `AGENTS.md`。
