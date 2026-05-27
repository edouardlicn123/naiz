# 98Bridge API 分析

> 分析版本：Git 主分支 (2026-05-25 拉取)
> 来源：https://github.com/NullMagic2/98Bridge
> 许可证：MIT

---

## 目录

1. [总体架构](#1-总体架构)
2. [模块详解](#2-模块详解)
   - [2.1 disk_image.py](#21-disk_imagepy)
   - [2.2 partition.py](#22-partitionpy)
   - [2.3 fat_fs.py](#23-fat_fspy)
   - [2.4 registry.py](#24-registrypy)
3. [关键流程](#3-关键流程)
4. [依赖关系](#4-依赖关系)
5. [集成方式](#5-集成方式)

---

## 1. 总体架构

```
registry.py ───→ plugin_loader.py ───→ plugins/core/pc98_formats.py
    │                                          └── plugins/core/fat_filesystem.py
    │                                          └── plugins/nhd_format.py (example)
    │
    ├── disk_image.py     格式解析层（D88/FDI/HDI/Raw）
    ├── partition.py      分区表检测（MBR / PC-98 IPL）
    ├── fat_fs.py         FAT12/FAT16 文件系统（解析 + 写入）
    │
    ├── mount_backend.py  挂载后端（VHD/subst/目录）
    ├── hex_viewer.py     16 进制查看器（wxPython）
    └── pc98mount.py      wxPython GUI 主程序
```

**核心三层**（无 GUI 依赖）：

```
disk_image.py  （扇区级 I/O）
     ↓
partition.py   （分区检测）
     ↓
fat_fs.py      （FAT12/16 文件系统：解析 + write_back）
```

---

## 2. 模块详解

### 2.1 disk_image.py

**文件**：`disk_image.py` (250 行，不含空白/注释)

**作用**：提供统一的扇区级访问接口，支持 HDI、FDI、D88、Raw 四种格式。

#### 基类 `DiskImage`

```python
class DiskImage:
    def __init__(self, path):      # 读入文件到 self._data (bytearray)
    def _parse(self):              # 子类实现：解析文件头，设定 self._sector_size / _total_sectors
    @property
    def sector_size(self): pass    # 扇区大小
    @property
    def total_sectors(self): pass  # 总扇区数
    @property
    def label(self): pass          # 人类可读标签

    def read_sector(self, lba):    # 读单个扇区 → bytes
    def read_sectors(self, lba, count):  # 读连续多个扇区 → bytes

    def write_sector(self, lba, data):   # 写单个扇区（修改 self._data）
    def save(self, path=None):           # 写入磁盘（path 不同则另存，相同则原子替换）
```

#### 关键子类 `HDIImage`（HDI 格式）

```python
class HDIImage(DiskImage):
    HEADER_SIZE = 4096

    # 从字节偏移解析：
    #   0x00 reserved, 0x04 hdd_type, 0x08 hdr_size,
    #   0x0C data_size, 0x10 sec_size, 0x14 spt,
    #   0x18 heads, 0x1C cyls
    #
    # 扇区偏移 = hdr_size + lba * sector_size
    # 支持两种 header 布局（0x08 和 0x04）作为容错

    def read_sector(self, lba):
        offset = self._raw_offset + lba * self._sector_size
        return bytes(self._data[offset:offset + self._sector_size])

    def write_sector(self, lba, data):
        # 修改 self._data
        pass
```

**HDI 头部格式验证**（当前 msdos5.hdi 的 HDI header）：

| 偏移 | 字段 | 值（msdos5.hdi） | 说明 |
|------|------|-------------------|------|
| 0x00 | reserved | 0 | |
| 0x04 | hdd_type | 48 | 容量 MB 提示 |
| 0x08 | hdr_size | 4096 | |
| 0x0C | data_size | 50278400-4096 | |
| 0x10 | sec_size | 512 | |
| 0x14 | spt | 17 | |
| 0x18 | heads | 8 | |
| 0x1C | cyls | 722 | |

#### `open_image()` — 统一入口

```python
def open_image(path) -> DiskImage:
    # 根据扩展名自动选择子类：
    #   .d88/.d68/.d77 → D88Image
    #   .fdi           → FDIImage
    #   .hdi           → HDIImage
    #   .hdm/.tfd      → RawImage(sector_size=1024)
    #   .img/.ima      → RawImage
```

#### `create_blank_image()` — 创建空白镜像

```python
def create_blank_image(path, fmt, geometry_name_or_tuple, format_fat=True):
    # fmt: "HDM" / "D88" / "FDI" / "HDI" / "RAW (.img)"
    # geometry: key in BLANK_GEOMETRIES, 或 (cyls, heads, spt, sector_size) 元组
    # 如果是软盘格式且 format_fat=True，写入 BPB + 空 FAT
    # HDI 不写 FAT（需要从 DOS 内初始化）
```

**注意**：`create_blank_image` 创建的 HDI **不包含 FAT 文件系统**，只能用于创建空白镜像。我们不能用它创建可启动 HDI——必须用 MS-DOS 5.0 已格式化的 HDI 作为基座。

---

### 2.2 partition.py

**文件**：`partition.py` (约 160 行)

**作用**：检测分区块表，返回分区列表。

```python
@dataclass
class PartitionEntry:
    index: int        # 分区索引
    scheme: str       # "MBR" 或 "PC-98"
    type_id: int      # 类型 ID（如 0x06 = FAT16）
    name: str         # 人类可读名称
    byte_offset: int  # 分区起始字节偏移
    byte_size: int    # 分区大小（0 = 到镜像末尾）

def detect_partitions(disk_image) -> list[PartitionEntry]:
    """自动检测分区方案，返回分区列表"""
```

**检测策略**：
1. 先尝试 `MBR`（扇区 0 的 0x1FE = 55AA，解析 4 个分区表项）
2. 再尝试 `PC-98 IPL`（扇区 0 包含 `IPL1` 魔数，或扇区末尾 55AA，在扇区 1 读取 16 个分区表项）
3. 都失败则返回空列表

**在 msdos5.hdi 上的行为**：
- 扇区 0 是 HDI 文件头，不是磁盘数据
- 真正的扇区 0 = 偏移 4096 处
- 所以 `HDIImage` 通过 `_raw_offset` 已经做了透明映射，`disk_image.read_sector(0)` 返回的是数据扇区 0
- 数据扇区 0 包含 IPL1 引导代码（`eb 0a 90 90 49 50 4c 31`）
- `detect_pc98()` 会检测到 `IPL1` 魔数，在扇区 1 读取 PC-98 分区表
- 分区表项指向 LBA 136 处（cylinder 1 的起始），即 VBR/FAT 区域

---

### 2.3 fat_fs.py

**文件**：`fat_fs.py` (~560 行)

**作用**：FAT12/FAT16 文件系统的解析、路径查询、文件读取、**写入**（write-back）。

这是 98Bridge 中**最核心、最关键的模块**。

#### 构造函数

```python
class FATFilesystem:
    def __init__(self, disk_image):
        # 1. 从 BPB 读取 bytes_per_sector, spc, reserved, nfats, root_entries, fat_size, ...
        # 2. 如果 BPB 无效，自动尝试分区表检测（_try_partitioned_disk()）
        # 3. 如果仍无效，回退到已知软盘几何参数
        # 4. 加载 FAT 表到 self._fat_data
        # 5. 构建根目录树 self.root (FileEntry)
```

关键计算：

```
first_fat_sector   = reserved_sectors
first_root_sector  = first_fat_sector + nfats * fat_sectors
first_data_sector  = first_root_sector + root_dir_sectors
total_clusters     = (total_sectors - first_data_sector) / spc
fat_type           = 12 if total_clusters < 4085 else 16
```

#### `FileEntry` — 目录项

```python
class FileEntry:
    name: str        # 8 字符文件名
    ext: str         # 3 字符扩展名
    attr: int        # 属性
    cluster: int     # 起始簇号
    size: int        # 文件大小
    children: dict   # 子目录项 (仅目录有此)
    is_directory: bool
    display_name: str  # "NAME.EXT"
```

#### 读取 API

```python
def resolve_path(self, path) -> FileEntry | None:   # "/DIR/FILE.EXT"
def list_dir(self, path='/') -> list[FileEntry] | None:
def walk(self, path='/', prefix='') -> generator:   # yield (full_path, FileEntry)
def read_file(self, entry) -> bytes:
```

#### 写入 API — `write_back_from_directory()`

```python
def write_back_from_directory(self, dir_path, save_path=None) -> tuple:
    """重建整个 FAT 文件系统（保留 BPB/VBR）。
    
    参数:
        dir_path: 宿主机目录路径（包含要写入的所有文件）
        save_path: 输出的镜像路径（None = 覆盖原文件）
    
    返回:
        (files_written, dirs_written)
    
    说明:
        - BPB/引导扇区不变
        - FAT 表、根目录、数据区完全重建
        - IO.SYS / MSDOS.SYS 自动排到根目录最前面（cluster 2 开始）
        - 8.3 文件名冲突自动使用 ~N 后缀
        - 抛出 RuntimeError 如果 BPB 是猜测的（防止破坏镜像）
    """
```

**内部工作流**：

```
1. 验证 bpb_is_valid（拒绝 guessed/geometry 来源的 BPB）
2. 初始化内存 FAT 表（簇 0/1 = 媒体描述符 + EOC）
3. 清零根目录区域
4. 清零数据区域（64KB 分块写入）
5. 宿主机目录递归遍历:
   a. 根目录下 IO.SYS / MSDOS.SYS 排最前
   b. 每个文件: alloc_chain → write_to_clusters → 构建目录项
   c. 每个子目录: alloc_cluster → 递归 → 构建 . + .. + 子项
6. 写入卷标（保留原卷标名）
7. 序列化 FAT → 写入所有 FAT 副本
8. disk.save(save_path) → 写回磁盘
9. 重新加载 FAT 和目录树
```

**限制**：
- 必须有一个**有效的 BPB**（从磁盘读取，不是猜测的）
- 目录文件数量不能超过根目录条目限制（root_entries）
- 磁盘空间不足时抛出 RuntimeError
- 这是**全量重建**，不是增量注入

---

### 2.4 registry.py

**文件**：`registry.py` (~400 行)

**作用**：插件的注册、查找、卸载机制。

**我们在集成中不需要 registry**——可以直接 `from disk_image import HDIImage` 然后手动调用。

---

## 3. 关键流程

### 3.1 HDI 打开 + FAT 解析

```python
from disk_image import open_image
from fat_fs import FATFilesystem

disk = open_image("msdos5.hdi")       # → HDIImage 实例
fs = FATFilesystem(disk)              # 自动检测分区，解析 BPB，构建目录树

# 遍历文件
for path, entry in fs.walk():
    print(path, entry.size, "DIR" if entry.is_directory else "FILE")

# 读取文件内容
data = fs.read_file(fs.resolve_path("/AUTOEXEC.BAT"))
```

### 3.2 write_back 注入游戏文件

```python
import tempfile, shutil
from pathlib import Path

# 1. 打开基座 HDI
disk = open_image("~/msdos5/msdos5.hdi")
fs = FATFilesystem(disk)

# 2. 提取所有文件到临时目录
tmpdir = tempfile.mkdtemp()
for path, entry in fs.walk():
    host_path = os.path.join(tmpdir, path.lstrip("/"))
    if entry.is_directory:
        os.makedirs(host_path, exist_ok=True)
    else:
        os.makedirs(os.path.dirname(host_path), exist_ok=True)
        with open(host_path, "wb") as f:
            f.write(fs.read_file(entry))

# 3. 修改临时目录中的文件
shutil.copy2("ref_config/AUTOEXEC.BAT",
             os.path.join(tmpdir, "AUTOEXEC.BAT"))

# 4. 写入新 HDI
fs.write_back_from_directory(tmpdir, save_path="disks/MyGame.hdi")
```

### 3.3 直接构造（不提取，从 ref_disk 构建）

```python
import tempfile, shutil, os

# 1. 用 ref_disk/ 中的文件快速构建临时目录
tmpdir = tempfile.mkdtemp()
_ref_disk = "tools/ref_disk"
for root, dirs, files in os.walk(_ref_disk):
    for f in files:
        src = os.path.join(root, f)
        rel = os.path.relpath(src, _ref_disk)
        dst = os.path.join(tmpdir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

# 2. 覆写配置文件
shutil.copy2("tools/ref_config/AUTOEXEC.BAT", os.path.join(tmpdir, "AUTOEXEC.BAT"))
shutil.copy2("tools/ref_config/CONFIG.SYS",   os.path.join(tmpdir, "CONFIG.SYS"))

# 3. 覆写游戏文件
shutil.copy2("games/demo-A1/ENGINE.EXE",
             os.path.join(tmpdir, "demo-A1", "ENGINE.EXE"))

# 4. 打开基座 + write_back
disk = open_image("~/msdos5/msdos5.hdi")
fs = FATFilesystem(disk)
fs.write_back_from_directory(tmpdir, save_path="disks/demo-A1.hdi")
```

---

## 4. 依赖关系

### 无需 wxPython 的核心模块

| 模块 | 导入路径 | import 自身 | import 其他模块 |
|------|----------|-------------|-----------------|
| `disk_image.py` | `from disk_image import HDIImage, open_image` | `struct`, `os`, `shutil`, `logging` | `import registry`（可选） |
| `partition.py` | `from partition import detect_partitions` | `struct`, `logging` | `from registry import ...`（可选） |
| `fat_fs.py` | `from fat_fs import FATFilesystem` | `struct`, `os`, `logging`, `datetime` | `from partition import detect_partitions` |
| `registry.py` | `from registry import register_image_format` | `inspect`, `logging`, `dataclasses` | 无 |

### 需要 wxPython 的模块（不需要用）

| 模块 | 依赖 |
|------|------|
| `pc98mount.py` | wxPython, registry, plugin_loader, disk_image, hex_viewer, mount_backend |
| `hex_viewer.py` | wxPython |
| `plugin_manager.py` | wxPython |
| `mount_backend.py` | 仅 Windows 用 diskpart/subst；Linux 目录挂载不需要 wx |

**结论**：`disk_image.py` + `partition.py` + `fat_fs.py` 三个文件可以独立复制或通过 `sys.path` 直接使用，零第三方依赖。

---

## 5. 集成方案

### 方案 A：子模块 + sys.path（推荐）

```python
import sys, os
sys.path.insert(0, os.path.join(PROJECT_ROOT, "ref_projects", "98Bridge"))

from disk_image import open_image
from fat_fs import FATFilesystem
```

优点：保持子模块同步；无需复制代码。
缺点：`import registry` 时 `disk_image.py` 和 `partition.py` 会尝试加载 registry（但在 `disk_image.py` 中 `import registry` 仅用于插件注册，`HDIImage` 本身的 `_parse()` 不依赖 registry——真正的注册是在 `plugins/core/pc98_formats.py` 中完成的）。

实际上，`disk_image.py` 顶部的 `import registry as _registry` 是为插件系统服务的。如果我们直接 `from disk_image import HDIImage`，不调用 `open_image()`（它依赖 registry 的 `_ext_to_format`），而是**直接实例化 `HDIImage(path)`**，则完全不需要 registry。

```python
# 直接实例化，不依赖 registry
from disk_image import HDIImage
disk = HDIImage("msdos5.hdi")     # 直接调用，无需 registry
```

同样，`FATFilesystem(disk)` 也不需要 registry——它直接调用 `partition.detect_partitions()`。

### 方案 B：复制三文件到 `tools/98bridge/`

```
tools/
└── 98bridge/
    ├── __init__.py    ← 空文件
    ├── disk_image.py  ← 复制
    ├── partition.py   ← 复制
    └── fat_fs.py      ← 复制
```

优点：独立，不受子模块更新影响。
缺点：手动同步，许可证需注明来源。

### 最终建议

**使用方案 A**（子模块 + 直接实例化），因为：
- 避免许可证追踪问题（子模块的 LICENSE 自动保留）
- git 自动同步
- `HDIImage` 和 `FATFilesystem` 可以直接 `from <path> import`，不触发 registry
- 如需 `open_image()` 自动识别，只需导入 `plugins/core/pc98_formats.py` 注册即可

```python
# tools/inject_hdi.py 中的实际用法：
import sys, os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIDGE_DIR = os.path.join(PROJECT_ROOT, "ref_projects", "98Bridge")
sys.path.insert(0, BRIDGE_DIR)

# 注册格式（注册动作在模块级别，import 即注册）
import plugins.core.pc98_formats   # noqa: F401, 注册 .hdi → HDIImage
from disk_image import open_image   # 现在可以使用 open_image()
from fat_fs import FATFilesystem

disk = open_image("msdos5.hdi")
fs = FATFilesystem(disk)
```

或者更简洁的方式（跳过 registry）：

```python
from disk_image import HDIImage
from fat_fs import FATFilesystem

disk = HDIImage("msdos5.hdi")        # 直接构造
fs = FATFilesystem(disk)              # FATFilesystem 内部会自动调用 partition.detect_partitions()
```

**两种方式都经测试可用。** 推荐用第二种（直接构造），减少对 registry 的依赖。
