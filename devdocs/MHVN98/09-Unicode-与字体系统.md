# Unicode 与字体系统

**源文件**: `src/unicode.c` (608 行), `src/unicode.h` (50 行)

MHVN98 使用纯 Unicode（弃用 Shift-JIS）处理文本，所有文本数据以 UTF-8 编码存储。字体文件包含 Unicode BMP 范围内的 glyph。

## UTF-8 解码 `UTF8CharacterDecode()` (行 341–389)

将指向 UTF-8 字符串的指针前进一位并返回解码后的 Unicode 码点：

| 字节范围 | 编码位数 | 码点范围 |
|----------|----------|----------|
| `0x00-0x7F` | 1 字节 | U+0000-U+007F |
| `0xC0-0xDF` | 2 字节 | U+0080-U+07FF |
| `0xE0-0xEF` | 3 字节 | U+0800-U+FFFF (BMP) |

不处理 4 字节 UTF-8（超出 BMP 范围），遇到孤立的续编字节 (`0x80-0xBF`) 会跳过。

## 字体文件格式

字体文件在 `ROOTINFO.DAT` 的 `font_file` 字段中指定。

### 文件结构

```
0x00000000  uint32[]  char_ranges  码点范围列表
            每个条目：lower 16 bits = 起始码点, upper 16 bits = 结束码点
            以 0x00000000 结束
var         uint32[]  char_infos   每个字形的信息条目
            HHHH YYYY  W00A AAAA  AAAA AAAA  AAAA AAAA
            A = glyph 数据（相对于 glyph 数据块的字节偏移）
            W = glyph 宽度 (0=8像素, 1=16像素)
            Y = Y 轴偏移（行数）
            H = 高度 - 1（行数）
var         uint8[]   glyph_data   实际 glyph 数据，1-bit bitmap，大端序
```

### 解析过程

`InitFontFile()` (行 277–338)：

1. 读取字体文件中的范围列表
2. 将范围条目转换为内部格式（含起始码点、起始条目索引、长度）
3. 加载所有 ASCII 字符 (0x21-0x7E) 到永久缓存 `asciiCharacterCache`

## Glyph 缓存系统

### 缓存层次

```
永久缓存 (asciiCharacterCache[94][16])
  └── ASCII 可打印字符 (0x21-0x7E)，2048 字节，永不淘汰

临时缓存 (glyphCache[256][32])
  └── 非 ASCII 字符，LRU 淘汰
```

### 数据结构

```c
#define GLYPHCACHE_SIZE    256    // 缓存槽位数
#define GLYPHCACHE_ADDRBITS 9     // 散列地址位
#define GLYPHCACHE_ADDRMASK 0x01FF

unsigned char glyphCache[32 * GLYPHCACHE_SIZE];       // glyph 位图数据 (每个 32 字节)
unsigned char glyphInfoCache[GLYPHCACHE_SIZE];        // glyph 元信息（宽度）
unsigned int nextGlyphIndex;                           // 下一个要写入的缓存槽

IndexBufferEntry glyphIndexBuffer[GLYPHCACHE_SIZE];   // 码点 → 缓存索引的映射
unsigned int nextBufferIndex;                          // 下一个索引条目位置

PresenceMapEntry glyphPresenceMap[GLYPHCACHE_ADDRMASK + 1];  // 存在性哈希表
```

### LRU 淘汰策略

`LoadGlyphCacheWithCharacter()` (行 457–529)：

1. **ASCII 字符** (码点 < 0x80) → 直接从永久缓存读取，无需加载
2. **非 ASCII 字符**：
   - 通过哈希表 (`glyphPresenceMap`) 检查是否存在
   - 冲突解决：开放寻址，线性探测
   - **Cache miss** → 从字体文件读取 → 写入下一个槽位
   - 如果待写入槽位已有数据 → **淘汰旧条目**（清理存在性哈希表 + 解决散列冲突）
   - **Cache hit** → 更新索引缓冲区位置（LRU 排序）

### Glyph 加载 `LoadGlyphFromFile()` (行 391–455)

1. 在范围列表中二分查找码点
2. 从字体文件读取 `char_info`（4 字节）：地址、宽度、Y偏移、高度
3. 读取 glyph 位图数据 (32 字节)
4. 转换为内部 "edit-friendly" 格式：
   - 8 像素宽字形：每行 1 字节，扩展到 `buffer[2*i]`
   - 16 像素宽字形：每行 2 字节，直接复制到 `buffer`

### 格式转换 `SwapCharDataFormats()` (行 586–608)

将 glyph 数据从 "edit-friendly" 格式（每个行像素放在 `buffer[i]` 的连续位中）转换为 "VRAM-compatible" 格式（每个行像素以字节大端序对齐），以便使用 EGC 写入显存。

## Glyph 数据获取

```c
int UnicodeGetCharacterWidth(unsigned int code);
// 返回字符宽度（像素），-1 = 无字形

int UnicodeGetCharacterData(unsigned int code, unsigned long* buffer);
// 获取字符的 glyph 数据（edit-friendly 格式），返回宽度
```

## 字符发生器接口

`pc98_chargen.c/h` 提供了与 PC-98 硬件字符发生器（CG）交互的功能：

```c
void CGModeSet(void);                    // 设置 CG 模式
void CGRead(unsigned short code, unsigned char* buffer);  // 从 CG ROM 读取字模
unsigned short SjisToInternalCode(unsigned short sjis);   // Shift-JIS → 内部编码转换
```

不过 MHVN98 不依赖这些——它使用自己的字体文件和 Unicode 体系，仅在早期原型中可能使用。
