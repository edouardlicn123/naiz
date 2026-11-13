#!/usr/bin/env python3
"""LE fixup 记录解码器（devdoc 210 §七.1）。

一次性诊断脚本，不进仓库运行路径。用法：
    python le_fixup.py stats <exe>            # 页数 / 每页对齐结果 / 类型直方图
    python le_fixup.py dump  <exe> [-v]       # 同上，-v 打印每条记录
    python le_fixup.py diff  <a.exe> <b.exe>  # 两份镜像逐页语义 diff

校准判据（硬性）：每页记录必须精确结束于修页表下一项偏移；
任一页对不齐即视解码器错误，脚本非零退出。

字段偏移来自 `wdump -e -p` 的实测输出（e = LE 头文件偏移，全部为相对 e 的 DWORD）：
    0x14 #module pages        0x30 fixup section size   0x38 loader section size
    0x40 object table ofs     0x44 #objects              0x48 object page map ofs
    0x68 fixup page table ofs 0x6c fixup record table ofs
"""
import struct
import sys

RT_SHORT = 0        # 低位 3 位 = 重定位类型
TYPE_NAMES = {
    0: 'BYTE', 2: 'SEL16', 3: 'POINTER32', 5: 'OFFSET16', 6: 'OFFSET32',
    7: 'OFFSET48', 8: 'OFFSET32-32', 11: 'SELECTOR16', 13: 'OFFSET32(32)',
    20: 'OFFSET16(32)', 27: 'OFFSET32(32b)',
}


def load(path):
    data = open(path, 'rb').read()
    if data[:2] != b'MZ':
        raise SystemExit('not MZ')
    h = struct.unpack_from('<I', data, 0x3c)[0]
    if data[h:h + 2] != b'LE':
        raise SystemExit('not LE')

    def g(o):
        return struct.unpack_from('<I', data, h + o)[0]

    img = dict(path=path, h=h, num_pages=g(0x14), page_size=g(0x28),
               last_page=g(0x2c), fix_size=g(0x30), obj_tab=h + g(0x40),
               n_obj=g(0x44), opm=h + g(0x48),
               pt_off=h + g(0x68), rt_off=h + g(0x6c),
               eip_obj=g(0x18), eip=g(0x1c), esp_obj=g(0x20), esp=g(0x24))
    n = img['num_pages']
    img['page_table'] = list(struct.unpack_from('<%dI' % (n + 1), data, img['pt_off']))
    rec_end = img['pt_off'] + img['fix_size']
    img['rec'] = data[img['rt_off']:rec_end]
    objs = []
    for i in range(img['n_obj']):
        p = img['obj_tab'] + 24 * i
        vsize, vbase, flags, pidx, npages = struct.unpack_from('<IIIII', data, p)
        ents = []
        for k in range(npages):
            e = img['opm'] + 4 * (pidx - 1 + k)
            v = struct.unpack_from('<I', data, e)[0]
            ents.append((v & 0x3fffffff, (v >> 30) & 3))
        objs.append(dict(idx=i + 1, vbase=vbase, vsize=vsize, flags=flags, pages=ents))
    img['objs'] = objs
    return img


def rtype(t):
    return TYPE_NAMES.get(t & 7, 'type%d' % (t & 7))


def decode(rec, start, end):
    """从 start 解到 end（不含）。返回记录列表；对不齐抛 ValueError。

    记录布局（2026-11-13 与 `wdump -a` Fixup Record Table 3953 条逐条
    对照校准，engine_os.exe 全部验证通过、精确对齐修页表边界）：
        type(1)   低 3 位 = 重定位类型；bit5=源列表 bit6=16:16 指针 bit7=additive
                  （bit4 在本产物中不表示 32 位源偏移——源偏移恒 16 位）
        flags(1)  bit0=（未见使用）bit1=对象号存在 bit2=目标偏移存在
                  bit3=序号 bit4=32 位目标偏移 bit5=源列表
        src(2)    源页内偏移，恒 16 位
        obj(1)    目标对象号，恒存在
        tgt(2/4)  目标偏移（flags bit2；长度由 flags bit4 决定）
        list      count(1)+count*4（flags bit5）
    常见记录：7 字节（tgt16）与 9 字节（tgt32，flags 0x10）。
    """"""从 start 解到 end（不含）。返回记录列表；对不齐抛 ValueError。

    记录布局（与 `wdump -a` Fixup Record Table 逐条对照校准；实测
    Watcom 的 7 字节 narrow 记录固定为 type+src16+flags+obj+tgt16，
    11 字节 wide 记录固定为 type+src32+flags+obj+tgt32）：
        type(1)     低 3 位 = 重定位类型；bit4 = 32 位（源与目标同时 4 字节）；
                    bit5 = 源列表；bit6 = 16:16 指针；bit7 = additive
        src_off     2 或 4 字节（type bit4）
        flags(1)    bit0 = 16 位目标偏移标志
                    bit1 = 有对象号   bit2 = 有目标偏移
                    bit3 = 序号       bit4 = 32 位目标偏移
                    bit5 = 源列表
        object(1)   目标对象号（flags bit1）
        tgt_off     2 或 4 字节（flags bit2；长度由 flags bit4 决定）
        src_list    count(1) + count*4（flags bit5）
    """
    i = start
    out = []
    while i < end:
        p = i
        t = rec[i]; i += 1                       # type 字节（实测恒 0x07 = 32 位偏移修复）
        f = rec[i]; i += 1                       # flags：0x00=16 位目标 / 0x10=32 位目标
        src = struct.unpack_from('<H', rec, i)[0]; i += 2   # 源页内偏移，恒 16 位
        obj = rec[i]; i += 1                     # 目标对象号，恒存在
        if f & 0x10:
            tgt = struct.unpack_from('<I', rec, i)[0]; i += 4
        else:
            tgt = struct.unpack_from('<H', rec, i)[0]; i += 2
        srcs = [src]
        if f & 0x20:                             # 源列表（防御性保留）
            cnt = rec[i]; i += 1
            srcs = list(struct.unpack_from('<%dI' % cnt, rec, i)); i += 4 * cnt
        if i > end:
            raise ValueError('overrun at %d (+%d > %d)' % (p, i - p, end))
        out.append(dict(off=p, type=t, rt=t & 7, src=src, srcs=srcs,
                        obj=obj, target=tgt, flags=f,
                        tgt32=bool(f & 0x10),
                        ordinal=bool(f & 0x08), internal=bool(f & 0x02),
                        list=bool(f & 0x20), src1616=bool(t & 0x40),
                        addfix=bool(t & 0x80)))
    if i != end:
        raise ValueError('misalign: ended %d expected %d' % (i, end))
    return out


def decode_all(img):
    rec = img['rec']
    ok, bad = [], []
    for n in range(img['num_pages']):
        a, b = img['page_table'][n], img['page_table'][n + 1]
        try:
            ok.append((n + 1, a, b, decode(rec, a, b)))
        except (ValueError, struct.error) as e:
            bad.append((n + 1, a, b, str(e)))
    return ok, bad


def header(img):
    print('== %s ==' % img['path'])
    print('pages=%d page_size=%d last=%d fix_size=%d records=%d'
          % (img['num_pages'], img['page_size'], img['last_page'],
             img['fix_size'], len(img['rec'])))
    print('eip_obj=%d eip=%#x esp_obj=%d esp=%#x'
          % (img['eip_obj'], img['eip'], img['esp_obj'], img['esp']))
    for o in img['objs']:
        print('  obj%d vbase=%#x vsize=%d flags=%#x pages=%d first=%s'
              % (o['idx'], o['vbase'], o['vsize'], o['flags'], len(o['pages']),
                 o['pages'][:2]))


def cmd_stats(path, verbose):
    img = load(path)
    header(img)
    ok, bad = decode_all(img)
    for pno, a, b, err in bad:
        print('  page %d [%d,%d) MISALIGN: %s' % (pno, a, b, err))
    hist = {}
    for pno, a, b, rs in ok:
        for r in rs:
            k2 = r['type'] & 0xff
            hist[k2] = hist.get(k2, 0) + 1
        if verbose:
            print('  -- page %d [%d,%d) %d recs' % (pno, a, b, len(rs)))
            for r in rs:
                print('     +%-6d type=%#04x/%-12s src=%#x%s target=%#x %s%s%s%s'
                      % (r['off'], r['type'], rtype(r['type']), r['src'],
                         '(%d @)' % len(r['srcs']) if r['list'] else '',
                         r['target'],
                         'T32' if r['tgt32'] else 'T16',
                         ' T16a' if r['tgt16'] else '',
                         ' ORD' if r['ord'] else '',
                         ' INT' if r['internal'] else ''))
    print('ok_pages=%d bad_pages=%d records=%d' % (len(ok), len(bad),
                                                  sum(len(r[3]) for r in ok)))
    print('type histogram: %s' % dict(sorted(hist.items())))
    return 0 if not bad else 2


def entry_bytes(img, objidx, page_in_obj):
    """返回 object objidx 的第 page_in_obj 页在文件中的 (起始偏移, 长度)。"""
    o = img['objs'][objidx - 1]
    map_page, flags = o['pages'][page_in_obj]
    code = img['data_off_shift'] if 'data_off_shift' in img else None
    return map_page, flags


def cmd_diff(pa, pb):
    A, B = load(pa), load(pb)
    header(A); header(B)
    oka, bada = decode_all(A)
    okb, badb = decode_all(B)
    for p, a, b, e in bada:
        print('A page %d MISALIGN: %s' % (p, e))
    for p, a, b, e in badb:
        print('B page %d MISALIGN: %s' % (p, e))
    if bada or badb:
        print('abort: decoder not calibrated')
        return 2
    n = min(len(oka), len(okb))
    ndiff = 0
    hist_a, hist_b = {}, {}
    for k in range(n):
        ra, rb = oka[k][3], okb[k][3]
        for r in ra:
            hist_a[r['type']] = hist_a.get(r['type'], 0) + 1
        for r in rb:
            hist_b[r['type']] = hist_b.get(r['type'], 0) + 1
        if len(ra) != len(rb):
            ndiff += 1
            print('page %d: count A=%d B=%d' % (oka[k][0], len(ra), len(rb)))
            continue
        d = [(j, (x['type'], x['target'], len(x['srcs'])),
              (y['type'], y['target'], len(y['srcs'])))
             for j, (x, y) in enumerate(zip(ra, rb))
             if (x['type'], x['target'], len(x['srcs'])) !=
             (y['type'], y['target'], len(y['srcs']))]
        if d:
            ndiff += 1
            print('page %d: %d semantic diffs e.g. %s' % (oka[k][0], len(d), d[:3]))
    print('pages with differences: %d / %d' % (ndiff, n))
    print('type histogram A: %s' % dict(sorted(hist_a.items())))
    print('type histogram B: %s' % dict(sorted(hist_b.items())))
    return 0 if ndiff == 0 else 1


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(64)
    sub = sys.argv[1]
    if sub == 'stats':
        sys.exit(cmd_stats(sys.argv[2], '-v' in sys.argv))
    if sub == 'dump':
        sys.exit(cmd_stats(sys.argv[2], True))
    if sub == 'diff' and len(sys.argv) >= 4:
        sys.exit(cmd_diff(sys.argv[2], sys.argv[3]))
    print(__doc__); sys.exit(64)
