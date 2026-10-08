# OPNA(OPN2)FM 寄存器参考与 BGM 通路选型

> **来源**:
> - Yamaha《YM2608 OPNA Application Manual》英译(`http://nemesis.hacking-cult.org/MegaDrive/Documentation/YM2608J%20Translated.PDF`)——寄存器 bank 选择表、SSG/RHYTHM/ADPCM 寄存器名
> - `ymfm`(`https://raw.githubusercontent.com/aaronsgiles/ymfm/master/src/ymfm_opn.h`,BSD-3-Clause,MAME 所用 FM 核)——FM 寄存器位域与取值范围的**主依据**
> - FMP 官方文档 `fmpdoc.fmp.jp`(`@FA` 音色定义、LFO 页、音色直接变更页)——音色参数名与范围的交叉印证
> - PMD MML 手册英译(`https://pigu-a.github.io/pmddocs/pmdmml.htm`,PMD 4.8,1997-04-04,M.Kajihara 原著)——MML 记谱法与通道分配
> - `mml-guide` PMD 篇(`https://mml-guide.readthedocs.io/pmd/`)、Battle of the Bits `Professional Music Driver Effects Commands`——PMD/FMP 生态与转换工具
> - `YM2608-Tone-Editor`(`github.com/rerrahkr/YM2608-Tone-Editor`,GPL-2.0-or-later)——`.FF` / MUCOM88 `.DAT` 音色文件字段布局(**仅取二进制结构这一硬件无关事实**)
> - NP2kai `README.md` 与 issue #112(`github.com/AZO234/NP2kai`)——模拟器音源配置与保真度投诉
> - 板卡与 DOS 音源驱动沿革:`F01_sound_boards.md`(radioc 列表页)
>
> **许可与转写说明**:本文件**不搬运任何来源的代码**。ymfm 为 BSD-3-Clause、MAME 同源,可作为事实印证渠道;`YM2608-Tone-Editor` 为 GPL-2.0,**仅用于核对二进制字段偏移这一事实,不作文本来源**(AGENTS §十:GPL v2 不得复制)。FMP 文档页表存在**已证实的错误**(见 §5.3),本文件按 ymfm 为准并标出。寄存器位域是硬件行为,不受版权保护。
>
> **配套**:PCM 侧(A4xx)见 `F02_86pcm_registers.md`;板卡构成见 `F01_sound_boards.md`。本文件是**外部知识参考 + 选型分析**,不是引擎规格——引擎侧尚未实现任何 FM 代码(§4.6)。
>
> **⚠ 阅读顺序**:只想拿结论的读者看 **§1**。§3 是寄存器表。§4 是本项目的选型判断(有推荐,但明确标注为**待决**)。§6 是坑。§7 是显式未确认项——**动手前必读**。

---

## 1. 结论先行

### 1.1 三条 BGM 通路对照

| 通路 | 真实 PC-98 硬件 | NP2kai | 本项目代码状态 |
|------|-----------------|--------|----------------|
| **PCM**(语音/音效) | 86 板 YM3433B,**板载标配** | ✅ **已验证可闻** | ✅ 已实现(`hal_audio.c`) |
| **MIDI**(现方案 A) | ⚠️ **需扩展卡**(MPU-401 / Qvision MidiMaster),**PC-98 从无内置 MIDI** | ⚠️ 需**宿主有 MIDI 输出设备**;issue #112 实录 `midiStreamOut failed with error 11`,作者自述 core "is not support MIDI device" | 已实现,但**本机静音**(`hal_audio_detect()` 返回 0) |
| **FM**(方案 C) | ✅ **板载标配**(26K = YM2203 OPN;86 板 = YM2608 OPNA) | ✅ **fmgen 已模拟,开箱可听** | ❌ **未实现**(HAL 无任何 FM 端口访问) |

依据都在本仓:`F01_sound_boards.md:100-102` 的兼容声卡清单里,唯一的 MIDI 选项 **Qvision MidiMaster 明确标注为「WaveMaster 子卡」**;`F02_86pcm_registers.md:33` 直接写「**MIDI(BGM)在另一块卡上**」。

### 1.2 选型结论(已决)

> **已决(0.3.021 第十三轮,承接本文件初稿的「待决」状态)**
>
> | 项 | 决定 |
> |---|---|
> | **输入格式** | **MIDI**(SMF),复用 `core/lib/midi.c` 解析器,不新写解析器 |
> | **后端选择** | **自动检测**:有 MPU-401 走现有 MIDI 通路,无则走 FM |
> | **v1 范围** | **FM 6 通道 + SSG 3 通道**;**RHYTHM 推迟**(§1.4) |
> | **PMD** | **不引入运行时依赖**;仅借鉴 MML 记谱法 |
>
> 落地计划见 `devdocs/123-MIDI转FM通路实现计划.md`。**本节以下的三条理由仍然成立**(它们解释的是「为什么走 FM」,不是「为什么选 MIDI 输入」)。

**主线走自研 FM(OPNA)后端;MIDI 通路保留为「检测到 MPU-401 才启用」;不引入 PMD 作为运行时依赖。**

三条理由,都是硬的:

1. **硬件可得性**:OPNA 是 PC-98 板载标配,不占扩展槽、不需要 1980 年代的第三方卡。MIDI 则是 PC-98 从无内置的、需要扩展卡的路径。
2. **架构相容性**:本项目 HAL 只允许 `core/plat/` 触碰硬件。写 OPNA 寄存器与写现有 A4xx 是同一类动作;而引入 PMD 需要**从 32 位保护模式切回实模式**去调它的 INT 60h 接口,这撞在 `docs/B91` §3 的「32-bit 保护模式禁止表」上,且 PMD **独占 OPNA 芯片**(自行重置寄存器、跑中断驱动的播放循环)。
3. **我们已经站在门口**:`core/plat/hal_audio.c:143` **已经在写 OPNA 的 mask 寄存器**(`outb(PCM_ID_PORT, 0x01)`),`F02` §3.2 已确认其语义为 **bit0 = 选 OPNA / bit1 = 强制 OPNA 静音**——即**一条现成的 FM 静音通路已经存在**;OPNA 端口窗口也已在 `F02` §1 记录。

**这是架构选型,已于 0.3.021 第十三轮拍板**(见本节开头表格)。`devdocs/122-BGM本地静音根因与音频通路取舍.md:213` 曾把「FM 乐谱格式选型(MML/PMD vs 直接驱动 YM2608 vs MIDI+音源映射)」列为待研究项——**该三项中的「MML/PMD」已被排除,选中「MIDI+音源映射」**。**在真的动手前,§7 的未确认项必须先消解**(尤其第 1 条端口分工,它是 S2 的硬门控)。

### 1.4 为什么 v1 不做 RHYTHM(与 §3.6 的 `2608_*.WAV` 直接相关)

RHYTHM 的 6 个鼓读**芯片内置 ROM**,实机零素材依赖;`2608_*.WAV` 是 **NP2kai 模拟器侧**补这段 ROM 用的文件。⇒ 做 RHYTHM 就引入**唯一一处「实机有 / 模拟器要外挂」的行为差异**。v1 改用 **SSG 3 通道**合成鼓(SSG 本身即方波 + 噪声源),使 FM 输出在实机与 NP2kai 上**逐字节一致**。

### 1.3 关于「借用 PMD」的正确说法

PMD 值得借鉴的**只有 MML 这套记谱法**(纯文本、diffable、通道即声部),**不是它的代码**。

- ❌ 不捆绑 PMD 作为运行时依赖:实模式互操作,与 32 位保护模式冲突(§1.2 理由 2)
- ❌ 不读 PMD 的 `.M` 编译产物:`libopenpmd`(`github.com/OPNA2608/libopenpmd`)虽是开源 C 库,但自述为 **WIP**,且**只做文件解析、完全不管芯片输出**——输出那一半仍需自己写,收益有限
- ✅ **采用 MML 作为作曲输入格式**,自己写极简 FM 后端

这个组合(`MML 文本 → 自研解析器 → 自研 FM 后端 → OPNA 寄存器`)正是当年 PC-98 的标准分工:`F01_sound_boards.md:109-110` 记着 **FMP 管 FM、PPZ8「与 FMP 配合的 PCM 驱动」**;`F02_86pcm_registers.md:242` 已证明 **BGM(FM) 与 PCM 语音无资源冲突**,分属 OPNA 与 86 板 PCM 两套通路。

---

## 2. 芯片与板卡定位

| 器件 | FM 通道 | SSG | ADPCM | RHYTHM | 端口 |
|------|---------|-----|-------|--------|------|
| **YM2203**(OPN,26K) | **3** | 3 | — | — | `0188h`–`018Bh` |
| **YM2608**(OPNA,86 板) | **6** | 3 | 1 | 6 通道(内置 ROM) | `0188h`–`018Fh`(DIP 可选 `0288h`–`028Fh`) |

> **⚠ 常见误解纠正**:**YM2203 是 3 个 FM 通道(不是 6 个)**,YM2608 才是 6 个。ymfm 里写死为 `CHANNELS = IsOpnA ? 6 : 3`。
>
> **FM 通道 7/8 不存在于 OPN/OPNA**,它们属于 YM2610(OPN2L)。**OPNA 上没有「LFO 波形选择」**(`WAVEFORMS = 1`),可选波形是 OPL3/OPZ 的特性,不是 OPN 的。
>
> **OPNA 上没有 `D2L` / `DT2L` 寄存器**——那是 OPM/YM2151 的名字。OPN 的包络是 **`AR, D1R, D2R, SL, RR`**。FMP 文档把 `$70` 叫 **SR(Sustain Rate)**,那是 Yamaha 的 **D2R**(`.opm`→OPN 转换会显式丢弃 `DT2/AMD/PMD/WF/NE/SLOT`)。

**YM2608 内部四个模块**:FM(6ch 4-op)、SSG(3ch,YM2149 同源,与 AY-3-8910 寄存器兼容)、ADPCM(单声道)、RHYTHM(6 通道,读内置 ROM 的 6 个鼓采样)。外部配 **YM3016 立体声 DAC**。

**ADPCM 是单声道**,采样率区间各来源说法不一(2–16 kHz / 2–55 kHz / 4-bit),**未实测**,见 §7。

---

## 3. 寄存器参考

### 3.1 寄存器 bank 选择(A1/A0)

芯片用 **A1/A0** 选寄存器 bank。**FM 通道 4–6 的寄存器地址 = 通道 1–3 的地址 + `0x100`**。

| A1A0 | 地址范围 | 作用 |
|------|---------|------|
| `00` | `00`–`2F` | SSG、FM 公共部分、RHYTHM |
| `01` | `30`–`B6` | **FM 通道 1–3** |
| `10` | `00`–`10` | ADPCM |
| `11` | `30`–`B6` | **FM 通道 4–6** |

读操作另有 status 口:`0 0 1 0 xx` = 读 status O,`0 0 1 1 0 xx` = 读 status 1。

### 3.2 FM 逐算子寄存器

算子由**寄存器地址的 bit2–3** 选定,通道由 **bit0–1** 选定。**每个通道 4 个算子(S1–S4)。**

| 寄存器 | 位域 | 字段 | 取值 |
|--------|------|------|------|
| `$30`–`$3F` | `-xxx----` / `----xxxx` | **DT** / **MUL** | 0–7 / 0–15 |
| `$40`–`$4F` | `-xxxxxxx` | **TL**(Total Level,音量) | 0–127 |
| `$50`–`$5F` | `xx------` / `---xxxxx` | **KS**(Key Scale) / **AR**(Attack Rate) | 0–3 / 0–31 |
| `$60`–`$6F` | `x-------` / `---xxxxx` | **LFO AM 使能**\*(OPNA) / **D1R** | 0–1 / 0–31 |
| `$70`–`$7F` | `---xxxxx` | **SR** = Yamaha 的 **D2R** | 0–31 |
| `$80`–`$8F` | `xxxx----` / `----xxxx` | **SL**(Sustain Level) / **RR**(Release Rate) | 0–15 / 0–15 |
| `$90`–`$9F` | `----x---` / `-----xxx` | **SSG-EG 使能 / 包络**\*(OPNA) | 0 / 0–7 |

\* **仅 OPNA**(YM2608)有 bit7 的 AM 使能与整段 SSG-EG。YM2203 的 `$60` bit7 与 `$90`–`$9F` 不存在。

### 3.3 FM 逐通道寄存器

| 寄存器 | 位域 | 字段 | 取值 |
|--------|------|------|------|
| `$A0`–`$A3` | — | **F-number** 低 8 位 | 0–255 |
| `$A4`–`$A7` | `xxx-----` / `-----xxx` | **BLOCK** / **F-number** 高 3 位 | 0–7 / 0–7 |
| `$B0` | `---xxx--` / `-----xxx` | **FB**(Feedback) / **AL**(Algorithm) | 0–7 / 0–7 |
| `$B4` | `xx------` / `------xx` / `----xxxx` | **PAN-L / PAN-R**\*(OPNA) / **LFO AMS** / **LFO PMS**\*(OPNA) | 0–1 / 0–3 / 0–7 |
| `$28` | `---xxxxx` | **KEYON**:CH = bit0–1,OPNA 的 +3 通道用 bit2;KEY 掩码 = bit4–7 | — |

> **YM2203 没有 `$22`,也没有 `$B4` 整条**——即**无 pan、无 LFO 深度**。这是 26K 与 86 板的功能差异,做跨机型兼容时要注意。

### 3.4 系统级寄存器

| 寄存器 | 作用 |
|--------|------|
| `$21` | TEST |
| `$22` | LFO 使能 + 速率\*(OPNA) |
| `$24` / `$25` | Timer A |
| `$26` | Timer B |
| `$27` | CSM / multifreq + timer 控制 |
| `$28` | KEYON(见 §3.3) |
| `$110` | IRQ flag |
| `$B8`–`$BF` | 内部使用,未用 |

**逐算子的「攻击时间快捷寄存器」**(OPNA 扩展通道 3 模式 / Furnace 记法):`$18` 切换扩展 ch3 模式,`$19` 全体算子攻击,`$1A`–`$1D` 算子 1–4 攻击。

### 3.5 SSG 部分(AY-3-8910 同源,3 通道)

方波 / 噪 / 衰减包络,外加**两个 8 位 GPIO 口**。

| 地址 | 作用 |
|------|------|
| `$00`–`$06` | Fine Tune(粗/细调音) |
| `$07` | I/O 方向(`D7`/`D6` 控制 `$0E`/`$0F` 的输入输出) |
| `$08`–`$0C` | 各通道 Noise/Tone 控制、衰减速率 |
| `$0D`–`0F` | I/O Port A / **I/O Port B** |
| `$10` | DM / **RKON**(dump / rhythm KON) |
| `$11` | **RTL**(Rhythm Total Level) |
| `$12` | TEST |

> ⚠ **SSG 的 `$0D`/`$0E` 是 I/O 口,不是寄存器**。驱动 SSG 时若盲目按「连续写寄存器」处理会踩到 GPIO。GPIO 用法需先用 `$07` 设方向。

### 3.6 RHYTHM 与 ADPCM(YM2608 独有)

| 寄存器 | 作用 |
|--------|------|
| `$18`–`$1D` | 6 个鼓通道的 Output Select / Instrument Level |
| `$100`–`$10F` | ADPCM(OKI M6295,**单声道**) |
| `$110` | IRQ flag |

**RHYTHM 的 6 个鼓**读**芯片内置 ROM**,不是外部采样。NP2kai 因此需要 6 个采样文件:`2608_BD.WAV`(底鼓)/ `2608_SD.WAV`(军鼓)/ `2608_RIM.WAV` / `2608_TOP.WAV` / `2608_TOM.WAV` / `2608_HH.WAV`(**库中标注为 Optional**)。

### 3.7 OPNA mask(PC-98 特有,本项目已在用)

**这不是 YM2608 自身的寄存器,而是 86 板上的选择寄存器**,端口 `A460h`:

| 位 | 作用 |
|----|------|
| bit0 | 选择 **OPNA**(1)/ OPN(0) |
| bit1 | 为 1 时**强制 OPNA 输出静音** |

`core/plat/hal_audio.c:143` 目前写 `0x01`(选 OPNA、**不**强制静音),所以**当前 PCM 播放时 FM 是开着的**——若将来加 FM 通路,这条 `0x01` 就是既有的「不静音」默认,无需改动。详见 `F02_86pcm_registers.md` §3.2 / §5.2。

### 3.8 PC-98 侧端口分工(`0188h`–`018Fh` 逐端口消解,0.3.022)

> §7 第 1 条(旧硬阻塞项)现已闭合。出处为 **NP2kai 86 板实现**(`AZO234/NP2kai`,`cbus/board86.c` + `cbus/pcm86io.c` + `cbus/cbuscore.c`,板卡遍历 `attachsndex` stride=2)与 **QEMU `pc98-opna.c`**(同一套端口语义,互为印证)。两者一致,即采用。

**端口窗口**:`0188h`–`018Fh`(DIP 可选 `0288h`–`028Fh`),只对**偶数端口**接线:

| 端口 | 写 | 读 |
|------|----|----|
| `0188h`(+4=0) | **地址锁存低半**(选中普通寄存器组的寄存器地址) | **状态**(status) |
| `018Ah`(+4=1) | **数据写** → 普通寄存器组(SSG/RHYTHM/系统/FM ch1–3) | **寄存器读回**(SSG 区 `0x00`–`0x0F` 回放;`0xFF` 读 = 芯片能力 ID,OPNA 返回 1) |
| `018Ch`(+4=2) | **地址锁存低半(扩展)**:仅当 **OPNA 扩展使能**时生效(§3.7 的 A460 bit0) | 扩展状态 |
| `018Eh`(+4=3) | **数据写 → 扩展寄存器组**(FM ch4–6 `0x30`–`0xB6`,ADPCM `0x00`–`0x10`) | 扩展寄存器读回(ADPCM 采样) |

**关键事实**(S2 实现必须遵守):

1. **FM 初始化必须先写 `A460h` = 0x01**(现 `hal_audio.c:143` 已在 `pcm_play` 时写),**否则扩展窗口 `018Ch`/`018Eh` 不工作**——NP2kai `pcm86_oa460()` 把 bit0 存进 `fmboard_extenable`,只有它置位时 `cbuscore_in/out8` 才把 `018Ch`/`018Eh` 路由给 opna(`pcm86.c`)。
2. **FM 通道 1–3**(bank `A1A0=01`)走 `0188h`+`018Ah`;**通道 4–6**(扩展 bank `A1A0=11`)走 `018Ch`+`018Eh`。KEYON `$28h` 与 SSG 仍走普通组(`0188h`/`018Ah`)。ch4–6 的 KEYON 用 `$28` 的 **bit2 加 3 通道**选择(§3.3),地址仍是普通 bank。
3. 端口读(需 SR 回读的任何调试图)一律经 **`0188h`(写地址)→ `018Ah`(读数据)**;QEMU 与 NP2kai 都支持;SSG `$00`–`$0F` 与 `$FF` 返回可控值(→ 可作为探测手段)。
4. 奇端口(`0189h`/`018Bh`/`018Dh`/`018Fh`)在两家实现都**无处理**——驱动一律写偶数端口。
5. 寄存器地址进位 `0x100`(§3.1 的 `A1A0=10/11`)在 PC-98 侧**由端口对体现**,不是把 `+0x100` 写进地址锁存:扩展组地址就是 `0x30`–`0xB6` 原值。

**F-number 公式**(S1 用):`f = (fnum<<BLOCK) × 7987200 / (144 × 2^20)` → A4(440Hz)= **BLOCK 4 + fnum 520**。交叉验证:`NP2kai/sound/opngenc.c` 的 `OPNA_CLOCK / 144.0` 与 `/ 72.0` 分频基准、S98 `device1clock = 7987200`(**主时钟 = 7.9872MHz 已证**,`s98.c:168`)。SSG 周期寄存器:频率 = `7987200 / 4 / (16 × period)`(19年 fmgen `psg.SetClock(clock/4)`)。

---

## 4. MML 子集(备选记谱法参考,**非本项目输入格式**)

> **⚠ 本节地位**:项目的输入格式已定为 **MIDI**(§1.2)。**本节不是要实现的东西**,而是保留下来作两件事用:
> ① PC-98 记谱法的语法参考(若日后需要人手写谱或做格式对照);② `#Zenlen` 的 CPU 预算警告(§4.5)对**任何**曲式编排都成立,不限于 MML。
> 若只想知道「引擎吃什么」,看 §4.6 即可,不必读本节其余部分。

### 4.1 为什么是 MML(**以及为什么本项目不用它**)

MML(Music Macro Language)是 PC-98 事实上的记谱法:**纯文本、一行一声部、通道字母即音源分配、diffable**。

本项目**不采用**它作为输入格式,理由是它会**丢掉 MIDI 侧已经免费拿到的东西**:

| 维度 | MIDI(SMF) | MML |
|---|---|---|
| 解析器 | **`core/lib/midi.c` 已实现(367 行)**,且保留全部 `0x80–0xEF` | 需**新写** |
| **力度** | 有(`b2` = velocity) | **无** ⇒ 白丢一路表达力,且力度→FM TL 本是近 1:1 映射 |
| 弯音 / CC | 有(bend、sustain pedal 等) | **无** |
| 上游生态 | 项目现有 AI 工具链(Mureka / Suno Studio / basic-pitch)**输出全是 MIDI** | 工具极少 |
| 记谱可读性 | 二进制,不可 diff | **纯文本,可读可 diff** ← MML 唯一的优势 |

⇒ **判据**:MML 的唯一优势(可读可 diff)可以用「素材侧维护」解决,**不需要在引擎里付出丢力度 + 新写解析器的代价**。故 MML 留作参考格式。

### 4.2 核心语法

| 项 | 写法 | 说明 |
|----|------|------|
| **声部标识** | 行首字母 | `A`–`F` = **FM 1–6**;`G`–`I` = SSG 1–3;`J` = PCM;`K` = 节奏选择;`R` = 节奏定义。多个字母**紧邻不空格**表示复声部(`AC1` 合法) |
| **音符** | `c d e f g a b`(+`x`) | `+` 升 / `-` 降 / `=` 本位;`x` = 重复前一音(继承其八度) |
| **时值** | `c4` | 数字 = **全音符除数**(默认全音符 = 96)。`c$10` 十六进制;`c%12` 直接给内部时钟 |
| **附点** | `c4.` | 时值 ×1.5,可叠加 `c2..` |
| **休止** | `r4` | 同音符语法 |
| **八度** | `o4`(1–8,默认 4) | `>` 升 / `<` 降 / `o+`/`o-` 相对 |
| **默认时值** | `l8` | 后续省略时值者沿用 |
| **乐器** | `@0` | `@0`–`@255` |
| **音量** | `v` | |
| **速度** | `#Tempo 60` | **每分钟的二分音符数**;默认二分音符 = 48 时钟 |
| **注释** | `;` 到行尾 | 行首空白 = 整行注释;`` ` `` 成对包裹 |
| **数字** | 十进制 / `$` 十六进制 | `%` 仅在时值处可用 |

**可整除约束**:`#Zenlen`(默认 96)决定合法时值集合 = 96 的因子 `{1,2,3,4,6,8,12,16,24,32,48,96}`;任意不可整除的时值必须用 `%`。

### 4.3 音色定义

```
@ <编号> <ALG> <FB> [=名字]
   <AR> <DR> <SR> <RR> <SL> <TL> <KS> <ML> <DT> <AMS>     ×4 算子
```

| 参数 | 范围 | ymfm 对应寄存器 |
|------|------|---------------|
| ALG | 0–7 | `$B0` 低 3 位 |
| FB | 0–7 | `$B0` bit4–6 |
| **AR** | 0–31 | `$5x` 低 5 位 |
| **DR** | 0–31 | `$6x` 低 5 位 |
| **SR** | 0–31 | `$7x`(**= D2R**) |
| **RR** | 0–15 | `$8x` 低 4 位 |
| **SL** | 0–15 | `$8x` 高 4 位 |
| **TL** | 0–127 | `$4x` |
| **KS** | 0–3 | `$5x` 高 2 位 |
| **ML** | 0–15 | `$3x` 低 4 位 |
| **DT** | −3–+3 或 0–7 | `$3x` 高 3 位 |
| **AMS** | 0–1 | `$6x` bit7(逐算子 LFO AM 使能) |

> **⚠ 别被 FMP 文档的一个错误误导**:FMP「音色直接变更(OPNA)」页的寄存器表把 **SR 范围写成 0–15**,而其音色定义页与 ymfm 都确认 `$70` 是 **5 bit、0–31**。**以 ymfm 为准。**(见 §5.3)

**PMD MML 文件大小上限 61 KB。**

### 4.4 「6 复音」约束的准确表述

真正的约束是 **同一时刻最多 6 个 FM 通道各发一个音**,不是「每声道单音所以要拆和弦」:

- 每通道确实单音(1 通道 = 1 音),但 **4 音和弦吃掉 4 个通道**
- `PMD.COM` 驱动下 **FM 通道 3 可同时发 4 个独立音**(`#FM3Extend` 把这个「扩展 ch3 模式」暴露成更多声部字母)——**这是 OPN 系列的原生特性**,正是它存在的理由
- SSG 的 3 个通道是**额外的**,常被用来补打击乐/低音,进一步缓解 FM 通道紧张
- RHYTHM 6 通道**不占 FM 通道**(走 ADPCM/内置 ROM)

`mc06-音频通路机制.html` 现有的「6 复音」表述准确,不应被替换成「必须拆和弦使每声道单音」。

### 4.5 CPU 预算(PMD 官方警告,直接适用于本项目)

PMD 手册在 `#Zenlen` 条目下明确警告:

> 「全音符越长、时值种类越多,播放时耗 CPU 越多。**特别是要用作电子游戏场景 BGM 的曲目**……把这个值改小,播放时耗 CPU 更少。」

这是**驱动作者自己给的告警**,对本项目直接成立:引擎在渲染对白/立绘的同时还要泵 PCM FIFO(FIFO 泵见 `hal_audio.c` 的 `PCM_TICK_MAX_BYTES`),**FM 事件调度必须与帧预算共存**。⇒ 建议默认 `#Zenlen` 取小值(时值种类少)。

### 4.6 与现有引擎的接口(**已定的数据流**;仍未实现)

> **⚠ 本节已按 §1.2 的决策重写。** 初稿此处自相矛盾——先说「只需把输出后端从 UART 换成 OPNA 寄存器写入」,紧接着又说「`midi.*` 的 SMF 解析器不能直接复用」。两句各自在**不同输入格式**下成立,却并排写在一起且未说明前提。**输入定为 MIDI 后,「不能直接复用」这个否决理由已不作数**:MIDI 正是 `midi.*` 已经在解的格式。

现有 `bgm()` 命令打的是 MPU-401 UART(`core/lib/midi.*`)。改为 FM 后,数据流如下——**前半段(解析 / 时钟 / 循环 / 释放)完全不动,只在事件泵的输出点插入一层翻译**:

```
  SMF (.mid)
     │
     ▼
 core/lib/midi.c   midi_parse()          ← 完全复用,不改一行
     │             保留全部 0x80–0xEF(含 velocity / program change / CC / bend)
     ▼
 MidEvent[]        时间有序,原始字节未解释
     │
     ▼
 audio.c:audio_tick()  60Hz 事件泵        ← 平滑时钟 hal_wallclock_smooth_ms()
     │             替换 core/engine/audio.c:370-374 的 hal_midi_out() 三连透传
     ▼
 【新增】M2  fmseq   MIDI → 6 声部
     │             · GM program → 32B patch(族归并)
     │             · 通道分配 / 抢声策略
     │             · 力度 → TL(近 1:1)
     │             · bend → F-number 偏移
     │             · sustain pedal / note-off → release
     ▼
 【新增】M1  fmopn   纯寄存器模型(零 outb())
     │             · bank 解码(A1A0) · 算子 → 寄存器地址
     │             · 音符 → F-number + BLOCK
     ▼
 【新增】M3  hal_fm_*  core/plat/ 唯一写 0188h–018Fh 处   ← 端口分工见 §3.8(已消解)
     ▼
 ┌────────────────────────┬─────────────────────────┐
 │ 86 板 OPNA (YM2608)    │ 现有 PCM (YM3433B)      │
 │ FM6 + SSG3 → BGM       │ → 语音 / 音效(单通道)   │
 └────────────────────────┴─────────────────────────┘
   两者硬件分离、端口不重叠 ⇒ 可同时发声
   (依据 F02 §1;FM 与 PCM 不构成资源冲突)
```

**为什么 MIDI 输入在这里是净收益**:`MidEvent` 已含 velocity / program change / CC / pitch bend,所以**音区换算与力度映射都是现成数据**,不需要解析器改动;真正要新写的只有 M1/M2/M3 三块,其中 **M1/M2 是纯逻辑、零 `outb()`、可在主机上穷举单测**。

模块拆分、分阶段(S0–S7)与硬门控、音色格式、GM 映射策略、验证矩阵,见 **`devdocs/123-MIDI转FM通路实现计划.md`**。

---

## 5. 音色(patch)格式

### 5.1 纠正一个流传很广的错误前提

**不存在所谓「S98 `.DAT` 音色库」。** S98 是一种**寄存器转储日志**格式(类似 OPN 版的 VGM),`s98spec3.txt` 定义的是头、设备列表(`YM2608`/`YM2151`/`AY-3-8910`…)、寄存器 dump、标签与时序——**它根本没有乐器/tone 这个概念**。歌曲文件是 `.s98`。

`FM-SoundConvertor` 把 MUCOM88 `.dat`、FMP `.mwi`、PMD `.mml`、VOPM `.fxb` 列为**四个互不相同的格式**,独立佐证 `.dat` 不是通用标准。

### 5.2 现存的 4-op 音色库格式

| 格式 | 记录大小 | 结构 | 工具链 |
|------|---------|------|--------|
| **PMD `.FF`** | **32 B**,最多 256 条(`size % 0x20 == 0`,上限 `0x2000`) | `+0x00..+0x17` 4 算子 × 6 B(偏移 `{0,6,12,18}`);`+0x18` FB/AL;`+0x19..+0x1F` **7 字节** SJIS 名 | PMD/MC.EXE、`YM2608-Tone-Editor` |
| **MUCOM88 `.DAT`** | **固定 `0x2000` = 256 × 32 B**,无头无计数 | `+0x01..+0x18` 4 算子 × 6 B(偏移 `{1,7,13,19}`);`+0x19` FB/AL;`+0x1A..+0x1F` **6 字节** SJIS 名 | MUCOM88 |
| YM2612 Inst. Editor `.DAT` | 可变长列表 | `+0x00..0x01` 大端条数 N;其后 N 组 (寄存器地址, 值);地址限 `$30`–`$9F` + `$B0` + `$B4` | 一次一个音色 |
| FMP | **无文件** | 音色内嵌在曲子里,用 MML 文本 `@` 定义 | FMP7/exFMP7 |

每算子 6 字节均为:`DT/MUL, TL, KS/AR, AM/D1R, D2R, SL/RR`。

### 5.3 三个必须注意的坑

1. **算子顺序被置换**。MUCOM88 `.DAT` 与 PMD `.FF` 都把算子存成 **1/3/2/4** 置换顺序(而非自然序 1/2/3/4)。ymfm 的 `operator_offset()` 算出同样的置换 `(opnum % 12) + ((opnum % 12) / 3)`——这正是 6 字节步长能落在正确寄存器上的原因。**搞错会静默地把每个算子音高都调错。**
2. **DT 编码在不同格式间不一致**。`.dat` 存硬件原始编码 **0–7**;`.tfi`/`.vgi` 用**线性 −3..+3**。跨格式直接拷字节会改变音高。
3. **名字字段长度不同**:MUCOM88 6 字节 vs PMD `.FF` 7 字节(均 SJIS),互不兼容。

**另外两处文档缺陷(已证实)**:FMP「音色直接変更(OPNA)」寄存器表把 SR 范围写成 0–15(应为 0–31);MUCOM88 `.dat` 与 Inst. Editor `.dat` 都**忽略 `$B4` 的 pan 位**。

### 5.4 许可:结论是不可用

**未找到任何 CC0 / 公有领域的 OPN patch 库。** 所有能找到的音色库都是**受版权保护的商用或免费Ware 转储**(MUCOM88 默认组、PMD `.FF`、FMP 音色集、EUPHONY `.FMB`)。

工具许可与**数据**许可无关:**转换工具的许可不会传递给被转换的数据**。

**⇒ 建议自研音色格式。** 一个 32 字节记录足以覆盖 MUCOM88/PMD 的全部能力并再加上 pan:

```
4 × { DT, MUL, TL, KS, AR, AM, D1R, D2R, SL, RR, SSG-EG }  +  AL, FB, PAN-L, PAN-R  +  名字
```

存成文本/JSON 放进 `assets/<项目>/`,沿用现有 `ASSETS.DB` 登记方式——这样既不沾 GPL,又能日后与 `.FF`/`.dat` 互转。**另两条不是版权问题、且完全够用**:寄存器语义本身(§3,硬件事实)与自己合成的音色。

工具许可参考:ymfm/MAME **BSD-3-Clause**(最干净);`YM2608-Tone-Editor` **GPL-2.0-or-later**(仓库**不含任何音色库**);BambooTracker GPL-2.0;Dn-FamiTracker GitHub 报 `NOASSERTION`(自定义头)。

### 5.5 生态里可用的现成素材(仅事实登记,许可待定)

PMD 官方「PMD98用 Preset FM音色集」由 KAJA 本人分发(<http://www5.airnet.ne.jp/kajapon/tool.html>,含 `.FF` 与纯文本两种形式);另有第三方音色集。**这些是可发现的事实,但授权条款未核实**,不构成「可用」结论。

### 5.6 MIDI ⇄ MML 转换(订正此前记录)

此前调研断言「无 PC-98/PMD 可用的 MIDI→MML 转换器」,**这句话需要收窄**:

- **ConvFMML(`github.com/rerrahkr/ConvFMML`)确实以 PMD 为输出目标之一**——mml-guide 明确写「A `.MID` -> MML converter for various formats **including PMD**」,**我此前把它归为「只面向别的方言」是错的**。
- 但**结论不变**,理由是质量而非方向:该工具**已停止维护**,且只转换序列数据、**只支持极少的命令**(mml-guide 原话 "Only converts sequence data and very few commands")。⇒ 不可作为依赖。
- 其他查到的 MIDI→MML(`midi2mml` 自述为 RP2040 玩具、`PetiteMM` 是 TinyMM 替代、tom7 `midimml` 面向 NES/NSF)**确实不是 PMD 方言**——**MML 是方言家族**,PMD 方言与其他不兼容。

反向工具:`PMD2S98`(.M→.S98)、`pmd2mid`(`github.com/ValleyBell/MidiConverters`,.M→.MID,仅源码需自建)、`pmd2mml`(见下)、`s3mml`(OPL2→PMD MML,顺带用 OPNA 格式近似重建音色)、`dmf2pmd`(Genesis .DMF→PMD MML)。

> **`pmd2mml` 方向**:它是 **PMD 二进制 → MML 反编译器**(`github.com/Blargzargo/pmd2mml`,**LGPL-3.0**),**不是 MIDI→MML**。此前记录正确。

---

## 6. 陷阱清单

1. **`D2L`/`DT2L` 在 OPN 上不存在**。看到这两个名字基本可以断定来源是 OPM/YM2151 的资料。OPN 是 `AR/D1R/D2R/SL/RR`。
2. **FMP 文档 SR 范围 0–15 是错的**,实为 0–31。以 ymfm 为准。
3. **算子顺序置换(1/3/2/4)** 静默出错,不报错但每个算子音高都错。
4. **DT 编码跨格式不一致**(原始 0–7 vs 线性 −3..+3)。
5. **SSG 的 `$0D`/`$0E` 是 GPIO 不是寄存器**,连续写会踩 GPIO;须先用 `$07` 设方向。
6. **YM2203 无 `$22`、无 `$B4`**,即无 pan、无 LFO 深度;跨 26K/86 兼容必须降级。
7. **`$28` KEYON 的通道选择含 OPNA 专属 bit2**(+3 通道),移植时容易漏。
8. **OPNA mask(`A460h`)bit1 = 强制 FM 静音**。改 PCM 路径的 `A460` 写入值会**静默把 FM 一起静音**。当前写 `0x01`(不静音)。
9. **RHYTHM 6 通道读内置 ROM**,不是外部采样;NP2kai 侧的 `2608_*.WAV` 是**可选**文件。
10. **PMD 自己的 CPU 警告**:`#Zenlen` 取大会显著增加播放 CPU,游戏 BGM 尤其明显(§4.5)。
11. **`.M`/`.dat` 音色库全部受版权保护**,工具许可≠数据许可(§5.4)。

---

## 7. 未确认项(显式标注,勿当已验证)

| # | 项 | 状态 |
|---|----|------|
| **1** | **`0188h`–`018Fh` 每个端口对应哪个 bank 的「地址」还是「数据」** | ✅ **已消解(0.3.022)**。NP2kai(`board86.c`/`pcm86io.c`/`pcm86.c`/`fmboard_extenable`)与 QEMU `pc98-opna.c` 给出**一致**的端口分工,见 **§3.8**:`0188h`=地址锁存+RW、`018Ah`=数据读写普通组、`018Ch`/`018Eh`=扩展组且受 A460 bit0 使能门控。 |
| 2 | FM 音质在 **NP2kai vs 独立 `np2fmgen` 构建** | **NP2kai 较差,已有投诉但未量化。** issue #112 实录其 FM「tinny / distorted」,对比独立 `np2fmgen` 构建;作者归因于 fmgen 与音量混音,并表示仍在调。⇒ **模拟器里能听出 FM,但不要把模拟器听感当作参考级音质**。 |
| 3 | ADPCM 采样率与音质 | 各来源说法不一(2–16 kHz / 2–55 kHz / 4-bit),**未实测**。 |
| 4 | YM3433B PCM 的实际采样率档位 | `hal_pcm_play()` 用 `rate` 码 0–7 编程,但**各档对应的实际采样率未在本仓确认**(F02 §7 已列 8bit/16bit 音质差异未测)。 |
| 5 | PMD / FMP 音色库的**授权条款** | 未核实。§5.4 的「不可用」结论只依赖「未找到 CC0/公有领域库」+「商用转储受版权保护」,**不依赖对具体库的条款判断**。 |
| 6 | 26K(YM2203)与 86 板(YM2608)在**实机上的装机比例** | 未知。影响「兼容两代」是否值得投入。 |
| 7 | FM 事件调度与现有帧循环 + PCM FIFO 泵的**实测 CPU 占用** | 未测。§4.5 只给出 PMD 的定性警告。 |
| 8 | `RYO` 音色格式规格 | **未能取得一手规格**,故本文件**不含任何 RYO 相关断言**。 |
| 9 | EUPHONY(FM Towns)`.FMB` 字段布局 | 6152 字节为二手来源,结构未证。FM Towns 是 YM2612 + RF5C68,**与 PC-98 非同一血脉**。 |
| 10 | YMPLAY / UNIMON / MML 系 tracker 的音色格式 | **未取得一手来源**,故不作断言。 |

---

## 8. 来源索引(本文件新增)

| 来源 | URL | 用途 | 许可 |
|------|-----|------|------|
| YM2608 OPNA Application Manual(英译) | `http://nemesis.hacking-cult.org/MegaDrive/Documentation/YM2608J%20Translated.PDF` | bank 选择表、SSG/RHYTHM/ADPCM 寄存器名 | Yamaha 文档 |
| ymfm `ymfm_opn.h` | `https://raw.githubusercontent.com/aaronsgiles/ymfm/master/src/ymfm_opn.h` | **FM 寄存器位域/范围主依据** | BSD-3-Clause |
| FMP 官方文档 | `http://fmpdoc.fmp.jp/` | 音色参数名与范围交叉印证 | FMP |
| PMD MML 手册英译(PMD 4.8) | `https://pigu-a.github.io/pmddocs/pmdmml.htm` | MML 语法与通道分配 | KAJA 原著 / 英译 |
| mml-guide PMD 篇 | `https://mml-guide.readthedocs.io/pmd/` | PMD 生态、转换工具、素材 | CC-BY? |
| BOTB PMD Effects Commands | `https://battleofthebits.org/lyceum/View/Professional%20Music%20Driver%20Effects%20Commands` | PMD 命令客观参考 | — |
| S98 规格 | `http://vgmrips.net/mirror/s98spec3.txt` | **证伪「S98 `.DAT` 音色库」** | — |
| YM2608-Tone-Editor | `https://github.com/rerrahkr/YM2608-Tone-Editor` | `.FF`/MUCOM88 `.DAT` 字段偏移 | **GPL-2.0-or-later**(仅核对二进制事实) |
| libopenpmd | `https://github.com/OPNA2608/libopenpmd` | **WIP**,只解析不管输出 | — |
| pmd2mml | `https://github.com/Blargzargo/pmd2mml` | **PMD→MML 反编译器**(非 MIDI→MML) | LGPL-3.0 |
| ConvFMML | `https://github.com/rerrahkr/ConvFMML` | **PMD 是其输出目标之一**;已停止维护 | — |
| NP2kai | `https://github.com/AZO234/NP2kai` | 音源配置;issue #112 保真度投诉 | — |
| PMD98 Preset FM 音色集(KAJA) | `http://www5.airnet.ne.jp/kajapon/tool.html` | 现成素材(**授权未核**) | — |
| FM Towns Technical Databook(3rd, 1994, Chiba/ASCII) | 经 `https://raw.githubusercontent.com/captainys/TOWNSEMU/master/references.txt` 转引 | EUPHONY 背景 | — |
| NP2kai 86 板源码 | `github.com/AZO234/NP2kai` → `cbus/board86.c` / `pcm86io.c` / `cbuscore.c` / `pcm86.c` / `sound/opna.c` / `sound/opngenc.c` / `sound/s98.c` | **§3.8 端口分工唯一出处**;主时钟 7987200 确认;KEYON/pan/寄存器细节 | — |
| QEMU `hw/audio/pc98-opna.c` | `gitlab.com/qemu-project/qemu`(PC-98 ops 界面) | §3.8 端口语义第二出处(与 NP2kai 一致) | GPL-2.0(仅事实参照) |

---

**下一步**:§7 余项中第 2/5/6 条对后期调优有影响但不阻塞 S1–S5;**端口分工(第 1 条)已消解于 §3.8**,硬阻塞项解除。本文件**不构成实现授权**,实现授权见 `devdocs/123`。
