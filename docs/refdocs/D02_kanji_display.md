# PC-9800シリーズでの漢字の表示

> **作者**: なむら
> **来源**: [printf.neocities.org](https://printf.neocities.org/pc98/99_kanji.html) (Wayback Machine 归档)
> **原文编码**: Shift-JIS

---

## 1. 文字 VRAM 的结构

PC-98 的文字显示采用 80 列 × 25 行模式。文字 VRAM 位于 0xA0000-0xA3FFF，分为两个区域：

- **文字码区**: 0xA0000-0xA1FFF (80×25=2000 字 × 2 字节)
- **属性区**: 0xA2000-0xA3FFF (每个文字对应一个属性字节)

### ANK (半角) 文字

半角文字每个占 2 字节：

```
Addr+0: ANK 代码
Addr+1: 0x00
```

### 汉字 (全角) 文字

全角文字每个占 4 字节：

```
Addr+0: JIS コード (上位) - 0x20
Addr+1: JIS コード (下位)
Addr+2: JIS コード (上位) + 0x60
Addr+3: JIS コード (下位)
```

其中 JIS コード 是汉字在 JIS 中的区点编号。注意不是 Shift-JIS，而是 JIS 编码。

**重要**: 直接写入文字 VRAM 时，必须使用 JIS 编码（即区点表示），而非 Shift-JIS。Shift-JIS 需要转换为 JIS 后写入。

## 2. 属性字节

属性字节位于 0xA2000-0xA3FFF，每个文字对应 1 字节：

| Bit | 说明 | 备注 |
|-----|------|------|
| 7 | G (绿) | — |
| 6 | R (红) | — |
| 5 | B (蓝) | — |
| 4 | VL (垂直行) | — |
| 3 | UL (下划线) | — |
| 2 | RV (反转) | — |
| 1 | BL (闪烁) | — |
| 0 | SP (消去) | 0=显示, 1=不显示 |

文字颜色的 RGB 信号与通用约定相反：Bit7=绿, Bit6=红, Bit5=蓝。

## 3. BIOS 功能 (INT 18h)

以下是使用汉字显示的 BIOS 功能：

### AH=0x50: 汉字写入

```
AH = 0x50
AL = 写入的文字数
BH = 写入的开始行 (0-24)
BL = 写入的开始列 (0-79)
DS:CX = 汉字 JIS 码的偏移地址
ES:DX = 属性字节的偏移地址

输出: 无
```

该功能将汉字写入文字 VRAM。

### AH=0x71: 字符串写入

```
AH = 0x71
BH = 写入的开始行 (0-24)
BL = 写入的开始列 (0-79)
AL = 0x01 (写入位指定)

DS:DX = 字符串指针
CX = 文字数
```

该功能将 Shift-JIS 字符串写入文字 VRAM。

### AH=0x00: 键盘输入 (等待)

```
INT 18h / AH=0x00
输出:
  AH = 机种依赖的扫描码
  AL = JIS 8 ビットコード (半角) / 0xFF (全角)
  BF = (全角时) JIS コード 上位
```

返回的 JIS コード 可用于 BIOS 汉字写入。

## 4. 从文件名读入

由于 PC-98 的文件名是 Shift-JIS (部分 ROM/RAM 盘可能不同)，需要正确处理。

PC-98 的 ROM BIOS 使用 "A.COM" 和 "B.SJIS" 两种方式处理文件名：
- 全角文件名使用 Shift-JIS
- 实际的目录/文件访问转化为内部编码

在 DOS 层面，INT 21h 的文件功能也使用 Shift-JIS 文件名。

## 5. まとめ

1. 文字 VRAM 直接写入需要 JIS 编码（区点表示）
2. Shift-JIS → JIS 转换公式：
   - 如果是第 1 字节 (0x81-0x9F, 0xE0-0xEF):
     JIS 高位 = (Shift-JIS 高位 - 0xA0) >> 1 (1-15区)
     JIS 低位 = Shift-JIS 低位 - 0x40 - (是否为偶数区 ? 0x1F : 0)
     如果是偶数区, JIS 高位 += 0x70
   - 如果是第 2 字节 (0xF0-0xFC):
     JIS 高位 = (Shift-JIS 高位 - 0xA0) >> 1 + 0x10 (16-47区)
     JIS 低位 = Shift-JIS 低位 - 0x40 (- (是否为偶数区 ? 0x1F : 0))
3. 属性字节的彩色位顺序是 G-R-B (与 VRAM 平面的 B-G-R 不同)
4. BIOS AH=0x50 可以批量写入汉字到文字 VRAM
5. 通过 BIOS AH=0x71 可以直接写入 Shift-JIS 字符串
