# PC-98 声音板 (26K & 86)

> **来源**: 
> - PC-9801-26K: http://radioc.web.fc2.com/column/pc98bas/pc980126k_en.htm
> - PC-9801-86: http://radioc.web.fc2.com/column/pc98bas/pc980186_en.htm

---

## PC-9801-26K (OPN)

| 属性 | 值 |
|------|-----|
| 价格 | 25,000 日元 |
| 发售 | 1985年7月 (26), 1986年11月 (26K) |
| 芯片 | YAMAHA YM2203 (OPN) |
| 功能 | FM 3 声道 + PSG 3 声道, 8 音阶, 单声道 |
| I/O | RCA × 1, 3.5mm 单声道 × 1, 内置扬声器, Atari 摇杆 × 2 |
| BIOS ROM | 8KB EPROM × 2 (Sound BIOS for N88-BASIC) |

### 跳线设置

**ROM 地址 (6A2)**:
| 跳线 | 地址 |
|------|------|
| 1-10 | C8000h |
| 2-9 | CC000h (默认) |
| 3-8 | D0000h |
| 4-7 | D4000h |
| 5-6 | 禁用 ROM |

**中断 (6A1, 6A3)**:
| 设置 | 中断 |
|------|------|
| 2-3, 2-3 | INT0 |
| 2-3, 1-2 | INT4 |
| 1-2, 1-2 | **INT5 (默认)** |
| 1-2, 2-3 | INT6 |

**I/O 地址 (6A4)**:
| 跳线 | 端口 |
|------|------|
| 1-4 | 88h |
| 2-3 | **188h (默认)** |

### 集成机型

以下机型内置等同 26K 的音源（无摇杆口）：
PC-9801UV2, UV21, UX21, UX42, CV21, UV11, EX, DX, UF, UR, DA, DS, CS, US, PC-98DO, DO+

### BIOS 兼容

Sound BIOS ROM 为 N88-BASIC(86) 提供音源函数。需在内存开关中启用该 ROM 地址。

---

## PC-9801-86 (OPNA + PCM)

| 属性 | 值 |
|------|-----|
| 价格 | 25,000 日元 |
| 发售 | 1993年 |
| 芯片 | YAMAHA YM2608 (OPNA), YM3433B (PCM), Burr-Brown PCM61P × 2 (DAC) |
| 功能 | FM 6 声道 + SSG 3 声道 + ADPCM + PCM (max 44.1kHz/16bit/2ch) |
| I/O | 麦克风输入 × 1, 线路输入 × 2, Mini 输出 × 2ch, DC 12V 外接电源 |
| FIFO | Oki 32KB DRAM (PCM 播放缓冲) |

### DIP 开关设置 (O=开, X=关)

| 开关 | 功能 | O | X |
|------|------|---|---|
| 1 | I/O 地址 | 288h-28Eh | 188h-18Eh |
| 2 | Sound BIOS ROM | 禁用 | 启用 (CC000h) |
| 3,4 | 中断 | OO=INT0, XO=INT4, XX=INT5, OX=INT6 |
| 5 | 中断启用 | 禁用 | 启用 |
| 6,7,8 | 声音功能 ID | 见下表 |

**声音功能 ID (SW6-8)**:
| SW6-8 | ID | 模式 |
|-------|-----|------|
| XXX | 0 | PC-98DO+ |
| OXX | 1 | PC-98GS |
| XOX | 2 | PC-9801-73 (188h) |
| OOX | 3 | PC-9801-73 (288h) |
| XXO | **4** | **PC-9801-86 (188h, 默认)** |
| OXO | 5 | PC-9801-86 (288h) |
| XOO | 6 | PC-9821Nf/Np |
| OOO | 7 | Mate-X PCM |

### 集成机型

PC-9821Ap, As, Ae, Ce, Af, Ap2, As2, Cs2, Ce2, An 主板集成 86 音源功能。

**注意**: PC-9821Xn（1994年9月）及后期机器的 WSS-PCM 与 86 板**不兼容**。安装 86 板时需在系统设置菜单中禁用 WSS-PCM。

### 兼容声卡

| 产品 | 价格 | 说明 |
|------|------|------|
| 愚蠢 Japan Super Sound 10 (SS-10) | 19,800 | 26K 兼容 (OPN) |
| 愚蠢 Japan Speak Board (SP-26) | 49,800 | 73 兼容 (OPNA+ADPCM) |
| Qvision WaveMaster | 26,800 | 86 完全兼容 (OPNA+PCM+SCSI) |
| Qvision MidiMaster | 12,800 | WaveMaster 子卡 (OPL4+GM MIDI) |

### DOS 音源驱动

大多数 PC-98 DOS 游戏使用第三方驱动，而非 NEC 官方 AVSDRV.SYS：

- **FMP**: FM 音源驱动/播放器
- **PPZ8**: 与 FMP 配合的 PCM 驱动
- **PMD (PMD98)**: FM 音源驱动/播放器 + MML 编译器
