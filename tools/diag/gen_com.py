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
import struct
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


@preset("serialwrite", "Init COM1 via direct uPD8251 port I/O (0x30/0x32), send 'Hello from DOS!\\r\\n', exit")
def make_serialwrite():
    # PC-9821 BIOS has NO INT 14h handler (see FAQ 9.3), so the engine and
    # this test talk directly to the uPD8251: 0x30 = data, 0x32 = cmd/status.
    # Mirror the engine reset sequence, but pace each byte on TXRDY so the
    # very first byte is not swallowed while the UART is still settling.
    code = bytearray()
    msg = b'Hello from DOS!\r\n'
    msg_off = 0x160
    entry_off = 0x100

    # uPD8251 reset: 3x dummy write + software reset, then mode, then enable.
    code += b'\xba\x32\x00'             # mov dx, 0x32  (SERIAL_CMD)
    code += b'\xb0\x00'                 # mov al, 0x00 (dummy)
    code += b'\xee\xee\xee'             # out dx, al x3
    code += b'\xb0\x40\xee'             # mov al, 0x40 (CMD_RESET); out dx, al
    code += b'\xb0\x4e\xee'             # mov al, 0x4E (mode 9600 8N1); out dx, al
    code += b'\xb0\x27\xee'             # mov al, 0x27 (TXEN|RXEN|RTS|DTR); out dx, al
    code += b'\xbe' + struct.pack('<H', msg_off)  # mov si, offset msg
    code += b'\xb9' + struct.pack('<H', len(msg))  # mov cx, len(msg)
    # offsets: loop@23, wait_tx@31, tx_ready@42, delay@51, done@60
    code += b'\xac'                     # loop: lodsb
    code += b'\x24\x7f'                 #       and al, 0x7F
    code += b'\x8a\xe0'                 #       mov ah, al
    code += b'\xbb\xff\xff'             #       mov bx, 0xFFFF (timeout guard)
    code += b'\xba\x32\x00'             # wait_tx: mov dx, 0x32 (SERIAL_STATUS)
    code += b'\xec'                     #       in al, dx
    code += b'\xa8\x01'                 #       test al, 0x01 (TXRDY)
    code += b'\x75\x03'                 #       jnz tx_ready
    code += b'\x4b'                     #       dec bx
    code += b'\x75\xf5'                 #       jnz wait_tx (disp -11)
    code += b'\x8a\xc4'                 # tx_ready: mov al, ah
    code += b'\xba\x30\x00'             #       mov dx, 0x30 (SERIAL_DATA)
    code += b'\xee'                     #       out dx, al
    code += b'\xbb\xc8\x00'             #       mov bx, 200 (inter-byte delay)
    code += b'\xba\x32\x00'             # delay: mov dx, 0x32 (SERIAL_STATUS)
    code += b'\xec'                     #       in al, dx
    code += b'\x4b'                     #       dec bx
    code += b'\x75\xf9'                 #       jnz delay (disp -7)
    code += b'\xe2\xdb'                 #       loop loop (disp -37)
    code += b'\xb8\x4c\x02'             # done: mov ax, 0x4C02
    code += b'\xcd\x21'                 #       int 21h

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
        if 0x10E + len(filename) + len(data) > 0xFFFF:
            print("[gen_com] ERROR: create+data exceeds 64KB COM limit")
            sys.exit(1)
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


if __name__ == '__main__':
    main()
