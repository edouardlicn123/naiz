"""
Extract a file from an HDI image by path.

Usage:
    python -m tools.naiz_img.extract <hdi_path> <file_path> [output_path]
"""
import sys, os
from .hdi import HDIImage
from .fat import NAIZFatFS

def find_entry(fs, path):
    parts = path.upper().replace('\\', '/').strip('/').split('/')
    parts = [p for p in parts if p]
    cur = fs.root
    for i, part in enumerate(parts):
        if part not in cur.children:
            return None
        cur = cur.children[part]
    return cur

def main():
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    hdi_path = sys.argv[1]
    file_path = sys.argv[2]
    output = sys.argv[3] if len(sys.argv) > 3 else None
    img = HDIImage(hdi_path)
    fs = NAIZFatFS(img)
    entry = find_entry(fs, file_path)
    if entry is None:
        print(f"NOT FOUND: {file_path}", file=sys.stderr)
        sys.exit(1)
    data = fs.read_file(entry)
    if output:
        with open(output, 'wb') as f:
            f.write(data)
        print(f"Extracted {len(data)} bytes -> {output}")
    else:
        sys.stdout.buffer.write(data)

if __name__ == '__main__':
    main()
