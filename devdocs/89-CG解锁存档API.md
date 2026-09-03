# 89 - CG 解锁存档 API：sys_save_unlock_cg / is_cg_unlocked

> 状态：**活动文档**（CG feature 阶段 2 的权威设计 + 实施计划载体；实施落地后按实际代码复核修订本档）。
> 前序关系：devdoc 88（CG 数据管线）→ **本档**（存档解锁 API）→ 90（cg 展示命令，消费本 API）→ 91/92（画廊）。
> 后续消费方：阶段 3 `nb_cg.c`（**写入**解锁位）、阶段 5 画廊网格（**查询**解锁位）。

---

## 一、背景与决策记录

### 1.1 需求

CG 解锁状态需持久化到系统存档 `SYSTEM.SAV`，供：
- **剧情 `cg` 命令**：玩家看到一张 CG → `sys_save_unlock_cg(id)` 置位 + 即时写盘（阶段 3）。
- **画廊网格**：`sys_save_is_cg_unlocked(id)` 判定每格锁定/解锁 → 决定占位符或可回看（阶段 5）。

`SystemSave` 结构体已预留 `cg_flags[CG_FLAG_WORDS]`（`save.h`），但**函数完全未实现**，本阶段补齐。

### 1.2 关键决策

| # | 决策 | 理由 |
|---|------|------|
| D1 | `sys_save_unlock_cg` / `sys_save_is_cg_unlocked` 声明为**公开非 static**，加入 `save.h` | 与既有 `sys_save_unlock_scene` 模式完全对称（`save.h` 已公开）；阶段 3/5 跨文件调用必需。**推翻 B90 §函数的"内部 static"过期描述**（见 §二） |
| D2 | `cg_id` 语义 = **逻辑 CG 编号，1-based，范围 [1, CG_TOTAL]**，越界**静默防御**（同 `unlock_scene`） | 与 scene 解锁位完全同构（`scene_id` 来自 `nbook%u`，CG 位号由阶段 3 从 `cg_map[]` 下标 +1 得出）。静默防御是既有约定，保持一致性优先于"消灭静默失败"（逻辑号越界属作者笔误，非资源故障） |
| D3 | 解锁**幂等**：重复 unlock 即 OR 置位，多次调用无害 | 剧情可多分支重复命中同一 CG；天然满足，无需额外处理 |
| D4 | 位布局沿既有 `scene_flags` 写法：`flags[(id-1)/32] |= 1u<<((id-1)%32)` | 工程内已验证模式；4 word 覆盖 128 位 > CG_TOTAL(99)，无溢出 |

### 1.3 与新资源 id 的关系（跨阶段契约）

- `cg_map[].id`（IMAGE.DAT TOC 索引，来自 `img_map.id`）与**解锁位号是两套 id**，不在本阶段绑定。
- 本阶段只定义**契约**：`sys_save_unlock_cg(cg_id)` 的 `cg_id` 是 1..CG_TOTAL 的逻辑号。
- **映射责任**：阶段 3 在 `cmd_cg` 中把 `cg_map` 数组下标 → `cg_id = 下标 + 1`；阶段 5 画廊同规则遍历。两处必须一致（§四 风险 R-1）。

---

## 二、现状分析（含文档脱节点曝光）

### 2.1 save.h 现状

```c
#define CG_TOTAL        99
#define ENDING_TOTAL    16
#define SCENE_TOTAL     100
#define CG_FLAG_WORDS   ((CG_TOTAL + 31) / 32)     // 4
#define ENDING_FLAG_WORDS ...
#define SCENE_FLAG_WORDS ...

typedef struct {
    unsigned int magic;
    unsigned int version;
    unsigned int checksum;
    unsigned int cg_flags[CG_FLAG_WORDS];     // ★ 已预留
    unsigned int ending_flags[ENDING_FLAG_WORDS];
    unsigned int clear_count;
    unsigned int scene_flags[SCENE_FLAG_WORDS];
    unsigned int reserved[32 - SCENE_FLAG_WORDS];
} SystemSave;
```
`save.h` 当前仅声明 `sys_save_load()` / `sys_save_unlock_scene()`。

### 2.2 save_sys.c 现状

实现了 `sys_save_load()` + `sys_save_unlock_scene()`，以及内部 `static sys_save_write()`（置位后即时写盘）。

### 2.3 文档脱节点（本阶段需修正）

- `docs/B90-参考-函数索引.md` line 132–133 称 `sys_save_unlock_cg()/is_cg_unlocked()` 等为"save_sys.c 内部 static"。**实际未实现**——这是过期描述（原 `save_sys_internal.h` 删除后残留的记录错误）。
- 本阶段落地后，应将这两函数从"内部 static 清单"移到"跨模块 API 公开清单"（阶段 7 文档收口时同步 B90）。
- `docs/B18-存档读档系统设计.md` §2.4 表格列 `sys_save_unlock_*(id) | 290–333`——该行号区间描述同样过期，阶段 7 修正。

---

## 三、细化实现（逐文件）

### 3.1 save.h —— 公开声明

在 `sys_save_unlock_scene(int scene_id);` 之后追加：

```c
void sys_save_unlock_cg(int cg_id);
int  sys_save_is_cg_unlocked(int cg_id);
```

### 3.2 save_sys.c —— 实现

在 `sys_save_unlock_scene` 之后追加（对称实现，`sys_save_write` 为既有 static，同文件可见）：

```c
/* Unlock a CG (1..CG_TOTAL) in SYSTEM.SAV and flush to disk. */
void sys_save_unlock_cg(int cg_id)
{
    if (cg_id < 1 || cg_id > CG_TOTAL) return;
    sys_sd.cg_flags[(cg_id - 1) / 32] |= (1u << ((cg_id - 1) % 32));
    sys_save_write();
}

/* Return non-zero when CG cg_id has been unlocked. */
int sys_save_is_cg_unlocked(int cg_id)
{
    if (cg_id < 1 || cg_id > CG_TOTAL) return 0;
    return (sys_sd.cg_flags[(cg_id - 1) / 32] & (1u << ((cg_id - 1) % 32))) != 0;
}
```

改动仅两个文件，各两处，零新增依赖。

---

## 四、Bug 检查（§十七 规则逐条过）

### C 类（本阶段改 C 代码）

| # | 规则 | 落点 | 检查结论 |
|---|------|------|---------|
| C1 | malloc 检查 | 无 malloc | ✓ |
| C2/C3 | fopen/fread | save_sys_write 走既有 `save_file_write`，已有 C2/C3 守护 | ✓ |
| C5 | snprintf | 无 sprintf 新增 | ✓ |
| C6 | 数组下标越界 | `(cg_id-1)/32` 经 `cg_id ≤ CG_TOTAL(99)` 约束 → 最大 3 < CG_FLAG_WORDS(4) | ✓ |
| C7 | offsetof | 复用 `offsetof(SystemSave, checksum)`（已在 sys_write/sys_read 参数化） | ✓ |
| C8 | 有符号溢出 | `cg_id-1`：cg_id ≥ 1 受检，最小 0，无 INT_MIN 场景；`1u<<x` 用 unsigned | ✓ |
| C10 | switch default | 无 switch | ✓ |
| C12 | void 用返回值 | `is_cg_unlocked` 声明 `int` 返回，非 void | ✓ |
| C13 | static 未用 | 两个新函数均公开且将被阶段 3/5 消费；`sys_save_write` 仍是内部 static 且被新函数复用 → 不会"未使用" | ✓ |
| C14 | OOM/失败日志 | 写盘失败路径已由 save_io 打 `[SYS] ...` 日志 | ✓ |
| C15 | fclose 提前 return | 无 fopen 新增 | ✓ |
| C16 | offsetof 跳距 | 不新增二进制布局 | ✓ |
| C18 | 快路径副作用 | 无缓存/快路径 | ✓ |
| C21 | 禁 strcpy | 无 | ✓ |
| C22 | INT_MIN 取负 | `cg_id-1` 无取负 | ✓ |
| C23 | 双重 free | 无 free | ✓ |
| C24 | memcpy 尺寸 | 无 memcpy 新增 | ✓ |
| C25 | use-after-free | 无 | ✓ |

### 特定于本阶段的风险

- **R-1：cg_map 下标 → cg_id 映射两处不一致风险**（阶段 3 vs 阶段 5）。本阶段定契约，devdoc 90/92 必须共同遵守 `cg_id = cg_map[] 数组下标 + 1`。若未来 cg_map 重排（`ORDER BY id` 恒定），解锁记录随 build 漂移——属可接受行为（与场景 id 同源逻辑），在阶段 7 记录。
- **R-2：cg_flags word 越界**。CG_TOTAL=99 → 4 words → 128 位，位 96–127 未用。即使未来 cg_map 达 99，`(99-1)/32=3` 上限仍安全。若调大 CG_TOTAL，须同步加大 CG_FLAG_WORDS（编译期常量联动，天然一致）。
- **R-3：`is_cg_unlocked` 必须在 `sys_save_load()` 之后才有意义**。调用链：启动 `main` 已调 `sys_save_load()`；阶段 3/5 均运行于启动后，无需重复加载。devdoc 90 会校验此前提。

---

## 五、验证方案（阶段 2 完成标准）

C 侧无独立单测 harness（tools/tests 仅覆盖 Python 工具链），采用：

1. **编译**：
   ```bash
   make -C core
   ```
   确认 0 errors / 0 warnings（声明与实现匹配，无 static/未用告警）。
2. **静态检查**：
   ```bash
   ./start.sh fullaudit --no-make   # 规则审计 + symbol_audit 确认两函数非"死导出"
   ```
   `symbol_audit` B 节（死导出）应**不**报 `sys_save_unlock_cg`/`sys_save_is_cg_unlocked`（因 save.h 公开，跨 TU 链接）。
3. **逻辑审查**：对照 §三代码逐行核对 C6/C8（位号边界）与对称性（与 `unlock_scene` 一致）。
4. **跨阶段契约登记**：将 `cg_id = cg_map[]下标 + 1` 契约记入 devdoc 90（阶段 3 消费方必须遵守）。

---

## 六、范围外（后续阶段）

- `cg` 命令消费解锁写位（**devdoc 90**）
- 画廊网格消费解锁查位（**devdoc 92**）
- ending 解锁 / clear_count（本 feature 无关，不实现）
- B90/B18 文档修订归入阶段 7 收口