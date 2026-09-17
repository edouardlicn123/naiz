# 101 音频后端：MIDI 直放 + 86 板 PCM 实施计划

## 1. 背景与目标

`core/plat/hal_pc98.c:168-199` 的音频 HAL（`hal_bgm_play/stop`、`hal_sound_play`、`hal_voice_play`）目前是 `hal_log` 空转 stub。脚本命令 `bgm(){key}`/`bgm(stop)`/`sound(){key}`/`voice(){key}`（`core/engine/nb_audio.c`）语法与参数校验已就绪，只差真实后端。

本 devdoc 定案 P0 音频后端：

| 命令 | 后端 |
|------|------|
| `bgm` | **SMF（MIDI 标准格式）原样打包，运行时解析 + 时序调度，写 MPU-401 UART 字节流**（不转格式） |
| `sound` / `voice` | **WAV 构建期转制为 `.pcm`（16bit mono），运行时逐帧灌入 86 板 YM3433B PCM FIFO**（运行时零转格式，直灌） |

已确认决策：
1. BGM + sound/voice 本轮一并实施
2. demo 素材用临时生成的测试 GM MIDI（`tools/naiz_audio/gen_test_midi.py`）
3. 实机目标 MIDI 接口 = **MPU-PC98 兼容**（Roland 类，端口 `0xC0D0`）

## 2. 硬件事实（已核实）

### 2.1 MIDI：MPU-401 / MPU-PC98

- **MPU-401 UART 模式**是 MIDI 字节直通的最简通道：命令口写 `0x3F` 进入 UART，之后数据口写字节即被当 MIDI 流发出。
- NP2kai 模拟 **MPU-PC98**（`cbus/mpu98ii.c`）：
  - 数据口 = 基址 `0xC0D0`（DIP 可调，引擎按固定 `0xC0D0` 实现，NP2kai 默认即此）
  - 命令/状态口 = 基址 +2（`0xC0D2`）
  - 状态寄存器 bit6 = MIDIOUT_BUSY（0x40），写前须轮询至清
  - 使能由配置 `mpuenable` 控制；未使能的机器读状态返回 0xFF
  - 输出路由：宿主 MIDI 设备 或 内置 **vermouth GS 软件合成器**（X11/libretro 均支持，免外设）
- 实机需 MPU-PC98 兼容卡 + 外置音源模块；无卡时 `hal_audio_detect` 必返回未检测，行为等价旧 stub。

### 2.2 86 板 PCM：YM2608 OPNA + YM3433B

| 端口 | 功能 |
|------|------|
| `A460h` | 设备 ID（D7-4 = ID，本实现不依赖） |
| `A466h` | FIFO 状态 / 电子音量 |
| `A468h` | FIFO 控制 + PCM 速率 |
| `A46Ah` | 量化位（8/16）/ 单双声道 |
| `A46Ch` | FIFO 数据写入 |
| `A66Eh` | 输出静音 |

- PCM 速率 3bit 码：000=44.10k / 001=33.08k / 010=22.05k / 011=16.54k / 100=11.03k / 101=8.27k / 110=5.52k / 111=4.13k
- FIFO 32KB DRAM；支持 8/16 bit、单/双声道
- 引擎用 **60Hz 主循环轮询泵**（非 DMA 非中断）：44.1k 16bit mono = 88200 B/s ≈ 1470 B/帧，FIFO 满则本帧跳过，纯轮询充分——规避实机编 IRQ 复杂度
- **不写 DMA**：帧节奏由 `vblank_wait()` 心跳对齐（main.c:111），NP2kai 下实时性足够；本实现固定 8bit mono 减小搬运量

### 2.3 设计定案（相对草案的收敛）

- **PCM 位深定死 8bit mono**：8bit 单声道 44100B/s ≈ 735 B/帧，搬运量最小、FIFO 更不易满；`.pcm` 转换器将 16bit→8bit 在构建期完成（位移重采样）
- **SE 与 voice 共享单 PCM 通道，后到覆盖**：本轮不引入混音，语义于 B92 文档明示
- **MIDI 事件表常驻内存**：demo 级 .mid 数十 KB 内存可承受，回放循环不经归档二次读

## 3. 复用设施（零新增平台依赖）

| 设施 | 位置 | 用途 |
|------|------|------|
| farchive | `core/lib/farchive.{c,h}`（devdoc 100） | 音频归档 `AUDIO.DAT` 按需读：`lookup_name`/`read_alloc`/`name_match` |
| 毫秒时钟 | `hal_wallclock_ms()`（hal_pc98.c:97，PIT 8254） | MIDI delta-time 调度、PCM 泵节流 |
| 帧心跳 | 主循环 `vblank_wait()`（main.c:111） | 每帧 `audio_tick()` 驱动 |
| 命令层 | `nb_audio.c` | 已解析 key，命令改委托 `audio_*` |
| 归档打包 | `tools/naiz_lib/toc_archive.py` | `make_toc_archive()` 复用出 `AUDIO.DAT` |

## 4. 架构分层

```
┌─ 引擎层 core/engine/nb_audio.c  命令解析（既有）→ audio_* 
│  core/engine/audio.c            BGM 调度 + SE/语音 FIFO 泵 + audio_init/tick/stop_all
│  core/engine/main.c             60Hz 循环 audio_tick()；layer.c 场景停音 → audio_stop_all()
├─ lib 层 core/lib/midi.{c,h}     SMF 解析（纯函数、零 hal 依赖、边界夹逼）
└─ plat 层 core/plat/hal.{h,c}    hal_audio_detect / hal_midi_init/out / hal_pcm_play/tick/stop
   core/plat/hal_pc98.c           MPU-401 UART 初启 + 86 板 FIFO 寄存器写
```

### 4.1 SMF 解析（core/lib/midi.c）

- 遍历 `MThd` 与各 `MTrk` chunk：
  - `MThd`：format/ntrks/division（PPQN 取 division & 0x7FFF；SMPTE 不期支持→返回错误码）
  - `MTrk`：变长 delta-time VLV + 事件
    - 频道消息（Status 0x80-0xEF）：统一转成 3B 预制消息（running status 展开），压成事件 `{abs_tick, b0, b1, b2}`
    - meta（0xFF）：取 `tempo`（51 03）与 `track end`（2F）; 其余丢弃；meta/系统消息不回放
    - system（0xF0/0xF7）：丢弃
- 所有读取以 `len` 为硬边界（C6/C9）：chunk 长度读越界即错误码；事件表 malloc 总长度 = 事件数 × 4B（C1 判空）
- tempo/PPQN → ms：累积 `abs_tick`，逐段 `ms = tick_delta * us_per_quarter / ppqn / 1000`；tempo 变化切段
- 失败返回 `< 0`、成功返回事件数（静默合计指针）；lib 静态规避先例：不 hal_log，引擎调用方 C14 日志
- 内存所有权归调用方（`midi_free`）

### 4.2 BGM 调度（core/engine/audio.c）

- `audio_bgm_start(key)`：`farchive_read_alloc` 取 `.mid` → `midi_parse` → 事件表常驻 + `audio_bgm.wall0 = hal_wallclock_ms()` + `audio_bgm.tick0` 播放头
- `audio_tick()`：`cur = hal_wallclock_ms() - wall0`，滚动播放头到 `ev.tick_ms <= cur`，每事件 `hal_midi_out` 逐字节（b0/b1/b2）；到事件表尾 loop=1 复位播放头+fence 重置
- `audio_bgm_stop()`：16 通道 All-Notes-Off（`0xB0+ch 0x7B 0x00`），清状态；再按须发 reset
- 缺 MPU（detect=0）→ 降级旧 stub 行为（hal_log key），绝不写寄存器

### 4.3 SE/语音 FIFO 泵（core/engine/audio.c + hal_pcm_*）

- 数据结构：`{const uint8_t *data; uint32_t len, pos; uint8_t rate; int loop; int active;}`
- `audio_snd_play/audio_vc_play(key)`：`farchive_read_alloc` 取 `.pcm` → 校验 magic/rate → 写 `A468`(rate 3bit 在 bit0-2，FIFO 控制) 、`A46A`(8bit mono) → `hal_pcm_start`
- `hal_pcm_tick()`：单次至多灌入至 FIFO 空余量（`A466` 状态 + `A468` 控制读回）上限；每帧泵一次直到满为止；pos 越 len 时 loop? 回卷 : stop
- 到 EOF：loop=1 复位 pos，否则 `hal_pcm_stop`（清 A468 FIFO 控制/静音，active=0）
- **加载时机**：`hal_pcm_start` 在开播触发时瞬时读归档；帧泵期不再读盘

### 4.4 .pcm 容器（构建期产物）

```
0x00  magic  "NAIZPCM" (8B)
0x08  rate   1B（0-7，对应 A468 3bit 速率表）
0x09  flags  1B（恒 8bit mono：bit0=1 表示 16bit 未用；loop 建议位不落盘，由素材表语义定）
0x0A  reserved 6B（恒 0）
0x10  数据区（8bit mono 样本）
```
引擎校验 magic + rate∈[0,7]；数据直灌。

## 5. 工具链

| 工具 | 职责 |
|------|------|
| `tools/naiz_audio/wav_convert.py` | WAV→`.pcm`：8bit mono、保原采样率就近归位到 8 档速率表、登记 ASSETS.DB |
| `tools/naiz_audio/gen_test_midi.py` | 生成 GM 单轨测试 .mid（一小节旋律 + program/volume CC），验证全链路 |
| `tools/naiz_audio/pack_audio.py` | 读 ASSETS.DB 新 type（`BGM`/`SND`/`VC`）→ `make_toc_archive` 产出 `AUDIO.DAT`，8.3 名互异硬校验复用 |
| `tools/naiz_build/export_asset_table.py` | 增 `bgm_map/snd_map/voice_map` 三表（对齐 anim_map 先例） |
| `tools/naiz_build/build_game.py` + `tools/naiz_img/inject_common.py` | build 接入 pack_audio；`AUDIO.DAT` 注入 HDI（对齐 SCENE.DAT） |

ASSETS.DB 登记 SQL 模板（对齐 ANI 先例）：
```sql
INSERT INTO img_map (filename, type, name) VALUES ('bgm/test1.mid', 'BGM', 'test1');
INSERT INTO img_map (filename, type, name) VALUES ('se/chime.pcm', 'SND',  'chime');
INSERT INTO img_map (filename, type, name) VALUES ('voice/hi.pcm', 'VC',   'hi');
```

### 5.1 export_asset_table.py 输出

`nb_asset_table.h` 增三表（`#[...]` 未用，带 NULL 终结）：
```c
static const struct { const char *name; int id; } bgm_map[] = { {"test1",0}, {NULL,0} };
static const struct { const char *name; int id; } snd_map[] = { {"chime",1}, {NULL,0} };
static const struct { const char *name; int id; } voice_map[] = { {"hi",2}, {NULL,0} };
```

## 6. 实施步骤

| 步 | 内容 |
|----|------|
| P1 | `core/lib/midi.{c,h}` SMF 解析 |
| P2 | plat：`hal_audio_detect` + MPU UART 初启 + `hal_midi_out` |
| P3 | plat：`hal_pcm_play/tick/stop`（86 板 FIFO，8bit mono 定案） |
| P4 | engine：`audio.c` BGM 调度 + SE/语音泵；`nb_audio.c` 改委托；main.c/layer.c 接线 |
| P5 | tools：wav_convert / gen_test_midi / pack_audio + export_asset_table + build/inject；demo 素材 + nbook001.nb 演示命令 |
| P6 | 验证（见 §7） |
| P7 | 收尾：`bump_version`；B90/B92/B91 更新；防复发规则全查 |

## 7. 验证

1. `make -C core`：0 errors / 0 warnings
2. pytest：`test_wav_convert`（8bit 转换/速率归位/坏文件）、`test_pack_audio`（AUDIO.DAT 往返/8.3 碰撞）、`test_midi_gen`（SMF 字节向量）
3. `start.sh fullaudit` 6/6 全绿（含 symbol_audit A/B --gate）
4. NP2kai：X11 配 MIDI-OUT（宿主或 vermouth）+ 86 板；串口日志断言 `audio_bgm_start/note_on/note_off/audio_pcm_loop` 事件流；实听 BGM+SE
5. 无 MPU 配置回放：detect=0 降级路径不崩溃、日志 WARN

## 8. 已知边界（前置披露）

- NP2kai 侧需 MPU 使能 + MIDI-OUT 设备（X11 内置 vermouth 软合成免外设；libretro 走 RetroArch MIDI 设置）——写入 B92 文档
- 实机需 MPU 卡 + 外置音源；无卡时自动降级旧 stub
- `voice` 与 `sound` 共享单 PCM 通道，后到覆盖（本轮不引入混音）
- 采样率就近归位 + 16bit→8bit 属构建期转制；运行时 MIDI 原样、`.pcm` 直灌，无转格式

## 9. 变更后规约对照

- 增删改 C 函数 → 更新 `docs/B90-参考-函数索引.md`
- NB 命令语义变更（bgm/sound/voice 从 stub→真实）→ 更新 `docs/B92-NB脚本命令参考.md`
- 新增数据管线（AUDIO.DAT/.pcm）→ 更新 `docs/B92 §3`
- 新增 Python 工具 → 更新 `docs/B90`
- 构建环境/运行参数（NP2kai MIDI 配置）→ 更新 `docs/B91`

## 10. 测试向量细节

### 10.1 test_midi_gen
- 生成 bytevector：header `4D 54 68 64` length6 format0 ntrks1 division `01E0`（480PPQN）
- 单轨含：tempo(微秒/四分) + program change + note on/off + track end
- 断言解析引擎（C lib 由 NP2kai 串口事件流人工核验；pytest 仅校验生成字节合法 + wav 越界不崩）

### 10.2 test_wav_convert
- 构造 16bit stereo 随机波 → 转换 → 断言 8bit mono + 长度减半/减四之一（stereo→mono 合并）、rate 码归位、magic 正确
- 构造非法文件（长度不足 44B/非 RIFF）→ 报错退出码

### 10.3 test_pack_audio
- 构造假 .mid/.pcm 文件 → pack_audio 产出 AUDIO.DAT → 用 toc_archive 读回字节一致
- 两文件 8.3 互异冲突（基名超长截断相撞）→ RuntimeError
- 空资产（无 BGM/SND/VC 行）→ 不产出归档或产出 0 项（跟随 SCENE.DAT 先例：无文件则不写）

## 11. 防复发核对（§十七）

P1-P7 全程遵守：C1(malloc 判空)/C2(归档打开失败 C14 日志)/C6/C9(边界夹逼)/C13(static 未用即删)/C21(无 strcpy)/C22(无 INT_MIN 取负)/C23(无双重 free)/C25(无 use-after-free)/C26(无所有权分离 escape)。事件表 `midi_free` 与归属：事件所有权自 read_alloc 起全程归 audio.c，stop 时 free；重建时先 free 后重分配（不存在双重释放路径）。

## 12. 交付确认清单

- [ ] `make -C core` 0 err/0 warn
- [ ] pytest 全绿（新增 3 组测试）
- [ ] `start.sh fullaudit` 6/6
- [ ] demo-a2 含 1 MIDI + 2 SE + 1 voice，`nbook001.nb` 首场景演示
- [ ] `bump_version` 全项目同步
- [ ] B90/B92/B91 文档更新