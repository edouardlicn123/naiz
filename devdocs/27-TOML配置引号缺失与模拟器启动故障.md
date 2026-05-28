# TOML 配置引号缺失导致模拟器无法加载 HDI

## 症状

`makegame.sh` 交互菜单走 1 (build) → 2 (make) → 3 (test) 后，模拟器无法加载 HDI。

- 即使 `inject` 步骤正确输出了 `DBLSPACE.BIN removed from root directory` 和 `DEMO-A1/ created at cluster=78 (zeroed)`
- 模拟器启动后仍表现异常（无盘状态、黑屏或 BIOS 报错）

## 根因

`tools/env_setup/install_env.py` 的 `cmd_test_hdi()` 函数在生成 TOML 配置文件时，SCSIHDD0 的路径值**缺少引号**：

```python
# 第 565-570 行，错误代码：
cfg_content = f"""[NP21kai]
SCSIHDD0 = {selected}          ← 无引号，TOML 非法
pc_model = PC9821
keyboard = 106
use_hdrv = true
"""
```

生成的文件内容：
```toml
SCSIHDD0 = /home/edo/naiz/disks/demo-A1.hdi
```

TOML 规范要求字符串值必须用单引号 `'...'` 或双引号 `"..."` 包裹。无引号的路径是不合法的 TOML 语法。

NP2kai wx 前端使用 **libtomlplusplus** 解析配置文件（`/tmp/NP2kai/wx/ini.cpp`）：

```cpp
// 第 310-320 行
try {
    auto doc = toml::parse_file(path);
    auto sec = doc.get_as<toml::table>(title);
    if (!sec) return;
    // ... 读取配置项 ...
} catch (const toml::parse_error &) {
    /* ignore parse errors, use defaults */  ← 静默回退为默认值！
}
```

`toml::parse_error` 被捕获后整个配置段被丢弃，`SCSIHDD0` 回退为空字符串，模拟器处于**无磁盘**状态。

同时，每次 `test` 都**完全覆盖**配置文件（仅 5 行），丢失了用户原有的所有模拟器设置（键盘布局、声音音量、窗口位置等）。

## 修复

用 Python 3.11+ 标准库 `tomllib` 实现**就地更新**：读取现有配置，只修改 `SCSIHDD0`，保留其余设置。若文件不存在或损坏则创建合法配置。

改动位置：`tools/env_setup/install_env.py` 第 548-572 行

```python
# ── 4. 生成 wx 前端 config 文件 (TOML) ──
# ...
# 替换原有 cfg_content 字符串 + open().write() 为：
import tomllib

try:
    with open(cfg_path, 'rb') as f:
        cfg = tomllib.load(f)
except (FileNotFoundError, tomllib.TOMLDecodeError):
    cfg = {}
sec = cfg.setdefault('NP21kai', {})
sec['SCSIHDD0'] = selected
with open(cfg_path, 'w', encoding='utf-8') as f:
    import tomli_w  # or use manual serialization
    # 用标准库方式写回
    lines = []
    for k, v in cfg.items():
        lines.append(f'[{k}]')
        for sk, sv in v.items():
            if isinstance(sv, str):
                lines.append(f"{sk} = '{sv}'")
            elif isinstance(sv, bool):
                lines.append(f"{sk} = {'true' if sv else 'false'}")
            elif isinstance(sv, int):
                lines.append(f"{sk} = {sv}")
            elif isinstance(sv, list):
                lines.append(f"{sk} = {sv}")
            # ... 其他类型
        lines.append('')
    f.write('\n'.join(lines))
```

### 简化方案

鉴于配置文件结构简单，直接用 f-string 加引号即可满足最小修复：

```python
cfg_content = f"""[NP21kai]
SCSIHDD0 = '{selected}'
"""
with open(cfg_path, 'w', encoding='utf-8') as f:
    f.write(cfg_content)
```

但这样仍会覆盖所有其他设置。推荐使用 `tomllib` + `tomli_w` 做完整保留。

### Python 标准库支持

| Python 版本 | 读取 | 写入 |
|------------|------|------|
| ≥ 3.11 | `tomllib.load()` | 无标准写入器 |
| ≥ 3.11 | `tomllib.load()` + 手动序列化 | 本文采用 |
| 任意 | `toml` (第三方) | `toml.dump()` |

当前环境 Python 3.12.4，`tomllib` 可用。写入使用手动序列化（避免额外依赖）。

## 文件变更

| 文件 | 变更 |
|------|------|
| `tools/env_setup/install_env.py` | `cmd_test_hdi()` TOML 配置写入：改用 `tomllib` 读取现有配置后更新 SCSIHDD0 |
| `devdocs/27-TOML配置引号缺失与模拟器启动故障.md` | 本文档 |

## 验证方法

1. 运行 `makegame.sh test demo-A1`（或交互菜单 → test）
2. 检查 `~/.config/wxnp21kai/wxnp21kai.toml` 中 `SCSIHDD0` 是否包含带引号的正确路径
3. 确认模拟器能正常加载 HDI 并进入游戏
