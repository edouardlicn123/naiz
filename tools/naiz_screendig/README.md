# naiz_screendig - NP2kai 截图调试工具

专门用于 NP2kai 模拟器渲染问题的调试工具。

## 功能

- **连续截图序列捕获**：支持 2 秒间隔的自动连续截图
- **自动化分析**：检测颜色问题（如青色偏色）、文本层状态
- **会话管理**：自动创建会话目录，保存所有相关数据
- **基准对比**：与基准图像对比差异
- **HTML 报告生成**：可视化调试报告

## 安装依赖

```bash
pip install Pillow numpy
```

## 使用方法

### 基本连续截图

```bash
# 2 秒间隔，无限截图（Ctrl+C 停止）
python -m naiz_screendig -c

# 3 秒间隔
python -m naiz_screendig -c -i 3

# 截图 20 张后停止
python -m naiz_screendig -c -n 20
```

### 带分析的连续截图

```bash
# 自动分析所有截图
python -m naiz_screendig -c --analyze

# 30 秒连续截图并分析
python -m naiz_screendig -c -d 30 --analyze

# 20 张截图，对比基准图像
python -m naiz_screendig -c -n 20 --analyze --baseline /path/to/baseline.png
```

### 启动模拟器

```bash
# 自动启动模拟器并调试 60 秒
python -m naiz_screendig --launch -c -d 60 --analyze

# 启动模拟器，截图 30 张
python -m naiz_screendig --launch -c -n 30 --analyze
```

### 单次截图（兼容原工具）

```bash
# 单次截图
python -m naiz_screendig -o /tmp/screenshot.png

# 等待 5 秒后截图
python -m naiz_screendig -o /tmp/screenshot.png -w 5

# 分析单张截图
python -m naiz_screendig -o /tmp/screenshot.png --analyze --baseline /path/to/baseline.png
```

## 输出结构

```
/tmp/naiz_screendig/
└── session_20260603_143025/
    ├── screenshot_143025_123.png
    ├── screenshot_143027_456.png
    ├── ...
    ├── session_data.json
    ├── report.html
    └── README.txt
```

### session_data.json

```json
{
  "session_id": "20260603_143025",
  "start_time": "/tmp/naiz_screendig/session_20260603_143025",
  "screenshots": [
    {
      "filename": "screenshot_143025_123.png",
      "timestamp": "143025_123",
      "elapsed": 0.123,
      "size": 7441
    }
  ],
  "analysis": {
    "screenshot_143025_123.png": {
      "color": {
        "mean": [123, 254, 200],
        "issues": ["red_channel_low"]
      },
      "text": {
        "edge_density": 0.032,
        "text_layer_present": false
      }
    }
  }
}
```

### report.html

自动生成的 HTML 调试报告，包含：
- 截图序列展示
- 颜色统计和问题检测
- 文本层检测结果
- 基准对比相似度

## 主要分析功能

### 1. 颜色平衡分析

检测常见的颜色问题：
- **red_channel_low**：R 通道异常低（青色偏色）
- **near_white**：接近全白
- **near_black**：接近全黑

### 2. 文本层检测

基于边缘密度的简单检测：
- edge_density：边缘密度值
- text_layer_present：是否检测到文本层

### 3. 基准对比

与指定基准图像对比：
- diff_mean：差异均值
- diff_max：最大差异
- similarity：相似度 (0-1)

## API 使用

```python
from tools.naiz_screendig import ScreenDig

# 创建调试器
screendig = ScreenDig(output_dir="/tmp/my_debug")

# 运行调试会话
result = screendig.run_debug_session(
    interval=2.0,
    count=20,
    analyze=True,
    baseline_path="/path/to/baseline.png"
)

# 访问会话数据
print(f"Session ID: {result['session_id']}")
print(f"Screenshots: {len(result['screenshots'])}")
```

## 注意事项

1. **磁盘空间**：连续截图会产生大量文件，请注意磁盘空间
2. **窗口权限**：需要 xdotool 和 ImageMagick (import) 工具
3. **时间精度**：截图间隔基于系统时间，精度有限
4. **分析准确性**：文本层检测算法较简单，可能需要调整阈值

## 依赖工具

```bash
# xdotool - 窗口管理
sudo apt install xdotool

# ImageMagick - 截图捕获
sudo apt install imagemagick

# Python 依赖
pip install Pillow numpy
```

## 示例场景

### 场景 1：诊断启动过程

```bash
# 自动启动模拟器，捕获启动前 30 秒
python -m naiz_screendig --launch -c -d 30 --analyze
```

### 场景 2：对比修复前后

```bash
# 修复前基准
python -m naiz_screendig -o baseline.png

# 修复后调试
python -m naiz_screendig -c -n 5 --analyze --baseline baseline.png
```

### 场景 3：定时监控

```bash
# 每 3 秒截图 100 张（5 分钟）
python -m naiz_screendig -c -i 3 -n 100 --analyze
```

## 故障排除

### No NP2kai windows found

检查：
1. NP2kai 是否正在运行
2. 使用 `--list-windows` 查看可用窗口
3. 确保窗口标题包含 "NP21kai" 或 "np21kai"

### xdotool not found

安装 xdotool：
```bash
sudo apt install xdotool
```

### import failed

检查 ImageMagick 是否正确安装：
```bash
which import
```

## 技术细节

- **窗口查找**：使用 xdotool 获取窗口信息
- **截图捕获**：使用 ImageMagick import 命令
- **图像处理**：使用 Pillow 和 NumPy
- **报告生成**：动态 HTML 生成

## 许可证

遵循项目主许可证。

## 更新日志

### v1.0.0 (2026-06-03)

- 首次发布
- 支持连续截图
- 支持基本分析功能
- 支持 HTML 报告生成
