# 192 - 纯 DOS/32A 镜像上 `mag_decode` 间歇失败：现象、证据与排查路线

> 交接文档。上一份：191（CWTEST 第五轮）。上游：185（部署双管线）、178（部署链开源化）。
> **状态：只记录，不处理。** 本轮没有修改解码行为，也没有下结论"已修复"。
> 观测时间：2026-11-01 21:44–22:26，全部命令可复现，产物见 §十。

---

## 一、一句话现象

在**纯开源基座**（FreeDOS(98) + HIMEMX，无 VEM486；引擎是 DOS/32A 绑定版 `engine32a.exe`）的镜像上，
启动菜单背景 `image_load(13)` 会**间歇**解不出来；同一 EXE、同一 IMAGE.DAT，约 **1/4 的启动**会失败。
失败族始终是 `code=11`（flag A 位流枯竭），且失败后引擎**继续正常运行**（BGM ISR、菜单、进入游戏、场景背景都正常）。

对照：同一份引擎代码、同一份 IMAGE.DAT，在 DOS4GW 变体（`engine.exe` + VEM486 基座）没有观察到该现象。

---

## 二、失败样本（两处实测日志，形态不同）

### 样本 A —— 早退（约 14% 进度处）

`/tmp/final2.log:26-27`：

```
image_load(13): mag_decode failed (size=11017 code=11 at=36044)
  bpp=8 bw=640 h=400 total=256000 fabits=64000 clen=80 iters=9012 fb=440 col=80
```

### 样本 B —— 尾退（最后一个 2 字节块）

`/tmp/diag_open3.log:26`（同一份镜像的另一次启动），且**同一日志里 image 5 也在同一点失败**（`diag_open3.log:115`）：

```
image_load(13): mag_decode failed (size=11017 code=11 at=255998)
bootmenu: bg image 13 MISSING, black fallback
...
image_load(5): mag_decode failed (size=135553 code=11 at=255998)
bg: display_apply_bg(5) failed
```

注意样本 B 的 `at=255998 = 256000 - 2`，即"最后一块还差一个 bit"。

---

## 三、被解码对象是静态确定的（零余量）

`image 13`（`yellow_grid`）实测头（`/tmp/id13.mag`，11017B，从 IMAGE.DAT 取出）：

| 字段 | 值 |
|---|---|
| 尺寸 / 位深 / 色数 | 640×400 / 8bpp / 256 |
| `hdr_start` | 17 |
| `left,top,right,bottom` | 0,0,639,399 |
| `fa_off` / `fb_off` / `fb_size` | 800 / 8800 / 2120 |
| `c_off` / `c_size` | 10920 / 80 |
| flag A 可用字节 | `fb_off - fa_off = 8000` → **64000 bit** |
| `action_size` | `byte_width / 4 = 160` |

把 [mag.c](file:///home/edo/naiz/core/lib/mag.c#L323-L407) 的主循环逐行等价地翻译成 Python 再跑一遍，结果是**确定性**的：

```
err None  iters 64000  bits 64000  bytes_used 8000  out 256000  fbp 2120  cp 80  A len 8000
```

也就是说：

1. 正常路径**恰好** 64000 次迭代、**恰好**吃掉 64000 bit（8000 字节），一次都不多；
2. flag B（2120）与 color（80）也**恰好**用尽；
3. 这是一个 **零余量** 的位流——解码器只要多要一个 bit，就必然 `br_read()` 返回 -1。

`mag_decode` 的 `br_read` 只有一处返回 -1（越界），见 [mag.c](file:///home/edo/naiz/core/lib/mag.c#L95-L105)。

---

## 四、零余量解释了"为什么总是 code=11"

主循环的循环不变量：**每次迭代固定产出 4 字节**（2 nibble × 2 字节，8bpp）。
于是 `out_pos / 4 == iters` 必须恒成立。任何一次偏离都会**立刻**表现为位流枯竭：

| 偏离 | 结果 |
|---|---|
| 多跑一次迭代（循环条件/`out_pos` 步进异常） | 下一次 `br_read` 立刻 -1 → `code=11` |
| 某次迭代只产出 2 字节（内层 nibble 提前 break） | 后续要把 64000 bit 用光才能凑够 256000 字节 → 尾退 `code=11` |

这就是为什么本问题**不表现为** `code=12`（color 枯竭）或 `code=13`（复制越界）：
`code=11` 的检查在每次迭代最前面，是第一个有机会报错的点，同时它也是**唯一**能"无数据错误却失败"的错误码。

### 样本 A 是"矛盾样本"，最值得注意

`iters=9012`、`at=36044 = 4 × 9011`：前 9011 次迭代每次 4 字节，第 9012 次在 `br_read` 就失败。
此时实际只消耗了 **9012 bit ≈ 1127.5 字节**，而 flag A 静态可用 **8000 字节**。

也就是说：**在没有走到位流边界的时候，`br_read` 报了越界。**
这不是数据问题、也不是算法问题，只能是 `BitReader` 的两个字段被外部改写：

- `fa.byte_len` 被改小（< 1127），或
- `fa.byte_pos` 被改大（≥ 8000，但 `mag_diag.fa_byte_pos` 这一版日志没打印，无法确认）。

`BitReader` 是 `mag_decode` 的**栈上局部变量**（`base/byte_len/byte_pos/bit_mask`，16 字节），
所以样本 A 是"栈帧被踩"的强指纹。

### 样本 B 是"尾退样本"，一致性检查也对不上

`255998 = 4 × 63999 + 2`：说明**有且仅有一次**迭代只写了 2 字节（或 `out_pos` 起点偏移了 2）。
在 8bpp 路径里，单 nibble 必产出 2 字节、双 nibble 必产出 4 字节，内层唯一能少写一次的 break 条件是
`out_pos + 1 >= output_total`（即 `out_pos ≥ 255999`），而从 0 以 +2 步进永远到不了 255999。
所以样本 B 同样**不是**纯算法可以产生的状态。

两个样本都不符合"数据坏了"的形状（数据坏了会给出 `code=12/13` 或解出错图），
两个样本都符合"**解码器运行期状态被外部扰动**"的形状。

---

## 五、已排除项（都做过实测，不是推测）

| 排除项 | 依据 |
|---|---|
| MAG 数据本身 | gcc 单独编译 [mag.c](file:///home/edo/naiz/core/lib/mag.c) + 读 `/tmp/id13.mag` 的本地 harness：`rc=0 err=0`，`img 640x400 colors=256 bpp=8` |
| 算法实现 | §三 的 Python 等价实现同样成功，且给出零余量的确定结果 |
| IMAGE.DAT / TOC / 注入 | 同一镜像多次启动成功过；失败与成功用的是同一份文件；注入报告 `29 files, 62,237 free clusters`，无簇链错误 |
| 4bpp / malloc / 裁剪路径 | 失败发生在主循环，`bpp=8`，不经过 4bpp 展开与 crop；`code=10/14/15/16` 都没出现 |
| 整体崩溃 / 内存不足 | 失败后引擎继续跑：`[ISR] ticks=...`、bootmenu 选语言、logo/op/mainmenu 场景推进、游戏内 640×400 棋盘完整渲染（有截图实证） |
| extender 绑定失败 | 绑定成功时 `e_lfanew=27536`；未绑定的 EXE 是"banner 后立刻退出"，与本现象不同 |

---

## 六、候选根因（按可能性排序，待验证）

1. **BGM IRQ 的 ISR 与解码并发（首要嫌疑）**
   日志顺序固定为：`BGM IRQ: scanning FM IRQ line; co-operative pump stays active`
   → `bootmenu: enter` → `image_load(13)`；失败行之后紧接着 `[ISR] ticks=…`。
   即 **OPNA Timer-B（IRQ12/slave 4）在解码期间是活的**。
   在保护模式 + DOS/32A 下，IRQ 需要经 DPMI 回调（或实模式 ISR → PM 反射）进入；
   若回调路径的寄存器保存/栈切换不完整，就会踩到被中断的栈帧——而 `BitReader` 正好在栈上，
   且位流零余量，任何 1 字节的偏移都会立刻放大成 `code=11`。
2. **DOS/32A 下的堆布局差异**
   `farchive_read_alloc()` 的 raw blob、`calloc` 的 `output`/`action` 在 DOS/32A 的堆里相邻方式与 DOS4GW 不同；
   任一处越界写（action 索引、ISR 的临时缓冲）都可能落到 raw blob 或栈上。
3. **栈/堆在低位内存被硬件或 DMA 改写**
   开源基座只有 HIMEMX（无 EMM386/VEM486），DPMI 分配落点与商业基座不同；
   若某块与 DMA 缓冲或未受保护的 XMS 句柄重叠，会"偶发"。
4. **编译器未定义行为**
   `(unsigned int)src < (unsigned int)output_total - 1` 在 `output_total==0` 时下溢（本图为 256000，不成立）；
   `br_read` 被内联后的优化差异理论上也可疑，但不足以解释"1127 字节就报越界"。

---

## 七、下一步验证顺序（只加观测，不改行为）

| 编号 | 动作 | 判据 |
|---|---|---|
| V1 | code=11 分支补齐打印 `fa_byte_pos` / `fa_mask` / `fa.byte_len` / `&fa` | 区分"pos 被改大"还是"len 被改小" |
| V2 | 在 `BitReader fa` 前后各放 4 个 `uint32_t` canary（固定魔数），失败时打印 8 个值 | canary 变了 = 栈帧被踩（样本 A 应中） |
| V3 | 给 `mag_diag` 加 magic 字段，解码前写、失败时校验 | 判断全局区是否被踩 |
| V4 | 解码前不 unmask IRQ12（等价于 `bgmmode=COOP` 且不探测）连跑 20 次 | 失败率降到 0 → 锁定 ISR |
| V5 | 同一开源基座换 DOS4GW 变体连跑 20 次 | 稳定 → 锁定 extender 侧（DPMI 回调/堆布局） |
| V6 | 仅在 `mag_decode` 期间 `cli/sti`（实验性） | 失败消失 → 确认并发假设 |

统计口径：每次 **20 连跑**，记录失败率，并把失败点分成两类（早退≈36044 类 / 尾退≈255998 类）；
两类占比不同即说明存在两种独立扰动源。

---

## 八、影响与当前缓解

- **不阻断**：bootmenu 已有黑底回退（[bootmenu.c](file:///home/edo/naiz/core/engine/bootmenu.c#L287-L298)），游戏内画面完整。
- **但不止是观感问题**：样本 B 里 `image 5 (mainmenu)` 也同点失败，会连带 `bg: display_apply_bg(5) failed`，
  也就是说凡是"恰好在这段时间窗内被解码"的大图都受影响，量级随图大小增加。
- 复现率不稳定：曾出现约 1/4，也曾 3+3 连续成功过；因此任何"改了就没事"的结论都必须以 20 连跑为口径。

---

## 九、代码位置索引

| 用途 | 位置 |
|---|---|
| `br_read`（唯一越界返回点） | [mag.c](file:///home/edo/naiz/core/lib/mag.c#L95-L105) |
| 主循环与 `code=11` 埋点 | [mag.c](file:///home/edo/naiz/core/lib/mag.c#L320-L409) |
| `MagDiag` 结构与错误码 | [mag.h](file:///home/edo/naiz/core/lib/mag.h#L57-L81) |
| 失败日志输出 | [image.c](file:///home/edo/naiz/core/engine/image.c#L189-L196) |
| 黑底回退 | [bootmenu.c](file:///home/edo/naiz/core/engine/bootmenu.c#L287-L298) |
| DOS/32A 绑定（PATH 需含 `binw`） | [Makefile](file:///home/edo/naiz/core/Makefile) |

> `mag_decode_into()`（pool 版，[mag.c](file:///home/edo/naiz/core/lib/mag.c#L570-L827)）是同一套算法的第二份实现，
> 但它**不带 `mag_diag` 埋点**。若后续怀疑是 pool 路径，需要单独加观测；当前失败日志来自 `mag_decode()`（`image_load` 走 `farchive_read_alloc` + `mag_decode`）。

---

## 十、可复现命令

```bash
# 1) 建 DOS/32A 变体（注意 Makefile 在 WATCOM/binw 里找 dos32a.exe）
rm -f /home/edo/naiz/core/engine32a.exe /home/edo/naiz/core/engine_a32a.exe
make -C /home/edo/naiz/core open

# 2) 注入到开源基座（引擎变体由环境变量选择）
NAIZ_EXTENDER=dos32a python3 -c "from tools.naiz_img import inject; inject.main()" ... -y

# 3) 串口观测（多次重复以统计失败率）
python3 -m tools.diag.np2kai_serial --hdi <img> --listen-only --timeout 30 -o /tmp/runN.log
```

历史产物：

| 文件 | 内容 |
|---|---|
| `/tmp/final2.log` | 样本 A（`code=11 at=36044` + `iters=9012 fb=440 col=80`） |
| `/tmp/diag_open3.log` | 样本 B（id13 与 id5 都 `at=255998`） |
| `/tmp/diag_open3b.log`、`/tmp/f1.log`、`/tmp/f2.log` | 成功对照（`bg image 13 loaded (640x400, colors=256, bpp=8)`） |
| `/tmp/id13.mag` | image 13 原始数据（11017B），用于本地 harness 复现 |
