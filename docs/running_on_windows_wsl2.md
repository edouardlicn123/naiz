# 在 Windows 上用 WSL2 + WSLg 运行打补丁的 wxnp21kai

> **状态**：活跃维护
> **适用场景**：Windows 用户无编译工具链、也不想自己重编 NP21X64W，但遇到 stock NP21X64W 进入游戏后黑屏。
>
> 黑屏根因是 NP2kai 模拟器缺 `grphdisp` / `gdc_analogext` 补丁（`tools/np2kaipatch/` 的 P1–P3）。
> 本项目在 Linux 侧 `start.sh np2kai` 会自动 `git apply` 这 5 个补丁并编译出**已打补丁的 `wxnp21kai`**。
> 本方案不在 Windows 编 NP21X64W，而是改用 WSL2 跑这个 Linux 打补丁二进制，窗口经 WSLg 直接显示在 Windows 桌面。

---

## 1. 前置条件

- Windows 10 21H2 及以上 / Windows 11。
- 管理员 PowerShell 一次：`wsl --install`（装 Ubuntu 与 WSL2）。
  - Win11：WSLg 内建，窗口直接弹出，无需额外 X 服务器。
  - 老 Win10：WSLg 不可用，需装 VcXsrv，并在 WSL2 内 `export DISPLAY=$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}'):0.0`，再启动 X 服务。
- 磁盘：WSL2 内至少需要约 6–8 GB（NP2kai 源码 + 编译 + 依赖）。

---

## 2. 一次性环境搭建（在 WSL2 内）

打开 Ubuntu（WSL2）终端，把仓库放进 **WSL2 自己的 Linux 文件系统**（不要用 `/mnt/c/...`，避免交叉挂载的权限与性能问题）：

```bash
# 推荐：直接克隆（或把已有仓库 cp/mv 到 ~/naiz）
git clone <本仓库地址> ~/naiz
cd ~/naiz

# 系统工具链（wxWidgets / SDL3 构建依赖 / cmake / git 等）
bash start.sh deps

# Open Watcom（编译引擎 engine.exe 需要）
bash start.sh watcom

# Python 虚拟环境 + 依赖（构建管线需要）
bash start.sh pip

# 编译打补丁的 NP2kai（自动 git apply tools/np2kaipatch/*.patch 再 cmake 编 wxnp21kai）
bash start.sh np2kai
```

`start.sh np2kai` 会：

1. 检出 NP2kai `wx_alpha` 到 `/tmp/NP2kai`；
2. 依文件名顺序 `git apply` 5 个补丁（已应用则跳过，可重入）；
3. 编译 `wxnp21kai` 并安装到 `/usr/local/bin/wxnp21kai`。

> 若补丁因上游 `wx_alpha` 漂移而 `git apply` 失败，`start.sh np2kai` 会报错退出。
> 此时需回到 `tools/np2kaipatch/` 重定位补丁上下文（rebase）后重跑。

---

## 3. 构建游戏并运行

在 WSL2 内（仍在 `~/naiz`）：

```bash
# 编译游戏数据 + 注入 HDI
bash makegame.sh build demo-a2

# 启动打补丁的 wxnp21kai（WSLg 窗口会直接出现在 Windows 桌面）
bash makegame.sh test demo-a2
```

可选调试开关：`bash makegame.sh test demo-a2 --serial`（串口输出到 PTY，用于排查）。

---

## 4. 在 Windows 桌面一键运行（`run_wsl2.bat`）

项目根目录已提供 `run_wsl2.bat`，在 Windows 资源管理器双击即可：

```bat
run_wsl2.bat            # 默认游戏 demo-a2
run_wsl2.bat animatest # 指定游戏
```

它的实质是调用 WSL2 执行与第 3 节相同的命令：

```bat
wsl.exe bash -lc "cd \"$(wslpath -u '%~dp0')\" && bash makegame.sh build %GAME% && bash makegame.sh test %GAME%"
```

前提（一次性）：

- 已按第 2 节在 **WSL2 默认发行版** 完成 `start.sh np2kai` 等环境搭建；
- 仓库存在于 WSL2 可访问路径（`run_wsl2.bat` 通过 `wslpath -u` 把自身的 Windows 路径转成 WSL 路径 `cd` 进去，因此仓库放在 Windows 侧也能用，只是首次编译会慢一些）。

> 多 WSL 发行版时，可把 `wsl.exe` 改成 `wsl.exe -d <发行版名>`。

---

## 5. 常见问题

| 症状 | 可能原因 | 处理 |
|------|----------|------|
| 窗口不弹出 / DISPLAY 错 | 老 Win10 无 WSLg | 装 VcXsrv 并设 `DISPLAY` |
| `wcl386: command not found` | 未跑 `start.sh watcom` | 回到第 2 节补装 |
| `git apply` 失败 | 上游 `wx_alpha` 漂移 | rebase `tools/np2kaipatch/` 后重跑 `start.sh np2kai` |
| 仍黑屏（但本机 Linux 正常） | 用了 unpatched NP21X64W 而非 WSL2 的 wxnp21kai | 确认是双击 `run_wsl2.bat` / 在 WSL2 内 `makegame.sh test`，而非 Windows NP21X64W |
| 编译极慢 | 仓库在 `/mnt/c` 交叉挂载 | 把仓库移入 WSL2 家目录 `~/naiz` |

---

## 6. 与替代方案对比

- **方案 A（未采用）**：Windows 装 Visual Studio + vcpkg 重编打补丁版 NP21X64W。最贴近原生 Windows，但需一次性装大型工具链。
- **方案 C（已否决）**：从引擎侧绕开补丁。不可行——`grphdisp` 标志位是模拟器内部行为，引擎无 I/O 可触发；`gdc_analogext` 即使能绕也不彻底且会偏离真机正确代码。
- **本方案**：零 Windows 编译、复用项目既有打补丁二进制，黑屏根因已在 Linux 侧解决。
