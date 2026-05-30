"""
Generate DOS COM test files for diagnostics.

Usage:
    python -m tools.diag.gen_com --preset rwcheck -o /tmp/rwcheck.com
    python -m tools.diag.gen_com --preset vramwrite -o /tmp/vram.com
    python -m tools.diag.gen_com --preset serialwrite -o /tmp/serial.com
    python -m tools.diag.gen_com --list-presets
    python -m tools.diag.gen_com -o /tmp/test.com --create TEST.LOG --data "HELLO"
"""

import argparse
import sys


PRESETS = {}


def preset(name, desc):
    def wrap(fn):
        PRESETS[name] = (fn, desc)
        return fn
    return wrap


def _asm_bytes(code_bytes):
    return code_bytes


@preset("rwcheck", "Create RWCHECK.LOG, write 'RWCHECK OK', exit (verify DOS file I/O)")
def make_rwcheck():
    code = bytearray()
    filename = b'RWCHECK.LOG\x00'
    data = b'RWCHECK OK\r\n'
    data_len = len(data)

    filename_off = 0x10E
    data_off = filename_off + len(filename)
    entry_off = 0x100

    def off(addr):
        return addr - entry_off

    code += b'\xba' + struct.pack('<H', filename_off)
    code += b'\xb9\x00\x00'
    code += b'\xb8\x3c\x00'
    code += b'\xcd\x21'
    code += b'\x72\x0d'
    code += b'\x8b\xd8'
    code += b'\xba' + struct.pack('<H', data_off)
    code += b'\xb9' + struct.pack('<H', data_len)
    code += b'\xb8\x40\x00'
    code += b'\xcd\x21'
    code += b'\xb8\x4c\x00'
    code += b'\xcd\x21'
    code += b'\xb8\x4c\x01'
    code += b'\xcd\x21'

    while len(code) < filename_off - entry_off:
        code.append(0x00)
    code += filename + data
    return bytes(code)


@preset("vramwrite", "Write 'ABCD' to text VRAM @ 0xA000:0, then HLT (verify screen output)")
def make_vramwrite():
    code = bytearray()
    code += b'\xb8\x00\xa0'
    code += b'\x8e\xc0'
    code += b'\x26\xc6\x06\x00\x00\x41'
    code += b'\x26\xc6\x06\x02\x00\x42'
    code += b'\x26\xc6\x06\x04\x00\x43'
    code += b'\x26\xc6\x06\x06\x00\x44'
    code += b'\xf4'
    code += b'\xeb\xfe'
    return bytes(code)


@preset("serialwrite", "Init COM1 (INT 14h AH=0), send 'Hello from DOS!\\r\\n', exit")
def make_serialwrite():
    code = bytearray()
    msg = b'Hello from DOS!\r\n'
    msg_off = 0x120
    entry_off = 0x100

    code += b'\xba\x00\x00'             # mov dx, 0  (COM1)
    code += b'\xb8\x00\xe3'             # mov ax, 0x00E3 (AH=0 init, AL=0xE3)
    code += b'\xcd\x14'                 # int 14h
    code += b'\xbe' + struct.pack('<H', msg_off)  # mov si, offset msg
    code += b'\xb9' + struct.pack('<H', len(msg))  # mov cx, len(msg)
                                        # loop:
    code += b'\xac'                     #   lodsb   (al = [si], si++)
    code += b'\x24\x7f'                 #   and al, 0x7F
    code += b'\xb4\x01'                 #   mov ah, 1
    code += b'\xba\x00\x00'             #   mov dx, 0  (COM1)
    code += b'\xcd\x14'                 #   int 14h
    code += b'\xe2\xf5'                 #   loop loop
                                        # done:
    code += b'\xb8\x4c\x02'             # mov ax, 0x4C02
    code += b'\xcd\x21'                 # int 21h

    while len(code) < msg_off - entry_off:
        code.append(0x00)
    code += msg
    return bytes(code)


def list_presets():
    print("Available presets:")
    for name in sorted(PRESETS):
        fn, desc = PRESETS[name]
        print(f"  {name:15s}  {desc}")


def main():
    parser = argparse.ArgumentParser(description="Generate DOS COM test files")
    parser.add_argument('-o', '--output', help='Output COM file path')
    parser.add_argument('--preset', choices=list(PRESETS.keys()), help='Use a built-in test preset')
    parser.add_argument('--list-presets', action='store_true', help='List available presets')
    parser.add_argument('--create', help='Filename to create (for custom COM)')
    parser.add_argument('--data', help='Data to write (for custom COM)')
    args = parser.parse_args()

    if args.list_presets:
        list_presets()
        sys.exit(0)

    if not args.output:
        parser.print_help()
        sys.exit(1)

    if args.preset:
        fn, desc = PRESETS[args.preset]
        code = fn()
        print(f"[gen_com] Generating '{args.preset}': {desc}")
        print(f"[gen_com] Output: {args.output}")
        print(f"[gen_com] Size:   {len(code)} bytes")
        with open(args.output, 'wb') as f:
            f.write(code)
        sys.exit(0)

    if args.create and args.data:
        print("[gen_com] Generating custom COM file")
        code = bytearray()
        filename = args.create.encode('ascii') + b'\x00'
        data = args.data.encode('ascii')
        filename_off = 0x10E
        data_off = filename_off + len(filename)
        entry_off = 0x100

        code += b'\xba' + struct.pack('<H', filename_off)
        code += b'\xb9\x00\x00'
        code += b'\xb8\x3c\x00'
        code += b'\xcd\x21'
        code += b'\x72\x0d'
        code += b'\x8b\xd8'
        code += b'\xba' + struct.pack('<H', data_off)
        code += b'\xb9' + struct.pack('<H', len(data))
        code += b'\xb8\x40\x00'
        code += b'\xcd\x21'
        code += b'\xb8\x4c\x00'
        code += b'\xcd\x21'
        code += b'\xb8\x4c\x01'
        code += b'\xcd\x21'

        while len(code) < filename_off - entry_off:
            code.append(0x00)
        code += filename + data

        print(f"[gen_com] Output: {args.output}")
        print(f"[gen_com] Size:   {len(code)} bytes")
        print(f"[gen_com] Create: {args.create}")
        print(f"[gen_com] Write:  {len(data)} bytes")
        with open(args.output, 'wb') as f:
            f.write(code)
        sys.exit(0)

    parser.print_help()
    sys.exit(1)


import struct
if __name__ == '__main__':
    main()
