# B95 — VM 执行核心规范

**代码**：`core/engine/vm.c` / `core/engine/vm.h`
**引入**：0.4.011（挂钟延迟）

## 一、职责

`vm` 是 NB 脚本的**推进控制器**，不解析、不执行命令，只负责回答一个问题：**现在能不能执行下一条命令**。

| 能力 | 接口 | 说明 |
|---|---|---|
| 进程标志 | `vm_pause_process()` / `vm_request_process()` / `vm_is_process_requested()` | 单字节 `VMFLAG_PROCESS`；`nb_process()` 每 pass 检查一次 |
| 延迟 | `vm_set_delay(ms)` / `vm_delay_tick()` / `vm_delay_active()` / `vm_delay_reset()` | 挂钟截止时间，非帧计数 |
| 状态复位 | `vm_delay_reset()` | 场景切换 / 脚本重载时清掉未完成的延迟 |

## 二、延迟语义（关键约束）

```c
void vm_set_delay(unsigned long ms);   /* 0..3600000，越界钳位 */
int  vm_delay_tick(void);              /* 到点返回 1 并自我清除，否则 0 */
int  vm_delay_active(void);            /* 仍在等待 */
```

- 截止时间 = `hal_wallclock_smooth_ms() + ms`，**不使用帧数**。
- `vm_delay_tick()` 只判断一次 `now >= deadline`；返回 1 表示「本次等待结束」。
- 主循环约定（`main.c`，AUTOEXIT 与普通路径一致）：

```c
if (vm_delay_tick())            vm_request_process();
else if (!vm_delay_active())    vm_request_process();
```

即：**等待中就 hold，非等待直接放行**。任何新增路径都必须同时包含这两个分支，否则 `delay()` 会退化为「立即放行」（历史 bug，见 devdoc 200 §十）。

## 三、禁止事项

1. **禁止用帧数表达时间**。NP2kai 的 GDC VSYNC 位不翻转，`hal_vblank_wait()` 轮询耗尽即返回，帧泵实测 ~700 fps；`delay(1.5)` 按帧计数只剩 129–387 ms。
2. `delay()` 只表达「脚本等待」，不应用于动画节奏、逐帧步进或 UI 计时；这些应由各自的帧驱动状态机负责（见 B97）。
3. 不要在 `vm_delay_tick()` 之外直接读写 `delay_deadline_ms`；它是 `vm.c` 私有状态。
4. `ms == 0` 由调用方（`cmd_delay`）钳为 1 ms，避免「设置即完成」的语义歧义。

## 四、与其它模块的关系

| 模块 | 关系 |
|---|---|
| `nb_commands.c` | `cmd_delay` 解析秒参数 → 换算毫秒 → `vm_set_delay()` + `vm_pause_process()` |
| `main.c` | 每 pass 调 `vm_delay_tick()` 决定是否 `vm_request_process()` |
| `transition.c` | 过渡是独立的帧驱动状态机，`nb_process()` 在 `transition_active()` 时同样挂起脚本 |
| `hal_clock.c` | 唯一时间来源（`hal_wallclock_smooth_ms`） |

## 五、验收

- `delay(1.5)` 实测应落在 1.50 s ± 50 ms（与帧率、串口日志开销无关）。
- 切换场景后未完成的延迟不得泄漏到下一个脚本：`vm_delay_reset()` 必须在场景装载路径调用。
