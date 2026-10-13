# PMD MML 手册（英译全文）：P.M.D. 4.8 MML Command Manual

> **来源**：https://pigu-a.github.io/pmddocs/pmdmml.htm
> **原著**：*Professional Music Driver [P.M.D.] version 4.8 MML Command Manual*，Apr. 4th 1997, by M.Kajihara (KAJA)
> **英译**：Blaze and Pigu；**HTML 版**：Pigu（GitHub Pages，仓库 https://github.com/Pigu-A/pmddocs ，基于 PC-98 DOS 商业版 4.8o 文档包整理）
>
> **性质说明（勿混淆）**：PMD MML 是 **PMD 驱动的输入语言**。**本项目 BGM 输入已定为 MIDI**（`F03_opna_fm_and_bgm_routes.md` §1.2，0.3.021 第十三轮决议：复用 `core/lib/midi.c`，不新写解析器）。本文件是**音乐侧参考**，用途有三：
> 1. 若调研 MIDI→FM 通路时对标「PC-98 原生音乐生态」的记谱/通道/音色概念，提供完整术语表；
> 2. `#Tempo`/`#Timer`/`#Zenlen` 与 Timer-B 的关系（见 `F05_pmd_driver_architecture.md` §2）以本手册 §2.10/§11 为准；
> 3. `y<register>,<value>` 直写等命令证明 OPNA 寄存器图是 PC-98 作曲者的显学（寄存器参考见 `F03`/`F04`）。
>
> **许可与转写说明**：本文是第三方英译文档的完整落盘（原站自述为文档整理，无代码搬运）。保留全部章节结构与术语；English text below is a faithful full conversion of the source HTML;章节编号、命令名、范围值按原文转写，未作改写。文中 `→` 交叉引用为原文档的内部跳转，在纯文本中保留编号。
>
> **本地导读**：§2.10 Tempo Setting（Timer-B 语义）、§1.1.3 通道-音源对应表（PMD/PMDB2 通道分配）、§3.1 FM 乐器定义（@ 参数表）、§14 节奏音源命令，与本项目 FM 通路关联最紧。

---

（以下为 pmdmml.htm 全文转换，GFM 格式，共 4654 行）



### Table of Contents

1\. [Basic Matter](#1)

-   1.1. [Part Notation](#1-1)
    -   1.1.1. [Part Notation Method](#1-1-1)
    -   1.1.2. [Multiple-channel Notation](#1-1-2)
    -   1.1.3. [Correspondence Between Channel Notation and Sound Sources](#1-1-3)
-   1.2. [Using the Rhythm Channel (K/R)](#1-2)
    -   1.2.1. [Using the Internal SSG Drums](#1-2-1)
    -   1.2.2. [Using the YM2608 Rhythm Sound Source](#1-2-2)
    -   1.2.3. [Using the K/R Channels' Rhythm With the SSG Channels](#1-2-3)
-   1.3. [Numerical Notation Methods](#1-3)
-   1.4. [Comment Notation Methods](#1-4)

2\. [Overall Control Commands](#2)

-   2.1. [Output Filename Specification](#2-1)
-   2.2. [Use SSGPCM Filename Setting](#2-2)
-   2.3. [Use PCM Filename Setting](#2-3)
-   2.4. [Use Instrument Filename Setting](#2-4)
-   2.5. [Compiler Option Settings](#2-5)
-   2.6. [Title Definition](#2-6)
-   2.7. [Composer Definition](#2-7)
-   2.8. [Arranger Definition](#2-8)
-   2.9. [Memo Definition](#2-9)
-   2.10. [Tempo Setting](#2-10)
-   2.11. [Whole Note Length Setting](#2-11)
-   2.12. [Octave Up/Down Sign Function Setting](#2-12)
-   2.13. [Default Loop Count Setting](#2-13)
-   2.14. [Whether To Use DT2 In Instrument Data Setting](#2-14)
-   2.15. [Bend Range Setting](#2-15)
-   2.16. [SSG Pitch Extend/Normal Selection](#2-16)
-   2.17. [Software LFO Speed Extend/Normal Selection](#2-17)
-   2.18. [Software Envelope Speed Extend/Normal Selection](#2-18)
-   2.19. [PCM Volume Value Extend/Normal Selection](#2-19)
-   2.20. [FM Channel 3 Expansion](#2-20)
-   2.21. [MML File Insertion](#2-21)
-   2.22. [Separate Volume Down Setting](#2-22)
-   2.23. [PCM Channel Specification Setting](#2-23)
-   2.24. [Playback Start Position Setting](#2-24)
-   2.25. [PPZ8 Channel Extension](#2-25)
-   2.26. [PPZ PCM Filename Setting](#2-26)
-   2.27. [Overall Transposition Setting](#2-27)

3\. [Definition Commands](#3)

-   3.1. [FM Instrument Definition](#3-1)
-   3.2. [MML Variable Definition](#3-2)

4\. [MML Commands — Pitch Interval/Duration](#4)

-   4.1. [Pitch Interval/Duration Setting](#4-1)
-   4.2. [Rest/Duration Setting](#4-2)
-   4.3. [Portamento Setting](#4-3)
-   4.4. [Octave Setting](#4-4)
-   4.5. [Octave Up/Down](#4-5)
-   4.6. [Octave Up/Down Notation Reversal](#4-6)
-   4.7. [Whole Octave Change](#4-7)
-   4.8. [Default Length Setting](#4-8)
-   4.9. [Processing the Previously Used Note Length](#4-9)
-   4.10. [Tie/Slur Setting](#4-10)
-   4.11. [Whole Note Length Setting](#4-11)
-   4.12. [Sound Cut Setting 1](#4-12)
-   4.13. [Sound Cut Setting 2](#4-13)
-   4.14. [Modulation Setting](#4-14)
-   4.15. [Transposition Setting](#4-15)
-   4.16. [Master Modulation Setting](#4-16)

5\. [MML Commands — Volume Section](#5)

-   5.1. [Volume Setting 1](#5-1)
-   5.2. [Volume Setting 2](#5-2)
-   5.3. [Overall Volume Change 1](#5-3)
-   5.4. [Overall Volume Change 2](#5-4)
-   5.5. [Relative Volume Change](#5-5)

6\. [MML Commands — Instrument Setting Section](#6)

-   6.1. [Instrument Number Setting](#6-1)
    -   6.1.1. [FM Channels Case](#6-1-1)
    -   6.1.2. [SSG Channels Case](#6-1-2)
    -   6.1.3. [SSG Rhythm Definition (Without PPSDRV) Case](#6-1-3)
    -   6.1.4. [SSG Rhythm Definition (With PPSDRV) Case](#6-1-4)
    -   6.1.5. [PCM Channels Case](#6-1-5)
-   6.2. [FM Slot Use Setting](#6-2)
-   6.3. [FM TL Setting](#6-3)
-   6.4. [FM FB Setting](#6-4)
-   6.5. [SSG/OPM Tone/Noise Output Selection](#6-5)
-   6.6. [Noise frequency setting](#6-6)
-   6.7. [Rhythm Pattern Selection/Playback](#6-7)

7\. [MML Commands — Detune section](#7)

-   7.1. [Detune Setting](#7-1)
-   7.2. [FM Channel 3 Per-Slot Detune Setting](#7-2)
-   7.3. [SSG Pitch Interval Correction Setting](#7-3)
-   7.4. [Bend Width Setting](#7-4)
-   7.5. [Pitch Setting](#7-5)
-   7.6. [Master Detune setting](#7-6)

8\. [MML Commands — Envelope Section](#8)

-   8.1. [SSG/PCM Software Envelope Setting](#8-1)
    -   8.1.1. [Format 1 Case](#8-1-1)
    -   8.1.2. [Format 2 Case](#8-1-2)
-   8.2. [Software Envelope Speed Setting](#8-2)

9\. [MML Commands — LFO Section](#9)

-   9.1. [Software LFO Setting](#9-1)
    -   9.1.1. [MW0 Case (Triangle Wave 1)](#9-1-1)
    -   9.1.2. [MW1 Case (Sawtooth Wave)](#9-1-2)
    -   9.1.3. [MW2 Case (Square Wave)](#9-1-3)
    -   9.1.4. [MW3 Case (Random Wave)](#9-1-4)
    -   9.1.5. [MW4 Case (Triangle Wave 2)](#9-1-5)
    -   9.1.6. [MW5 Case (Triangle Wave 3)](#9-1-6)
    -   9.1.7. [MW6 Case (One-shot)](#9-1-7)
-   9.2. [Software LFO Waveform Setting](#9-2)
-   9.3. [Software LFO Switch](#9-3)
-   9.4. [Software LFO Slot Setting](#9-4)
-   9.5. [Software LFO Speed Setting](#9-5)
-   9.6. [Dedicated Rise/Fall LFO Setting](#9-6)
-   9.7. [LFO Depth Temporal Change Setting](#9-7)
-   9.10. [Hardware LFO Speed/Delay Setting](#9-10)
-   9.11. [Hardware LFO Switch/Depth Setting (OPNA)](#9-11)
-   9.12. [Hardware LFO Frequency/Waveform/Depth Setting (OPM)](#9-12)
-   9.13. [Hardware LFO Delay Setting](#9-13)

10\. [MML Commands — Loop Control Section](#10)

-   10.1. [Local loop setting](#10-1)
-   10.2. [Global loop setting](#10-2)

11\. [MML Commands — Tempo Setting Section](#11)

-   11.1. [Tempo Setting 1](#11-1)
-   11.2. [Tempo setting 2](#11-2)

12\. [MML Commands — Note Processing Commands](#12)

-   12.1. [Grace Note Setting](#12-1)
-   12.2. [Pseudo Echo Setting](#12-2)
-   12.3. [Keyon Delay Per Slot Setting](#12-3)
-   12.4. [Broken Chord Setting](#12-4)

13\. [MML Commands — Pan Setting Commands](#13)

-   13.1. [Pan setting 1](#13-1)
-   13.2. [Pan Setting 2](#13-2)

14\. [MML Commands — Rhythm Sound Source Commands](#14)

-   14.1. [Rhythm Sound Source Shot/Dump Control](#14-1)
-   14.2. [Rhythm Sound Source Master Volume Setting](#14-2)
-   14.3. [Rhythm Sound Source Individual Volume Setting](#14-3)
-   14.4. [Rhythm Sound Source Output Position Setting](#14-4)

15\. [MML Commands — FM Chip/Driver Control](#15)

-   15.1. [FM Chip Direct Output](#15-1)
-   15.2. [PDR Operation Mode Control](#15-2)
-   15.3. [Fade Out Setting](#15-3)
-   15.4. [Individual Sound Source Volume Down Setting](#15-4)
-   15.5. [FM Sound Effect Playback](#15-5)
-   15.6. [SSG Sound Effect Playback](#15-6)
-   15.7. [Channel Mask Control](#15-7)
-   15.8. [Measure Length Setting](#15-8)
-   15.9. [Write to Status1](#15-9)
-   15.10. [PCM Method Selection](#15-10)

16\. [MML Commands — Compiler Control](#16)

-   16.1. [Defined Variable Utilization](#16-1)
-   16.2. [MML Skip Control 1](#16-2)
-   16.3. [MML Skip Control 2](#16-3)
-   16.4. [Part Limit Setting](#16-4)
-   16.5. [Compilation End](#16-5)
-   16.6. [Comment Setting](#16-6)
-   16.7. [Comment Setting 2](#16-7)

17\. [Producer Contact/Inquiries](#17)





``` title
    /IIII\  //| |I\  /IIII\   /|/\  /|/\  /
   //   // // \/ // //    I  /   / /   / /
  /IIII// //    // //    // /   / /   / /____
 //      //    // //    //
//      //    //  IIIII/  .MAN    [EN] [HTML]
```



\*Professional Music Driver \[P.M.D.\] version 4.8 MML Command Manual\*  
  
Apr.4th 1997 by M.Kajihara (KAJA)  
English Translation by Blaze and Pigu  
HTML Version by Pigu



# 1. Basic Matter

Explains the underlying matters of MML notation.

## 1.1. Part Notation

### 1.1.1. Part Notation Method

At the head of the line, specifying an attached alphabet letter for each channel will cause that channel to be played by MML.

MML will compile each in order from the beginning, and produce a composition.

It is necessary to separate the MML code from the channel notation with SPACE or TAB.

Example

    A @1v13cdefg

Result This MML will cause channel A to produce sound.

Incorrect Example 1

     A @1v13cdefg

Cause The channel notation is not at the beginning of the line.  
Result Because MML does not recognize this, it will not treat it as a command.

Incorrect Example 2

    A@1v13cdefg

Cause There is no SPACE or TAB between the channel notation and the MML.  
Result This is recognized as multiple-channel notation. ([→§1.1.2.](#1-1-2))

### 1.1.2. Multiple-channel Notation

It is possible to conjugate several channels in one part.

When specifying more than one, please do not leave space in between each channel notation.

If you specify a non-existent channel, it will not cause an error and will be skipped.

By using this in reverse, inputting the numerical value immediately after the channel notation will make the MML easier to read. This is especially useful for rhythm parts.([→§1.2](#1-2))

Example 1

    AC @1v13cdefg

Result This MML will produce sound from both channel A and C.

Example 2

    AC1 @1v13cdefg

Result This MML will produce sound from both channel A and C. "1" is ignored.

Incorrect Example

    A C @1v13cdefg

Cause The channel notation is separated.  
Result "C" is recognized as an MML command.

See also

-   \| command ([→§16.3.](#16-3))

### 1.1.3. Correspondence Between Channel Notation and Sound Sources

Depending on the driver(Sound Source), the assignment of channel notation to the sound source will differ.

According to the list below, any part may be specified by the user. ([→§2-18](#2-18),[§2-25](#2-25))

1\. PMD.COM / PMDVA1.COM (98,88VA1 normal driver)  
|            |                              |
|------------|------------------------------|
| A          | FM Channel 1                 |
| B          | FM Channel 2                 |
| C          | FM Channel 3                 |
| D/other FM | FM Channel 3                 |
| E/other FM | FM Channel 3                 |
| F/other FM | FM Channel 3                 |
| G          | SSG Channel 1                |
| H          | SSG Channel 2                |
| I          | SSG Channel 3                |
| K          | Rhythm Pattern Specification |
| R          | Rhythm Pattern Definition    |



2\. PMDB2.COM / PMD86.COM / PMDVA.COM (SpeakBoard,音美,86,VA2 driver)  
|         |                              |
|---------|------------------------------|
| A       | FM Channel 1                 |
| B       | FM Channel 2                 |
| C       | FM Channel 3                 |
| D       | FM Channel 4                 |
| E       | FM Channel 5                 |
| F       | FM Channel 6                 |
| G       | SSG Channel 1                |
| H       | SSG Channel 2                |
| I       | SSG Channel 3                |
| J       | PCM Channel                  |
| K       | Rhythm Pattern Specification |
| R       | Rhythm Pattern Definition    |
| other 1 | FM Channel 3                 |
| other 2 | FM Channel 3                 |
| other 3 | FM Channel 3                 |



3\. PMD.X (X68000)  
|     |              |
|-----|--------------|
| A   | FM Channel 1 |
| B   | FM Channel 2 |
| C   | FM Channel 3 |
| D   | FM Channel 4 |
| E   | FM Channel 5 |
| F   | FM Channel 6 |
| G   | FM Channel 7 |
| H   | FM Channel 8 |
| J   | PCM Channel  |



4\. PMD.EXP (FM-TOWNS)  
|     |               |
|-----|---------------|
| A   | FM Channel 1  |
| B   | FM Channel 2  |
| C   | FM Channel 3  |
| D   | FM Channel 4  |
| E   | FM Channel 5  |
| F   | FM Channel 6  |
| J   | PCM Channel 1 |
| K   | PCM Channel 2 |



5\. PMDIBM.COM (IBMPC)  
|     |              |
|-----|--------------|
| A   | FM Channel 1 |
| B   | FM Channel 2 |
| C   | FM Channel 3 |
| D   | FM Channel 4 |
| E   | FM Channel 5 |
| F   | FM Channel 6 |
| G   | FM Channel 7 |
| H   | FM Channel 8 |
| I   | FM Channel 9 |



6\. PMDPPZ.COM (86)  
|          |                                                  |
|----------|--------------------------------------------------|
| A        | FM Channel 1                                     |
| B        | FM Channel 2                                     |
| C        | FM Channel 3                                     |
| D        | FM Channel 4                                     |
| E        | FM Channel 5                                     |
| F        | FM Channel 6                                     |
| G        | SSG Channel 1                                    |
| H        | SSG Channel 2                                    |
| I        | SSG Channel 3                                    |
| J        | PCM Channel (play only if Chibi-Oto is attached) |
| K        | Rhythm Pattern Specification                     |
| R        | Rhythm Pattern Definition                        |
| other 1  | FM Channel 3                                     |
| other 2  | FM Channel 3                                     |
| other 3  | FM Channel 3                                     |
| other 4  | PPZ8-use PCM Channel 1                           |
| other 5  | PPZ8-use PCM Channel 2                           |
| other 6  | PPZ8-use PCM Channel 3                           |
| other 7  | PPZ8-use PCM Channel 4                           |
| other 8  | PPZ8-use PCM Channel 5                           |
| other 9  | PPZ8-use PCM Channel 6                           |
| other 10 | PPZ8-use PCM Channel 7                           |
| other 11 | PPZ8-use PCM Channel 8                           |

## 1.2. Using the Rhythm Channel (K/R)

### 1.2.1. Using the Internal SSG Drums

The K/R Channels are fundamentally set in PMD for the use of the internal SSG drums.

However, if PPSDRV(→PPSDRV.DOC) resides and PMD supports it (→PMD.DOC /P option), they will be the part playing SSGPCM sounds.

It is not a part exclusive to YM2608's rhythm sound source, so please be careful.([→§1.2.2.](#1-2-2))

Define the pattern in the R channel and then specify the order in which pattern will be played in the K channel.

The R parts are internally numbered from 0 to 255 in order of definition. To specify the order of performance, specify the number in the K part by using R command ([→§6.7.](#6-7)).

Example

    K   R0 L [R1]3R2
    R0  l16[@64c]4
    R1  l8 @1c@128c@2c@128c
    R2     @1c@16c@8c@4c

Result In the intro, a Snare2 roll (Line 2,R0) is entered, an 8 beat pattern (Line 3,R1) is repeated three times, and a tom fill-in (Line 4,R2) is entered, and the whole loops.

Since the numerical value after the part symbol R is a dummy, it is possible to omit it. But inputting it makes reading it easier to understand.([→§1.1.2.](#1-1-2))

See also

-   R command ([→§6.7.](#6-7))
-   @ command ([→§6.1.](#6-1))

### 1.2.2. Using the YM2608 Rhythm Sound Source

Although PMD does not have a channel exclusively for YM2608's rhythm sound source, it is convenient to specify in the SSG rhythm channels (K/R) that plays the same rhythm, as rhythm sound source commands ([→§14.](#14)) can be written to any parts.

Example

    K   \V63\vs31\vb31\vh15\vt31    ; rhythm sound source volume settings
    K   R0 L [R1]3R2
    R0  l16[\sr]4
    R1  l8 \br\hr\sr\hr
    R2     \br\tr\tr\tr

Result Although high and low toms are not included, this produces the same rhythm pattern as Example 1.2.1. using the rhythm sound source.

However, since rhythm sound source commands([→§14.](#14)) can basically be used in any channel, usage in FM channels and SSG channels is not prevented.

See also

-   MML Commands — Rhythm Sound Source Commands([→§14.](#14))

### 1.2.3. Using the K/R Channels' Rhythm With the SSG Channels

For producing an SSG rhythm with the K/R channels, the third SSG channel is used. Therefore, this results in competition with the I channel.

Although it is safer to avoid using both simultaneously, if it is used at the same time, the following rule is established:

1.  A KEYON for one channel will cut the sound for the other channel.
2.  If both channels have KEYON simultaneously, K/R channels will take precedence.

## 1.3. Numerical Notation Methods

For numerical notation, it is possible to specify in both decimal and hexadecimal.

To represent a hexadecimal number, add "$" symbol at the beginning.

You can specify the internal counter value directly by adding "%" symbol to the beginning only when tone length is specified.

Although it doesn't matter if you separate the command name and the number parameter with SPACE or TAB, a comma must be immediately after a number for the next number.

Example 1 `c4`  
Result A quarter note C is specified.

Example 2 `c$10`  
Result A sixteenth note C is specified.

Example 3 `c%12`  
Result An eighth note (12 internal clocks) C is specified.

Example 4 `MA 12, 1, 8, 2`  
Result Ignoring the spaces, it becomes equivalent to `MA12,1,8,2`

Incorrect Example `MB 12 , 1 , 8 , 2`  
Result Error. Space cannot be entered between the number and comma.

## 1.4. Comment Notation Methods

If you want to write comments into MML, basically write ; symbol ([→§16.5.](#16-5)) and comment up to the new line from there.

Example 1

    A @13 v13  ; A.Piano
               ~~~~~~~~~~ comment

However, if you have SPACE or TAB at the beginning of a line, the entire line will be treated as comments even without the semicolon.

Example 2

        Part A (←comment)
    A   ⋯
    B   ⋯

In MML, if you want to have several lines of comments, the \` symbol([→§16.6.](#16-6)) results in all info up to the next \` symbol being treated as comments.

Example 3

    `
    MML Coded by M.Kajihara.
    Copyright(c)1994.
    `

If you want to add a comment within MML code, it is possible to implement it with \` symbol.

Example 4

    A   @13 v13 `c major` cdefgab>c< `c minor` cde-fga-b->c<

Also, all multibyte characters in MML are ignored, excluding special commands like \# definition commands. So if it is a comment consisting only multibyte characters, you can omit the \` symbol in particular.

Example 5

    A   @13 v13 ハ長調→ cdefgab>c< ハ短調→ cde-fga-b->c<

However, below are special cases where a comment cannot be inputted.

1.  A character string inside a \# defined command
2.  A command defined or used with ! that contains a character string variable
3.  A command defined with @, =Instrument name character string

Incorrect Example

    #Title  Sample Music    ; music title
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~ The whole underlined part is treated as the title.

See also

-   ; command ([→§16.5.](#16-5))
-   \` command ([→§16.6.](#16-6))

# 2. Overall Control Commands

The following commands are specified at the beginning of the line and will perform various definitions of controls affecting all channels and the song themselves.

Alphabet character strings for "Filename", "Composer", "Extend", etc. can be in either lowercase or uppercase.

Command names, strings, and numbers must be separated by at least one SPACE or TAB.

Since it is processed in one pass, it can be located anywhere in the MML file. But if commands other than \#Memo are duplicated, whatever is behind the line will be validated.

## 2.1. Output Filename Specification

``` command
#Filename
```

Format 1 `#Filename Filename`  
Format 2 `#Filename .extension`

Changes the filename of the output song data by the MC.EXE compiler.

By default, MC.EXE compiles into the ".M" file extension.

The extension will be changed from the default ".M" only if the extension is specified.

The filename is defined until a control character other than TAB/ESC comes up. (usually up to the end of line (CR))

Caution You cannot attach a comment after it with ;

Example 1 `#Filename SAMPLE.M`  
Result Regardless of the MML filename, it compiles to a file named "SAMPLE.M".

Example 2 `#Filename .M2`  
Result Using the original MML filename, it will attempt to save it under the extension ".M2".

## 2.2. Use SSGPCM Filename Setting

``` command
#PPSFile
```

Format `#PPSFile filename`

Defines the name of the PPS (SSGPCM) file in use. (→PPS.DOC)

The filename is defined until a control character other than TAB/ESC comes up. (usually up to the end of line (CR))

Caution 1 You cannot attach a comment after it with ;

Caution 2 You cannot omit the file extension.

Caution 3 When using MC.EXE, if you do not define instrument data within the song data (→MC.DOC), the file will only be loaded if you use MC.EXE's /P or /S options for immediate playback.

Example `#PPSFile PPS01.PPS`  
Result Uses PPS01.PPS for the K/R parts' SSGPCM instrument patch.

## 2.3. Use PCM Filename Setting

``` command
#PCMFile , #PPCFile
```

Format1 `#PCMFile filename`  
Format2 `#PPCFile filename`

Defines a PCM file (.PPC/.PVI/.P86) for use on channel J. (→PMDPCM.DOC) If you are using PMDPPZE it indicates a .PVI/.PZI filename.

\#PCMFile and \#PPCFile are completely identical.

The filename is defined until a control character other than TAB/ESC comes up. (usually up to the end of line (CR))

Caution 1 You cannot write a comment with ; after it.

Caution 2 You cannot omit the filename.

Caution 3 When using MC.EXE, if you do not define instrument data within the song data (→MC.DOC), the file will only be loaded if you use MC.EXE's /P or /S options for immediate playback.

Example `#PCMFile SAMPLE.PPC`  
Result Uses SAMPLE.PPC for channel J's instrument data.

## 2.4. Use Instrument Filename Setting

``` command
#FFFile
```

Format `#FFFile  filename[.FF/.FFL]`

Defines an instrument filename (.FF/FFL) to be used.

The filename is defined until a control character other than TAB/ESC comes up. (usually up to the end of line (CR))

This has the exact function as writing the filename on the command line in MC.EXE (→MC.DOC). If the file exists, it will automatically be attached at the same time as the /V option is used. If the file does not exist, the specified filename will be used when writing with the effect of the /VW option.

If you omit the file extension, when the OPL option (/L) is used, it is assumed to be .FFL . If the OPL option is not used, it is assumed to be .FF .

Caution 1 When used jointly with the instrument definition command (@), please always respect the numbering sequence from the FFFile. There is the possibility of the file instruments being written to the top of the file if you write the instruments to the bottom.

Caution 2 Even if instruments are specified on the command line, they are valid only if this command is specified.

Example 1 `#FFFile  EFFEC.FF`  
Result Loads and uses the FM instrument "EFFEC.FF".

See also

-   FM instrument definition (@) ([→§3.1.](#3-1))
-   MC.DOC

## 2.5. Compiler Option Settings

``` command
#Option
```

Format `#Option  character string`

Sets the options for the compiler.

The settings on the character string are identical to those on a command line. (→MC.DOC)

Caution 1 In the settings on the command line, it is added in appended form. When conflicting options such as /N and /L are set simultaneously, the one that is set later becomes effective.

Caution 2 With /N, /M, and /L, If you set the option that pertains to FM sound definition, always set the sound definition (@) before it.

Example `#Option  /L/S/A/O`  
Result Sets the MC command line options: /L/S/A/O

See also

-   FM instrument definition(@) ([→§3.1.](#3-1))
-   MC.DOC

## 2.6. Title Definition

``` command
#Title
```

Format `#Title  Title character string`

Defines the song's title.

The name is defined by the string of characters ending with a CTRL code other than TAB or ESC. (Typically the end of the line.)

Caution 1 You cannot write a comment with ; after it.

Caution 2 When using MC.EXE, if you do not define instrument data within the song data (→MC.DOC), this string will not be displayed if you use MC.EXE's /P or /S options for immediate playback.

Example `#Title  sample song`  
Result The song title is set to "sample song".

## 2.7. Composer Definition

``` command
#Composer
```

Format `#Composer Composer name character string`

Defines the composer's name.

By default, if the environment variable "COMPOSER=" or "USER=" has been defined, that defined character string will be used. (→MC.DOC)

The name is defined by the string of characters ending with a CTRL code other than TAB or ESC. (Typically the end of the line.)

Caution 1 You cannot write a comment with ; after it.

Caution 2 When using MC.EXE, if you do not define instrument data within the song data (→MC.DOC), this string will not be displayed if you use MC.EXE's /P or /S options for immediate playback.

Example `#Composer M.Kajihara`  
Result The composer's name is set to "M.Kajihara".

## 2.8. Arranger Definition

``` command
#Arranger
```

Format `#Arranger Arranger's name character string`

Defines the arranger's name.

By default, if the environment variable "COMPOSER=" or "USER=" has been defined, that defined character string will be used. (→MC.DOC)

The name is defined by the string of characters ending with a CTRL code other than TAB or ESC. (Typically the end of the line.)

Caution 1 You cannot write a comment with ; after it.

Caution 2 When using MC.EXE, if you do not define instrument data within the song data (→MC.DOC), this string will not be displayed if you use MC.EXE's /P or /S options for immediate playback.

Example `#Arranger M.Kajihara`  
Result The arranger's name is set to "M.Kajihara".

## 2.9. Memo Definition

``` command
#Memo
```

Format `#Memo  memo character string`

Defines a memo character string.

Multiple specifications are possible and are defined in order. The maximum is 128 lines.

Caution 1 You cannot write a comment with ; after it.

Caution 2 When using MC.EXE, if you do not define instrument data within the song data (→MC.DOC), this string will not be displayed if you use MC.EXE's /P or /S options for immediate playback.

Example `#Memo  Made on 3/25/94`  
Result Defines the memo: "Made on 3/25/94".

## 2.10. Tempo Setting

``` command
#Tempo #Timer
```

Format 1 `#Tempo numerical value`  
Format 2 `#Timer numerical value`

|       |                   |
|-------|-------------------|
| Range | (Format 1) 18–255 |
|       | (Format 2) 0–250  |

Specifies the tempo.

If \#Tempo is used, it will specify how many times in one minute 48 clock cycles will repeat. The default length of 48 clock cycles is a half note, but it can be changed with the \#Zenlen command or the C command.

If \#Timer is used, it will directly set the value of TimerB.

If this command is used, a t or T command will be automatically issued at the beginning of channel G.

Example 1 `#Tempo  60`  
Result The tempo is set at 60 half notes in one minute. (120 quarter notes in one minute)

Example 2 `#Timer  100`  
Result The value of the internal TimerB is set to 100.

See also

-   t command ([→§11.1.](#11-1))
-   T command ([→§11.2.](#11-2))
-   C command ([→§4.11.](#4-11))
-   \#Zenlen command ([→§2.11.](#2-11))

## 2.11. Whole Note Length Setting

``` command
#Zenlen
```

Format `#Zenlen numerical value`

Range 1–255

Specifies the whole note length.

This is identical to the MML C command. If a value other than 96 is specified, a C command will be automatically added to channel G.

Any note length you specify cannot be an indivisible number.

Since the default value is 96, Possible values are 1,2,3,4,6,8,12,16,24,32,48,or 96.

Caution If you use this command, the note length that determines the tempo in the \#Tempo command will change.

Example `#Zenlen 192`

Result The whole note is set to the internal clock value of 192 and the possible note lengths are increased to 14 (1,2,3,4,6,8,12,16,24,32,48,64,96,192). Specifying a value for \#Tempo or t will determine the length of a quarter note.

Supplement If you use this command to make the whole note longer, the more parts your note lengths are, the more CPU power your track will consume at playback time.

In particular, when you are making a track which will be used as BGM for a video game scene which requires more CPU usage. If you make this value smaller, your track will use less CPU power at playback time.

See also

-   C command ([→§4.11.](#4-11))
-   \#Tempo command ([→§2.10.](#2-10))
-   t command ([→§11.1.](#11-1))

## 2.12. Octave Up/Down Sign Function Setting

``` command
#Octave
```

Format 1 `#Octave  Reverse`  
Format 2 `#Octave  Normal`

Reverse reverses the \< and \> commands, while Normal keeps them the same.

This is identical to the MML X command, if it is used, an X command will be automatically issued to channel A.

Example `#Octave Reverse`  
Result \> decrements the octave, while \< increments it.

See also

-   X Command ([→§4.6.](#4-6))
-   \> \< Commands ([→§4.5.](#4-5))
-   C command ([→§4.11.](#4-11))
-   \#Zenlen command ([→§2.11.](#2-11))

## 2.13. Default Loop Count Setting

``` command
#LoopDefault
```

Format `#LoopDefault number`

Range 0–255

When the number of loops is omitted on a "\]" loop, this sets the default number.

The default number is 0 (no loop).

Example `#LoopDefault 2`

Result If a number is omitted for the "\]" command, it sets the number of loops to 2.

See also

-   \] command ([→§10.1.](#10-1))

## 2.14. Whether To Use DT2 In Instrument Data Setting

``` command
#DT2Flag
```

Format 1 `#DT2Flag on`  
Format 2 `#DT2Flag off`

Sets whether DT2 values will be used in an instrument definition.

The default changes depending on the option of MC:  
If /m is set → on  
If /m is not set → off

If DT2 is required for the instrument and this flag is not specified as off, DT2 will be set to 0 for all slots.

Example `#DT2Flag on`

Result Regardless of the format, attaches DT2 to the instrument patch.

See also

-   FM Instrument Definition(@) ([→§3.1.](#3-1))

## 2.15. Bend Range Setting

``` command
#Bendrange
```

Format `#Bendrange number`

Range 0–255

Sets the bend range. The default is 0.

This is identical to the MML B command, if this is used, it automatically sets a B command at the beginning of channel A.

If a value other than 0 is specified, the I command will become effective, and for I±8192, the pitch deviation will be the bend range times the difference of a half-note.

Caution Bend specification requires considerable attention on the I command ([→§7.5.](#7-5)) and MML can be hard to look at. So it is better not to use it unless you are converting from MIDI.

Example `#Bendrange 12`

Result With I at ±8192, this sets the pitch shift to exactly one octave.

See also

-   B command ([→§7.4.](#7-4))
-   I command ([→§7.5.](#7-5))

## 2.16. SSG Pitch Extend/Normal Selection

``` command
#Detune
```

Format 1 `#Detune  Extend`  
Format 2 `#Detune  Normal`

Selects whether to use Extend or Normal for the SSG's Detune/LFO.

If you set this to Extend, it is equivalent to adding "DX1" to the beginning of each of the SSG channels (G,H,I).

If you set this to Normal, when the detune/LFO shifts by 1, the pitch value sent to the sound source will also be shifted by 1. (even with the same detune value, the deviation increases as the pitch goes higher)

When using Extend, the detune value is made smaller as the pitch becomes higher, the detune value will be revised to match up with the same pitch degree.

Example `#Detune  Extend`

Result The SSG Detune is changed to be extended.

See also

-   DX command ([→§7.3.](#7-3))
-   D DD commands ([→§7.1.](#7-1))
-   M MA MB commands ([→§9.1.](#9-1))

## 2.17. Software LFO Speed Extend/Normal Selection

``` command
#LFOSpeed
```

Format 1 `#LFOSpeed Extend`  
Format 2 `#LFOSpeed Normal`

Selects whether the software LFO will be extended to be independent of the tempo.

If you set this to Extend, it is equivalent to adding "MXA1 MXB1" to the beginning of the FM, SSG, and ADPCM channels.

If you only want to set one LFO please use the MX command.

Example `#LFOSpeed Extend`

Result Sets the software LFO to be independent of the tempo.

See also

-   MX MXA MXB commands ([→§9.5.](#9-5))
-   M MA MB commands ([→§9.1.](#9-1))

## 2.18. Software Envelope Speed Extend/Normal Selection

``` command
#EnvelopeSpeed
```

Format 1 `#EnvelopeSpeed Extend`  
Format 2 `#EnvelopeSpeed Normal`

Selects whether the SSG/PCM envelope speed will be independent of the tempo.

If you set this to Extend, it is equivalent to adding "EX1" to the beginning of the SSG and PCM channels (G–J).

Example `#EnvelopeSpeed Extend`

Result Sets the SSG/PCM envelope speeds to be independent of the tempo.

See also

-   EX command ([→§8.2.](#8-2))
-   E command ([→§8.1.](#8-1))

## 2.19. PCM Volume Value Extend/Normal Selection

``` command
#PCMVolume
```

Format 1 `#PCMVolume Extend`  
Format 2 `#PCMVolume Normal`

Selects which way the v and V volume commands will be related on the PCM channels:  
Normal: V = v×16  
Extend: V = v×v

Using Extend in PMDB2 and PMDVA, and using Normal in PMD86, will set the volume curve of the v command roughly to a straight line.

Example `#PCMVolume Extend`

Result Sets the volume conversion on the PCM channels to V = v×v.

See also

-   v command ([→§5.1.](#5-1))
-   V command ([→§5.2.](#5-2))

## 2.20. FM Channel 3 Expansion

``` command
#FM3Extend
```

Format `#FM3Extend notation1[notation2[notation3]]]`

Notation Any of LMNOPQSTUVWXYZabcdefghijklmnopqrstuvwxyz

Expands the 3rd FM channel by creating new channels with the notated letter. You may set up to 3 extension channels.

The third FM channel can play up to four independent tones, but by default, except for PMD/PMDVA1, the third FM channel has only one tone, this command creates more.

On PMD/PMDVA1, the D, E, and F channels are defined as the FM3 extension tones by default, so this command will change that.

Example `#FM3Extend XYZ`  
Result Channels X, Y, and Z are newly created for FM3. If using PMD/PMDVA1, it changes D, E, F to X, Y, Z.

See also

-   Correspondence Between Channel Notation and Sound Sources ([→§1.1.3.](#1-1-3))

## 2.21. MML File Insertion

``` command
#Include
```

Format `#Include filename`

Loads and inserts an MML file between the \#Include line and the next line. You cannot omit the file extension.

It is very useful to include default settings for \# commands, @ instruments, ! variables, etc. However, please pay attention to MML size limit (61 KB).

It is also possible to include a file which itself includes a file (nesting).

Example `#Include default.mml`  
Result Loads and inserts default.mml at that position.

## 2.22. Separate Volume Down Setting

``` command
#Volumedown
```

Format `#Volumedown [F[S[P[R]]]][±]number[,[F[S[P[R]]]][±]number,]...`

|       |                    |
|-------|--------------------|
| Range | (without ±) 0–255  |
|       | (with ±) -128–+127 |

Changes the volume down value separately for each sound source.

Each sound source is represented as:  
F = FM  
S = SSG  
P = PCM  
R = Rhythm

If this is used, DF, DS, DP, and DR commands will automatically be added to the beginning of channel G.

If a + or - is inserted before the number, the change will be relative to PMD's /DF, /DS, /DP, and /DR option values.  
Please note that + lowers the volume.

Caution Because the values set with this command are local to the track they are used on, when beginning playback again, this resets the values of PMD's /DF, /DS, /DP and /DR commands, then returns them to the normal values.

Example 1 `#Volumedown FR+16,P+128,S+32`  
Result Adds 16 to FM, 128 to PCM, and 32 to SSG, relative to the PMD options (lowers volume)

Example 2 `#Volumedown F-16`  
Result Subtracts 16 to FM, relative to the PMD options (raises volume)

Example 2 `#Volumedown P96`  
Result Regardless of the PMD options, sets the PCM volume down to 96.

See also

-   DF DS DP DR commands ([→§15.4.](#15-4))
-   PMD /DF /DS /DP /DR options (→PMD.DOC)

## 2.23. PCM Channel Specification Setting

``` command
#ADPCM
```

Format 1 `#ADPCM  on`  
Format 2 `#ADPCM  off`

This is only effective when used with PMD86.

When set to on, adjust volume and loops to ADPCM (with /s option)  
When set to off, do not adjust volume and loops to ADPCM (without /s option)

Regardless of the /s option, it changes the PCM condition.

Because the values set with this command are local to the track they are used on, playing back another song will return the values to normal.

When this command is used, it issues an A command to the beginning of channel J.

Example `#ADPCM on`  
Result When the track is played back on PMD86, it will playback with the PCM channels using the same methods as the ADPCM channel.

See also

-   A command ([→§15.10.](#15-10))

## 2.24. Playback Start Position Setting

``` command
#Jump
```

Format 1 `#Jump posnum`

Range 0–65535

Sets the starting position for playback. Effective only when the track is played back with MC.EXE or MCH.EXE using the /P and /S options.

Because this has no effect on a created .M file, when you play it back on a program such as PMP.COM, please note that it will be played from the beginning of the song.

Also, on slow CPUs, when the specified beginning position is large, it will take a bit of time before the song plays.

Example `#Jump 16`  
Result When played back on MC.EXE or MCH.EXE using the /P and /S options, it will begin at position 16.

## 2.25. PPZ8 Channel Extension

``` command
#PPZExtend
```

Format `#PPZExtend notation1[notation2[notation3]... (up to 8)]]`

Notation Any of LMNOPQSTUVWXYZabcdefghijklmnopqrstuvwxyz

Extends the PPZ8 channels with the notated channels. It is possible to set up to 8 new channels.

Example `#PPZExtend abcdefgh`  
Result Creates new PPZ8 channels a,b,c,d,e,f,g,h

See also

-   Correspondence Between Channel Notation and Sound Sources ([→§1.1.3.](#1-1-3))

## 2.26. PPZ PCM Filename Setting

``` command
#PPZFile
```

Format `#PPZFile filename[.PVI/.PZI][,filename[.PVI/.PZI]]`

Sets the filename of the PCM samples to be used on the extended PPZ8 channels. If the file extension is omitted, at loading time it will check for a matching PZI file, then a PVI file.

You may define up to two PCM files to use. The 2nd PCM file will have 128 added to each instrument number, ranging from @128–@255

The filename is defined by the string of characters ending with a CTRL code other than TAB or ESC. (Typically the end of the line.)

Caution 1 You cannot write a comment with ; after it.

Caution 2 When using a 2nd PCM file, you cannot leave space on either side of the comma.

Caution 3 When using MC.EXE, if you do not define instrument data within the song data (→MC.DOC), the file will only be loaded if you use MC.EXE's /P or /S options for immediate playback.

Example `#PPZFile SAMPLE.PZI`  
Result Uses SAMPLE.PZI for the PCM data on the channels set with \#PPZExtend.

Example 2 `#PPZFile BASEPCM.PZI,EXTEND.PVI`  
Result Uses BASEPCM.PZI for PCM instruments @0–@127 and uses EXTEND.PVI for PCM instruments @128–@255 on the channels set with \#PPZExtend.

Incorrect Example `#PPZFile BASEPCM.PZI , EXTEND.PVI`  
Result You cannot put space on either side of the comma. At PCM loading time there will be an error.

## 2.27. Overall Transposition Setting

``` command
#Transpose
```

Format `#Transpose number`

Range -128–+127

Sets the transposition for the whole song.

It is equivalent to adding "\_M" to the beginning of every channel except the rhythm channels.

For channels such as those used for rhythm, which you do not want to be transposed, please cancel this by putting "\_M0" at the beginning of each appropriate channel.

Example `#Transpose 1`  
Result Transposes the whole track up one half-note.

See also

-   \_M command ([→§4.16.](#4-16))

# 3. Definition Commands

Commands that define MML variables for FM channel sounds.

Since it is processed in one pass, it can be located anywhere in the MML file.

However, if a duplicate command is specified, the former will be used.

## 3.1. FM Instrument Definition

``` command
@
```

Format 1

    @ Instrument number ALG FB
    AR DR SR RR SL TL KS ML DT AMS
    AR DR SR RR SL TL KS ML DT AMS
    AR DR SR RR SL TL KS ML DT AMS
    AR DR SR RR SL TL KS ML DT AMS

Format 2

    @ Instrument number ALG FB
    AR DR SR RR SL TL KS ML DT DT2 AMS
    AR DR SR RR SL TL KS ML DT DT2 AMS
    AR DR SR RR SL TL KS ML DT DT2 AMS
    AR DR SR RR SL TL KS ML DT DT2 AMS

Format 3

    @ Instrument number ALG FB
    AR DR RR SL TL KSL ML KSR EGT VIB AM
    AR DR RR SL TL KSL ML KSR EGT VIB AM

Note In any location, it is possible to define an instrument.

|       |            |     |               |
|-------|------------|-----|---------------|
| Range | Format 1&2 | ALG | — 0–7         |
|       |            | FB  | — 0–7         |
|       |            | AR  | — 0–31        |
|       |            | DR  | — 0–31        |
|       |            | SR  | — 0–31        |
|       |            | RR  | — 0–15        |
|       |            | SL  | — 0–15        |
|       |            | TL  | — 0–127       |
|       |            | KS  | — 0–3         |
|       |            | ML  | — 0–15        |
|       |            | DT  | — -3–3 or 0–7 |
|       |            | AMS | — 0–1         |
|       | Format 2   | DT2 | — 0–3         |
|       | Format 3   | ALG | — 0–1         |
|       |            | FB  | — 0–7         |
|       |            | AR  | — 0–15        |
|       |            | DR  | — 0–15        |
|       |            | RR  | — 0–15        |
|       |            | SL  | — 0–15        |
|       |            | TL  | — 0–63        |
|       |            | KSL | — 0–3         |
|       |            | ML  | — 0–15        |
|       |            | KSR | — 0–1         |
|       |            | EGT | — 0–1         |
|       |            | VIB | — 0–1         |
|       |            | AM  | — 0–1         |

Defines an FM instrument.

The "@" must be the first character on a line, and you must insert a space, tab, comma, or new line between each number. However, the instrument name must be ended with a tab or a new line.

Format 1 In MC.EXE, without the /M option, it is treated according to "#DT2Flag off".  
Format 2 In MC.EXE, with the /M option, it is treated according to "#DT2Flag on".  
Format 3 It is treated according to the function of the /L option in MC.EXE.

From the @ to the last number, entering any character besides a number without inserting a ; or = will produce an error. You cannot omit any number except for the instrument name.

For the meanings of each parameter, please refer to the original manual and FM synthesis manual.

Caution When using MC.EXE, if you do not use a defined instrument within the track sequence, it is useless.(→MC.DOC)

Example 1

    @  0  4  5  =falsyn?
        31  0  0  0  0  22  0  2  3   0
        18 10  0  6  0   0  0  8  3   0
        31  0  0  0  0  23  0  4 -3   0
        18 10  0  6  0   0  0  4 -3   0

Result Instrument number 0 is defined as "falsyn?".

Example 2 When using the /M option in MC.EXE or \#DT2Flag on

    ; NM AG FB  Falcom Synth
    @  0  4  5  =falsyn?
    ;   AR DR SR RR SL  TL KS ML DT DT2 AMS
        31  0  0  0  0  22  0  2  3   0   0
        18 10  0  6  0   0  0  8  3   0   0
        31  0  0  0  0  23  0  4 -3   0   0
        18 10  0  6  0   0  0  4 -3   0   0

Result Instrument number 0 is defined as "falsyn?".

Example 3 When using the /L option in MC.EXE

    ; NM AG FB  E.Bass
    @  2  0  5  =E.Bass
    ;   AR DR RR SL TL KSL ML KSR EGT VIB AM
        11  5  2  2 29   0  0   0   0   1  0
        12  8  6  1  0   0  1   1   1   1  0

Result Instrument number 2 is defined as "E.Bass".

See also

-   @ command(MML) ([→§6.1.](#6-1))
-   \#DT2Flag command ([→§2.14.](#2-14))
-   MC.EXE /N /M /L options (→MC.DOC)

## 3.2. MML Variable Definition

``` command
!
```

Format 1 `!characterstring MMLsequence`  
Format 2 `!numericalvalue MMLsequence`

Character String Any character type or number of characters. Determined from the beginning up to 30 half-width characters.

Range 0–255

Defines MML variables.

Up to 256 kinds of character strings can be defined, same for numerical values. It is possible to define each independently.

For character strings, if the head line is not a numeral, any character can be used. (!Snare, etc. Defining multibyte characters is also possible)

Character strings and numerical values must be separated by at least one SPACE or TAB.

Variable nesting is also possible, but please do not use recursion.

Variables are used in MML by the ! command.

Caution 1 Only up to 30 half-width characters are recognized. If you input more than that, the remaining characters are not recognized.

Caution 2 If it became an endless loop by recursion, it will break in the worst case. Please be careful.

Example 1

    !A  cde
    !1  !A fga
    A   l8 !1 b

Result Equivalent to `A  l8 cdefgab`

Example 2

    !BassDrum   @0v12
    !SnareDrum  @1v14
    A   !BassDrum cc !SnareDrum g !BassDrum c

Result

    A   @0v12 cc @1v14 g @0v12 c

Incorrect Example

    !A  cde !B
    !B  cde !A
    A   !A

Result !A and !B continually refer back to each other. This results in a stack overflow, in the worst case the system may break.

See also

-   ! command(MML) ([→§16.1.](#16-1))

# 4. MML Commands — Pitch Interval/Duration

From here on is an explanation of real MML commands.

Optionally, you can enclose the parameters inside \[ \] brackets.

The Sound Source marker shows which channels may use a given command. Each specific sound source is listed below:

|          |                                                                                              |
|----------|----------------------------------------------------------------------------------------------|
| FM       | FM sound channel (PC-88/98: A–F as well as FM3 extensions, X68000: A–H, IBM: A–I)            |
| SSG      | SSG sound channel (G–I)                                                                      |
| PCM      | PCM sound channel (J (FM Towns: J–K) as well as PPZ extensions)                              |
| Rsel     | Rhythm selection channel (K)                                                                 |
| Rdef     | Rhythm definition channel (R)                                                                |
| FM(OPNA) | FM sound channel (Exclusively for PMDB2/VA/86: A–F as well as FM3 extensions)                |
| FM(OPM)  | FM sound channel (Exclusively for PMD.X: A–H)                                                |
| FM(ch3)  | FM sound channel (Exclusively for PMD.COM: C–F and PMDB2/VA/86: C as well as FM3 extensions) |

The commands involving intervals and duration are summarized in this section.

These commands can almost never be used on Channel K (R Selection).

## 4.1. Pitch Interval/Duration Setting

``` command
c/d/e/f/g/a/b/x
```

Format 1 `c/d/e/f/g/a/b [=] [+/-] [Duration] [.]`  
Format 2 `x [Duration] [.]`

Range 1–255, whole-note length divisor([→§2.11.](#2-11)) or clock value attached by %

Sound Source FM / SSG / PCM / Rdef

This represents a single note. Respectively,  
c = do  
d = re  
e = mi  
f = fa  
g = sol  
a = la  
b = ti  
are supported.

Also, if x is used for note data, previous notes will be adopted. (Example: By using c4x8, c4c8 is played)

For high-low octaves, o \< \> are used for commands. However, x adopts the octave of the previous note.

With the R channel, PMD.X's J channel(PCM), c–b and x will be the same for any note.

By using \_{ } commands([→§4.15.](#4-15)), if transposition specification is used in intervals c–b, The transposition will be automatically processed. But if = notation (natural) is attached, it will be ignored.

If + notation (sharp) is attached, it will jump up a half-tone. If - notation (flat) is attached, it will lower a half-tone. For + and - notation, specifying 2 or more commands is possible. (double-flat, etc.) However, This cannot be used with interval x.

If the note duration is omitted, it will use the duration specified by the l command.

If . notation (period) is attached, the duration is multiplied by 1.5. If 2 or more are attached, the note's length will be continually multiplied by 1.5.

Example 1 `c2..` Result `c2&c4&c8`

For 3,6 tuplets, please use the calculation of 3,6,12,24,48,96 length notes.

Example 2 `c12d12e12`  
Result Three 8-cycle length notes (same as {CDE}4 in N88Basic)  
Supplement Since adding three twelfth notes is the same as a quarter note, You can divide a quarter note into three equal twelfth notes.

For note lengths which are indivisible, use a % to directly set the number of clock cycles.

Example 3 `c%4 d%5 e%5 f%5 g%5`  
Result Splits a quarter note into 5 notes of cdefg (same as {CDEFG}4 in N88Basic)  
Supplement Since a quarter note is 24 clock cycles (If C = 96), dividing 24 by 5 gives 4 with a remainder of 4. Therefore, if four notes are of length %5, and one is of length %4, it will roughly sound like a quintuplet.

When using W or S commands, the note lengths will be affected by the automatic addition of software echoes or grace notes.

Caution 1 In PMD.X, notes c, c+, and d on octave 1 will be played back as note d+.

Caution 2 In PMDB2/VA, any notes above octave 6 will be played back at octave 6 on the PCM channel.

Caution 3 Please do not leave space between the scale notation (c/d/e/f/g/a/b) and the dot (.). In particular, please note that each =, +, or - symbol will be recognized as l=, l+, and l- commands respectively if there is a space between them.

Caution 4 If the number of clock cycles exceeds 255, depending on the condition it may not be possible to define such a note.

Incorrect Example `C192 W24,-2 c1.`  
Result Note length overflow error.  
Supplement If a W or S command would cause the note length to exceed 255 clock cycles, it cannot be used.

Caution 5 If you use an x note on channel R, it is unconditionally taken as a note data. Even if the note before it is a rest, it is not regarded as a rest.

See also

-   o command ([→§4.4.](#4-4))
-   \> \< commands ([→§4.5.](#4-5))
-   \_{ } commands ([→§4.15.](#4-15))
-   l command ([→§4.8.](#4-8))
-   W command ([→§12.2.](#12-2))
-   S command ([→§12.1.](#12-1))

## 4.2. Rest/Duration Setting

``` command
r
```

Format `r [duration] [.]`

Range 1–255, whole-note length divisor([→§2.11.](#2-11)) or clock value attached by %

Sound Source FM / SSG / PCM / Rdef

Represents one rest.

If the note duration is omitted, it will use the duration specified by the l command.

If . notation (period) is attached, the duration is multiplied by 1.5. If 2 or more are attached, the note's length will be continually multiplied by 1.5.

Example `r4.`

Result Dotted quarter rest

See also

-   l command ([→§4.8.](#4-8))

## 4.3. Portamento Setting

``` command
{ }
```

Format `{interval1 interval2} [length1] [.] [,length2]`

|       |                                                                                           |
|-------|-------------------------------------------------------------------------------------------|
| Range | (length1) 1–255, whole-note length divisor([→§2.11.](#2-11)) or clock value attached by % |
|       | (length2) Same as above, shorter than length1                                             |

Sound Source FM / SSG / PCM(AD,PPZ)

Specify a sound that connects smoothly from pitch 1 to pitch 2 with a length equal to the sound length.

When length2 is specified, the delay between the start of sound generation to the portamento is set.

Regarding note length and period, it is equivalent to c d e f g a b r command. Tone length exceeding 255 steps cannot be specified.

Inside the { }, please use only the c d e f g a b o \> \< commands.

This cannot be used on channel R.

Caution 1 PMD86 and PMD.X's PCM part cannot use the portamento. If it is specified, interval 1 will be ignored. ({cd}2 is the same as d2)

Caution 2 The effects of the W S commands are not reflected in this command.

Example 1 `{cg}4`  
Result A quarter note length portamento going from do to sol.

Example 2 `{cg}4,8`  
Result A quarter note length portamento going from do to sol after an eighth note delay, which is actually equivalent to `c8&{cg}8`.

See also

-   W command ([→§12.2.](#12-2))
-   S command ([→§12.1.](#12-1))

## 4.4. Octave Setting

``` command
o
```

Format `o numerical value`

|       |                           |
|-------|---------------------------|
| Range | 1–8                       |
|       | 1–6 (PMDB2's PCM channel) |
|       | 1–5 (PMD.X's PCM channel) |

Sound Source FM / SSG / PCM

Specifies the octave.

Possible settings: FM/PSG: 1–8, 88/VA/98's PCM: 1–6.

For the X68000 version's PCM channel, possible values are 1–5, roughly changing the pitch in octave units.

The default octave is 4.

Example `o6`  
Result The octave is set to 6.

## 4.5. Octave Up/Down

``` command
> <
```

Format 1 \>  

Format 2 \<

Sound Source FM / SSG / PCM

\> increases by one octave. \< decreases by one octave.

It is possible to reverse the function with X and \#Octave command.

Example 1 `o4 c8>c8`  
Result After an eighth octave 4 c note, An eighth octave 5 c note plays.

Caution If it is specified during a loop, on returning to the head of the loop, the octave will differ on returning to the beginning of the loop. If you use something similar to this, please use a \_\_ command.

Example 2 `o4[cdefgab>]2cde`  
Result `o4cdefgab o4cdefgab o5cde`

Example 3 `o4[cdefgab__12]2__-24cde`  
Result `o4cdefgab o5cdefgab o4cde`

See also

-   X command ([→§4.6.](#4-6))
-   \#Octave command ([→§2.12.](#2-12))
-   \_\_ command ([→§4.14.](#4-14))

## 4.6. Octave Up/Down Notation Reversal

``` command
X
```

Format `X`

Sound Source FM / SSG / PCM

Reverses the effect of the \> and \< commands. It is identical to the \#Octave command, but this command makes it possible to temporarily locally change the octave.

Example `c>c< X d<d> X`  
Result Identical to `c>c< d>d<`

Caution 1 Since the change is temporary, Always return to the original setting. If you don't, all parts will be affected starting from the next part.

Caution 2 With this command, if you want to change the MML entirely, it is necessary to describe it at the head of Channel A. This has the same effect as the \#Octave command.

See also

-   \#Octave command ([→§2.12.](#2-12))
-   \> \< command ([→§4.5.](#4-5))

## 4.7. Whole Octave Change

``` command
o+ o-
```

Format 1 `o+ numerical value`  
Format 2 `o- numerical value`

Range -7–+7

Sound Source FM / SSG / PCM

Increases / decreases the specified value of the part's o command from there by the specified numerical value.

At the same time, it also increases / decreases the current octave by the specified numerical value. (o command is issued)

Example

    G o-1
    H o-0
    GH o4 cdefg

Result cdefg is played with o3 for channel G and o4 for channel H. (octave layering)

## 4.8. Default Length Setting

``` command
l
```

Format `l[%]length[.]`

Range 1–255, whole-note length divisor([→§2.11.](#2-11)) or clock value attached by %

Sound Source FM / SSG / PCM / Rsel / Rdef

In c d e f g a b r { } l= l+ l- l^ commands, specify the length to be used when the length is omitted. The default is 4.

Example 1 `l8cdefg`  
Result cdefg is played with eighth note length.

Caution If this is used in the rhythm selection (K), only the most recently used setting will become the default value for the R channel.

If this is used in the rhythm definition (R) it will affect the R channel from then on. For example, if set in R0, it will also affect R1.

Example 2

    K   l8R0l2
    R0  @1c@2c

Result SSG rhythm's bass drum and snare drum will have half note length. (l8 is ignored.)

See also

-   c–b commands ([→§4.1.](#4-1))
-   r command ([→§4.2.](#4-2))
-   { } commands ([→§4.3.](#4-3))
-   l= l+ l- l^ commands ([→§4.9.](#4-9))

## 4.9. Processing the Previously Used Note Length

``` command
l= l+ l- l^
```

Format 1 `[l] [=] [length] [.]`  
Format 2 `[l] + length [.]`  
Format 3 `[l] - length [.]`  
Format 4 `[l] ^ numerical value`

|       |                                                                                          |
|-------|------------------------------------------------------------------------------------------|
| Range | (length) 1–255, whole-note length divisor([→§2.11.](#2-11)) or clock value attached by % |
|       | (numerical value) 1–255                                                                  |

Sound Source FM / SSG / PCM / Rdef

Changes the previously used note length.

l= changes the previous note length.  
l+ adds to the previous note length.  
l- subtracts from the previous note length.  
l^ multiplies the previous note length.

It is possible to omit l notation and = notation.

If . notation (period) is attached, the duration is multiplied by 1.5. If 2 or more are attached, the note's length will be continually multiplied by 1.5. However, length beyond 255 steps cannot be used.

For the l= command, if only a period is used, it has the effect of a period attached to the previous note length. If both the length and period are omitted, it will use the length determined by the l command.

For the l+ command, it has the same effect as when the length is written immediately after the & command. ([→§4-10 & command](#4-10))

The l= command is usually used together with the MML variables.

Example 1

    !b  @0c ;Bass Drum
    !s  @1c ;Snare Drum
    J   [!b4!s4!b8!b8!s4]2

Result

    J   [ @0c4 @1c4 @0c8 @0c8 @1c4 ]2

For the l- command, this is convenient for restoring a delayed part to the original length.

Example 2

    G   l4v10  cdefg        ab>c<
    H   l4v07r8cdefg l-8 v10fg a

Result In the last 3 notes, the G and H channels' timing and volume become uniform.

Example 3

    a8l=4.
    a8=4.
    a8 4.
    a8l+4
    a4+8
    a4&8
    a2l-8
    a2-8
    a8l^3
    a16^6
    a4.

Result All of la notes become a dotted quarter note.

Caution 1 For the l= and l^ commands, an error occurs if the length specified immediately before is compressed or processed. Also, for the l- command, an error occurs if the length longer than the length specified immediately before is specified.

    × c2&c2 =4 (the previous length is compressed to c1)
    × W24,-2 c2 =4 (the previous length is altered to c4(^2c4)
    × c2&c2^4  (the previous length is compressed to c1)
    × W24,-2 c2^4  (the previous length is changed to c4(^2c4)
    × C192 c1.^4   (the previous length is expanded to c%255&c%33)
    × c4-2
    × W24,-2 c1-2  (c1 is changed to c4(^2c4(^4c4(^6c4)

Caution 2 The note length added with the l+ command is not affected by the W and S commands.

Caution 3 The tone notations c d e f g a b with = + - attached right after are judged as natural/sharp/flat notation. In that case please attach a SPACE or l notation.

Example 4

    c=4     c natural quarter note
    c =4    c quarter note (identical to c4)
    cl=4    c quarter note (identical to c4)
    l2c-8   c flat eighth note
    l2c -8  c dotted quarter note
    l2cl-8  c dotted quarter note
    l4c+8   c sharp eighth note
    l4c +8  c dotted quarter note
    l4cl+8  c dotted quarter note

See also

-   & command ([→§4.10.](#4-10))

## 4.10. Tie/Slur Setting

``` command
& &&
```

Format 1 `&`  
Format 2 `&&`  
Format 3 `& [length][.]`  
Format 4 `&& [length][.]`

Sound Source FM / SSG / PCM / Rdef

Connects the sound before and after as a tie (&) or a slur (&&).

Because keyoff will not be done on the previous note in the case of tie but it will be done in the case of slur. The difference between the two is whether the keyon attack time will be understood (=&&) or not (=&).

Be sure to specify it immediately after the pitch command.

If a length is specified immediately after &, it is treated the same as an l+ command, and the length is added to the one right before it.

Example 1

    a8&2
    a8l+2
    a8&a2

Result All of la notes are eighth note + half note long

If you specify a length immediately after &&, it will play the note immediately preceding the command with the length immediately following it.

Example 2 `a8&&2`  
Result `a8&&a2`

Caution 1 During the execution of W and S commands, only the last sound/pitch will change after processing. Also, the notes immediately after the & command are not affected by the W and S commands.

Caution 2 On the rhythm definition(R) channel, only format 3 is effective. Formats 1, 2, and 4 cannot be used.

Example 3

    R0  @1 c4&c4

Result Causes an error. Please make it c2 or c4 r4  
For the SSG rhythm channel, the sound cannot be cut during a rest.

See also

-   l+ command ([→§4.9.](#4-9))

## 4.11. Whole Note Length Setting

``` command
C
```

Format `C number`

Range 1–255

Sound Source FM / SSG / PCM / Rsel / Rdef

Determines the length of the whole note. Equivalent to the \#Zenlen command.

If it is set at the head of any channel it will affect every channel.

All specified note lengths must be a divisor of this number.

Since the default value is 96, usable lengths are 1,2,3,4,6,8,12,16,24,32,48 and 96.

If you want to specify up to a sixty-fourth note, please specify C192, etc.

Caution 1 When changed, the specified tempo value for one minute for any note length will be changed.

Caution 2 At the specified point, the value of l command will be reverted to the initial value of 4.

Example `C192`  
Result The whole note length is set to the internal clock value of 192, so the possible note lengths are increased to 14 values: 1,2,3,4,6,8,12,16,24,32,48,64,96,192. The specified value of \#Tempo as well as t command will become the value for a quarter note.

See also

-   \#Zenlen command ([→§2.11.](#2-11))
-   \#Tempo command ([→§2.10.](#2-10))
-   t command ([→§11.1.](#11-1))
-   l command ([→§4.8.](#4-8))

## 4.12. Sound Cut Setting 1

``` command
Q
```

Format `Q [%] numerical value`

Range 0–8 (0–255 if % is attached)

Sound Source FM / SSG / PCM

Specifies the way of cutting sound.

Just like N88Basic's MML, it is possible to specify 0–8 in 1/8 units. If a % is specified, it is possible to specify the smaller 0–255 in 1/256 units.

If 8 is specified, all notes up to the last will not be cut. The default is 8.

Actually, keyoff timing is done by subtracting the number specified by the q command from the position when the sound is cut off specified by this command.

Example `Q4c4`  
Result The note's length is cut by one-half.

See also

-   q command ([→§4.13.](#4-13))

## 4.13. Sound Cut Setting 2

``` command
q
```

Format 1 `q [number1][-[number2]] [,number3]`  
Format 2 `q [l length[.]][-[l length]] [,l length[.]]`

|       |                                                                                |
|-------|--------------------------------------------------------------------------------|
| Range | (number1) 0–255                                                                |
|       | (number2) 0–255, provided that the difference from number1 is within +127–-127 |
|       | (number3) 0–255                                                                |
|       | (length) 1–255, divisible by the whole note length                             |

Sound Source FM / SSG / PCM

Sets a sound cut.

The sound after number1's time span (when number2 is not set) or *randomly* within number1–number2's range (when number2 is set) will be cut.

However, when the cut length becomes shorter than number3's length, the set length for number3 will be used for the length of the note. (Please recognize that number3 = the minimum length that you want it to sound)

The number is set by the note length when l is added, and by the internal clock value if it is not added.

If you specify 0 for number1, the sound will not be cut to the end. The default value is 0.

If number2 is set to the same value as number1 or omitted, the cut time will be fixed at number1's value. The default is fixed at this.

If you specify 0 for number3, the lowest guaranteed note length will be 1. The default value is 0.

It is possible to omit numbers 1–3 respectively. However, if number2 is specified, number1 must always be set as well.

If omitted, values not indicated for numbers 1–3 will be held from the previous value. To specify only number3, please specify it as q,4 and so on.

Actually, keyoff timing is done by subtracting the value between numbers 1–2 from the position when the sound is cut off specified by Q command. If it exceeds the timing of number3 then it is performed at the timing of that instead.

Example 1 `Q4 q2 c4`  
Result Since a quarter note with an internal clock value of C96 is 24, half of 24, which is 12, plus a value of 2, totaling 10 clocks will be keyoff.

Example 2 `ql8,l16 c4 c8`  
Result Actually, c4 is equivalent to c8 r8. For c8, the lowest pronunciation length becomes effective, which is actually equivalent to c16 r16.

Example 3 `q2-4 c4 c4 c4 c4`  
Result For each pronunciation, randomly select one of the states of q2, q3, q4

Supplement Randomization of volume/pitch can be done with LFO random wave. ([→§9.11.4.](#9-1-4)) For example, `M0,255,1,6MW3*2`

See also

-   Q command ([→§4.12.](#4-12))

## 4.14. Modulation Setting

``` command
_ __
```

Format 1 `_ +number`  
Format 2 `_ -number`  
Format 3 `__ +number`  
Format 4 `__ -number`

Range -128–+127

Sound Source FM / SSG / PCM

Change all the pitch commands from there by the specified number of semitone steps.

\_ is an absolute setting, while \_\_ is a relative setting.

This command is useful for things like modulation, glissando, etc.

If \_M command([→§4.16.](#4-16)) is specified, the master modulation value and the modulation value specified here are added and set.

Example `_-2[e__+1]8_0`  
Result `dd+eff+gg+a`

See also

-   \_M command ([→§4.16.](#4-16))

## 4.15. Transposition Setting

``` command
_{ }
```

Format 1 `_{+ tone1 tone2...}`  
Format 2 `_{- tone1 tone2...}`  
Format 3 `_{= tone1 tone2...}`

Sound Source FM / SSG / PCM

Sets the transposition.

After specifying this command in the specified part, sharp, flat and natural are automatically added to the specified pitch.

Example 1 `_{-eab}`  
Result Automatically add flat to e, a and b (E♭ major or C minor)

Example 2 `_{=eab}`  
Result Example 1's settings are reversed.

## 4.16. Master Modulation Setting

``` command
_M
```

Format 1 `_M +number`  
Format 2 `_M -number`

Range -128–+127

Sound Source FM / SSG / PCM

Set the master modulation for every parts.

When this command is recognized, the modulation will be immediately set. Furthermore, the following \_ commands will affect the pitch shift according to the value set by this command.

See also

-   \_ \_\_ command ([→§4.14.](#4-14))
-   \#Transpose command ([→§2.27.](#2-27))

# 5. MML Commands — Volume Section

This section summarizes volume commands.

## 5.1. Volume Setting 1

``` command
v
```

Format `v number`

|       |                        |
|-------|------------------------|
| Range | 0–15 (SSG, SSG rhythm) |
|       | 0–16 (FM, PCM)         |

Sound Source FM / SSG / PCM(AD,86,PPZ) / Rsel / Rdef

Roughly sets the volume.

On the SSG rhythm channels (K/R), this will have no effect if PPSDRV has not been loaded into memory.

For FM channels, v0–v16 are converted to the following V command values:

|     |     |     |     |     |     |     |     |     |     |     |     |     |     |     |     |     |     |
|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| v   | 0   | 1   | 2   | 3   | 4   | 5   | 6   | 7   | 8   | 9   | 10  | 11  | 12  | 13  | 14  | 15  | 16  |
| V   | 85  | 87  | 90  | 93  | 95  | 98  | 101 | 103 | 106 | 109 | 111 | 114 | 117 | 119 | 122 | 125 | 127 |

For PCM channels, it will be converted as follows. V(2) is for when \#PCMVolume has been set to Extend:

|       |     |     |     |     |     |     |     |     |     |     |     |     |     |     |     |     |     |
|-------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| v     | 0   | 1   | 2   | 3   | 4   | 5   | 6   | 7   | 8   | 9   | 10  | 11  | 12  | 13  | 14  | 15  | 16  |
| V (1) | 0   | 16  | 32  | 48  | 64  | 80  | 96  | 112 | 128 | 144 | 160 | 176 | 192 | 208 | 224 | 240 | 255 |
| V (2) | 0   | 1   | 4   | 9   | 16  | 25  | 36  | 49  | 64  | 81  | 100 | 121 | 144 | 169 | 196 | 225 | 255 |

Example `v13`  
Result Sets the volume to 13.

See also

-   \#PCMVolume command ([→§2.19.](#2-19))
-   V command ([→§5.2.](#5-2))

## 5.2. Volume Setting 2

``` command
V
```

Format `V number`

Sound Source FM / SSG / PCM(AD,86,PPZ) / RSel / RDef

|       |                             |
|-------|-----------------------------|
| Range | 0–127 (FM)                  |
|       | 0–255 (PCM)                 |
|       | 0–15 (SSG, SSG rhythm, PPZ) |

Finely sets the volume.

On the K/R channels, this will have no effect if PPSDRV has not been loaded into memory.

Example `V120`  
Result Sets the volume to 120.

## 5.3. Overall Volume Change 1

``` command
v+ v-
```

Format 1 `v+ number`  
Format 2 `v- number`

|       |          |
|-------|----------|
| Range | \+ 0–127 |
|       | \- 0–128 |

Sound Source FM / SSG / PCM(AD,86,PPZ) / RSel / RDef

Increases or decreases the volume of all volume assignment commands in the part by the specified value.

Also, it simultaneously increases or decreases the current volume. (V command is issued)

The number is set according to the V command level (fine value).

This is convenient when you want to switch the volume for the whole song.

Example 1 `v-8`  
Result Subtract 8 each time from the value of the volume command from that part.

Caution If this is used twice in the same part, the first designation will be invalid when second one is specified. (no relative changes)

Example 2 `v-4 V100 c4 v-6 V100 d4`  
Result c4 will be set to V96, d4 will be set to V94 (not V90).

See also

-   V command ([→§5.2.](#5-2))

## 5.4. Overall Volume Change 2

``` command
v) v(
```

Format 1 `v) number`  
Format 2 `v( number`

Range 0–16

Sound Source FM / SSG / PCM(AD,86,PPZ)

Increases or decreases the volume of all volume assignment commands in the part by the specified value.

The differences between this and the first one is that

1.  This command specifies the effect of a v command. (rough value)
2.  This command is only effective for the v command. (does not change V)
3.  This command will not have an immediate effect on the current volume. (comes into effect after the next v command)

Example 1 `v(2`  
Result After the part's v command, subtracts 2 from the volume.

Caution If this is used twice in the same part, the first designation will be invalid when second one is specified. (no relative changes)

See also

-   v command ([→§5.1.](#5-1))

## 5.5. Relative Volume Change

``` command
) (
```

Format 1 `) [^] [%] [number]`  
Format 2 `( [^] [%] [number]`

Range 0–255

Sound Source FM / SSG / PCM(AD,86,PPZ) / RSel / RDef

Causes relative change for the set volume value. ) results in addition and ( results in subtraction.

If a numerical value is omitted, it will be treated as 1.

If ^ notation is added, it restricts the note change to only the next note. (accent)

If % notation is added, the volume change will be fine (equivalent to V), otherwise, it will be coarse (equivalent to v).

Caution If the % is not specified, the volume value is simply changed by 4 times the specified value for FM channels and 16 times for PCM channels.

Therefore, In the FM channel and PCM channel with \#PCMVolume in Extend state, a deviation will occur from the expected volume value after change.

Example 1 `v12 c ) c` (FM channel section)  
Result `V117 c V121 c` (larger than v13)

Example 2 `v13 c ( c` (FM channel section)  
Result `V119 c V115 c` (smaller than v12)

See also

-   V command ([→§5.2.](#5-2))
-   v command ([→§5.1.](#5-1))

# 6. MML Commands — Instrument Setting Section

This section summarizes the commands for instrument number settings as well as instrument definition.

## 6.1. Instrument Number Setting

``` command
@
```

Format 1 `@[@] insnum`  
Format 2 `@[@] insnum[,number1[,number2[,number3]]]`

|       |         |            |               |
|-------|---------|------------|---------------|
| Range | insnum  | FM, PCM    | 0–255         |
|       | insnum  | SSG        | 0–9           |
|       | insnum  | SSG Rhythm | 0–16383       |
|       | number1 | PCM        | -32768–+32767 |
|       | number2 | PCM        | -32768–+32767 |
|       | number3 | PCM        | -32768–+32767 |

Sound Source FM / SSG / PCM / RDef

Sets the instrument number for the instrument to be used afterwards. If @@ is used, 128 will be added to the instrument number. (convenient for selecting the second PPZFile's instrument)

### 6.1.1. Instrument Number Setting/FM Channels Case

Specifies the instrument which uses the @ instrument number.

Example `@1 cde @2 fga`  
Result Plays c, d, e for instrument 1 and f, g, a for instrument 2.

Caution If a slot is masked with the s command, the instrument can only be defined in the specified slot in that part. When using the s command, it is safer to redefine the instrument wherever possible.

See also

-   s command ([→§6.2.](#6-2))
-   FM Instrument Definition (@) ([→§3.1.](#3-1))

### 6.1.2. Instrument Number Setting/SSG Channels Case

Expands @ instrument number selected from 10 types of SSG software envelope prepared inside the MML compiler as E command.

The contents to be expanded are as follows:

|     |                                     |                           |
|-----|-------------------------------------|---------------------------|
| @0  | E0,0,0,0                            | Default                   |
| @1  | E2,-1,0,1                           | Synth type 1              |
| @2  | E2,-2,0,1                           | Synth type 2              |
| @3  | E2,-2,0,8                           | Synth type 3              |
| @4  | E2,-1,24,1                          | Piano type 1              |
| @5  | E2,-2,24,1                          | Piano type 2              |
| @6  | E2,-2,4,1                           | Glockenspiel/Marimba type |
| @7  | E2,1,0,1                            | Strings Type              |
| @8  | E1,2,0,1                            | Brass type 1              |
| @9  | E1,2,24,1                           | Brass type 2              |
| @10 | Please do not specify beyond these. |                           |

Example `@6v10l8 cegb>c<gec`  
Result Plays a CMaj7 arpeggio with a percussion instrument type software envelope.

See also

-   E command ([→§8.1.](#8-1))

### 6.1.3. Instrument Number Setting/SSG Rhythm Definition (Without PPSDRV) Case

Selects any of the internal PMD SSG drums to be used for the R part.

The instrument numbers and corresponding sounds are listed below:

|       |              |
|-------|--------------|
| @1    | Bass Drum    |
| @2    | Snare Drum 1 |
| @4    | Low Tom      |
| @8    | Middle Tom   |
| @16   | High Tom     |
| @32   | Rim Shot     |
| @64   | Snare Drum 2 |
| @128  | Hi-Hat Close |
| @256  | Hi-Hat Open  |
| @512  | Crash Cymbal |
| @1024 | Ride Cymbal  |

For PMDB2/PMDVA/PMD86, if the /N option (→PMD.DOC) is not specified, an appropriate sound from the rhythm channels will be played simultaneously. In that case, if you add the instrument numbers together, the sound will be changed so that both desired drum sounds will be somewhat audible. (SSG rhythm sound takes priority on the sound with the lower number)

Example 1 `@2c`  
Result Plays a snare drum.

Example 2 `@129c`  
Result On PMD.COM, @1 plays a bass drum. On PMDB2/VA/86, the rhythm sound source's hi-hat plays simultaneously in addition to the above.

### 6.1.4. Instrument Number Definition/SSG Rhythm Definition (With PPSDRV) Case

If PDR,PPSDRV is loaded, selects a SSGPCM instrument.

In addition to the SSG rhythm instruments in §6.1.3., this adds three new rhythm instruments with numbers @2048, @4096, and @8192.

The relation between the rhythm sounds and the instrument numbers varies depending on the contents of the .PPS file.

If played back with PDR set to \#Double mode, it is possible to play up to 2 sounds simultaneously.

Example `@4c`  
Result Plays the third SSGPCM sound defined in the .PPS file.

### 6.1.5. Instrument Number Setting/PCM Channels Case

After adding an @insnum, in PMDB2/PMDVA/PMD86/PMDPPZ, it is possible to add a repeat address setting for the instrument behind it ([→§6.1.](#6-1) Format 2)

For each number:  
number1 = repeat start address  
number2 = repeat end address (default 0)  
number3 = note release address (default $8000) \*Invalid for PMDPPZ, PMDPPZE  
The value from -32768–+32767 can be specified.

If any number is positive (+), it is an addition to the start address of the instrument.  
If any number is negative (-), it is a subtraction from the end address of the instrument.

If number1 is not specified, repeat setting is not done. (one-shot PCM)

If number2 is 0 or not specified, the instrument will loop from the repeat start address to the instrument's end address.

If number3 is $8000 or not specified, even if keyoff is done, the instrument will remain looping from the repeat start address to the repeat end address.

Each value is calculated in units of 1 byte for PMD86/PMDPPZ and 16 bytes for PMDB2/PMDVA.

However, when the /S option (→PMD.DOC) is specified for PMD86, it is calculated in units of 32 bytes. (to correspond to ADPCM 16 bytes = PCM 32 bytes)

In this case, since this is only 32 times internally, please keep each number in the range of -1024\~+1023.

Example For PMDB2 with instrument @0 being 4000 bytes in size, in units of 16 bytes, the instrument's start address is 0 and end address is 250.  

    J   @0,100,-50,-50 g1

That is played back according to this sequence:

1.  Play from the beginning position to the position of +200 (250-\|number2\|).
2.  Repeat playback from +100 (number1) to +200 (250-\|number2\|).
3.  At the moment of keyoff, plays from +200 (250-\|number3\|) to +250, and then ends.

Supplement When repeating playback on the YM2608 (PMDB2/PMDVA)'s ADPCM it seems that the next delta prediction value of the next data is cleared to 0 at the moment of repeat. This seems to be a hardware's method, you cannot do anything to change it.

For this reason, when repeating, the phenomenon that the volume becomes extremely low at the moment of repeat often happens.

In this case, try changing the repeat address to various other values.

The trick is, first, if you try to return to the beginning of the instrument when repeating using the data that started recording suddenly while playing the target sound, that phenomenon will not happen. In that case, please use the software envelope to express the temporal change of the tone volume.

Furthermore, if you have a tool that can edit while watching the PCM waveform, please try setting the repeat start position and end position to a position close to the amplitude of ±0 and further select the place where the amplitude change is quiet, the noise at the moment of repeat seems to be reduced.

## 6.2. FM Slot Use Setting

``` command
s
```

Format `s number`

Range 0–15

Sound Source FM

Mainly used for the 3rd FM channel, specifies the slot position (operators) to be used for performance/definition.

The numerical value specifies the total sum of slot numbers to be used in that part, with slot1 = 1, slot2 = 2, slot3 = 4, and slot4 = 8.

For the 3rd FM channel, it is possible to playback each slot (4 total) independently. Thus, if you have separated the 3rd FM channel into multiple parts, you can use this command on those parts to play phrases separately on each of the slots.

Example 1 In case of dividing the instrument of ALG 4 into slot1,2 and slot3,4, let it be:

    #FM3Extend  X
    C   s3⋯
    X   s12⋯

After setting this command, using an instrument setting command @ ([→§6.1.](#6-1)) will only use the parameters for the available slots.

As an exception, FB is defined only if slot1 is used and ALG is always defined unconditionally.

Therefore, if the value of ALG is the same, another instrument number can be specified for each part even for the same FM channel 3.

If this command is specified for any channel other than the 3rd FM channel, only those selected slots will sound. (slot masking operation)

Caution 1 `s3 @200cde s15 fga`  
Because @200 is only defined for slots 1 and 2, the fga part will be played back strangely.

Caution 2 Please do not overlap used slots in FM channel 3 (channel C-F without \#FM3Extend and C + extended channels with \#FM3Extend in PMD.COM). Operation when overlapping is not guaranteed to work.

Caution 3 Because ALG is defined unconditionally, for example: While playing back slots 1, 2, 3, and 4 with ALG6, if the channel using slots 1 and 2 changes to an ALG4 instrument, slots 3 and 4 will sound strange. Please be careful. However, regarding FB, even if FB=7 sound is used on slots 1 and 2, and an instrument with FB=0 is defined on slots 3 and 4, since FB is not defined on those slots anyway, there will be no effect on slots 1 and 2.

Example 2 In PMD.COM

    ; nm alg fbl
    @202 004 007
    ; ar  dr  sr  rr  sl  tl  ks  ml  dt ams    Trumpet *2
     013 014 000 003 001 023 002 004 000 000    ;slot1
     019 003 000 010 000 000 001 008 000 000    ;slot2
     013 014 000 003 001 020 002 004 000 000    ;slot3
     019 003 000 010 000 000 001 004 000 000    ;slot4

    C   s$3 ;slot1,2 only
    D   s$c ;slot3,4 only
    CD  @202v12M12,1,8,2*1
    C   o3l8W12,-2[[a4ga4>c4d4:c4<ba4g4]4:>c4<ab4g4]2>f4fg4 d4
    D   o3l8W12,-2[[e4ee4 a4b4:a4 ge4e4]4: a4 fg4d4]2>c4cd4<b4

Result Algorithm 4 divides 1 channel into 2 slots at a time and plays a chord.

## 6.3. FM TL Setting

``` command
O
```

Format 1 `O number1,number2`  
Format 2 `O number1,±number2`

|       |           |            |           |
|-------|-----------|------------|-----------|
| Range | (number1) |            | 1–15      |
|       | (number2) | (Format 1) | 0–127     |
|       |           | (Format 2) | -128–+127 |

Sound Source FM

Directly sets the TL (True Level, or operator volume) value of an FM instrument.

This is useful when you want to express the change due to the velocity of the instrument, or when you want to express human-like wah-wah pedal control instead of periodic like LFO.

number1 specifies the total sum of slot numbers to be used in that part, with slot1 = 1, slot2 = 2, slot3 = 4, and slot4 = 8.

number2 is the TL value to set. When a + or - is specified (Format 2), it will change relatively to the current TL.

Example 1 `O3,10`  
Result Sets the TL of slots 1 and 2 to 10.

Example 2 `O5,-2`  
Result Subtracts 2 from the TL of slots 1 and 3.

## 6.4. FM FB Setting

``` command
FB
```

Format 1 `FB number1`  
Format 2 `FB ±number2`

|       |                 |
|-------|-----------------|
| Range | (number1) 0–7   |
|       | (number2) -7–+7 |

Sound Source FM

Directly sets the FB (feedback) value of an FM instrument.

Like how O command controls the TL value, this command controls the FB value. The application for use, etc. also follows O command.

The specified number is the FB value to set. When a + or - is specified (Format 2), it will change relatively to the current FB.

Example 1 `FB3`  
Result Sets the FB of the current FM instrument to 3.

Example 2 `FB-2`  
Result Subtracts 2 from the current FM instrument's FB value.

## 6.5. SSG/OPM Tone/Noise Output Selection

``` command
P
```

Format `P number`

Range 1–3

Sound Source FM (OPM) / SSG

For slot4 of channel H of FM sound source (OPM) and SSG sound source, selects the output of the tone/noise.

When specified for SSG channels

|     |                |
|-----|----------------|
| 1   | tone (default) |
| 2   | noise          |
| 3   | tone + noise   |

When specified for the FM (OPM)'s H channel

|     |                |
|-----|----------------|
| 1   | tone (default) |
| 2   | noise          |

Example 1 `P3` (SSG Source)  
Result Outputs a mix of tone and noise afterwards for the SSG channel.

## 6.6. Noise frequency setting

``` command
w
```

Format 1 `w number`  
Format 2 `w ±number`

|       |                    |
|-------|--------------------|
| Range | (Format 1) 0–31    |
|       | (Format 2) -31–+31 |

Sound Source FM (OPM) / SSG

For slot4 of channel H of FM sound source (OPM) and SSG sound source, selects the noise frequency.

The larger the number, the lower the frequency sound becomes.

When a + or - is specified, it will change relatively to the current value.

Even if the frequency is set with this, the noise will not sound unless it is turned on by the P command.

Caution When this command is performed on a SSG channel, when an SSG sound effect like a drum effect is played, this command will not take effect until the next keyon after the sound effect ends.

Until then, it may be affected by the noise frequency change of the SSG sound effect. It is safest to allow the SSG noise to be erased by the SSG sound effect, and to only use this command on channel I.

Example 1 `w31`  
Result Sets the noise frequency to the lowest value 31.

See also

-   P command ([→§6.5.](#6-5))

## 6.7. Rhythm Pattern Selection/Playback

``` command
R
```

Format `R number`

Range 0–255

Sound Source RSel

By using the rhythm definition part (R), plays a rhythm pattern specified by the number of the defined rhythm value.

Example `R0R0R0R1`  
Result Plays the R0 pattern 3 times, and then the R1 pattern once.

See also

-   Using the Rhythm Channel (K/R) ([→§1.2.](#1-2))

# 7. MML Commands — Detune section

This section summarizes the detune commands that delicately change the pitch.

## 7.1. Detune Setting

``` command
D DD
```

Format 1 `D number`  
Format 2 `DD number`

Range -32768–+32767

Sound Source FM / SSG / PCM(AD,86,PPZ)

Sets the detune (frequency shift value).

D command sets an absolute detune. DD command changes the value relative to the previous set detune.

The default detune value is 0.

On the SSG channels, even if the same value is applied, the degree will change depending on \#Detune or DX command.

If \#Detune Normal or DX0 is used, the value to be output to the FM chip is shifted as it is, for example, +1 if it is +1.

If \#Detune Extend or DX1 is used, every octave is compensated to be shifted by the same degree for the same value. However, when it is not 0 (D1 for example), it is set to be at least 1 at all times.

For the PCM and FM sources, they will be added or subtracted from the pitch value given to the FM chip as it is.

If the DM command ([→§7.6.](#7-6)) is used, the detune will be set to the value of this command plus the master detune value.

Example

    G D0 v13 o5g1
    H D1 v13 o5g1

Result For parts G and H, they will be played together with slightly different frequencies.

Caution By executing DD command, it does not check if the detune value exceeds +32767 or falls below -32768.

See also

-   DX command ([→§7.3.](#7-3))
-   \#Detune command ([→§2.16.](#2-16))
-   DM command ([→§7.6.](#7-6))

## 7.2. FM Channel 3 Per-Slot Detune Setting

``` command
sd sdd
```

Format 1 `sd slotnum, number`  
Format 2 `sdd slotnum, number`

|       |                        |
|-------|------------------------|
| Range | (slotnum) 1–15         |
|       | (number) -32768–+32767 |

Sound Source FM (Channel 3)

Only usable on FM channel 3, this sets the detune value for each slot.

sd command sets an absolute detune. sdd command changes the value relative to the previous set detune.

Specify the slot with the slotnum and specify the detune value with the number.

slotnum specifies the total sum of slot numbers to be used in that part, with slot1 = 1, slot2 = 2, slot3 = 4, and slot4 = 8.

It is also possible to use this command simultaneously with the D command. In that case, detune will be applied to each slot specified by this command after adding/subtracting the value of the D command to all the slots used in the specified part.

By default all slots are set to 0.

Caution All of the FM Channel 3 MML parts share access to the slot values. For example, in PMD.COM, while playing slot1,2 in channel C and slot3,4 in channel D, if you use the command sd8,+10 on channel C, the detune of +10 will be applied to slot 4 of the instrument being played in channel D.

In order to avoid such a phenomenon, please do not specify sd command outside of the playing slots. Also, if you change the playing slot in the middle, you need to reset the detune value of the slot that will not be played back to 0.

Example `sd6,-4`  
Result Subtracts 4 from the detune on slots 2 and 3.

See also

-   s command ([→§6.2.](#6-2))
-   D DD commands ([→§7.1.](#7-1))

## 7.3. SSG Pitch Interval Correction Setting

``` command
DX
```

Format `DX number`

Range 0–1

Sound Source SSG

Selects whether or not to adjust the SSG pitch interval.

If set to 0, when the detune/LFO shifts by 1, the pitch value sent to the sound source will also be shifted by 1. (even with the same detune value, the deviation increases as the pitch goes higher)

If set to 1, it makes the deviation decreases as you go to the higher pitch, and correct it so that the same detune/LFO value will be shifted by the same extent at any interval.

This has the same function as \#Detune, but it is possible to change it for each channels with this command. The default value is 0.

Example `DX1`  
Result Correct the detune value after that for each pitch interval.

See also

-   \#Detune command ([→§2.16.](#2-16))
-   D DD commands ([→§7.1.](#7-1))
-   M MA MB commands ([→§9.1.](#9-1))

## 7.4. Bend Width Setting

``` command
B
```

Format `B number`

Range 0–255

Sound Source FM / SSG / PCM(AD,86,PPZ)

Sets a MIDI-like bend width. Identical to \#Bendrange. It is possible to set between 0 and 255 semitones.

The I command will be valid if you set any value other than 0.

The effect of this command extends over all subsequent parts. For example, if you only set B12 on channel C, channels A and B will not be set, but all parts after C (CDEFGHIJ + \#FM3Extend channels) will be set. However, if the value is set with \#Bendrange it will take effect on all parts.

Caution At the time of setting the bend width, cautions shown in the I command ([→§7.5.](#7-5)) are effective and MML can be hard to look at. So it is better not to use it unless you are converting from MIDI.

Example `B12`  
Result An I command with a value of 8192 will slide the pitch exactly one octave.

See also

-   \#Bendrange command ([→§2.15.](#2-15))
-   I command ([→§7.5.](#7-5))

## 7.5. Pitch Setting

``` command
I
```

Format `I number`

Range -32768–+32767

Sound Source FM / SSG / PCM(AD,86,PPZ)

Set the MIDI-like pitch value.

With ±8192, shift the frequency by the bend width.

It will be invalid unless you set the bend width \#Bendrange or B command.

Caution 1 Only the FM sound source will set the pitch exactly. SSG/ADPCM parts will go up and down as it is, but the ones that do not use it is safe.

Caution 2 When the bend width is set and this command is valid, the value of pitch/detune will be set only when the next pitch interval command comes after it.

Example 1

    A   B2I0[cdeI8192fga]2

Result The same as

    A   B2[I0cdeI8192fga]2

The D command will also be affected.

Example 2 If written like this...

    A   B0D10[cdeD0]2

Result it will sound like this, but...

    A   D10 cdeD0 cdeD0

Example 3 if written like this...

    A   B2D10[cdeD0]2

Result it will sound like this, please be careful.

    A   D10cdeD0 D10cdeD0

Example 4

    A   B12o4l8 I0cI1000cI2000cI3000cI4000cI5000cI6000cI7000cI8192c

Result The pitch will be raised little by little from c on octave 4 to c on octave 5.

See also

-   \#Bendrange command ([→§2.15.](#2-15))
-   B command ([→§7.4.](#7-4))
-   D DD command ([→§7.1.](#7-1))

## 7.6. Master Detune setting

``` command
DM
```

Format `DM number`

Range -32768–+32767

Sound Source FM / SSG / PCM(AD,86,PPZ)

Sets the master detune value for each respective channel.

When this command is recognized, the detune will be immediately set. Furthermore, the following D commands will affect the detune according to the value set by this command.

See also

-   D DD commands ([→§7.1.](#7-1))

# 8. MML Commands — Envelope Section

This section summarizes software envelope related commands that change the sound of SSG/PCM.

## 8.1. SSG/PCM Software Envelope Setting

``` command
E
```

Format 1 `E number1, number2, number3, number4`  
Format 2 `E number1, number2, number3, number4, number5 [,number6]`

Sound Source SSG / PCM(AD,86,PPZ)

|       |            |                 |
|-------|------------|-----------------|
| Range | (Format 1) | number1 0–255   |
|       |            | number2 -15–+15 |
|       |            | number3 0–255   |
|       |            | number4 0–255   |
|       | (Format 2) | number1 0–31    |
|       |            | number2 0–31    |
|       |            | number3 0–31    |
|       |            | number4 0–15    |
|       |            | number5 0–15    |
|       |            | number6 0–15    |

Sets a software envelope (only for OPN/OPNA's SSG/ADPCM channels). Two kinds of envelopes can be selected. However, they cannot be used at the same time.

If you only write 4 numbers, it will be treated as Format 1 and for 5 or 6 numbers it will be treated as Format 2.

With \#EnvelopeSpeed Normal or EX0, the speed depends on the tempo. With \#EnvelopeSpeed Extend or EX1, the speed is fixed.

### 8.1.1. Software Envelope Setting/Format 1 Case

PMD's unique simplified envelope specification method.

number1 = Attack Length (AL)  
number2 = Decay Depth (DD)  
number3 = Sustain Rate (SR)  
number4 = Release Rate (RR)

If \#EnvelopeSpeed Normal or EX0 is used, 1 clock = 1 internal clock  
If \#EnvelopeSpeed Extend or EX1 is used, 1 clock = 54.17 Hz  
and it will change as follows:

1.  After keyon, wait for AL clocks at the set volume, then add/subtract DD to/from volume.
2.  For each SR clocks, decrease the volume by -1
3.  When keyoff is done, decrease the volume by -1 for each RR clocks

When SR = 0, At step 2 the volume will not decay.  
When RR = 0, At step 3 the volume will instantly drop to 0.

Example `C96 EX0 E1,-2,2,1 v13 l16 gr`  
Result The volume will change as follows:

    13 11 11 9 9 7 7 6 5 4 3 2
    ↑keyon         ↑keyoff

### 8.1.2. Software Envelope Setting/Format 2 Case

The method is nearly identical to an FM volume envelope.

number 1 = Attack Rate (AR)  
number 2 = Decay Rate (DR)  
number 3 = Sustain Rate (SR)  
number 4 = Release Rate (RR)  
number 5 = Sustain Level (SL)  
number 6 = Attack Level (Default 0)

Attack Level specifies the level at which the attack starts.

While it is similar to an FM envelope, please note that it is not the same in terms of speed. In particular, with \#EnvelopeSpeed Normal or EX0, the envelope speed will be dependent on tempo.

For the meaning of the parameters, please refer to the FM tone generator manual, etc.

Example `E31,18,4,15,2`  
Result Sets a piano-like envelope.

See also

-   \#EnvelopeSpeed command ([→§2.18.](#2-18))
-   EX command ([→§8.2.](#8-2))

## 8.2. Software Envelope Speed Setting

``` command
EX
```

Format `EX number`

Range 0–1

Sound Source SSG / PCM(AD,86,PPZ)

If set to 1 the E command will change to be in constant speed independent of the tempo.

If set to 0 it will be dependent on the tempo. (if the tempo is slow, the envelope is slow)

This has the same function as \#EnvelopeSpeed, but it is possible to change it for each channels with this command. The default value is 0.

Example `EX1`  
Result Makes sure that the envelope of the specified part does not depend on tempo from there.

See also

-   \#EnvelopeSpeed command ([→§2.18.](#2-18))
-   E command ([→§8.1.](#8-1))

# 9. MML Commands — LFO Section

This section summarizes LFO (low frequency oscillator) related commands.

LFOs are generally used for the FM/SSG/PCM pitch/volume, as well as FM modulation level, to create effects such as vibrato (pitch), tremolo (volume), and "wah-wah" effect (modulation level).

Also, various waveforms are prepared, especially random waves, etc. which are useful for processing sound effects.

## 9.1. Software LFO Setting

``` command
M MA MB
```

Format 1 `M number1`  
Format 2 `M l length[.]`  
Format 3 `M number1, number2, number3, number4`  
Format 4 `M l length[.], number2, number3, number4`  
Format 5 `MA number1`  
Format 6 `MA l length[.]`  
Format 7 `MA number1, number2, number3, number4`  
Format 8 `MA l length[.], number2, number3, number4`  
Format 9 `MB number1`  
Format 10 `MB l length[.]`  
Format 11 `MB number1, number2, number3, number4`  
Format 12 `MB l length[.], number2, number3, number4`

|       |                                                    |
|-------|----------------------------------------------------|
| Range | (number1) 0–255                                    |
|       | (number2) 0–255                                    |
|       | (number3) -128–+127                                |
|       | (number4) 0–255                                    |
|       | (length) 1–255, divisible by the whole note length |

Sound Source FM / SSG / PCM(AD,PPZ)

Sets the software LFO.

PMD has two software LFOs, each of which can be used independently. M or MA sets the first LFO (LFO1) and MB sets the second LFO (LFO2).

Specified values are as follows:

number1 = delay  
number2 = speed  
number3 = depthA  
number4 = depthB

If the only setting is delay, only the current delay value will change.

Delay is set by note length when l is added, and by the value of the internal clock if not added.

For the LFO speed, if \#LFOSpeed Normal or MX0 is used, it will depend on the tempo. If \#LFOSpeed Extend or MX1 is used, it will be based on a fixed speed.

The LFO waveform depends on what you specified with the MW command. The meaning of each numbers will differ slightly depending on the waveform.

If \#LFOSpeed Normal or EX0 is used, 1 clock = 1 internal clock  
If \#LFOSpeed Extend or EX1 is used, 1 clock = 54.17 Hz  
and it will change as described below.

Please receive each command of MX MW \* which is described in the explanation below as a command to change the specified LFO respectively. (MXB MWB \*B for MB)

### 9.1.1. Software LFO Setting/MW0 Case (Triangle Wave 1)

1.  After keyon, wait for delay clocks.
2.  For each speed clocks, add depthA to the pitch/volume change amount.
3.  Repeat 2. depthB times. If 255 is set, it will loop infinitely.
4.  DepthA is inverted from positive to negative, and when it is inverted for the first time, depthB is multiplied by two.
5.  Go to 2.

Image

![](data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDcwIiBoZWlnaHQ9IjE2MiI+CiAgICA8bGluZSBzdHJva2U9ImJsYWNrIiBzdHJva2UtZGFzaGFycmF5PSI1LCA1IiB4MT0iNDAiIHkxPSI4NSIgeDI9IjQzMCIgeTI9Ijg1Ij48L2xpbmU+CiAgICA8dGV4dCB4PSIwIiB5PSI4OSI+wrEwIOKGkjwvdGV4dD4KICAgIDx0ZXh0IHg9IjQzMCIgeT0iODkiPuKGkjwvdGV4dD4KICAgIDxwb2x5bGluZSBmaWxsPSJub25lIiBzdHJva2U9ImJsYWNrIiBzdHJva2Utd2lkdGg9IjIiIHBvaW50cz0iNDAsODUgMTIwLDg1IDE4MCwxMCAzMDAsMTYwIDQyMCwxMCI+PC9wb2x5bGluZT4KICAgIDx0ZXh0IHg9IjM1IiB5PSIxMDUiPkE8L3RleHQ+CiAgICA8dGV4dCB4PSIxMTUiIHk9IjEwNSI+QjwvdGV4dD4KICAgIDx0ZXh0IHg9IjE3NSIgeT0iMTA1Ij5DPC90ZXh0PgogICAgPHRleHQgeD0iMTYwIiB5PSIxNSI+RDwvdGV4dD4KICA8L3N2Zz4=)

A–B (length) : delay (parameter1)  
B–C (length) : speed × depthB (parameter2 × parameter4)  
B–D (depth) : depthA × depthB (parameter3 × parameter4)

### 9.1.2. Software LFO Setting/MW1 Case (Sawtooth Wave)

1.  After keyon, wait for delay clocks.
2.  For each speed clocks, add depthA to the pitch/volume change amount.
3.  Repeat 2. depthB times. If 255 is set, it will loop infinitely.
4.  Pitch/volume change amount is inverted from positive to negative, and when it is inverted for the first time, depthB is multiplied by two.
5.  Go to 2.

Image

![](data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDcwIiBoZWlnaHQ9IjE2MiI+CiAgICA8bGluZSBzdHJva2U9ImJsYWNrIiBzdHJva2UtZGFzaGFycmF5PSI1LCA1IiB4MT0iNDAiIHkxPSI4NSIgeDI9IjQzMCIgeTI9Ijg1Ij48L2xpbmU+CiAgICA8dGV4dCB4PSIwIiB5PSI4OSI+wrEwIOKGkjwvdGV4dD4KICAgIDx0ZXh0IHg9IjQzMCIgeT0iODkiPuKGkjwvdGV4dD4KICAgIDxwb2x5bGluZSBmaWxsPSJub25lIiBzdHJva2U9ImJsYWNrIiBzdHJva2Utd2lkdGg9IjIiIHBvaW50cz0iNDAsODUgMTIwLDg1IDE4MCwxMCAxODAsMTYwIDMwMCwxMCAzMDAsMTYwIDQyMCwxMCI+PC9wb2x5bGluZT4KICAgIDx0ZXh0IHg9IjM1IiB5PSIxMDUiPkE8L3RleHQ+CiAgICA8dGV4dCB4PSIxMTUiIHk9IjEwNSI+QjwvdGV4dD4KICAgIDx0ZXh0IHg9IjE4NSIgeT0iMTA1Ij5DPC90ZXh0PgogICAgPHRleHQgeD0iMTYwIiB5PSIxNSI+RDwvdGV4dD4KICA8L3N2Zz4=)

A–B (length) : delay (parameter1)  
B–C (length) : speed × depthB (parameter2 × parameter4)  
B–D (depth) : depthA × depthB (parameter3 × parameter4)

### 9.1.3. Software LFO Setting/MW2 Case (Square Wave)

1.  After keyon, wait for delay clocks.
2.  Set the pitch/volume change amount to depthA×depthB.
3.  Wait for speed clocks. If it is 255 it will not change.
4.  Pitch/volume change amount is inverted from positive to negative.
5.  Go to 3.

Image

![](data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDcwIiBoZWlnaHQ9IjE2MiI+CiAgICA8bGluZSBzdHJva2U9ImJsYWNrIiBzdHJva2UtZGFzaGFycmF5PSI1LCA1IiB4MT0iNDAiIHkxPSI4NSIgeDI9IjQzMCIgeTI9Ijg1Ij48L2xpbmU+CiAgICA8dGV4dCB4PSIwIiB5PSI4OSI+wrEwIOKGkjwvdGV4dD4KICAgIDx0ZXh0IHg9IjQzMCIgeT0iODkiPuKGkjwvdGV4dD4KICAgIDxwb2x5bGluZSBmaWxsPSJub25lIiBzdHJva2U9ImJsYWNrIiBzdHJva2Utd2lkdGg9IjIiIHBvaW50cz0iNDAsODUgMTIwLDg1IDEyMCwxMCAxODAsMTAgMTgwLDE2MCAyNDAsMTYwIDI0MCwxMCAzMDAsMTAgMzAwLDE2MCAzNjAsMTYwIDM2MCwxMCA0MjAsMTAiPjwvcG9seWxpbmU+CiAgICA8dGV4dCB4PSIzNSIgeT0iMTA1Ij5BPC90ZXh0PgogICAgPHRleHQgeD0iMTE1IiB5PSIxMDUiPkI8L3RleHQ+CiAgICA8dGV4dCB4PSIxODUiIHk9IjEwNSI+QzwvdGV4dD4KICAgIDx0ZXh0IHg9IjE4NSIgeT0iMTUiPkQ8L3RleHQ+CiAgPC9zdmc+)

A–B (length) : delay (parameter1)  
B–C (length) : speed (parameter2)  
B–D (depth) : depthA × depthB (parameter3 × parameter4)

### 9.1.4. Software LFO Setting/MW3 Case (Random Wave)

1.  After keyon, wait for delay clocks.
2.  Set the pitch/volume change amount to a random value between -depthA×depthB and depthA×depthB.
3.  Wait for speed clocks. If it is 255 it will not change.
4.  Go to 2.

Image

![](data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDcwIiBoZWlnaHQ9IjE2MiI+CiAgICA8bGluZSBzdHJva2U9ImJsYWNrIiBzdHJva2UtZGFzaGFycmF5PSI1LCA1IiB4MT0iNDAiIHkxPSI4NSIgeDI9IjQzMCIgeTI9Ijg1Ij48L2xpbmU+CiAgICA8dGV4dCB4PSIwIiB5PSI4OSI+wrEwIOKGkjwvdGV4dD4KICAgIDx0ZXh0IHg9IjQzMCIgeT0iODkiPuKGkjwvdGV4dD4KICAgIDxwb2x5bGluZSBmaWxsPSJub25lIiBzdHJva2U9ImJsYWNrIiBzdHJva2Utd2lkdGg9IjIiIHBvaW50cz0iNDAsODUgMTIwLDg1IDEyMCwxMCAxNTAsMTAgMTUwLDQyIDE4MCw0MiAxODAsMTQzIDIxMCwxNDMgMjEwLDEyNiAyNDAsMTI2IDI0MCwxMTcgMjcwLDExNyAyNzAsNTMgMzAwLDUzIDMwMCw3OCAzMzAsNzggMzMwLDE1NCAzNjAsMTU0IDM2MCw4MSAzOTAsODEgMzkwLDEwNiA0MjAsMTA2Ij48L3BvbHlsaW5lPgogICAgPHRleHQgeD0iMzUiIHk9IjEwNSI+QTwvdGV4dD4KICAgIDx0ZXh0IHg9IjExNSIgeT0iMTA1Ij5CPC90ZXh0PgogICAgPHRleHQgeD0iMTQ1IiB5PSIxMDUiPkM8L3RleHQ+CiAgICA8dGV4dCB4PSIxMDUiIHk9IjE1Ij5EPC90ZXh0PgogIDwvc3ZnPg==)

A–B (length) : delay (parameter1)  
B–C (length) : speed (parameter2)  
B–D (depth) : 0–±(depthA × depthB) (0–±(parameter3 × parameter4))

### 9.1.5. Software LFO Setting/MW4 Case (Triangle Wave 2)

1.  After keyon, wait for delay clocks.
2.  For each speed clocks, add depthA to the pitch/volume change amount.
3.  Repeat 2. depthB times. If 255 is set, it will loop infinitely.
4.  DepthA is inverted from positive to negative. Unlike MW0, depthB does not change here.
5.  Go to 2.

Image

![](data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDcwIiBoZWlnaHQ9IjEwNyI+CiAgICA8bGluZSBzdHJva2U9ImJsYWNrIiBzdHJva2UtZGFzaGFycmF5PSI1LCA1IiB4MT0iNDAiIHkxPSI4NSIgeDI9IjQzMCIgeTI9Ijg1Ij48L2xpbmU+CiAgICA8dGV4dCB4PSIwIiB5PSI4OSI+wrEwIOKGkjwvdGV4dD4KICAgIDx0ZXh0IHg9IjQzMCIgeT0iODkiPuKGkjwvdGV4dD4KICAgIDxwb2x5bGluZSBmaWxsPSJub25lIiBzdHJva2U9ImJsYWNrIiBzdHJva2Utd2lkdGg9IjIiIHBvaW50cz0iNDAsODUgMTIwLDg1IDE4MCwxMCAyNDAsODUgMzAwLDEwIDM2MCw4NSA0MjAsMTAiPjwvcG9seWxpbmU+CiAgICA8dGV4dCB4PSIzNSIgeT0iMTA1Ij5BPC90ZXh0PgogICAgPHRleHQgeD0iMTE1IiB5PSIxMDUiPkI8L3RleHQ+CiAgICA8dGV4dCB4PSIxNzUiIHk9IjEwNSI+QzwvdGV4dD4KICAgIDx0ZXh0IHg9IjE2MCIgeT0iMTUiPkQ8L3RleHQ+CiAgPC9zdmc+)

A–B (length) : delay (parameter1)  
B–C (length) : speed × depthB (parameter2 × parameter4)  
B–D (depth) : depthA × depthB (parameter3 × parameter4)

### 9.1.6. Software LFO Setting/MW5 Case (Triangle Wave 3)

1.  After keyon, wait for delay clocks.
2.  For each speed clocks, add depthA × \|depthA\| to the pitch/volume change amount.
3.  Repeat 2. depthB times. If 255 is set, it will loop infinitely.
4.  DepthA is inverted from positive to negative, and when it is inverted for the first time, depthB is multiplied by two.
5.  Go to 2.

Image

![](data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDcwIiBoZWlnaHQ9IjE2MiI+CiAgICA8bGluZSBzdHJva2U9ImJsYWNrIiBzdHJva2UtZGFzaGFycmF5PSI1LCA1IiB4MT0iNDAiIHkxPSI4NSIgeDI9IjQzMCIgeTI9Ijg1Ij48L2xpbmU+CiAgICA8dGV4dCB4PSIwIiB5PSI4OSI+wrEwIOKGkjwvdGV4dD4KICAgIDx0ZXh0IHg9IjQzMCIgeT0iODkiPuKGkjwvdGV4dD4KICAgIDxwb2x5bGluZSBmaWxsPSJub25lIiBzdHJva2U9ImJsYWNrIiBzdHJva2Utd2lkdGg9IjIiIHBvaW50cz0iNDAsODUgMTIwLDg1IDE4MCwxMCAzMDAsMTYwIDQyMCwxMCI+PC9wb2x5bGluZT4KICAgIDx0ZXh0IHg9IjM1IiB5PSIxMDUiPkE8L3RleHQ+CiAgICA8dGV4dCB4PSIxMTUiIHk9IjEwNSI+QjwvdGV4dD4KICAgIDx0ZXh0IHg9IjE3NSIgeT0iMTA1Ij5DPC90ZXh0PgogICAgPHRleHQgeD0iMTYwIiB5PSIxNSI+RDwvdGV4dD4KICA8L3N2Zz4=)

A–B (length) : delay (parameter1)  
B–C (length) : speed × depthB (parameter2 × parameter4)  
B–D (depth) : depthA × \|depthA\| × depthB (parameter3 × \|parameter3\| × parameter4)

Supplement This is a deeper triangle wave.

Caution The possible range of LFO variation is -32768–+32767. In order to reduce processing, a check for when this range is exceeded is not done. So please be careful.

Example `M0,1,32,64 MW5 *1`  
For the above example, it changes by 32×32 = 1024 at every 1 clock. However, it reaches +32768 at 32768/1024 = 32 clocks. So if you play a note longer than this length, the sound turns inside out.

### 9.1.7. Software LFO Setting/MW6 Case (One-shot)

1.  After keyon, wait for delay clocks.
2.  For each speed clocks, add depthA to the pitch/volume change amount.
3.  Repeat 2. depthB times. If 255 is set, it will loop infinitely.
4.  Continue to maintain the state where repetition has ended.

Image

![](data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDcwIiBoZWlnaHQ9IjEwNyI+CiAgICA8bGluZSBzdHJva2U9ImJsYWNrIiBzdHJva2UtZGFzaGFycmF5PSI1LCA1IiB4MT0iNDAiIHkxPSI4NSIgeDI9IjQzMCIgeTI9Ijg1Ij48L2xpbmU+CiAgICA8dGV4dCB4PSIwIiB5PSI4OSI+wrEwIOKGkjwvdGV4dD4KICAgIDx0ZXh0IHg9IjQzMCIgeT0iODkiPuKGkjwvdGV4dD4KICAgIDxwb2x5bGluZSBmaWxsPSJub25lIiBzdHJva2U9ImJsYWNrIiBzdHJva2Utd2lkdGg9IjIiIHBvaW50cz0iNDAsODUgMTIwLDg1IDE4MCwxMCA0MjAsMTAiPjwvcG9seWxpbmU+CiAgICA8dGV4dCB4PSIzNSIgeT0iMTA1Ij5BPC90ZXh0PgogICAgPHRleHQgeD0iMTE1IiB5PSIxMDUiPkI8L3RleHQ+CiAgICA8dGV4dCB4PSIxNzUiIHk9IjEwNSI+QzwvdGV4dD4KICAgIDx0ZXh0IHg9IjE2MCIgeT0iMTUiPkQ8L3RleHQ+CiAgPC9zdmc+)

A–B (length) : delay (parameter1)  
B–C (length) : speed × depthB (parameter2 × parameter4)  
B–D (depth) : depthA × depthB (parameter3 × parameter4)

Supplement It is useful when you want to use the volume LFO and want to temporarily make the sustainable sound attenuation. Also, it can also be used for things like fade-in effect after trumpet's pronunciation, depending on how it is used.

Caution 1 This command will not immediately change the LFO. The LFO will receive the effect of this command after the LFO is turned on with the \* command. However, this limitation does not apply if the LFO is already turned on.

Caution 2 When this command is processed, even if an LFO switch independent of keyon is set inside a tie, the LFO used up to that point will be reset, and the next note will receive the effect of the delay value.

Example `MW0 M24,1,8,2 *1`  
Result Sets LFO 1 to be a triangle wave LFO with delay 24, speed 1, and depth 8×2.

See also

-   \#LFOSpeed command ([→§2.17.](#2-17))
-   MX MXA MXB commands ([→§9.5.](#9-5))
-   MW MWA MWB commands ([→§9.2.](#9-2))
-   \* \*A \*B commands ([→§9.3.](#9-3))

## 9.2. Software LFO Waveform Setting

``` command
MW MWA MWB
```

Format 1 `MW number`  
Format 2 `MWA number`  
Format 3 `MWB number`

Range 0–6

Sound Source FM / SSG / PCM(AD,PPZ)

Sets the LFO waveform.

MWA and MWB set the waveforms of LFOs 1 and 2 respectively. MW is identical to MWA.

Specified values are as follows. For the actual way of applying, see the comment of M MA MB commands.

0 Triangle Wave 1 (default)  
1 Sawtooth Wave  
2 Square Wave  
3 Random Wave  
4 Triangle Wave 2  
5 Triangle Wave 3  
6 One-shot

Example `MW2`  
Result From this point LFO2 will have a square wave waveform.

See also

-   M MA MB commands ([→§9.1.](#9-1))

## 9.3. Software LFO Switch

``` command
* *A *B
```

Format 1 `* number1[,number2]`  
Format 2 `*A number1[,[B] number2]`  
Format 3 `*B number1[,A number2]`

Range 0–7

Sound Source FM / SSG / PCM(AD,PPZ)

Controls on/off and keyon synchronization of software LFO.

By default, number1 affects LFO1, and number2 (optional) affects LFO2. But you can change the target by writing the symbol A or B after \*.

The meaning of the specified number is as follows:

|            |                  |                                |
|------------|------------------|--------------------------------|
| number = 0 |                  | LFO off (default)              |
| number = 1 | pitch            | LFO on, keyon synchronized     |
| number = 2 | volume           | LFO on, keyon synchronized     |
| number = 3 | pitch and volume | LFO on, keyon synchronized     |
| number = 4 |                  | LFO off                        |
| number = 5 | pitch            | LFO on, not keyon synchronized |
| number = 6 | volume           | LFO on, not keyon synchronized |
| number = 7 | pitch and volume | LFO on, not keyon synchronized |

Example 1 `*1`  
Result Turn on LFO1 targeting pitch with keyon sync. LFO2 is not affected.

Example 2 `*0,2`  
Result Turn off LFO1 and Turn on LFO2 targeting volume with keyon sync.

Example 3 `*B5`  
Result Turn on LFO1 targeting pitch with no keyon sync. LFO1 is not affected.

Caution 1 When multiplying the FM sound source by the volume LFO, the LFO change value actually applied to the TL is inverted between positive and negative. Therefore, when the LFO value is positive, the volume rises (TL value goes down). Even if you change the target slot and make it a wah-wah effect, please be careful as well.

Caution 2 The PCM(86) channel does not take a pitch LFO.

Caution 3 In the rhythm (K/R) channels, this becomes the PDR operation mode control command.

Caution 4 Both the pitch and volume LFOs use the same LFO parameters (set with the M, MA, and MB commands). When you want to use it at the same time with different parameters please use two separate LFOs.

Caution 5 When duplicate designation such as \*B1,B2 is done, the previous B1 portion is ignored and has the same meaning as \*B2.

See also

-   M MA MB commands ([→§9.1.](#9-1))
-   \* command (PDR Operation Mode Control, [→§15.2.](#15-2))

## 9.4. Software LFO Slot Setting

``` command
MM MMA MMB
```

Format 1 `MM slotnum`  
Format 2 `MMA slotnum`  
Format 3 `MMB slotnum`

Range 0–15

Sound Source FM

Only effective on the FM channels, this sets the slot number to apply the effect of the software LFO to.

For the FM channel 3, both pitch and volume LFOs are affected. While on the other FM channels, only the volume LFO is affected.

MMA sets LFO1 and MMB sets LFO2. MM is identical to MMA.

slotnum specifies the total sum of slot numbers to be affected, with slot1 = 1, slot2 = 2, slot3 = 4, and slot4 = 8.

For example, if you want to affect operators 2 and 4, you will use MM10.

If 0 is specified (default):  
For a volume LFO, it affects the carrier operators.  
For a pitch LFO, it affects all operators.

Example `MM3`  
Result The effect of LFO1 is applied to slot 1 and slot 2.

Caution If you specify a value other than 0, this value remains the same even if the instrument is changed.

## 9.5. Software LFO Speed Setting

``` command
MX MXA MXB
```

Format 1 `MX number`  
Format 2 `MXA number`  
Format 3 `MXB number`

Range 0–1 Sound Source FM / SSG / PCM(AD,PPZ)

If set to 1, change the LFO by the M MA MB commands to an extended specification that makes it constant speed independent of tempo.

MXA sets LFO1 and MXB sets LFO2. MX is identical to MXA.

If set to 0, the LFO speed is dependent on tempo. So if the tempo is slow the LFO will also be slow.

This has the same function as \#LFOSpeed, but it is possible to change it for each channels with this command. The default value is 0.

Example `MXB1`  
Result LFO2 is set to be independent of the tempo.

See also

-   \#LFOSpeed command ([→§2.17.](#2-17))
-   M MA MB commands ([→§9.1.](#9-1))

## 9.6. Dedicated Rise/Fall LFO Setting

``` command
MP MPA MPB
```

Format 1 `MP ±number1[,number2[,number3]]`  
Format 2 `MP ±number1[,l length[.][,number3]]`  
Format 3 `MPA ±number1[,number2[,number3]]`  
Format 4 `MPA ±number1[,l length[.][,number3]]`  
Format 5 `MPB ±number1[,number2[,number3]]`  
Format 6 `MPB ±number1[,l length[.][,number3]]`

|       |                                                    |
|-------|----------------------------------------------------|
| Range | (number1) -128–+127                                |
|       | (number2) 0–255                                    |
|       | (number3) 0–255                                    |
|       | (length) 1–255, divisible by the whole note length |

Sound Source FM / SSG / PCM(AD,PPZ)

Selects the rise/fall-type software LFO and turns it on.

MPA sets LFO1 and MPB sets LFO2. MP is identical to MPA.

±number1 = depth  
number2 = delay (0 if omitted)  
number3 = speed (1 if omitted)

If l is included before the delay, it will be a note length, otherwise it will be a number of clock cycles.

Actually, it is the same as `MA(or MB) number2,number3,number1,255 *1`.

Example `MP-80`  
Result Sets a falling LFO for something like a drum channel.

Caution Since this is simply a combined M and \* command, if you have selected a square wave or random wave with MW, MWA, or MWB, it will not work properly.

See also

-   M MA MB commands ([→§9.1.](#9-1))
-   \* \*A \*B commands ([→§9.3.](#9-3))
-   MW MWA MWB commands ([→§9.2.](#9-2))

## 9.7. LFO Depth Temporal Change Setting

``` command
MD MDA MDB
```

Format 1 `MD number1[,±number2[,number3]]`  
Format 2 `MDA number1[,±number2[,number3]]`  
Format 3 `MDB number1[,±number2[,number3]]`

|       |                     |
|-------|---------------------|
| Range | (number1) 0–255     |
|       | (number2) -128–+127 |
|       | (number3) 0–127     |

Sound Source FM / SSG / PCM(AD,PPZ)

Sets the temporal change of depth (depth A) of LFO.

With this, it is possible to express LFO becoming increasingly deeper. And conversely, LFO becoming increasingly shallow.

MDA sets LFO1 and MDB sets LFO2. MD is identical to MDA.

number1 = speed  
±number2 = depth (plus sign may be omitted)  
number3 = times (0 is infinite)

For each LFO speed cycle, it changes depthA according to the value of depth and repeat it for the set number of times, then stops.

Regardless of the LFO's depthA sign, the plus sign means increasing depth, and the minus sign means decreasing depth.

If number1 is 0, there is no temporal change.

number2 can be omitted only when number1 is 0. (it will be 0)

number3 will be 0 (infinite times) if omitted.

The LFO cycle will increase by one at the following timing. Since one-shot LFO has no cycles, it will not change.

1.  When the LFO change amount is 0 for triangle wave.
2.  When the LFO change amount is inverted between positive and negative for sawtooth wave and square wave.
3.  When the LFO change amount is changed for random wave.

Example 1 `MD2,1`  
Result Increases depthA by 1 every 2 LFO cycles and continues until Keyoff.

Example 2 `MD3,2,4`  
Result Increases depthA by 2 every 3 LFO cycles and repeats for 4 times.

See also

-   M MA MB commands ([→§9.1.](#9-1))

## 9.10. Hardware LFO Speed/Delay Setting

``` command
H
```

Format 1 `H number1[,number2][,number]`  
Format 2 `H number1[,number2][,l length[.]]`

|       |                                                    |
|-------|----------------------------------------------------|
| Range | (number1) 0–7                                      |
|       | (number2) 0–3                                      |
|       | (number3) 0–255                                    |
|       | (length) 1–255, divisible by the whole note length |

Sound Source FM(OPNA,OPM)

Sets PMS and AMS of hardware LFO. (OPNA/OPM FM sound source only)

number1 = PMS (pitch speed)  
number2 = AMS (volume speed)  
number3 = Delay (time to take from keyon, equivalent to \#D command)

If AMS is omitted, 0 is set. If Delay is omitted, it is not set. (previous values are retained)

It is necessary to set the depth with the \# or \## commands before starting the LFO.

Caution In OPNA, even if the hardware LFO is set to off with the \# command, increasing the AMS seems to reduce the volume of that channel. Therefore, to completely turn off the LFO when using AMS, please specify \#0H0.

Example `H6,2,l4`  
Result Sets the hardware LFO to have a PMS value of 6, an AMS value of 2, and to be delayed by a quarter note.

See also

-   \# command ([→§9.11.](#9-11))
-   \## command ([→§9.12.](#9-12))
-   \#D command ([→§9.13.](#9-13))

## 9.11. Hardware LFO Switch/Depth Setting (OPNA)

``` command
#
```

Format `# number1[,number2]`

|       |               |
|-------|---------------|
| Range | (number1) 0–1 |
|       | (number2) 0–7 |

Sound Source FM(OPNA)

Sets hardware LFO on/off. (OPNA FM sound source only)

number1 = switch (0 is off/1 is on, default is 0)  
number2 = depth (can be omitted only when switch = 0)

Each of the FM channels (A-F) share the same values.

Example `#1,6`  
Result Switches the hardware LFO on and sets the depth to 6.

See also

-   H command ([→§9.10.](#9-10))

## 9.12. Hardware LFO Frequency/Waveform/Depth Setting (OPM)

``` command
## #f #w #p #a
```

|        |                                       |
|--------|---------------------------------------|
| Format | `## number1,number2,±number3,number4` |
|        | `#f number1`                          |
|        | `#w number2`                          |
|        | `#p ±number3`                         |
|        | `#a number4`                          |
| Range  | (number1) 0–255                       |
|        | (number2) 0–3                         |
|        | (number3) -64–+63                     |
|        | (number4) 0–127                       |

Sound Source FM(OPM)

Sets hardware LFO FRQ, Waveform, PMD and AMD. (OPM FM sound source only)

number1 LFO_FRQ (frequency)  
number2 Waveform (waveform)  
±number3 PMD (pitch depth)  
number4 AMD (volume depth)

\#f is FRQ, \#w is Waveform, \#p is PMD, \#a is AMD. Each one can be specified individually.

Each of the FM channels (A–H) share the same values.

Example `##100,0,20,10`  
Result Sets the hardware LFO to have LFO_FRQ 100, Waveform 0, PMD +20, and AMD 10.

See also

-   H command ([→§9.10.](#9-10))

## 9.13. Hardware LFO Delay Setting

``` command
#D
```

Format 1 `#D number`  
Format 2 `#D l length[.]`

|       |                                                    |
|-------|----------------------------------------------------|
| Range | (number) 0–255                                     |
|       | (length) 1–255, divisible by the whole note length |

Sound Source FM(OPNA,OPM)

Sets the hardware LFO delay. This allows you to set the third parameter of the H command independently.

After keyon, temporarily set PMS/AMS to 0 until the specified time passes.

If l is included before the length, it will be a note length, otherwise it will be a number of clock cycles.

This has no meaning unless PMS and AMS are set with H command.

Example `#D24`  
Result Sets the hardware LFO to start after a quarter note length (C96 time) of time has passed.

See also

-   H command ([→§9.10.](#9-10))

# 10. MML Commands — Loop Control Section

This section summarizes commands to control the global and local loop.

Local loops are useful for reducing the MML size and compiled data size.

The global loop sets the song to loop infinitely.

## 10.1. Local loop setting

``` command
[ : ]
```

Format `[ mml1 [:] mml2 ] [number]`

Range 0–255

Sound Source FM / SSG / PCM / RSel / RDef

Sets a loop (repetition).

If the number of times to repeat is 0, it repeats indefinitely.

If omitted, the value specified by \#LoopDefault is set. It becomes 0 if \#LoopDefault is not specified.

When : is specified, it will break out of the loop at that point during the last iteration of the loop.

Example 1 `[ cde : fga ]2 b`  
Result Plays `cde fga cde b`.

Caution 1 You may nest up to 32 loops. Nesting is when you include a loop within a loop, and `[[[[[[[cde]2]2]2]2]2]2]2` has a depth of 7 nested loops, but `[[cde]2[fga]2[b>cd<]2]2` has a depth of 2 nested loops.

Caution 2 The values of the following commands will return to their values before the loop when the loop point is reached. Also, when breaking a loop, they will have the value set at the end of the loop.

|           |                               |
|-----------|-------------------------------|
| o \> \< X | — Octave Setting              |
| l         | — Default Note Length Setting |
| S         | — Grace Note Setting          |
| W         | — Pseudo Echo Setting         |
| C         | — Whole Note Length Setting   |
| \_{ }     | — Transpose Setting           |

However, the values of other commands such as the volume setting will be carried over.

Supplement If a single note is specified in MML, it is easier to understand if you consider that the compiler automatically sets five values: "pitch", "note length", "octave", "grace note" and "pseudo echo".

Example 2 `o4l8 cccc`, the compiler expands this into:  
Result `o4c8 o4c8 o4c8 o4c8`

Example 3 `o4l8 [ c o5l4c ]2`  
Result `o4c8 o5c4 o4c8 o5c4`  
The o and l commands are o5l4 when the loop ends, but when it returns to the beginning of the loop, it will return to the value of o4l8 at the start of the loop.

Example 4 `o4 [ c : >c ]2 d`  
Result `o4c o5c o4c o5d`  
At the loop break the octave is o4, but after the break it will be o5 just before the \] command.

If you think you can not understand well in the above explanation, it is always possible to set o and l immediately after the \[ and \] commands, and S and W commands when using it, so the confusion can be avoided.

Example 5 `[ o4l8 cdl4ef : gab>c ] o5l8 def`  
Result `o4l8 cdl4ef gab>c o4l8 cdl4ef o5l8 def`

See also

-   \#LoopDefault command ([→§2.13.](#2-13))

## 10.2. Global loop setting

``` command
L
```

Format `L`

Sound Source FM / SSG / PCM / RSel / RDef

Set this to return to the specified position when MML of that part is over.

If it is not specified, the playback ends.

Caution Like with a local loop, the octave, default note length, etc. are restored to the value at the position specified by L.

But conversely, any other commands will have their settings carried over from the end of the global loop, so please be careful.

As much as possible, put initialization commands immediately after the L command, to avoid having the song repeat in an unexpected way.

Incorrect Example

    A   @0 v12 cccc
    A   L cccc
        ⋮
    A   @1v10 cccc

Result On line 2, the sequence will be played once with @0v12, but at the 2nd iteration and after, it plays with @1v10.

Correct example

    A   @0 v12 cccc
    A   L @0 v12 cccc
        ⋮
    A   @1v10 cccc

Result On line 2, every repetition will play @0 v12.

In fact, if LFO settings, envelopes, transposition commands, etc. are changed after the global loop, they should also have reset commands placed immediately after the L command.

# 11. MML Commands — Tempo Setting Section

This section summarizes commands to set tempo.

## 11.1. Tempo Setting 1

``` command
t
```

Format 1 `t number`

Format 2 `t ±number`

Range 18–255

Sound Source FM / SSG / PCM / Rsel / Rdef

Sets the tempo. This is equivalent to \#Tempo, but with this command you can change the tempo during the song.

All channels share the same tempo value.

When a + or - is specified, the tempo will be changed relatively to the current value.

This will set how many times a 48 internal clock cycles will be in one minute.

In C96 (default) state, this will be equivalent to half notes. For C192, this will be equivalent to quarter notes.

Values less than 18 cannot be specified.

Example 1 `C96 t100`

Result This sets the tempo to be so that one minute is equivalent to 100 half notes of length.

Example 2 `t+10`

Result Adds 10 to the tempo value.

See also

-   \#Tempo command ([→§2.10.](#2-10))

## 11.2. Tempo setting 2

``` command
T
```

Format 1 `T number`

Format 2 `T± number`

Range 0–255

Sound Source FM / SSG / PCM / Rsel / Rdef

This sets the tempo, but unlike the t command, this sets the direct value passed to TimerB.

This is equivalent to \#Timer, but with this command you can change the tempo during the song.

All channels share the same tempo value.

When a + or - is specified, the tempo will be changed relatively to the current value.

Especially at a slow tempo, it is possible to make finer settings than the t command.

In the X68000, in order to be compatible with the OPN version, it calculates and outputs the OPM setting value using this value as the OPN setting value.

The default value is 200.

Example 1 `T180`

Result TimerB is set to a value of 180.

Example 2 `T+10`

Result Adds 10 to TimerB.

See also

-   \#Timer command ([→§2.10.](#2-10))

# 12. MML Commands — Note Processing Commands

This section summarizes grace notes, pseudo echoes and note processing commands.

It is unique to PMD, unfamiliar with other music drivers. Although these effects can be performed using other commands, if you can master it, you will be able to create more realistic sounding compositions with fewer sound channels.

## 12.1. Grace Note Setting

``` command
S
```

Format 1 `S number1[,±number2[,number3]]`

Format 2 `S l length[.][,±number2[,number3]]`

|       |                                                    |
|-------|----------------------------------------------------|
| Range | (number1) 0–255                                    |
|       | (number2) -128–+127                                |
|       | (number3) 0–1                                      |
|       | (length) 1–255, divisible by the whole note length |

Sound Source FM / SSG / PCM(AD,86,PPZ)

This automatically adds grace notes at compile time to the notes after this command on a single sound channel.

number1 = speed (0 is off)  
±number2 = depth (default is -1)  
number3 = tie flag (default is 1)

For pitches to be output, it becomes a grace note that returns to the original pitch at the set speed from the pitch shifted by depth (semitones).

If l is included before the speed, it will be a note length, otherwise it will be a number of clock cycles.

If the tie flag is 0, the sound will not be connected, similar to a glissando.

If a note length less than \|speed×depth\| is set, processing will not be performed.

Specify S0 to return to normal.

Example 1 `S2,-2e8`  
Result `d%2 & d+%2 & e%10`

Example 2 `S1,-3,0e8`  
Result `c+%1 d%1 d+%1 e%9`

Caution 1 Since this effect is added at compile time, if you use it too much, the data size will become large.

Caution 2 The l^ l= commands can not be used while using this command.

See also

-   l^ l= commands ([→§4.9.](#4-9))

## 12.2. Pseudo Echo Setting

``` command
W
```

Format 1 `W number1[,[%]±number2[,number3]]`

Format 2 `W l length[.][,[%]±number2[,number3]]`

|       |                                                    |
|-------|----------------------------------------------------|
| Range | (number1) 0–255                                    |
|       | (number2) -128–+127                                |
|       | (number3) 0–3                                      |
|       | (length) 1–255, divisible by the whole note length |

Sound Source FM / SSG / PCM(AD,86,PPZ)

After this command is used, all notes specified from it are automatically multiplied by a pseudo echo at the compile time. This is useful for when you want to apply echo but there are not enough channels.

number1 = delay (0 is off)  
±number2 = depth (default is -1)  
number3 = continuation/tie flag (default is 0)

After keyon, when the delay has passed, it does keyoff (don't do keyoff if a tie flag is set), increases/decreases the volume by depth, then does keyon again. If the continuation flag is set, it repeats as long as the note length permits.

If l is included before the delay, it will be a note length, otherwise it will be a number of clock cycles.

After Keyoff, it returns to the original volume.

Continuation/tie flags:  
0: Continuation/no tie  
1: Continuation/with tie  
2: One time/no tie  
3: One time/with tie

For the depth, if % is not specified, it will be equivalent to a v command level, otherwise it will be equivalent to a V command level.

If a note length less than delay is set, processing will not be performed.

Specify W0 to return to normal.

Example 1 `W8,-2a4`  
Result `a%8 (^2 a%8 (^4 a%8`

Example 2 `W12,-2,3a2`  
Result `a%12& (^2 a%36`

Example 3 `W12,%-3,1a2`  
Result `a%12 (^%3 a%12 (^%6 a%12 (^%9 a%12`

Caution 1 Like the S command, since this effect is added at compile time, if you use it too much, the data size will become large.

Caution 2 If you attach a % to set a fine value, the range of the volume change will be -128–+127. Because the PCM volume has a range of 0–255, you cannot have a volume change from the current volume greater than +127 or less than -128.

Caution 3 The l^ l= commands can not be used while using this command.

See also

-   l^ l= commands ([→§4.9.](#4-9))

## 12.3. Keyon Delay Per Slot Setting

``` command
sk
```

Format 1 `sk number1[,number2]`

Format 2 `sk number1[,l length[.]]`

|       |                                                    |
|-------|----------------------------------------------------|
| Range | (number1) 0–15                                     |
|       | (number2) 0–255                                    |
|       | (length) 1–255, divisible by the whole note length |

Sound Source FM

This command may only be used on the FM channels. It delays the keyon of specified slots.

number1 = slot number  
number2 = delay

The slot number specifies the total sum of slot numbers to delay keyon, with slot1 = 1, slot2 = 2, slot3 = 4, and slot4 = 8.

If l is included before the delay, it will be a note length, otherwise it will be a number of clock cycles.

number2 (note length) can be omitted only when number1 is 0.

Example `sk12,l8`  
Result After this command, slot 3 and 4 will have keyon delayed by an eighth note length.

Caution If a note has a length shorter than the set delay value, the keyon of the delayed slots will not be done.

## 12.4. Broken Chord Setting

``` command
{{ }}
```

Format `{{ pitch1[pitch2..pitch16] }} [length1][.][,length2[,number1[,number2[,±number3]]]]`

Range



(length1) 1–255, whole-note length divisor([→§2.11.](#2-11)) or clock value attached by %

(length2) Same as above, shorter than length1

(number1) 0–1

(number2) 0–255, shorter than length1/td\>

(number3) -128–+127

Sound Source FM / SSG / PCM(AD,PPZ)

Expands a chord with the duration of length1 before the compilation using the pitches listed in {{}}

length1 = total length  
length2 = note length (defaults to %1)  
number1 = tie flag (0 = off, 1 = on (default))  
number2 = gate time (defaults to 0)  
number3 = volume adjustment per one round (V command level, defaults to ±0)

The note length and dots are the same as c d e f g a b r commands. You cannot specify a length longer than 255 steps. Please specify only c d e f g a b o \> \< commands inside the {{ }}

The tie flag indicates whether to add a tie (&) after each note. The gate time is the specified clock value to treat the end portion as a rest. And the volume adjustment is the volume change each time the pitches goes around.

If you turn off the tie and set length2 to a reasonable length, things like playing arpeggios are also possible. However, please note that the sound will be cut off when the duration is length1(-number2)

Caution 1 If the volume adjustment takes place, the changed volume will remain after this command. You need to redefine the volume as needed to produce the next note.

Caution 2 The effects of the W S commands are not reflected in this command.

Example 1 `{{cg}}4`  
Result A quarter note length broken chord that switches between do and sol at high speed (1 clock).

Example 2 `{{ceg>c<}}4,32,0`  
Result Equivalent to `[c32e32g32>c32<]2`.

# 13. MML Commands — Pan Setting Commands

This section summarizes commands to set sound output position (pan).

However, for OPN and SSG, these commands will have no effect because the sound source itself is monaural.

## 13.1. Pan setting 1

``` command
p
```

Format `p number`

Range 0–3

Sound Source FM(OPNA,OPM) / PCM

Sets the sound output position (pan).

The settings are listed below:

|                       |     |                  |
|-----------------------|-----|------------------|
| FM(OPNA), PCM(AD,PPZ) | 1   | right            |
|                       | 2   | left             |
|                       | 3   | center (default) |
| FM(OPM), PCM(68)      | 1   | left             |
|                       | 2   | right            |
|                       | 3   | center (default) |
| PCM(86)               | 1   | right            |
|                       | 2   | left             |
|                       | 3   | center (default) |
|                       | 0   | reverse phase    |

Supplement The reverse phase switches the left-right phases. As an effect, it gives a feeling that it sounds behind the usual performance. This effect can be heard especially when using headphones.

## 13.2. Pan Setting 2

``` command
px
```

Format `px ±number1[,number2]`

|       |                     |
|-------|---------------------|
| Range | (number1) -128–+127 |
|       | (number2) 0–1       |

Sound Source FM(OPNA,OPM) / PCM

Sets the sound output position (pan) as well as setting in-phase/reverse-phase.

Fine designation is possible only when used in PCM(86,PPZ) channels.

|                   |         |         |               |                                    |
|-------------------|---------|---------|---------------|------------------------------------|
| FM(OPNA), PCM(AD) | number1 | -128–-1 | right         | (constant regardless of the value) |
|                   |         | +1–+127 | left          | (constant regardless of the value) |
|                   |         | 0       | center        | (default)                          |
| FM(OPM), PCM(68)  | number1 | -128–-1 | left          | (constant regardless of the value) |
|                   |         | +1–+127 | right         | (constant regardless of the value) |
|                   |         | 0       | center        | (default)                          |
| PCM(86)           | number1 | -128–-1 | rightwards    |                                    |
|                   |         | +1–+127 | leftwards     |                                    |
|                   |         | 0       | center        | (default)                          |
|                   | number2 | 0       | in phase      |                                    |
|                   |         | 1       | reverse phase |                                    |
| PCM(PPZ)          | number1 | -128–-4 | left          | (constant regardless of the value) |
|                   |         | -3–-1   | leftwards     |                                    |
|                   |         | +1–+3   | rightwards    |                                    |
|                   |         | +4–+127 | right         | (constant regardless of the value) |
|                   |         | 0       | center        | (default)                          |

# 14. MML Commands — Rhythm Sound Source Commands

This section summarizes commands to control the rhythm sound source that can be used in YM2608.

Although it is possible to specify it to any parts, there is no direct influence on the performance of that part.

Usually, it will become easier to understand if you write the rhythm at the same time on the part that plays the rhythm. If you play the rhythm only with rhythm sound source, it is better to use the SSG rhythm channels for this. ([→§1.2.2.](#1-2-2))

## 14.1. Rhythm Sound Source Shot/Dump Control

``` command
\b \s \c \h \t \i \bp \sp \cp \hp \tp \ip
```

Format 1 `\b[p]`  
Format 2 `\s[p]`  
Format 3 `\c[p]`  
Format 4 `\h[p]`  
Format 5 `\t[p]`  
Format 6 `\i[p]`

Sound Source FM(OPNA) / SSG / PCM(AD,86,PPZ) / Rsel / Rdef

Outputs/stops each sound in the rhythm sound channels. Each command's corresponding rhythm sound is listed below.

|     |            |                           |
|-----|------------|---------------------------|
| b   | Bass Drum  |                           |
| s   | Snare Drum |                           |
| c   | Cymbal     |                           |
| h   | Hi-Hat     |                           |
| t   | Tom        |                           |
| i   | Rim Shot   | (notice that it is not r) |

With p, the sound stops (dumps).

If you want to output them at the same time, please specify it like `\s\t\i`.

Example 1 `\b\s`  
Result The bass drum and snare drum play simultaneously.

Example 2 `\cp`  
Result The cymbal sound is cut.

Caution 1 When used before the p and px (pan) commands, for example, `\bp3`, it will be treated as `\bp 3` and an error will occur. Please set them apart like `\b p3`.

Caution 2 Due to the specification of OPNA, when outputting the rhythm sound source SHOT/DUMP consecutively, a considerably large wait is required between outputs.

In PMD, it deals with this issue by inserting an appropriate wait time only when consecutive \\ commands are used. But if there are commands that do not have a note length (q, v, etc.) in between those that output continuously, the necessary waits will not be entered and may not be played properly.

Especially, if there are other rhythm sound dump commands after shot, it seems that this problem will become obvious, so please be careful.

Example 3

    I   [\h \cp r32 ]0

Result PMD automatically inserts the wait and the hi-hat is outputted normally in 32nd note beats.

Example 4

    I   [\h q0 \cp r32 ]0

Result Since no wait is inserted, the output of the hi-hat may become abnormal in some cases.

## 14.2. Rhythm Sound Source Master Volume Setting

``` command
\V
```

Format `\V [±]number`

Range 0–63

Sound Source FM(OPNA) / SSG / PCM(AD,86,PPZ) / Rsel / Rdef

Sets the master volume of the rhythm sound source.

When a + or - is specified, the volume will be changed relatively to the previous volume.

The volume range is 0–63 and the default is 48.

Range `\V63`

Result The rhythm sound source's volume is set to the maximum.

## 14.3. Rhythm Sound Source Individual Volume Setting

``` command
\vb \vs \vc \vh \vt \vi
```

|        |                 |
|--------|-----------------|
| Format | `\vb [±]number` |
|        | `\vs [±]number` |
|        | `\vc [±]number` |
|        | `\vh [±]number` |
|        | `\vt [±]number` |
|        | `\vi [±]number` |

Range 0–31

Sound Source FM(OPNA) / SSG / PCM(AD,86,PPZ) / Rsel / Rdef

Sets the volume for individual rhythm channels. When a + or - is specified, it will be changed relatively to the previous volume.

The next letter of \\v represents the corresponding rhythm sound similar to shot/dump control.

Example 1 `\vb25`

Result Sets the bass drum volume to 25.

Example 2 `\vs+2`

Result Adds 2 to the snare drum volume.

## 14.4. Rhythm Sound Source Output Position Setting

``` command
\lb \ls \lc \lh \lt \li \mb \ms \mc \mh \mt \mi \rb \rs \rc \rh \rt \ri
```

|        |       |       |       |
|--------|-------|-------|-------|
| Format | `\lb` | `\mb` | `\rb` |
|        | `\ls` | `\ms` | `\rs` |
|        | `\lc` | `\mc` | `\rc` |
|        | `\lh` | `\mh` | `\rh` |
|        | `\lt` | `\mt` | `\rt` |
|        | `\li` | `\mi` | `\ri` |

Sound Source FM(OPNA) / SSG / PCM(AD,86,PPZ) / Rsel / Rdef

Sets each output position of the rhythm sound source.

The next character of \\ represents the output position, as listed below:

|     |        |
|-----|--------|
| l   | Left   |
| r   | Right  |
| m   | Center |

The next letter represents the corresponding rhythm sound similar to shot / dump control.

Example `\lh`

Result Sets the hi-hat to output to the left side.

# 15. MML Commands — FM Chip/Driver Control

This section summarizes the commands that directly control the driver such as FM chip, PMD, PDR.

Although it is rare to use it, please be careful when using it since you often need sufficient knowledge on how to use them.

## 15.1. FM Chip Direct Output

``` command
y
```

Format `y number1,number2`

|       |                 |
|-------|-----------------|
| Range | (number1) 0–255 |
|       | (number2) 0–255 |

Channels FM / SSG / PCM / Rsel / Rdef

Specify the value to be outputted to the FM chip as it is.

Outputs number2 as data to the register specified by the number1.

For OPNA, channels D, E, and F will output to the rear port, but the other channels will output to the front port.

Example `y$58,7`  
Result Sets the attack rate of slot 2 of FM channel 1 to 7.

Caution 1 Since this is dangerous if you do not have enough knowledge of the FM chip, please avoid using it.

Caution 2 While this makes it possible to finely set FM instrument parameters, keep in mind that after returning from a pause, sound effects, or channel masking, the FM instrument will be redefined and return to normal.

When changing FB and TL values, only use the FB and O commands. That way you can avoid that kind of phenomenon.

See also

-   FB Command ([→§6.4.](#6-4))
-   O Command ([→§6.3.](#6-3))

## 15.2. PDR Operation Mode Control

``` command
*
```

Format `* number`

Range 0–5

Sound Source Rsel / Rdef

Used in the K/R channels to control the PDR operation mode.

|     |                     |
|-----|---------------------|
| n=0 | Double mode setting |
| n=1 | Single mode setting |
| n=2 | 16KHz mode setting  |
| n=3 | 8KHz mode setting   |
| n=4 | EI mode setting     |
| n=5 | DI mode setting     |

Example `*0`  
Result Sets the PDR to double mode.

Caution 1 In PDR control, normally, please do not use anything other than 0 or 1. There is the danger of hanging up on the spot especially when using \*2 with PDR resident on a slower model.

Caution 2 It has the same command name as software LFO switch and they are identified by the specified channel. Be careful not to confuse them.

See also

-   \* command (software LFO switch) ([→§9.3.](#9-3))

## 15.3. Fade Out Setting

``` command
F
```

Format `F number`

Range 0–127

Sound Source FM / SSG / PCM / Rsel / Rdef

Fades out from the specified position.

The number sets the speed. 1 is the slowest speed and 127 is the fastest speed.

Example `F16`  
Result Fades out at speed 16.

## 15.4. Individual Sound Source Volume Down Setting

``` command
DF DS DP DR
```

Format 1 `DF [±]number`  
Format 2 `DS [±]number`  
Format 3 `DP [±]number`  
Format 4 `DR [±]number`

|       |                    |
|-------|--------------------|
| Range | (without ±) 0–255  |
|       | (with ±) -128–+127 |

Sound Source FM / SSG / PCM / Rsel / Rdef

Changes an individual sound source's volume down.

DF is for FM sound source, DS is for SSG sound source, DP is for PCM sound source, DR is for the Rhythm sound source.

When a + or - is added to the number, it will be changed relatively to the current value. Please note that the volume drops with +.

However, if +0 or -0 is specified, it is reinitialized to the value specified by PMD option.

Example

      G [cdefgab>c< DS+16]8

Result For each loop iteration, all SSG channels will gradually drop in volume.

Caution The volume down values set here are local to the track in which they are used. When another track is played, the PMD options /DF, /DS, /DP, and /DR will be reset and return to normal.

See also

-   \#VolumeDown command ([→§2.22.](#2-22))
-   PMD /DF /DS /DP /DR options (→PMD.DOC)

## 15.5. FM Sound Effect Playback

``` command
N
```

Format `N number`

Range 0–255

Sound Source FM / SSG / PCM / Rsel / Rdef

Plays back an FM sound effect. If 0 is set it stops playback.

Caution While an FM sound effect can be defined as number 0, number 0 cannot be played back in MML.

Example `N4`  
Result Plays back FM sound effect 4.

## 15.6. SSG Sound Effect Playback

``` command
n
```

Format `n number`

Range 0–255

Sound Source FM / SSG / PCM / Rsel / Rdef

Plays back an SSG sound effect. If 0 is set it stops playback.

When PDR and PPSDRV are resident, 1–127 plays an SSG sound effect and 128–255 plays an SSGPCM sound effect. (value added by 128)

Example `n15`  
Result Plays back SSG sound effect 15.

## 15.7. Channel Mask Control

``` command
m
```

Format `m number`

Range 0–1

Sound Source FM / SSG / PCM / Rsel / Rdef

Sets the channel mask to on or off.

|         |                         |
|---------|-------------------------|
| 0 = off | (channel plays)         |
| 1 = on  | (channel does not play) |

Usually there is no reason to use this.

Example `m1`  
Result Masks this part.

## 15.8. Measure Length Setting

``` command
Z
```

Format `Z number`

Range 0–255

Sound Source FM / SSG / PCM / Rsel / Rdef

Sets the measure length. Has no influence on the sound at all.

When incorporating PMD into things like games, programmers can get the measure number currently being played so that they can be processed according to it with visuals, etc. However, because there is no concept of measures in MML, if you are using 3 or irregular time signatures, you cannot get accurate values unless the measure length is known.

This command always tells the driver the measure length and making it possible to return accurate values, programmers will be able to get them.

The default value is 96.

Example `Z72`  
Result After this it tells the driver that the song is in 3/4 time signature.

Caution If you change the time signature during a track, always change the measure length at the beginning of the measure.

Supplement Taking this function to the opposite, if you let the driver decide, for example, that a quarter note is one measure, synchronization in quarter note units becomes possible.

## 15.9. Write to Status1

``` command
~
```

Format 1 `~ number`  
Format 2 `~ ±number`

|       |                    |
|-------|--------------------|
| Range | Format 1 0–255     |
|       | Format 2 -128–+127 |

Sound Source FM / SSG / PCM / Rsel / Rdef

Writes a number to Status1. (programmers can get this through the driver)

When a + or - is included (Format 2), it adds/subtracts to the current number in Status1.

Caution The possible range of Status1 is 0–255. Since the check is not done when it exceeds this value, for example, if -1 is set from 0, the Status1 will become 255.

Example `~2`  
Result Writes 2 to Status1.

## 15.10. PCM Method Selection

``` command
A
```

Format `A number`

Range 0–1

Sound Source FM / SSG / PCM / Rsel / Rdef

This is effective when you play in PMD86.

Changes the PCM channel method to:

|     |                                                                         |
|-----|-------------------------------------------------------------------------|
| 0   | PMD86 normal method                                                     |
| 1   | PMDB2 compatibility method (volume and loop specifications will change) |

It is almost the same as PMD86's /s option, but here it is a local change and if you play a different song it returns to original.

Example `A1`  
Result Matches the PCM method to the ADPCM method.

See also

-   \#ADPCM command ([→§2.23.](#2-23))

# 16. MML Commands — Compiler Control

This section summarizes various control commands at compile time.

## 16.1. Defined Variable Utilization

``` command
!
```

Format 1 `! characterstring`  
Format 2 `! number`

Character String Any character type or number of characters. Determined from the beginning up to 30 half-width characters.

Range 0–255

Sound Source FM / SSG / PCM / Rsel / Rdef

Paste the MML character string of the variable defined by the specified character string or numerical value to the specified place.

Caution 1 It is safer to avoid variable designation such as "!b" and "!bc" where one variable name is another variable name + characters as much as possible.

For example, when two MML variables "!b" and "!bc" are defined, it is very difficult to understand whether it is "!b cc" or "!bc c" if MML sequence "!bcc" comes.

If MML like that is used, the one with the longest variable name ("!bc" in this case) is used. (searches in "!bcc", "!bc", "!b" order)

If you want to use !b in this state, you can insert space or tab after the variable name like "!b cc". (see Example 1)

Caution 2 If you want to write numbers (l= command with l= omitted) after `! number`, space or tab is required between them.

Caution 3 Even when referring to a variable with a name longer than 30 half-width characters, space or tab is always required after the name. (since it is not defined any further, it is impossible to judge where the variable ends)

Example 1

    !b  @0
    !bc @1
    !s  @2
    A   !bcc !sg !bc

Result `@1 c @2g @1`

Example 1'

    !b  @0
    !bc @1
    !s  @2
    A   !b cc !s g !b c

Result `@0 cc @2 g @0 c`

For details, please refer to MML Variable Definition. ([→§3.2.](#3-2))

See also

-   ! command (MML Variable Definition) ([→§3.2.](#3-2))

## 16.2. MML Skip Control 1

``` command
"
```

Format `"`

Sound Source FM / SSG / PCM / Rsel / Rdef or the beginning of a line

Commands with note length are skipped until the next " command or until a ' command is found.

When a " command has already been specified", skipping will be terminated.

At the same time, m command is issued, and skipping is done by channel masking so that it is skipped at high speed.

This command can be written either in a channel or at the beginning of a line.

Example 1

    A   "@0v13o3 cdefgab >@1 cdefgab " >c

Result

    A   m1 @0v13 o3 > @1 m0 >c

  
Only c,d,e,f,g,a,b in double quotes are skipped.

Example 2

    "   ; start skip
    A   @0 v13 o5 cde
    B   @1 v13 o4 ccc
    "   ; cancel skip
    A   gfd
    B   <ggg>

Result

    A   @0 v13 o5  gfd
    B   @1 v13 o4 <ggg>

## 16.3. MML Skip Control 2

``` command
'
```

Format `'`

Sound Source FM / SSG / PCM / Rsel / Rdef or the beginning of a line

Forcibly terminate the MML skip state.

At the same time, issue the m0 command.

This command can be written either in a channel or at the beginning of a line.

Example 1

    A   " t80 v12 @10 cder ' def

Result

    A     t80 v12 @10        def

Example 2

    "
    A   cde
    B   efg
    '
    A   fga
    B   ab>c

Result

    A   fga
    B   ab>c

## 16.4. Part Limit Setting

``` command
| |!
```

Format 1 `| [symbol[symbol...]] mml`  
Format 2 `|! [symbol[symbol...]] mml`

Sound Sources FM / SSG / PCM / Rsel / Rdef

It is effective when specifying more than one channel at the beginning of the line, and limits the parts compiled from there.

When ! is added, it is limited to parts other than the specified part.

Between the channel symbols and mml, you must always have at least one space or tab as a delimiter.

For the compiler's operation, if the channel being compiled is not specified (or specified in case of !), it will skip the MML until the end of the next \| command or line.

If there is no character after \|, it will cancel all limited states.

Example

    ABC @12v11o4l2 |A D0ccd |B D3efg |C D-3gab |!C >c& |C g4e4 | c

Result

    A   @12v11o4l2 D0 ccd >c&  c
    B   @12v11o4l2 D3 efg >c&  c
    C   @12v11o4l2 D-3gab g4e4 c

## 16.5. Compilation End

``` command
/
```

Format `/`

Sound Source FM / SSG / PCM / Rsel / Rdef

Stops the compilation for that part.

Example

    A   cde /
    A   fga

Result

    A   cde

## 16.6. Comment Setting

``` command
;
```

Format `;`

Sound Source FM / SSG / PCM / Rsel / Rdef

Stops the compilation for that line and ignore the rest as comments.

Example

    A   cde ; comment
    A   fga

Result

    A   cde
    A   fga

## 16.7. Comment Setting 2

``` command
`
```

Format `` ` ``

Sound Source FM / SSG / PCM / Rsel / Rdef Or the beginning of a line

Once specified, ignore all MML in that interval as comments until it is specified once again.

If it is written at the beginning of a line, the flag of whether it is a comment is inverted in all parts. Also, various \# @ ! definition commands in between are ignored.

Make sure to have it inside MML or at the beginning of the line.

This is useful for when you want to write a documentation in MML, or when you want to write comments between an MML sequence.

Example 1

    A   l4cde ` this is a comment
    A   this is also a comment ` cde

Result The text between the \`s becomes a comment.

Example 2

    !A  cdefg
    `
    #Detune Extend
    `

Result Variable !A is defined, but the line with \#Detune Extend is ignored.

Caution 1 Even if you set this between MML on a particular channel, it has no effect on other channels.

Example 3

    `
    G   cde   fga ` b
    H   cde ` fga   b

Result Channel G up to a and channel H up to e are comments and will be ignored.

Caution 2 It is only possible within channel MML to write this command somewhere other than the beginning of the line. If you want the whole text to be comments, please always write this at the beginning of the line.

Example 4

    `   Comment     `

In the above example, the second \` is ignored, and all subsequent MML will be skipped.

It must be written like this:

    `   Comment
    `

# 17. Producer Contact/Inquiries

梶原　正裕 (Masahiro Kajihara / KAJA)

|         |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
|---------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Mail    | : ![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAJEAAAAPCAYAAADktC0QAAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAC4jAAAuIwF4pT92AAAE3UlEQVRo3u2ZW2xUVRSGP8S2XmihHYhXjNwUIoKEkABi1cR4QXgxEpsQUND6gEWjokZDE0CiDXiLN15UIiaQyC1BkHg3gKBSUwpolKqkOlUbLi1QOpYK48t/kuX2zJxz5kzMNHa9zNn7rLX3Xv/+z9pr7QE4DCwknuRjjP9SbgLWAM1AF3AEqAeeAsoLbK0utgWH9Vl5Gqca2NADyHMesBp4BdghMpUBQ4GHgdFAIzCugNbcI7DtaVEkVzkb2AmsBEqy6NUAB0Wu3v3KMRJdrxB/v9qDgXeBVuBP4AfggQDHwtgcBx4BXtZxchLYCCSMTgmwHPgVOKXj51mgyOi0AvOAWuAPjbsZuMCZbxHQCcwFTgOLgSTQoehUCXwDrBCJZhnbSzRmJ9CiqLVUftl11ADPA+3yqRYo1dHZIT/mRMQpKmmKhNlvQArYr2gWFdNIvthFjpDBUjPge8BuYAxwKbAASAPTszgaxuYI8AuwBBgGTFPfOqPzlvqmAxcCdwDHgBeNThLYCzwDXCEyHAZeMzplwAkdWwDviDBXC5glwO/ALr2fC2wx9p+JWJO08WuAJm2QXce3+jCGA8vk81Zgtvre1saWx8A2iFSvi0DTNGe1CHp7REwj+eItKgEc0MsgaQZejfi1+NnUOzq1QDdwPjAQ+At4wtFZpi+h2Di809FZCXxt2vcCn+q5UqBe5ti0GSArRUy0uWmB58m5wCEfEn1i2gNl96bpu0Z9E2Ngmw3r/s4p4koUTEP74h1nxUreksB9IUjUooGjiJ/NdqfdqNxlmL7OviY6eLJbJBth+r5ydI46VdY4JdIAdwEfKwp60kfz7jLHfLeeR+m3weingG0+PjY6kTZTX/88Y+vJWO1lQ4b3UTAN7YtHooeAKcAgTWJlArBJzqUE7qQAZ8LaHHPaHaaKKjMRwkq7fktN30lHJy1iYKJJUs/Dge8d/SlAP0PGkcBPeu7nrM2TQz7+dDpryNTXJwa22aTMZ06/92EwDe2LR6LvgPEK8XVGsQL4ADgD3AAMUAL2ZRZHotgMcNrehp0wBCv3Gd+PgNmk24TqlEhqo9BCkaRZfTOA940+jg1OAZCL5IJtkBwPWFs+Mf1XdbYF2APMBx4EbjbHQLku4Zp03lYAV2UZM4rNBJ9w26UosEebP9nRmShnmyL4edDM/7mSyTFKtFcJ/NMiSg1wkSo2zDyjzXjnKG+KI7lgGyR7hdl1Gd7nE9OMJf4qYL0S04S+zDRQpZL5WlU2DcDlzpFhE8OwNkOAx1VC36hjda0S3zatYwEwVZVElaqNl5QghpUNwJ0K1ytUrm8ToepVjR1QaXsbcIvKXwyhFylaDwbeUIIbR3LB1k/qDBbtKowek7+jgHt0DM3MM6ZZ7yESKhHXqz1f+URKVdB4Ad0G7MswRlibxc490VrniCtW5dCiL+hn4EkH4KRzJQHwHPCj07dJdzJFATfafknvlUrMuxTVqlVK1wesI+0UKl6ld2sMbN12nbP5JcALujPz7p4ezQOmQb7ElqMKy4V881phIk8VcLEIlVBOslzAz8xAoqFO34cifa/ElFLlBmecm9hCvb7vC9wNfKRoe0pR8AvgaV1W+slmRbbJKj7myeepvRSIL7MU4rcT/b+mnvSfXYVyjVYdu43882+R/7X8DclEtpKj2hMUAAAAAElFTkSuQmCC) |
| Website | : <http://www5.airnet.ne.jp/kajapon/>                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| (alt)   | : <https://sites.google.com/site/kajapon/>                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| Twitter | : <https://twitter.com/kajaponn>                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| YouTube | : <https://www.youtube.com/channel/UC3Ytls4c0n_OpFFQQDXFYhA>                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |



------------------------------------------------------------------------

*End of PMDMML.MAN*


