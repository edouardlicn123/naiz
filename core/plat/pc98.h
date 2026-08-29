#ifndef PC98_H
#define PC98_H

#ifndef HAL_BUILD_ALLOWED
#error "plat/pc98.h is platform-internal. Use hal.h instead."
#endif

/*
 * pc98.h — PC-98 硬件寄存器与常量定义（仅活跃符号）
 *
 * 本节仅保留被平台层（plat/）实际引用的符号。
 * 完整的参考定义见文件底部 `#ifdef PC98_FULL_REFERENCE` 块。
 *
 * 参考：
 *   docs/refdocs/ — PC-98 硬件参考文档分类索引
 *   devdocs/0.1版开发文档总结.html#doc-09 — VRAM 调查
 *   devdocs/0.1版开发文档总结.html#doc-19 — NP2kai 平台差异
 */

/*
 * uPD8251 串口（COM1, 9600 8N1）
 * ================================
 * PC-98 第一串口使用 uPD8251 USART。
 * STATUS/MODE/CMD 共用同一端口 0x32，不同上下文含义不同。
 *
 * 端口映射：
 *   0x30 — 数据寄存器（SERIAL_DATA）
 *   0x32 — 状态（读）/ 命令（写） / 模式（写，需先复位）
 */
#define SERIAL_DATA   0x30   /* 收发数据 */
#define SERIAL_STATUS 0x32   /* 读：状态寄存器 */
#define SERIAL_CMD    0x32   /* 写：命令寄存器 */

#define SERIAL_RXRDY  0x02   /* bit 1：接收器就绪 */

#define SERIAL_CMD_RESET  0x40  /* 软件复位命令 */
#define SERIAL_CMD_RTS    0x20  /* 请求发送（RTS） */
#define SERIAL_CMD_DTR    0x02  /* 数据终端就绪（DTR） */
#define SERIAL_CMD_RXEN   0x04  /* 接收使能 */
#define SERIAL_CMD_TXEN   0x01  /* 发送使能 */

#define SERIAL_MODE_8N1   0x4E  /* 9600 baud 模式寄存器值：1× 时钟，8 数据，无校验，1 停止 */

/*
 * PEGC（256 色）VRAM 访问 MMIO
 * ==============================
 * PEGC（PC-9801 Enhanced Graphics Charger）是 PC-98 的 256 色扩展。
 * VRAM 通过 bank 窗口（0xA8000-0xAFFFF）而非平面直接访问。
 *
 * MMIO 端口：
 *   0xE0004 — Bank 选择寄存器（word，0-7）
 *   0xE0100 — PEGC 模式控制寄存器
 *   0xE0102 — VRAM 窗口使能寄存器
 */
#define PEGC_BANK_PORT  ((volatile uint16_t *)0xE0004L)   /* VRAM bank 选择 */
#define PEGC_MODE_PORT  ((volatile uint16_t *)0xE0100L)   /* PEGC 模式控制 */
#define PEGC_VRAM_ENABLE ((volatile uint16_t *)0xE0102L)  /* VRAM 窗口使能 */

/*
 * I/O 端口访问内联包装（基于 Open Watcom conio.h）
 * ==================================================
 * 封装 Open Watcom 的 inp()/outp() 系列，提供更清晰的命名。
 */
#include <conio.h>

static inline void outb(unsigned short port, unsigned char val) { outp(port, val); }
static inline unsigned char inb(unsigned short port)             { return (unsigned char)inp(port); }

/*
 * 8255 PPI 鼠标接口
 * ====================
 * PC-98 板载 8255 PPI 连接鼠标，通过 4 步握手读取相对位移。
 * 详见 devdocs/0.1版开发文档总结.html#doc-44。
 */
#define MOUSE_PORT_DATA   0x7FD9   /* 读：按钮状态(bit7-6) + 数据半字节(bit3-0) */
#define MOUSE_PORT_CTRL   0x7FDD   /* 写：控制 HC(7)/SX(6)/SH(5)/IN(4) */
#define MOUSE_PORT_MODE   0x7FDF   /* 写：8255 模式设置 */

#define MOUSE_HC  0x80   /* Handshake Clock 上升沿锁存计数器 */
#define MOUSE_SX  0x40   /* Select X/Y (0=X, 1=Y) */
#define MOUSE_SH  0x20   /* Select High/Low nibble (0=low, 1=high) */
#define MOUSE_IN  0x10   /* Interrupt enable */

/*
 * ============================================================================
 * 以下为完整的 PC-98 硬件参考定义。所有符号无条件可用。
 * 新代码优先使用本头文件中的命名常量，而非直接书写魔数。
 * REVIEWED: 部分常量当前未被引用，但作为完整参考故意保留。
 * ============================================================================
 */

/*
 * GDC（μPD7220）端口地址
 * ========================
 * PC-98 使用两套 GDC：图形 GDC（主显示器）和文本 GDC（字符叠加层）。
 * 每套 GDC 有参数端口（写入参数/读取状态）和命令端口。
 */
#define GDC_GFX_PARAM    0xA0   /* 图形 GDC 参数 / 状态 */
#define GDC_GFX_CMD      0xA2   /* 图形 GDC 命令 */
#define GDC_TEXT_PARAM   0x60   /* 文本 GDC 参数 / 状态 */
#define GDC_TEXT_CMD     0x62   /* 文本 GDC 命令 */

/*
 * GDC mode 1（显示控制）
 */
#define GDC_MODE1_MONOCHROME     0x02   /* 单色模式 */
#define GDC_MODE1_COLOUR         0x03   /* 彩色模式 */
#define GDC_MODE1_LINEDOUBLE_ON  0x09   /* 行加倍（垂直放大） */
#define GDC_MODE1_LINEDOUBLE_OFF 0x08   /* 行加倍关闭 */
#define GDC_MODE1_DISPLAY_ON     0x0F   /* 显示 ON（VSYNC 同步） */
#define GDC_MODE1_DISPLAY_OFF    0x0E   /* 显示 OFF */
#define GDC_MODE1_DISPENABLE     0x80   /* bit 7：显示使能总开关 */

/*
 * GDC mode 2（色深）
 */
#define GDC_MODE2_16COLOURS      0x01   /* 16 色模式 */
#define GDC_MODE2_8COLOURS       0x00   /* 8 色模式 */

/*
 * GDC 命令（通过命令端口写入）
 */
#define GDC_CMD_START        0x0D   /* 启动屏幕刷新 */
#define GDC_CMD_STOP         0x0C   /* 停止屏幕刷新 */
#define GDC_CMD_SCROLL(s)    (0x70 | ((s) & 0xF))  /* 滚动屏幕（s 为滚动量） */
#define GDC_CMD_CSRFORM      0x4B   /* 光标形状设置 */
#define GDC_CMD_PITCH         0x47  /* 显示间距（每行扫描线字数） */
#define GDC_CMD_SYNC_OFF      0x0E  /* 同步关闭 */
#define GDC_CMD_SYNC_ON       0x0F  /* 同步开启 */
#define GDC_CMD_ZOOM          0x46  /* 显示缩放因子 */

/*
 * GDC 调色板端口（16 色与 PEGC 256 色共用）
 */
#define GDC_PALETTE_PORT    0xA8   /* 调色板索引端口 */
#define GDC_BORDER_PORT     0xA9   /* 边框颜色寄存器 */
#define GDC_PALETTE_BLUE     0x04  /* bit 2：蓝色分量 */
#define GDC_PALETTE_RED      0x02  /* bit 1：红色分量 */
#define GDC_PALETTE_GREEN    0x01  /* bit 0：绿色分量 */

/*
 * GDC 显示区域控制
 */
#define GDC_DISP_TOP_ADDR   0xA4   /* R03：显示起始地址（按 word 偏移） */

/*
 * GDC 状态标志（从参数端口读取）
 * 位定义来源：docs/refdocs/C01_display_system.md §状态寄存器（读 60h/A0h）
 *   bit5=VSYNC 垂直同步, bit2=FIFO EMPTY
 */
#define GDC_SYNC_NOCHAR      0x02  /* bit 1：字符模式未同步 */
#define GDC_VSYNC            0x20  /* bit 5：垂直同步（VSYNC 期间为 1） */

/*
 * VRAM 平面地址（物理地址）
 * ==========================
 * PC-98 GDC 将视频内存分为 4 个位平面：
 *   平面 0: 0xA8000 — 通常用于蓝色/第 0 位平面
 *   平面 1: 0xA9000 — 红色/第 1 位平面
 *   平面 2: 0xAA000 — 绿色/第 2 位平面
 *   平面 3: 0xAB000 — 亮度/第 3 位平面（16 色模式下）
 *
 * PEGC 256 色 packed-pixel 模式下通过 bank 窗口（0xA8000）访问，
 * 平面地址仅用于 vram.c 的 DPMI 映射。
 */
#define VRAM_PLANE0  0xA8000UL   /* 平面 0 物理基址 */
#define VRAM_PLANE1  0xA9000UL   /* 平面 1 物理基址 */
#define VRAM_PLANE2  0xAA000UL   /* 平面 2 物理基址 */
#define VRAM_PLANE3  0xAB000UL   /* 平面 3 物理基址 */
#define VRAM_PLANE_SIZE  0x8000  /* 每平面 32KB（32K words） */

#define VRAM_WORDS_PER_LINE  40  /* 640px ÷ 16px/word */
#define VRAM_LINES           400 /* 标准 PC-98 图形模式线数 */
/* 屏幕尺寸单一来源：LAYER_SCREEN_W/H（engine/render.h） */

/*
 * uPD8251 串口附加定义
 */
#define SERIAL_MODE   0x32   /* 写（复位后第一字节）：模式寄存器 */
#define SERIAL_TXRDY  0x01   /* bit 0：发送器就绪 */
#define SERIAL_TXEMPTY 0x04  /* bit 2：发送器空 */

/*
 * PIC（i8259A 可编程中断控制器）
 */
#define PIC0_CMD   0x00   /* 主 PIC 命令端口 */
#define PIC0_IMR   0x02   /* 主 PIC 中断屏蔽寄存器 */
#define PIC1_CMD   0x08   /* 从 PIC 命令端口 */
#define PIC1_IMR   0x0A   /* 从 PIC 中断屏蔽寄存器 */

#define PIC_EOI    0x20   /* 中断结束（End of Interrupt）命令 */

/*
 * 中断向量号（PC-98 标准）
 */
#define IVT_VSYNC    0x0A   /* 垂直同步中断 */
#define IVT_TIMER    0x08   /* 定时器中断（~1.25ms） */
#define IVT_KBD      0x09   /* 键盘中断 */
#define IVT_CRT      0x18   /* CRT BIOS 功能调用入口 */

/*
 * IRQ 屏蔽位（对 PIC0 IMR 取值）
 */
#define IRQ_TIMER    0x01   /* bit 0：定时器 IRQ */
#define IRQ_KBD      0x02   /* bit 1：键盘 IRQ */
#define IRQ_VSYNC    0x04   /* bit 2：垂直同步 IRQ */
#define IRQ_SERIAL   0x10   /* bit 4：串口 IRQ */

/*
 * 键盘控制器端口与 BIOS 数据区偏移
 * =================================
 * PC-98 键盘通过 USART 连接（端口 0x40/0x42），BIOS 数据区
 * 偏移已包含段 0x58 的基址。
 * 注意：当前键盘驱动（keyboard.c）使用 BIOS 缓冲区（0x0502）
 * 而非直接 USART I/O，因此下面这些定义目前仅作参考。
 */
#define KBD_DATA      0x40   /* 键盘数据输入端口 */
#define KBD_STATUS    0x42   /* 键盘状态输入 / 命令输出端口 */
#define KBD_RESET     0xFA   /* 键盘缓冲区复位命令 */

#define KBD_BUF_HEAD  0x50C  /* BIOS 数据区段 0x58：缓冲区头指针 */
#define KBD_BUF_TAIL  0x50E  /* BIOS 数据区段 0x58：缓冲区尾指针 */
#define KBD_KEYTABLE  0x52C  /* 按键状态表（16 字节，每键 1 bit） */

#define KBD_ATN       0x01   /* 键盘状态位：ATN（Attention） */

/*
 * CRT BIOS（INT 18h）功能号
 */
#define CRT_SETMODE  0x42   /* AH=42h：设置显示模式 */
#define CRT_TEXT_OFF 0x0D   /* AH=0Dh：关闭文本叠加层 */
#define CRT_TEXT_ON  0x0C   /* AH=0Ch：启用文本叠加层 */
#define CRT_GFX_ON   0x40   /* AH=40h：启用图形显示层 */
#define CRT_GFX_OFF  0x41   /* AH=41h：关闭图形显示层 */

/* CRT 模式值（CX 寄存器） */
#define CRT_MODE_640x400_16C      0xC0   /* CX=0xC0：640×400 16 色图形模式 */

/* CRT BIOS 256 色模式设置（INT 18h AH=30h） */
#define CRT_MODE_256_CLOCK         0x08   /* AL=0x08：24kHz 标准点时钟 */
#define CRT_MODE_256_400LINE       0x01   /* BH=0x01：640×400 线 */

/*
 * 文本 VRAM
 * ==========
 * 在标准文本模式下，文本 VRAM 位于 0xA0000，分为平面 0（字符码）
 * 和平面 1（属性字节）。
 * 图形模式下文本层仍存在但通常被图形层覆盖。
 */
#define TXT_VRAM_OFFSET  0x0000  /* 文本平面 0：字符码 */
#define TXT_VRAM_ATTR    0x2000  /* 文本平面 1：属性字节（颜色等） */
#define TXT_COLS         80     /* 文本模式列数 */
#define TXT_ROWS         25     /* 文本模式行数 */

/*
 * 颜色常量（PC-98 数字 4-bit → 8-bit 调色板索引）
 * ===================================================
 * PC-98 16 色模式使用 4-bit（IRGB）颜色索引，PEGC 256 色模式
 * 扩展为 8-bit 索引。以下常量对应标准 16 色调色板索引。
 * 注意：PEGC 模式下颜色索引可任意重映射，这些常量仅作默认值。
 */
#define COL_BLACK   0
#define COL_WHITE   7
#define COL_RED     4
#define COL_GREEN   2
#define COL_BLUE    1
#define COL_YELLOW  6
#define COL_MAGENTA 5
#define COL_CYAN    3

#endif /* PC98_H */
