# 18 — 镜像工具链方案（基于 98Bridge 设计思路）

## 背景

之前的方向变更（change.txt）提出：
1. 基于已确认可启动的 `~/msdos5/msdos5.hdi` 制作游戏 HDI
2. 引入 98Bridge 替代自维护的 FAT16 注入代码

98Bridge 已于 `docs/98bridge/api-分析.md` 做了完整源码分析。**不直接引用 98Bridge 代码**，而是借鉴其设计思路，在 `tools/naiz_img/` 下独立实现。

## 目标

在 `tools/naiz_img/` 中构建一套镜像工具链：
- 支持 PC-98 常见镜像格式（HDI / FDI / D88 / Raw / NHD）
- FAT12/FAT16 文件系统解析 + `write_back_from_directory` 全量重建注入
- 基于 `~/msdos5/msdos5.hdi` 注入游戏文件，保留原版 boot chain

## 目录结构

```
tools/naiz_img/
├── __init__.py        公开 API：open_image(), create_blank_image()
├── base.py            DiskImage 基类（扇区级 I/O 接口 + save）
├── hdi.py             HDIImage   (Anex86 HDI, 4096B 头)
├── fdi.py             FDIImage   (Anex86 FDI 软盘, 4096B 头)
├── d88.py             D88Image   (D88/D68/D77 磁道格式)
├── raw.py             RawImage   (无头裸盘, 自动检测扇区大小)
├── nhd.py             NHDImage   (T98-Next NHD, 512B 文本头)
├── partition.py       MBR / PC-98 IPL 分区表检测
├── fat.py             NAIZFatFS: FAT12/FAT16 解析 + write_back
├── inject.py          CLI 入口: 注入游戏到 msdos5.hdi
└── README.md          用法 + 来源声明
```

## 模块设计

### base.py — DiskImage 基类

```python
class DiskImage:
    """扇区级 I/O 接口。所有容器格式继承自此类。"""
    def __init__(self, path):          # 读入文件到 self._data
    def _parse(self):                  # 子类实现：解析文件头，设定几何参数
    @property
    def sector_size(self) -> int
    @property
    def total_sectors(self) -> int
    def read_sector(self, lba) -> bytes
    def read_sectors(self, lba, count) -> bytes
    def write_sector(self, lba, data)
    def save(self, path=None)          # path = None 时原文件原子覆盖
```

### hdi.py / fdi.py — HDI/FDI 容器

两者头部结构相同，fd 仅几何参数不同（软盘 vs 硬盘），可提取公共解析逻辑到 `base.py` 或分别实现。

HDI 头部（HDIImage 解析）：

| 偏移 | 大小 | 字段 |
|------|------|------|
| 0x00 | 4 | reserved |
| 0x04 | 4 | hdd_type（容量 MB 提示） |
| 0x08 | 4 | hdr_size（通常 4096） |
| 0x0C | 4 | data_size |
| 0x10 | 4 | bytes_per_sector |
| 0x14 | 4 | spt |
| 0x18 | 4 | heads |
| 0x1C | 4 | cylinders |

扇区 LBA → 文件偏移 = hdr_size + LBA × bytes_per_sector。

### d88.py — D88 磁道格式

D88 头部 0x2B0 字节，内含 164 × 4 字节磁道偏移表。
每个磁道内扇区有 16 字节头（C/H/R/N），数据紧随其后。
软盘格式，当前作为备用，主开发用 HDI。

### raw.py — 裸镜像

无头文件，整个文件就是连续扇区数据。
已知几何表：1.2MB(1024B), 720KB(512B), 1.44MB(512B)，其余按文件大小对齐到 512/1024。

### nhd.py — T98-Next NHD 格式

512 字节 ASCII 文本头，以 `T98HDDIMAGE.R0\0` 开头，`key=value` 换行分隔几何参数。
数据体从偏移 512 开始。

### partition.py — 分区表检测

```python
@dataclass
class PartitionEntry:
    scheme: str       # "MBR" 或 "PC-98"
    byte_offset: int  # 分区起始字节偏移
    byte_size: int    # 分区大小

def detect_partitions(img: DiskImage) -> list[PartitionEntry]
    # 按优先级尝试:
    #   1. MBR（扇区 0 0x1FE = 55AA，解析 4 个分区项）
    #   2. PC-98 IPL（扇区 0 含 "IPL1" 魔数，扇区 1 解析 16 个分区项）
```

### fat.py — FAT12/FAT16 文件系统

核心模块。拆解 98Bridge `fat_fs.py` 的设计，独立实现。

```python
class FileEntry:
    name: str          # 8.3 格式
    ext: str
    attr: int
    cluster: int
    size: int
    children: dict     # 目录专用
    is_directory: bool

class NAIZFatFS:
    def __init__(self, img: DiskImage, part_offset: int | None = None):
        # 1. 自动分区检测（或使用 part_offset）
        # 2. 读 VBR → BPB 验证 → 计算布局
        # 3. 根据 total_clusters < 4085 自动选择 FAT12 / FAT16
        # 4. 加载 FAT 表（12 或 16 位）
        # 5. 构建目录树

    # ── 查询（复用 98Bridge 设计）──
    def resolve_path(self, path) -> FileEntry | None
    def walk(self) -> generator                    # (path, FileEntry)
    def read_file(self, entry) -> bytes

    # ── 写入（核心接口）──
    def write_back_from_directory(self, dir_path, save_path=None) -> tuple
        """全量重建 FAT 文件系统。
           保留 VBR/BPB → 清零 FAT + Root + Data →
           从 dir_path 递归遍历并构建文件和目录 →
           IO.SYS / MSDOS.SYS 自动排根目录最前 →
           write_back 内根据 self.fat_type 分别用 12/16 位编码 →
           写回所有 FAT 副本 → save。
        """
```

### inject.py — CLI 入口

```python
# 用法:
#   python -m tools.naiz_img.inject --game demo-A1
#   python -m tools.naiz_img.inject --game mygame --output disks/mygame.hdi

# 工作流:
#   1. 构建 temp_dir（ref_disk/ 系统文件 + ref_config/ 覆写 + games/<game>/ 覆写）
#   2. NAIZFatFS(open_image(base_hdi)).write_back_from_directory(temp_dir, save_path)
#   3. 清理 temp_dir
```

CLI 参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-g, --game` | **必填** | 游戏名，对应 `games/<name>/` |
| `-b, --base` | `~/msdos5/msdos5.hdi` | 基座 HDI |
| `-o, --output` | `disks/<game>.hdi` | 输出路径 |
| `--preview` | false | 只预览文件清单 |
| `--list-files` | false | 列出全部文件 |
| `--no-dos` | false | 跳过 DOS 工具 |
| `--no-config` | false | 不覆写 CONFIG.SYS |
| `--no-autoexec` | false | 不覆写 AUTOEXEC.BAT |
| `-y, --yes` | false | 非交互模式 |

## 执行步骤

### Step 1：创建 `tools/naiz_img/` 目录 + `__init__.py` + `README.md`

- 空目录结构
- `__init__.py` 导出 `open_image()` 和 `create_blank_image()`
- `open_image()` 按扩展名自动分发

### Step 2：实现容器格式层

| 文件 | 实现内容 |
|------|----------|
| `base.py` | `DiskImage` 基类（read_sector / write_sector / save） |
| `hdi.py` | `HDIImage` |
| `fdi.py` | `FDIImage` |
| `d88.py` | `D88Image` |
| `raw.py` | `RawImage`（自动检测扇区大小 + 已知几何表） |
| `nhd.py` | `NHDImage` |

### Step 3：实现 `partition.py`

- `PartitionEntry` dataclass
- `detect_mbr()` — IBM-PC MBR 分区
- `detect_pc98()` — PC-98 IPL 分区（`IPL1` 魔数 + 扇区 1 分区表）
- `detect_partitions()` — 按优先级调度

### Step 4：实现 `fat.py`

- `FileEntry` 类
- `NAIZFatFS` 类（FAT12/FAT16 自动检测，解析 + write_back）
- 核心算法：write_back 中的 FAT 重建、12/16 位序列化、簇分配、目录构建、IO.SYS 排序

### Step 5：实现 `inject.py`

- CLI 参数解析
- temp_dir 构建逻辑
- 调用 NAIZFatFS.write_back_from_directory

### Step 6：更新 `core/Makefile` test target

```makefile
test: $(OUTPUT)
	python3 -m tools.naiz_img.inject --game demo-A1 --yes
	sdlnp2kai_sdl2
```

### Step 7：端到端测试

```bash
cd core
make clean && make all
make test
# → NP2kai 启动，AUTOEXEC.BAT 运行 C:\demo-A1\ENGINE.EXE
# → 蓝屏输出
```

## 与现有 `make_hdi.py` 的关系

| 工具 | 职责 | 何时用 |
|------|------|--------|
| `make_hdi.py`（保留） | 从零创建 HDI（自建 IPL/VBR） | 备选/测试 |
| `inject.py`（新增） | 基于 msdos5.hdi 注入游戏 | **主要开发流程** |
| `naiz_img/` 各模块 | 镜像格式 + FAT12/FAT16 操作库 | 被 inject.py 调用 |

## 来源声明

每个 `.py` 文件开头添加（参考 98Bridge MIT License 的设计思路独立实现）：

```python
"""
参考 98Bridge (MIT) 的设计思路独立实现。
来源: https://github.com/NullMagic2/98Bridge
"""
```
