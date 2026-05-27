"""Extract file from HDI by path."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'naiz_img'))
from hdi import HDIImage
from fat import NAIZFatFS

def find_file(fs, path):
    parts = path.upper().replace('\\', '/').strip('/').split('/')
    dirs = [p for p in parts if p]

    # Start with root
    current = fs.root
    for i, part in enumerate(dirs):
        found = None
        for entry in current.children:
            ename = entry.name.upper().rstrip(' ') if entry.name else ''
            if ename == part.rstrip(' '):
                found = entry
                break
        if found is None:
            return None
        if i == len(dirs) - 1:
            return found
        # Descend into subdirectory
        if found.attr & 0x10:
            current = found
        else:
            return None
    return None

img = HDIImage(sys.argv[1])
fs = NAIZFatFS(img)
path = sys.argv[2]
entry = find_file(fs, path)
if entry is None:
    print(f"NOT FOUND: {path}")
    sys.exit(1)
data = entry.read()
sys.stdout.buffer.write(data)
