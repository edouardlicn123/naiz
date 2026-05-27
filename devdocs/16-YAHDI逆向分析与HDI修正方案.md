# YAHDI 逆向分析与 HDI 修正方案

## 现状

当前 `tools/hdi_tool/hdi_img.py` 手动构造的 `DOS62.hdi` 的启动链是：

```
IPL(NP2kai) → [LBA 0] MBR → 读 VBR → [LBA 32] VBR → 读根目录 → 加载 IO.SYS
```

strace 证明 VBR 已经能正确读取根目录、找到 `IO.SYS`、并开始加载数据到 `LBA 256-379`。但：
- 读取次数是正常的 8 倍（`O_DIRECT` 导致每次 INT 1Bh 只消耗 256 字节，8 次才读完 8 扇区）
- 无法确认是否最终到达 DOS 提示符
- 手动构造的 BPB 参数可能和真实的 FORMAT.EXE 不一致

## 方案

### 1. 下载参考镜像

从 Internet Archive 下载 YAHDI（77.5 MB，RAR 压缩）：

```bash
wget -c https://archive.org/download/YAHDI/YAHDI.rar -O /tmp/YAHDI.rar
```

或下载更小的 win95.7z（31.7 MB，内含完整 MS-DOS 6.2）：

```bash
wget -c https://archive.org/download/win95-pc98-hdi/win95.7z -O /tmp/win95.7z
```

### 2. 解压并提取 MBR/VBR/FAT 结构

```bash
# 解压
mkdir -p /tmp/yahdi && cd /tmp/yahdi
unrar x /tmp/YAHDI.rar
# 或
7z x /tmp/win95.7z

# 提取 MBR
dd if=/tmp/yahdi/YAHDI.hdi bs=512 skip=4096 count=1 of=mbr.bin   # HDI header 4096B
# 或直接用 Python 处理
```

### 3. Python 分析脚本

写 `tools/hdi_tool/analyze_hdi.py`，对给定 HDI 输出以下信息：

```
=== HDI Header ===
Raw offset:      4096
Total sectors:   X
Geometry:        C/H/S

=== MBR (LBA 0) ===
Boot code:       <first 32 bytes hex>
Partition table:
  #0: type=06(LBA)
    bootable=80
    start CHS:  (0/1/1)
    start LBA:  32
    size:       Y sectors
  #1-3:         empty

=== VBR (LBA = partition_start) ===
JMP:             EB 45
OEM:             "NEC  5.0"
BytesPerSector:  512
SectorsPerClust: X
ReservedSectors: X
NumFATs:         2
RootEntries:     X
TotalSectors16:  0
Media:           F8
FatSize16:       X
SPT:             32
Heads:           8
Hidden:          Y (partition start LBA)
TotalSectors32:  Z

=== Boot code analysis ===
[0x42] data_offset (low): X
[0x44] byte_divisor:      X
[0x3E] hidden_low:        X

=== Layout Summary ===
LBA 0:            MBR
LBA 1..31:        gap
LBA 32:           Partition start
  +0:             VBR
  +Reserved-1:    slack
  +Reserved:      FAT1 (F sectors)
  +Reserved+F:    FAT2 (F sectors)
  +Reserved+2F:   Root dir (R sectors)
  +Reserved+2F+R: Data area

=== Alignment Check ===
Root dir LBA:      X (8-aligned? Y/N)
Data area LBA:     X (8-aligned? Y/N)
FAT1 LBA:          X (8-aligned? Y/N)

=== O_DIRECT Verification ===
Every critical read crosses a 4096-byte boundary? Y/N
```

### 4. 比对分析项

| 比对项目 | 我们的值 (hdi_img.py) | YAHDI 值 | 差异 | 行动 |
|----------|----------------------|-----------|------|------|
| ReservedSectors | 8 | ? | ? | 调整 |
| SectorsPerCluster | 4 | ? | ? | 调整 |
| RootEntries | 512 | ? | ? | 调整 |
| FatSize16 | 92 | ? | ? | 调整 |
| Partition Start LBA | 32 | ? | ? | 调整 |
| [0x42] data offset | 224 | ? | ? | 调整 |
| [0x44] byte divisor | 512 | ? | ? | 调整 |
| MBR boot code | 自定义 | ? | ? | 对比尺寸/逻辑 |
| Root dir 8-aligned | 是 (LBA 224) | ? | ? | 保持/调整 |
| Data area 8-aligned | 是 (LBA 256) | ? | ? | 保持/调整 |

### 5. 根据比对结果修正 hdi_img.py

可能的方向（按优先级）：

#### 方向 A：BPB 参数修正
如果 YAHDI 的 ReservedSectors/FatSize/SectorsPerCluster 与我们的不同，按 YAHDI 的取值调整。

#### 方向 B：MBR 代码改进
如果 YAHDI 的 MBR 引导代码与我们差异大（例如使用 IPL 兼容的 MBR），参考重写。

#### 方向 C：完全采用 YAHDI 的 MBR + VBR
从 YAHDI 提取 LBA 0 和 LBA 32，直接替换到我们的镜像中，只用自己的 FAT/根目录/数据区。这确保引导代码和 BPB 与已知工作镜像完全一致。

### 6. 重新生成和测试

```bash
python tools/hdi_tool/install_dos.py --rebuild

# 用 strace 跟踪确认读取正确
timeout 120 strace -f -e trace=read,write,lseek \
  sdlnp21kai_sdl2 -h1 tools/DOS62.hdi 2>/tmp/np2_strace2.log

# 分析 strace 日志
grep 'read.*4096' /tmp/np2_strace2.log | tail -50
```

### 7. 额外优化：去掉 O_DIRECT

如果上述修改后启动仍然慢（8x 读取放大），考虑编译去掉 O_DIRECT 的 NP2kai：

```bash
# 定位 sasiio.c
grep -r O_DIRECT ~/opencode_work/np2kai/ --include='*.c'

# 去掉 O_DIRECT 标志
sed -i 's/O_DIRECT/0/g' sasiio.c

# 重新编译
make
```

去掉 O_DIRECT 后，每次 INT 1Bh 读取 512 字节直接返回，无需 8 次轮询，启动时间从 ~60s 降到 ~10s。

### 8. 验证 DOS 启动

如果装有 Xvfb，截图验证：

```bash
Xvfb :99 -screen 0 640x480x8 &
DISPLAY=:99 timeout 90 sdlnp21kai_sdl2 -h1 tools/DOS62.hdi &
sleep 85
import -window root dos_screen.png
kill %1
```

或在 `AUTOEXEC.BAT` 中加入 `HOSTDRV.COM` 写文件测试，启动后检查目标文件是否存在。

### 9. 手工修复 FAIL 时的降级方案

如果上述自动修正仍不工作：

- 从 YAHDI 中提取完整 LBA 0-255（MBR + gap + VBR + FAT + 根目录）
- 仅替换自己的数据区（LBA 256+）
- 用 Python 将我们的文件注入到 YAHDI 的 FAT/根目录中

### 10. 文档化最终结果

将 YAHDI 分析得出的 BPB 参数记录到 `devdocs/` 中，作为后续 HDI 创建的标准参照值。
