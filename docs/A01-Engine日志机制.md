# Engine 运行时日志机制

## 概述

Engine 在 MS-DOS 下运行时通过 HAL 层的 DOS INT 21h 文件操作，在游戏目录 `A:\DEMO-A1\` 下生成日志文件 `ENGINE.LOG`。测试结束后通过 Python 工具链将该文件从 HDI 镜像中提取到宿主机的 `logs/` 目录，并加上时间戳重命名。

## 数据流

```
Engine（DOS 环境）               宿主机（Linux）
┌──────────────────┐          ┌─────────────────────┐
│ main.c           │          │ inject.py --extract  │
│  │               │          │                      │
│  ↓               │          │ NAIZFatFS            │
│ hal_file_open    │          │  .read_file()        │
│  (INT 21h 3Ch)   │          │                      │
│  ↓               │          │ 将 ENGINE.LOG         │
│ hal_file_write   │          │ → logs/ENGINE.RUN.   │
│  (INT 21h 40h)   │          │      YYYYMMDD.HHMMSS │
│  ↓               │          │       .log           │
│ hal_file_close   │          └─────────────────────┘
│  (INT 21h 3Eh)   │
│  ↓               │
│ ENGINE.LOG       │
│ (C:\DEMO-A1\)    │
└──────────────────┘
```

## HAL 文件 I/O

HAL 层提供 5 个文件操作函数，全部通过 DOS INT 21h 实现：

### `hal_file_open`

| mode | DOS 功能 | 用途 |
|------|----------|------|
| 0 | AH=3Dh, AL=0 | 打开已有文件，只读 |
| 1 | AH=3Ch | 创建/截断新文件，读写 |
| 2 | AH=3Dh, AL=1 → seek to end | 打开已有文件追加 |

返回值：文件句柄（≥0），失败返回 -1。

### `hal_file_read`

- INT 21h AH=3Fh
- 参数：句柄、缓冲区、请求字节数
- 返回：实际读取字节数，失败返回 -1

### `hal_file_write`

- INT 21h AH=40h
- 参数：句柄、数据缓冲区、字节数
- 返回：实际写入字节数，失败返回 -1

### `hal_file_close`

- INT 21h AH=3Eh
- 参数：句柄
- 返回：0 成功，-1 失败

### `hal_file_seek`

- INT 21h AH=42h
- AL=0: 从文件开头算偏移
- AL=1: 从当前位置算偏移
- AL=2: 从文件末尾算偏移
- 参数：句柄、(CX:DX) 偏移量、(DX:AX) 新位置
- 通过 `newpos` 指针返回新位置
- 返回：0 成功，-1 失败

### 错误检测

所有 DOS 调用后检查进位标志 CF。使用 `pushf`/`pop` 读取 FLAGS 寄存器，检测位 0（进位标志）：

```c
unsigned short result;
unsigned short flags;
__asm volatile (
    "int $0x21\n\t"
    "pushf\n\t"
    "pop %0\n\t"
    : "=rm" (flags), "=a" (result)
    : "a" (ax_val), ...);
if (flags & 1) return -1;
return result;
```

注：`pushf`/`pop` 方式兼容 8086+ 所有 CPU，不依赖 386+ 的 `setc` 指令。

> 以下日志埋点对应 `core/engine/main.c`（核心 SASI 测试版）。
> 游戏项目入口（`projects/<name>/main.c`）使用不同的埋点。

## Engine 日志写入点

| 位置 | 内容 |
|------|------|
| main 入口 | `OPEN`（含 DOS 日期时间） |
| hal_check_compatibility 前 | `A` |
| hal_check_compatibility 结果 | `B OK` / `B FAIL` |
| hal_video_init 前 | `C VIDEO_INIT` |
| ROOTINFO 加载 | `ROOTINFO` |
| GRAPHICS 系统初始化 | `GRAPHICS` |
| TEXT 系统初始化 | `TEXT` |
| SCENE 系统初始化 | `SCENE` |
| 主循环开始 | `MAIN_LOOP` |
| ENGINE.LOG 关闭前 | `F DONE`（含 DOS 日期时间） |
| 引擎错误 | `ERR: <子系统名>` |

日志文件在引擎退出前通过 `hal_file_close` 关闭。

## 文件命名

### DOS 端（8.3 格式）

```
ENGINE.LOG
```

固定名，每次引擎启动覆盖旧文件。

### 宿主机提取后

```
logs/ENGINE.RUN.YYYYMMDD.HHMMSS.log
```

由 `inject.py --extract` 在提取时根据当前宿主机时间自动生成。

## 提取命令

```bash
python3 -m tools.naiz_img.inject --game demo-A1 --extract ENGINE.LOG
```

执行流程：
1. 打开 `disks/demo-A1.hdi`
2. `NAIZFatFS.resolve_path("DEMO-A1/ENGINE.LOG")`
3. `NAIZFatFS.read_file(entry)` 读取内容
4. 写入 `logs/ENGINE.RUN.YYYYMMDD.HHMMSS.log`

## 测试验证

```bash
cd ~/naiz
make -C core clean all                     # 编译新 engine
cp core/engine.exe games/demo-A1/
source tools/env_setup/venv/bin/activate
python3 -m tools.naiz_img.inject --game demo-A1 --yes   # 注入 HDI
bash test_hdi.sh demo-A1 ia32              # 运行 NP2kai IA32 核心（engine 生成 ENGINE.LOG）
python3 -m tools.naiz_img.inject --game demo-A1 --extract ENGINE.LOG  # 提取
cat logs/ENGINE.RUN.*.log                  # 查看日志
```
