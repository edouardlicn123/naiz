import struct

with open('games/demo-A1/SCENE.DAT', 'rb') as f:
    data = f.read()

comp_size = struct.unpack('<I', data[8:12])[0]
compressed = data[12:12+comp_size]

def lz4_decompress(src):
    ip = 0
    dst = bytearray()
    while ip < len(src):
        token = src[ip]; ip += 1
        lit_len = token >> 4
        if lit_len == 15:
            while True:
                b = src[ip]; ip += 1; lit_len += b
                if b != 255: break
        dst.extend(src[ip:ip+lit_len]); ip += lit_len
        if ip >= len(src): break
        offset = struct.unpack('<H', src[ip:ip+2])[0]; ip += 2
        match_len = (token & 0x0F) + 4
        if (token & 0x0F) == 15:
            while True:
                b = src[ip]; ip += 1; match_len += b
                if b != 255: break
        match_start = len(dst) - offset
        for i in range(match_len):
            dst.append(dst[match_start + i])
    return bytes(dst)

decompressed = lz4_decompress(compressed)
print(f'Decompressed: {len(decompressed)} bytes')
print()

# Step through scene VM opcodes
pc = 0
textinbox = False
next_text_num = 0

while pc < len(decompressed):
    op = decompressed[pc]
    if pc >= len(decompressed):
        break

    if op == 0x00:  # LOAD SCENE
        s = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        print(f'  [{pc:3d}] OP_LOAD_SCENE({s})')
        pc += 3
    elif op == 0x01:  # SKIP
        skip = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        print(f'  [{pc:3d}] OP_SKIP(+{skip})')
        pc += 3
    elif op == 0x02:  # SKIP_IF_Z
        skip = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        print(f'  [{pc:3d}] OP_SKIP_IF_Z(+{skip})')
        pc += 3
    elif op == 0x0F:  # WAIT
        print(f'  [{pc:3d}] OP_WAIT')
        pc += 1
    elif op == 0x10:  # SHOW TEXT (with state)
        if textinbox:
            print(f'  [{pc:3d}] OP_SHOW_TEXT → CLEAR (TEXTINBOX set)')
            textinbox = False
        else:
            print(f'  [{pc:3d}] OP_SHOW_TEXT (text[{next_text_num}]) → TEXTINBOX')
            next_text_num += 1
            textinbox = True
        pc += 0
        # Since PC doesn't advance, break to avoid infinite loop
        # In actual VM, this pauses via control_process(0)
        print(f'  [{pc:3d}] (VM paused at PC={pc}, resume advances past? No, PC unchanged)')
        break
    elif op == 0x11:  # SHOW_TEXT_NUM
        tnum = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        print(f'  [{pc:3d}] OP_SHOW_TEXT_NUM({tnum}) → text_num = {tnum}', end='')
        pc += 3
        # Falls through to 0x10
        next_text_num = tnum
        if pc < len(decompressed) and decompressed[pc] == 0x10:
            pc -= 1  # re-read the 0x10 we're about to fall through to
        continue
    elif op == 0x12:  # SET_CHAR
        cnum = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        print(f'  [{pc:3d}] OP_SET_CHAR({cnum})')
        pc += 3
    elif op == 0x13:  # CLEAR_TEXT
        print(f'  [{pc:3d}] OP_CLEAR_TEXT')
        pc += 1
    elif op == 0x14:  # YN_CHOICE
        print(f'  [{pc:3d}] OP_YN_CHOICE')
        pc += 1
    elif op == 0x15:  # 2CHOICE
        var = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        t0 = struct.unpack('<H', decompressed[pc+3:pc+5])[0]
        print(f'  [{pc:3d}] OP_2CHOICE(var={var}, text0={t0})')
        pc += 5
    elif op == 0x18:  # BFADE_IN
        arg = decompressed[pc+1]
        amt = arg & 0x07; spd = (arg >> 3) & 0x1F
        print(f'  [{pc:3d}] OP_BFADE_IN(amt={amt}, speed={spd})')
        pc += 2
    elif op == 0x19:  # BFADE_OUT
        arg = decompressed[pc+1]
        amt = arg & 0x07; spd = (arg >> 3) & 0x1F
        print(f'  [{pc:3d}] OP_BFADE_OUT(amt={amt}, speed={spd})')
        pc += 2
    elif op == 0x1A:  # WFADE_IN
        arg = decompressed[pc+1]
        amt = arg & 0x07; spd = (arg >> 3) & 0x1F
        print(f'  [{pc:3d}] OP_WFADE_IN(amt={amt}, speed={spd})')
        pc += 2
    elif op == 0x1B:  # WFADE_OUT
        arg = decompressed[pc+1]
        amt = arg & 0x07; spd = (arg >> 3) & 0x1F
        print(f'  [{pc:3d}] OP_WFADE_OUT(amt={amt}, speed={spd})')
        pc += 2
    elif op == 0x1C:  # PFADE_IN
        arg = decompressed[pc+1]
        amt = arg & 0x07; spd = (arg >> 3) & 0x1F
        print(f'  [{pc:3d}] OP_PFADE_IN(amt={amt}, speed={spd})')
        pc += 2
    elif op == 0x1D:  # PFADE_OUT
        arg = decompressed[pc+1]
        amt = arg & 0x07; spd = (arg >> 3) & 0x1F
        print(f'  [{pc:3d}] OP_PFADE_OUT(amt={amt}, speed={spd})')
        pc += 2
    elif op == 0x1E:  # HUE_ROTATE
        arg = decompressed[pc+1]
        print(f'  [{pc:3d}] OP_HUE_ROTATE(arg={arg:02x})')
        pc += 2
    elif op == 0x1F:  # SHAKE
        arg = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        amp = arg & 0x003F
        period = (arg >> 6) & 0x001F
        damp = (arg >> 11) & 0x001F
        print(f'  [{pc:3d}] OP_SHAKE(amp={amp}, period={period}, damp={damp})')
        pc += 3
    elif op == 0x20:  # MULTI_CHOICE
        var = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        v0 = struct.unpack('<H', decompressed[pc+3:pc+5])[0]
        v1 = struct.unpack('<H', decompressed[pc+5:pc+7])[0]
        print(f'  [{pc:3d}] OP_MULTI_CHOICE(var={var}, v0={v0}, v1={v1})')
        pc += 7
    elif op == 0x21:  # 3CHOICE
        var = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        v0 = struct.unpack('<H', decompressed[pc+3:pc+5])[0]
        v1 = struct.unpack('<H', decompressed[pc+5:pc+7])[0]
        v2 = struct.unpack('<H', decompressed[pc+7:pc+9])[0]
        print(f'  [{pc:3d}] OP_3CHOICE(var={var}, v0={v0}, v1={v1}, v2={v2})')
        pc += 9
    elif op == 0x23:  # SWAP_Z_N
        print(f'  [{pc:3d}] OP_SWAP_Z_N')
        pc += 1
    elif op == 0x24:  # SET_VAR_IMM
        var = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        val = struct.unpack('<H', decompressed[pc+3:pc+5])[0]
        print(f'  [{pc:3d}] OP_SET_VAR_IMM(v{var}, {val})')
        pc += 5
    elif op == 0x25:  # SET_VAR_VAR
        var = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        svar = struct.unpack('<H', decompressed[pc+3:pc+5])[0]
        print(f'  [{pc:3d}] OP_SET_VAR_VAR(v{var}, v{svar})')
        pc += 5
    elif op == 0x28:  # CMP_VAR_IMM
        var = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        val = struct.unpack('<H', decompressed[pc+3:pc+5])[0]
        print(f'  [{pc:3d}] OP_CMP_VAR_IMM(v{var}, {val})')
        pc += 5
    elif op == 0x29:  # CMP_VAR_VAR
        var = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        var2 = struct.unpack('<H', decompressed[pc+3:pc+5])[0]
        print(f'  [{pc:3d}] OP_CMP_VAR_VAR(v{var}, v{var2})')
        pc += 5
    elif op == 0x2A:  # ADD_VAR_IMM
        var = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        val = struct.unpack('<H', decompressed[pc+3:pc+5])[0]
        print(f'  [{pc:3d}] OP_ADD_VAR_IMM(v{var}, {val})')
        pc += 5
    elif op == 0x2C:  # SUB_VAR_IMM
        var = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        val = struct.unpack('<H', decompressed[pc+3:pc+5])[0]
        print(f'  [{pc:3d}] OP_SUB_VAR_IMM(v{var}, {val})')
        pc += 5
    elif op == 0x2E:  # GET_FLAG
        var = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        print(f'  [{pc:3d}] OP_GET_FLAG(v{var})')
        pc += 3
    elif op == 0x2F:  # SET_FLAG
        var = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        print(f'  [{pc:3d}] OP_SET_FLAG(v{var})')
        pc += 3
    elif op == 0x30:  # LOAD_BG
        bg = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        print(f'  [{pc:3d}] OP_LOAD_BG({bg})')
        pc += 3
    elif op == 0x31:  # UNKNOWN (sprite?)
        val = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        print(f'  [{pc:3d}] OP_SPRITE?({val})')
        pc += 3
    elif op == 0x32:
        val = struct.unpack('<H', decompressed[pc+1:pc+3])[0]
        print(f'  [{pc:3d}] OP_32?({val})')
        pc += 3
    elif op == 0xFF:
        print(f'  [{pc:3d}] OP_END')
        pc += 1
        break
    else:
        print(f'  [{pc:3d}] OP_UNKNOWN({op:02x}) raw_bytes={decompressed[pc:pc+8].hex()}')
        pc += 1
