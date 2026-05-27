# PC-98 BIOS 设置计划

## 问题
- NP2kai 模拟器启动后系统卡死
- 模拟器完成内存检测后卡死
- 原因：缺少 FONT.ROM 和 SDL 视频驱动冲突

## 步骤

### 1. 获取 PC-98 BIOS 文件
- 从 `https://github.com/Abdess/retrobios` 下载
- 需要的文件：`FONT.ROM`, `ROM.ROM`

### 2. 创建目录并复制文件
- 目标：`tools/pc98bios/`

### 3. 修改 NP2kai 配置
- 文件：`core/sdlnp21kai/np21kai.cfg`
- 添加 `biospath` 和 `fontfile` 配置项

### 4. SDL 视频驱动自动检测
- 统一入口：`tools/sdl_env.sh`
- 所有启动脚本（`start.sh`, `testtemp.sh`, `tools/nhd_tool/inject_and_test.sh`）均通过 `source tools/sdl_env.sh` 引入
- 自动检测逻辑：
  - Wayland → `SDL_VIDEODRIVER=wayland`
  - X11 → 不强制指定，让 SDL 自动选择
  - 无显示服务器 → 发出警告
- 音频统一使用 PulseAudio，不可用时 SDL 自动 fallback

### 5. 验证 HDI 镜像
- 检查 `tools/DOS62.hdi` 引导扇区是否合法
