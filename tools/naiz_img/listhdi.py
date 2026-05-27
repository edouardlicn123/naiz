"""List all files in HDI."""
import sys
from .hdi import HDIImage
from .fat import NAIZFatFS

def list_tree(entry, indent=0):
    prefix = '  ' * indent
    if entry.is_directory:
        print(f"{prefix}[{entry.display_name}]")
        for child in entry.children.values():
            list_tree(child, indent + 1)
    else:
        print(f"{prefix}{entry.display_name:20s} cluster={entry.cluster} size={entry.size}")

def main():
    img = HDIImage(sys.argv[1])
    fs = NAIZFatFS(img)
    list_tree(fs.root)

if __name__ == '__main__':
    main()
