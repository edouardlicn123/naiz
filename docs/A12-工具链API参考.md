# 工具链 API 参考

## 1. 概述

`tools/naiz_img/` 是镜像工具链 Python 包，提供 5 种磁盘镜像格式读写和 FAT12/FAT16 文件系统操作。
参考 98Bridge (MIT) 的设计思路独立实现。

### 包结构

```
tools/naiz_img/
├── __init__.py    # 统一入口（open_image, create_blank_image）
├── base.py        # DiskImage 基类
├── hdi.py         # HDI (Anex86) 格式
├── fdi.py         # FDI (Anex86 软盘) 格式
├── d88.py         # D88/D68/D77 软盘格式
├── raw.py         # RAW 无头格式
├── nhd.py         # NHD (T98-Next) 格式
├── partition.py   # 分区表检测（MBR + PC-98 IPL）
├── fat.py         # FAT12/FAT16 文件系统
├── inject_common.py # 增量注入核心（inject_into_hdi, generate_autoexec）
├── inject.py      # CLI 入口：游戏注入工具
└── inject_file.py  # CLI 入口：二次注入
```

---

## 2. 镜像格式层

### 2.1 DiskImage（基类）

**模块**: `tools/naiz_img/base.py`

```python
class DiskImage:
    def __init__(self, path: str)
    def _parse(self)                     # 子类实现
    @property
    def sector_size(self) -> int
    @property
    def total_sectors(self) -> int
    def read_sector(self, lba: int) -> bytes
    def read_sectors(self, lba: int, count: int) -> bytes
    def write_sector(self, lba: int, data: bytes)
    def save(self, path: str = None)     # None = 覆盖源文件
```

- 构造时读取文件到 `self._data`（`bytearray`）
- `_parse()` 由子类实现，设定 `_sector_size` 和 `_total_sectors`
- `save()` 原子写入

### 2.2 HDIImage（HDI/Anex86 硬盘）

**模块**: `tools/naiz_img/hdi.py`

```python
class HDIImage(DiskImage):
    @property
    def spt(self) -> int
    @property
    def heads(self) -> int
    @property
    def cylinders(self) -> int
```

HDI 头部 4096 字节，扇区 LBA → 文件偏移：`hdr_size + LBA × sector_size`。

头部字段（偏移）：

| 偏移 | 类型 | 字段 |
|------|------|------|
| 0x04 | uint32 | hdd_type（容量提示） |
| 0x08 | uint32 | hdr_size（通常 4096） |
| 0x0C | uint32 | data_size |
| 0x10 | uint32 | bytes_per_sector |
| 0x14 | uint32 | spt |
| 0x18 | uint32 | heads |
| 0x1C | uint32 | cylinders |

`read_sector()` / `write_sector()` 内部自动加上 `_raw_offset`（= hdr_size），调用者无需关心。

### 2.3 其他格式

| 类 | 模块 | 格式 |
|----|------|------|
| `FDIImage` | `fdi.py` | FDI 软盘（继承 HDI 头部结构） |
| `D88Image` | `d88.py` | D88/D68/D77 软盘（0x2B0 头部 + 磁道偏移表） |
| `RawImage` | `raw.py` | 无头格式，自动检测扇区大小 |
| `NHDImage` | `nhd.py` | NHD (T98-Next)，512 字节 ASCII 文本头 |

### 2.4 统一入口

**模块**: `tools/naiz_img/__init__.py`

```python
def open_image(path: str) -> DiskImage
    # 按扩展名自动分派：.hdi→HDI, .fdi→FDI, .d88/.d68/.d77→D88,
    #                      .nhd→NHD, .raw/.bin/.img→RAW

def create_blank_image(path: str, format='hdi', sectors=..., sector_size=512,
                       spt=17, heads=8, cylinders=722) -> HDIImage
    # 创建空白 HDI 镜像（仅头部，无 FAT 文件系统）
```

---

## 3. 分区检测

**模块**: `tools/naiz_img/partition.py`

```python
@dataclass
class PartitionEntry:
    index: int
    scheme: str          # "MBR" 或 "PC-98"
    type_id: int
    byte_offset: int
    byte_size: int

def detect_partitions(img: DiskImage) -> list[PartitionEntry]
    # 先尝试 MBR（0x1FE 处 55AA），再尝试 PC-98 IPL（魔数 "IPL1" @ offset 4）
```

PC-98 分区表位于 LBA 1（扇区 1），每项 32 字节，最多 16 项。

LBA 计算公式：`cyl × heads × spt + head × spt + sector`

base_msdos5_scsi_48m.hdi 典型值：
- 分区起始：LBA 136 (cyl=1, head=0, sector=0)
- 类型 ID：`0x91`
- 大小：47520 扇区

---

## 4. FAT 文件系统

**模块**: `tools/naiz_img/fat.py`

### 4.1 FileEntry

```python
class FileEntry:
    name: str           # 8 字符文件名（已 strip）
    ext: str            # 3 字符扩展名
    attr: int           # 属性（ATTR_DIRECTORY=0x10, ATTR_ARCHIVE=0x20）
    cluster: int        # 起始簇号
    size: int           # 文件大小
    children: dict      # {显示名: FileEntry}（目录专用）

    @property
    def is_directory(self) -> bool
    @property
    def display_name(self) -> str   # "NAME.EXT"
```

### 4.2 NAIZFatFS

```python
class NAIZFatFS:
    def __init__(self, img: DiskImage, part_offset: int = None)
    def resolve_path(self, path: str) -> FileEntry | None
    def list_dir(self, path='/') -> list[FileEntry] | None
    def walk(self, path='/') -> Generator[tuple[str, FileEntry]]
    def read_file(self, entry: FileEntry) -> bytes
    # write_back_from_directory — 已由 inject_common.inject_into_hdi() 替代
```

#### 构造函数

自动检测分区（`detect_partitions`）或指定 `part_offset`。
读取 VBR → 验证 `EB` 跳转 + BPB（bps ∈ {512, 1024, 2048}）→ 计算 FAT 布局 → 构建目录树。

属性：

| 属性 | 类型 | 说明 |
|------|------|------|
| `bytes_per_sector` | int | 扇区大小 |
| `sectors_per_cluster` | int | 每簇扇区数 |
| `reserved_sectors` | int | 保留扇区数 |
| `num_fats` | int | FAT 副本数 |
| `root_entries` | int | 根目录条目数 |
| `fat_sectors` | int | 每份 FAT 的扇区数 |
| `cluster_size` | int | 簇大小（字节） |
| `fat_type` | int | 12 或 16 |
| `root` | FileEntry | 根目录 FileEntry |

#### resolve_path

```python
fs.resolve_path("/AUTOEXEC.BAT")    # → FileEntry（存在时）
fs.resolve_path("DEMO-A1/ENGINE.LOG")  # 支持 / 和 \ 分隔符
fs.resolve_path("/NONEXIST")        # → None
```

#### walk

递归遍历全部文件和目录：

```python
for path, entry in fs.walk():
    print(path, entry.size, entry.is_directory)
# 输出示例：
# /AUTOEXEC.BAT 123 False
# /DOS/ 0 True
# /DOS/FORMAT.EXE 45678 False
```

#### read_file

读取文件全部内容：

```python
data = fs.read_file(fs.resolve_path("/DEMO-A1/ENGINE.LOG"))
```

#### inject_into_hdi — 增量 FAT 注入（替代 write_back_from_directory）

`tools/naiz_img/inject_common.py` 提供当前核心注入逻辑。

```python
def inject_into_hdi(hdi_path, game_name, game_dir,
                    no_config=False, no_autoexec=False) -> tuple[int, int]:
```

流程：
0. 移除 DBLSPACE.BIN（根目录标记 0xE5），防 IO.SYS 弹出"how many files"询问
1. 打开 HDI，解析 FAT16
2. 替换 AUTOEXEC.BAT（原地覆写或重分配簇链）
3. 替换 CONFIG.SYS（同上）
4. 查找或创建游戏子目录 — 新分配目录簇立即清零
5. 遍历游戏文件：已存在 → 覆写，新文件 → 分配簇链
6. 写回所有 FAT 副本
7. `img.save()`

```python
def generate_autoexec(game_name) -> bytes:
    """生成 AUTOEXEC.BAT 内容，使用 \ 根相对路径"""
```

---

## 5. 注入工具（inject.py）

**模块**: `tools/naiz_img/inject.py`

### CLI

```bash
python -m tools.naiz_img.inject -g demo-A1
python -m tools.naiz_img.inject -g mygame -o disks/mygame.hdi
python -m tools.naiz_img.inject -g demo-A1 --preview
python -m tools.naiz_img.inject -g demo-A1 --list-files
python -m tools.naiz_img.inject -g demo-A1 --extract DEMO-A1/ENGINE.LOG
```

### 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-g, --game` | 必填 | 游戏名，对应 `games/<name>/` |
| `-b, --base` | `tools/base_msdos5_scsi_48m.hdi` | 基座 HDI |
| `-o, --output` | `disks/<game>.hdi` | 输出路径 |
| `--preview` | false | 预览文件清单 |
| `--list-files` | false | 列出基座镜像文件 |
| `--no-config` | false | 不覆写 CONFIG.SYS |
| `--no-autoexec` | false | 不覆写 AUTOEXEC.BAT |
| `--no-config` | false | 不覆盖 CONFIG.SYS |
| `--no-autoexec` | false | 不覆盖 AUTOEXEC.BAT |
| `-y, --yes` | false | 非交互模式 |
| `--extract PATH` | — | 从输出 HDI 提取文件到 `logs/` |

### 工作流程

```python
shutil.copy2(base_hdi, output)                    # 复制基座
inject_into_hdi(output, game, game_dir,
                no_config=..., no_autoexec=...)    # 增量注入
```

---

## 6. 交互式外层

| 工具 | 说明 |
|------|------|
| `makegame.sh` | 统一工作流：`make`（注入 HDI）/ `test`（模拟器）/ `build`（编译） |
| `makegame.sh make <game>` | 制作 HDI |
| `makegame.sh test <game>` | 启动 wxnp21kai 测试 |
| `makegame.sh build <proj>` | 编译项目数据 |

---

## 7. 完整使用示例

```python
# 打开 HDI → 遍历文件
from naiz_img import open_image
from naiz_img.fat import NAIZFatFS

img = open_image("tools/base_msdos5_scsi_48m.hdi")
fs = NAIZFatFS(img)

for path, entry in fs.walk():
    tag = "DIR" if entry.is_directory else f"{entry.size}B"
    print(f"{path} ({tag})")

# 读取文件
autoexec = fs.read_file(fs.resolve_path("/AUTOEXEC.BAT"))
print(autoexec.decode('ascii'))

# 注入游戏文件（通过 inject_common）
from tools.naiz_img.inject_common import inject_into_hdi
inject_into_hdi("disks/mygame.hdi", "mygame", "games/mygame")
```
