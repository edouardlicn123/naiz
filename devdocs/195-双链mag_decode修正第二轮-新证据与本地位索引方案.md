# 195 — 双链（商业 / 开源）MAG 解码修正：根因定案与落地记录

> 取代 194 的结论。194 的"action 表被外部写穿"与"新增静态对象导致 DOS/32A 4005"两条假设
> 均已被实验推翻；本轮通过单因子对照把两个独立缺陷同时定案并落地。
>
> 系统：Naiz（PC-98 引擎）· 范围：`core/lib/mag.c`、`core/Makefile`
> 两条交付链：cmpack（商业：tools_commercial + DOS/4GW）／openpack（开源：tools_open + DOS/32A）

> **后续状态（2026-11-02）**：本文 §三 P7（openpack 布局敏感失败）已定位并修复——
> 破坏源是 `frame_decode_pump()` 在 `cli` 区内调用 `hal_wallclock_smooth_advance()`
> （`INT 21h` 的 DPMI 反射落在解码活动栈帧上）；修复为移除该调用，**保留** `cli` 与 `audio_tick()`。
> 单布局（`NAIZ_AE_PAD=128`）40/40 通过；布局矩阵与 cmpack 回归仍待做。
> 详见 196 §4.0 与 refdoc I04。

---

## 一、现象

镜像 `disks/demo-a2.hdi` 开机时 `bootmenu` 加载背景 image 13（`yellow_grid`，
640×400、8bpp、256 色、11017B）：

```
image_load(13): mag_decode failed (size=11017 code=11 at=247756)
  fabits=64000 clen=80 iters=61941 fb=2120 col=80 fapos=7742 flen=8000
  short cnt=1 it=56974 pos 227892->227892 ab=11 fb=1960 col=80
bootmenu: bg image 13 MISSING, black fallback
```

image 13 的位流与输出之间是**严格 1:1**（每迭代 1 bit、输出 4 字节）：
64000 bit × 4B = 256000B。因此任何一次迭代少推进字节，都会在 bit 用尽时表现为
`code=11`，失败点离真正的事故点很远。这也是 194 一直误判的原因。

---

## 二、对照实验矩阵（全部单因子）

| # | 变量 | 结果 |
|---|------|------|
| E1 | 绑定 stub + QMOUSE + `-od` | **4/4 同一失败**（code=11 at=247756，short 同为 227892） |
| E2 | 外部 `DOS32A.EXE ENGINE.EXE` + QMOUSE + `-od` | **2/2 成功**（`image_load(13): ok 640x400`） |
| E3 | 绑定 stub + **无 QMOUSE** + `-od` | **2/2 成功** |
| E4 | 绑定 stub + QMOUSE + `-os`（含 `_disable()` 保护） | **3/3 同一失败**（code=13 at=149976） |
| E5 | 绑定 stub + QMOUSE + `-od` + `_disable()` 保护 | **4/4 + 2/2 成功** |

矩阵说明：E1 与 E3 只差常驻驱动 `QMOUSE.COM`；E1 与 E5 只差解码期是否屏蔽中断；
E4 与 E5 只差 `mag.c` 的优化开关。三者互不替代。

---

## 三、定案的两个缺陷

### P1（真因 A）— 常驻实模式 TSR 的 IRQ 反射覆盖解码循环的栈局部量

* E1/E3 证明：同一二进制，去掉 `QMOUSE.COM -z` 后 4/4 失败变成 2/2 成功。
* 失败签名是"记录下来的操作数互相矛盾"：错误分支在 `fa_bit=61941 < fa_bits=64000`
  时被判为真；某次迭代 `out_pos` 前后同为 227892（代码路径上不可能 0 推进）。
  这只能来自栈上局部量在迭代间被第三方改写，而非解码逻辑本身。
* 机理：QMOUSE 的硬件中断处理程序是实模式代码，经 DPMI 反射进入时，反射帧落在被中断
  的客户栈上；解码循环是长时间 CPU 密集段，`hal_irq.c` 在 DOS/32A 链上已因此禁用了
  PM IRQ 路径（194），但未保护主线程。
* 结论：不是编译器问题，也不是 194 的 `br_read` 堆结构体问题——堆结构体只是换个被改写
  的位置（194 记录的 `byte_pos=1591 / byte_len=8000` 同样是矛盾证据）。

### P2（真因 B）— `wcc386 -os` 对解码循环误编译

* E4/E5 证明：同一份源码、同样的 `QMOUSE` 与同样的中断保护，`-os` 必失败
  （`code=13` 无效反引用，位置固定 149976），`-od` 必成功。
* `code=13` 来自 `ref_off/src` 计算被优化后才出现，说明是代码生成缺陷，
  与数据/位流无关。
* 影响面：`build/mag.o` 与 `build/a_mag.o`（两条链共用同一份源码），必须两处都覆盖。

### P3 — 结构性放大（非独立缺陷）

解码外层循环由 `out_pos` 驱动、bit 流按 1 bit/迭代消费。P1/P2 任何一次"少推进"都会
把局部异常放大成"bit 流用尽"。P1/P2 修好后不再触发；本轮不改为计数驱动，
避免把错误静默吞掉（共 `code=13/11` 的显式报错仍是更好的可观测性）。

### P4 — DOS/32A 绑定 stub 的 `fatal (4005)`（已随 P2 消失）

`-os` 绑定版加载即 `fatal (4005): unrecognized fixup data`；`-od` 绑定版可加载。
两版 LE 的 fixup 记录经自写解析器逐页校验均为合法（类型仅 0x0007/0x1007，
OBJNUM∈{1,2}），因此 194 的"新增文件级静态对象触发 4005"不成立。当前交付形态
（绑定 stub，随 EXE 自带 extender）保持不变，不再需要盘上额外的 `DOS32A.EXE`。

### P5 — 商业链（cmpack / DOS/4GW）起不来（已定案：部署脚本漏了 PC-98 开关）

**现象**：clean 构建的 `engine.exe`（DOS/4GW 绑定）在 np21kai 上 **串口 0 行**；屏幕
`VEM486 1.29N` → `DOS/4GW 1.97` 横幅 → 直接回 `A>`，无错误行。

**排除过程**（全部单因子）：

| 实验 | 结果 | 排除项 |
|------|------|--------|
| 盘上 `DOS4GW.EXE` 作外部 loader（`DOS4GW.EXE ENGINE.EXE`） | 与绑定版完全一致 | wlink 绑定 stub |
| 自写 19KB hello（`wcl386 -l=dos4g`） | 同样横幅后回 DOS | 引擎代码 / LE / fixup / 体积 |
| CONFIG.SYS 去掉 VEM486 再跑 hello | `DOS/16M error: [26] 8042 timeout` | 见下 |
| AUTOEXEC 补回 `SET DOS16M=1` | **正常启动**（串口 2123B，`image_load(13): ok`） | 定案 |

**定案**：`SET DOS16M=1` 是 DOS/4GW 启用 PC-98 路径的开关（见
`docs/refdocs/E01_boot_disk.md` §158-162）。历史上 AUTOEXEC 一直有这一行；
devdoc 178 迁 CauseWay 时以"对 CauseWay 是 no-op"删除了它，之后回滚 DOS/4GW 却
没有恢复，于是整条商业链看起来"根本起不来"。

**修正上一轮的误判**：`8042 timeout` 只是"无 VCPI 时 DOS/4GW 走 raw 路径"的正常表现，
与本案无关；DOS/4GW 本身在 PC-98 + VEM486 下可用。

**代码修复**：`tools/naiz_img/inject_common.py` 的 `generate_autoexec()` 按打包形态
输出该行——cmpack（DOS/4GW）52 字节含 `SET DOS16M=1`；openpack（DOS/32A）38 字节不含。

### P7 — openpack 链的"修好"依赖内存布局（新发现，未解决）

删掉两条 ANI（`IMAGE.DAT` 由 940860B 变小）后，openpack 链**再次失败**：

```
image_load(13): mag_decode failed (code=11 at=255992)  iters=64001
  short cnt=3 it=4696 pos 18780->18782 ab=11 fb=280 col=80
```

* 去掉 QMOUSE 仍复现（`at=255994`，short 改为 `it=4575 pos 18296->18298`）⇒ 本次与 TSR 无关；
* `cli`（F6）与 `-od`（F7）都在生效，仍出现"某次迭代只前进 2 字节"；
* 同一二进制 `engine32a.exe`（225732B，07:53 构建）在旧 `IMAGE.DAT` 上 6/6 通过，
  换布局后 2/2 失败 ⇒ 失败点随**加载地址/堆布局**漂移。

结论：P1 的 `cli` 只是压住了某个布局下的表现，真正的写者（或另一个同签名缺陷）仍在，
必须单独立项（见 devdoc 196）。


---

## 四、修正方案（已落地）

### F6 — 解码热循环屏蔽中断（P1）

`core/lib/mag.c`：`mag_decode()` 与 `mag_decode_into()` 的主循环前后各加一次
`_disable()` / `_enable()`（`<i86.h>` 内建）。

* 理由：TSR 的反射帧只可能由硬件中断触发；屏蔽后不会落栈。
* 代价：一次整图解码约十几毫秒，最多延迟一个 55ms 定时器节拍；解码期本来就由
  `frame_decode_pump` 自行推进虚拟时钟，因此不产生可见停顿。
* 注意：两处都加，否则动画路径（`nb_anim` → `mag_decode_into`）仍会被改写。

### F7 — `mag.c` 强制 `-od`（P2）

`core/Makefile` 增加两条按文件规则（覆盖通用 pattern 规则）：

```make
build/mag.o: lib/mag.c | build
	$(CC) $(LIB_CFLAGS:-os=-od) -c -fo=$@ $<

build/a_mag.o: lib/mag.c | build
	$(CC) $(LIB_CFLAGS:-os=-od) -DAUTOEXIT -c -fo=$@ $<
```

* 只降级这一个翻译单元，其余代码继续 `-os`（体积优先），对两条链一致生效。
* 通用 pattern 规则保持不变，避免全局退化。

### F7 补充：WCL386 DOS/4GW 默认 BSS 段上限 64KB（devdoc 200 §6.1）

2026-11-04 实施 devdoc 200 S2（`image_set_palette` dirty-diff）时**偶然发现**同一类问题的另一个家族：

- **现象**：加 3×256=768B static 数组 + dirty-diff skip 后，bootmenu logo 白色变黑、剧情场景背景全黑只剩对话框文字。
- **排查**：控制变量法逐步缩小范围，最终确认是 dirty-diff 的三个 static 数组导致的 BSS 段溢出。
- **根因**：WCL386 DOS/4GW 默认 BSS 段上限 64KB。image.c 原本已有一定静态量，加 768B 刚顶破。段溢出导致 `g_last_pal_valid` 被意外覆盖为 1，且数组内容是垃圾值——恰好 bootmenu image 13 的 palette 部分槽垃圾值与硬件 palette 默认值（全 0）巧合匹配，skip 触发。
- **关键教训**：
  1. BSS 段溢出的症状可能非常隐蔽——不 crash，而是数据被覆盖后逻辑 silently 出错。
  2. 控制变量法（git bisect 逐步加回）是定位这类"段溢出/编译器 bug"的唯一有效手段。
  3. 即使把 `image.o` 也改成 `-od` 仍然坏——因为这根本不是优化器问题，是段大小问题。
- **未来规避**：改 BSS 段大小（`wlink` 加 `-bss=128K`）或显式段布局（`.exp` 文件）。
- **处理**：S2 dirty-diff 整个放弃，image.c 恢复 HEAD 版本。
- **关联**：跟 F7 的 `-od` 规则同属"WCL386 在 DOS/4GW 下的坑"家族，值得在项目里单独整理一份。

---

## 五、执行与验收

| 步骤 | 内容 | 结果 |
|------|------|------|
| S1 | 复现 E1（绑定 stub，QMOUSE，`-od`） | 4/4 同一失败，确认确定性（非"间歇"） |
| S2 | 去掉 QMOUSE（E3） | 2/2 成功 → 定位 P1 |
| S3 | 加 F6，`-od`（E5） | 3/3 + 4/4 成功 → P1 确认 |
| S4 | 加 F6，`-os`（E4） | 3/3 失败（code=13）→ 定位 P2 |
| S5 | 落地 F7，clean 重建 openpack | `image_load(13): ok 640x400`、`bg image 13 loaded (640x400, colors=256, bpp=8)`，连续 4/4 + 2/2 成功 |
| S6 | clean 重建 cmpack | 构建通过（`build/mag.o` 13177B，`-od` 生效）；补 `SET DOS16M=1` 后 **3/3 成功**（`image_load(13): ok 640x400`），见 P5 |
| S7 | 删除两条 ANI 后复测 openpack | **2/2 失败**（code=11 at=255992/255994），无 QMOUSE 亦复现 → 新增 P7 |

验收口径（openpack）：连续 ≥4 次开机，串口必须出现
`image_load(13): ok 640x400` 与 `bootmenu: bg image 13 loaded`，且零
`mag_decode failed`。**在 08:00 前后的镜像上满足（6/6）；删 ANI 后不再满足（见 P7）。**
验收口径（cmpack）：同口径，已验证 3/3。

---

## 六、遗留与后续

1. **P7 openpack 布局敏感失败（已定位，待布局矩阵验收）**：破坏源是
   `frame_decode_pump()` 在 `cli` 区内调用 `hal_wallclock_smooth_advance()`（`INT 21h` 反射
   改写解码活动栈帧）。已移除该调用并保留 `cli`，单布局 40/40 通过；仍需按 196 §4.4
   的判据扰动布局 ≥6 次、并回归 cmpack。
2. **P5 商业链启动（已结案）**：`SET DOS16M=1` 已补回并通过 3/3；回归时若再出现
   "横幅后回 DOS、串口 0 行"，先查 AUTOEXEC 是否被重新生成而丢掉这一行。
3. **像素正确性截图**：本轮以"解码成功 + 尺寸/色数/bpp 正确"为验收；
   人工截图复核（`makegame.sh test` 交互启动）仍建议补做。
4. **ASSETS.DB 与 ani 文件不同步**：`img_map` 的 id 17/18 指向已被删除的
   `ani/TESTFULL.ANI`、`ani/TESTCINE.ANI`，已删行（40 行、ANI=0）。若后续再从
   历史恢复 ANI，必须同时把行加回。
5. **194 文档修订**：`194-双链兼容的mag_decode修正-方案与执行记录.md` 中
   "action 表被外部写穿""新增静态对象导致 4005""`br_read` 假拒绝来自堆结构体"
   三条结论作废，以本文为准。
6. **诊断代码**：`mag_diag` 的 `short_*` / `tail_*` / `err12_*` 字段保留
   （仅在失败路径打印，正常运行零开销），作为后续回归的可观测性资产。
