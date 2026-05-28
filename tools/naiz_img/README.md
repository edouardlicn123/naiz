# naiz_img — PC-98 Disk Image Toolchain

Self-contained Python package for manipulating PC-98 disk images.
Inspired by [98Bridge](https://github.com/NullMagic2/98Bridge) (MIT).

## Supported formats

| Format | Class | File | Status |
|--------|-------|------|--------|
| Anex86 HDI | `HDIImage` | `hdi.py` | ✅ |
| Anex86 FDI | `FDIImage` | `fdi.py` | ✅ (via HDI) |
| D88/D68/D77 | `D88Image` | `d88.py` | ✅ |
| Raw (headerless) | `RawImage` | `raw.py` | ✅ |
| T98-Next NHD | `NHDImage` | `nhd.py` | ✅ |

## Usage

```python
from naiz_img import open_image, NAIZFatFS

img = open_image("tools/base_msdos5_scsi_48m.hdi")
fs = NAIZFatFS(img)
for path, entry in fs.walk():
    print(path)
```

### CLI: inject game files into MS-DOS base HDI

```bash
python -m tools.naiz_img.inject --game demo-A1
python -m tools.naiz_img.inject --game demo-A1 --yes
python -m tools.naiz_img.inject --game mygame --output disks/mygame.hdi
python -m tools.naiz_img.inject --game demo-A1 --list-files   # browse base
```

## License references

- All code references the design of 98Bridge (MIT) but is independently written.
- See each source file for attribution header.
