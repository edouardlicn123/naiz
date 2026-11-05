"""NAIZ_ANIM container (.ANI) v1 — binary format authority.

Single source of truth for building and parsing .ANI animation containers.
No file IO and no business logic lives here (mirrors image_dat.py precedent).

Layout v1 (all little-endian), offsets relative to file start:

    Header (28 bytes)
      0x00  u32   magic     0x5A494E41 ("ANIZ")
      0x04  u16   version   1
      0x06  u8    type      0=fullscreen / 1=cine
      0x07  u8    track     0=pixel / 1=palette
      0x08  u8    fps       nominal: uniform ticks t -> max(1, round(60/t));
                            variable durations -> 0
      0x09  u8    reserved1 must be 0 (loop policy belongs to the player,
                            never the container)
      0x0A  u16   nframes
      0x0C  u16   w
      0x0E  u16   h
      0x10  u32   palsz     palette track: nframes*768 / pixel: 0
      0x14  u32   nblob     pixel: nframes / palette: 1
      0x18  u32   reserved  0 (pads header to 28 bytes)

    Offset table   nblob × u32   MAG blob start offsets
    Tick table     nframes × u16 per-frame 60Hz tick count (>= 1)
    Frame data     nblob × MAG   mag_codec.encode_mag(bpp=8, user_string=b"naiz\\x1a")
    Palette table  [palette]     nframes × 768 raw RGB (R,G,B order)

Tick table sits at a fixed offset (right after the offset table) so a player
can address frame durations without parsing any MAG headers.

Load validation rules L1-L5 (devdoc 78 §4.4); L6 (fullscreen dimensions,
cine play position) belongs to script/import/play layers.
"""

import struct
from dataclasses import dataclass, field

from naiz_lib.mag_constants import (
    MAG_SIGNATURE,
    MAG_USER_TERM,
    MAG_HEADER_SIZE,
)

ANI_MAGIC = 0x5A494E41
ANI_VERSION = 1
ANI_HEADER_SIZE = 28
ANI_PALETTE_BYTES = 768

ANI_TYPE_FULLSCREEN = 0
ANI_TYPE_CINE = 1
ANI_TRACK_PIXEL = 0
ANI_TRACK_PALETTE = 1

_HDR = struct.Struct("<IHBBBBHHHIII")


def _fail(where, msg):
    raise ValueError(f"anim_container: {where}: {msg}")


def mag_blob_length(data):
    """Return total byte length of one MAG blob, or None if malformed.

    Lightweight header probe (signature + user-string terminator + the
    color-stream end offset); does not decompress pixel data.
    """
    if len(data) < 12 or data[0:8] != MAG_SIGNATURE:
        return None
    pos = 12  # signature (8) + machine ID (4)
    while pos < len(data) and data[pos] != MAG_USER_TERM:
        pos += 1
    if pos >= len(data):
        return None
    hdr_start = pos + 1
    if hdr_start + MAG_HEADER_SIZE > len(data):
        return None
    color_off = struct.unpack_from("<I", data, hdr_start + 24)[0]
    color_size = struct.unpack_from("<I", data, hdr_start + 28)[0]
    return hdr_start + color_off + color_size


@dataclass
class AnimContainerDef:
    """In-memory representation of one .ANI container."""
    type: int                  # ANI_TYPE_*
    track: int                 # ANI_TRACK_*
    width: int
    height: int
    blobs: list = field(default_factory=list)      # list[bytes], MAG data
    ticks: list = field(default_factory=list)      # list[int], len == nframes
    palettes: object = field(default=None)         # list[bytes] 768B each / None

    @property
    def nframes(self):
        return len(self.ticks)

    @property
    def nblob(self):
        return len(self.blobs)

    @property
    def palsz(self):
        if self.track == ANI_TRACK_PALETTE:
            return self.nframes * ANI_PALETTE_BYTES
        return 0

    @property
    def fps_nominal(self):
        """Uniform tick t -> max(1, round(60/t)); variable durations -> 0."""
        if not self.ticks:
            return 0
        first = self.ticks[0]
        if any(t != first for t in self.ticks):
            return 0
        return max(1, round(60 / first))

    def _validate_internal(self):
        if self.type not in (ANI_TYPE_FULLSCREEN, ANI_TYPE_CINE):
            _fail("header", f"bad type {self.type}")
        if self.track not in (ANI_TRACK_PIXEL, ANI_TRACK_PALETTE):
            _fail("header", f"bad track {self.track}")
        if self.width < 1 or self.height < 1:
            _fail("header", f"bad dimensions {self.width}x{self.height}")
        if self.nframes < 1:
            _fail("header", "nframes must be >= 1")
        if len(self.blobs) != self.nframes and self.track == ANI_TRACK_PIXEL:
            _fail("L3", f"pixel track needs nblob==nframes ({self.nblob}!={self.nframes})")
        if self.track == ANI_TRACK_PIXEL:
            if self.palettes is not None:
                _fail("L3", "pixel track must not carry palette tables")
        else:
            if self.nblob != 1:
                _fail("L3", f"palette track needs nblob==1 (got {self.nblob})")
            if self.palettes is None or len(self.palettes) != self.nframes:
                _fail("L3", "palette track needs one 768B table per frame")
            for i, pal in enumerate(self.palettes):
                if len(pal) != ANI_PALETTE_BYTES:
                    _fail("L3", f"palette[{i}] is {len(pal)}B, expected {ANI_PALETTE_BYTES}")
        for i, t in enumerate(self.ticks):
            if t < 1:
                _fail("L5", f"tick[{i}]={t}, must be >= 1")
            if t > 0xFFFF:
                _fail("L5", f"tick[{i}]={t}, exceeds u16")


def build_ani(def_: AnimContainerDef) -> bytes:
    """Assemble container bytes. Self-checks L3/L5 internal consistency."""
    def_._validate_internal()

    blobs_start = ANI_HEADER_SIZE + def_.nblob * 4 + def_.nframes * 2
    offsets = []
    cursor = blobs_start
    for blob in def_.blobs:
        offsets.append(cursor)
        cursor += len(blob)

    header = _HDR.pack(
        ANI_MAGIC, ANI_VERSION,
        def_.type, def_.track, def_.fps_nominal, 0,
        def_.nframes, def_.width, def_.height,
        def_.palsz, def_.nblob, 0,
    )

    out = bytearray()
    out.extend(header)
    for off in offsets:
        out.extend(struct.pack("<I", off))
    for t in def_.ticks:
        out.extend(struct.pack("<H", t))
    for blob in def_.blobs:
        out.extend(blob)
    if def_.track == ANI_TRACK_PALETTE:
        for pal in def_.palettes:
            out.extend(pal)
    return bytes(out)


def parse_ani(data) -> AnimContainerDef:
    """Parse container bytes with full L1-L5 validation.

    Raises ValueError("anim_container: ...") on any violation.
    """
    view = bytes(data)
    if len(view) < ANI_HEADER_SIZE:
        _fail("L1", f"file too small ({len(view)}B)")

    (magic, version, atype, atrack, _fps, reserved1,
     nframes, w, h, palsz, nblob, _reserved) = _HDR.unpack_from(view, 0)

    # L1
    if magic != ANI_MAGIC:
        _fail("L1", f"bad magic 0x{magic:08X}")
    if version != ANI_VERSION:
        _fail("L1", f"unsupported version {version}")
    # L2
    if atype > ANI_TYPE_CINE:
        _fail("L2", f"bad type {atype}")
    if atrack > ANI_TRACK_PALETTE:
        _fail("L2", f"bad track {atrack}")
    if reserved1 != 0:
        _fail("L2", f"reserved1 must be 0 (loop is player-side), got {reserved1}")

    # L3
    if nframes < 1:
        _fail("L3", f"nframes {nframes}")
    if atrack == ANI_TRACK_PIXEL:
        if nblob != nframes:
            _fail("L3", f"pixel track nblob {nblob} != nframes {nframes}")
        if palsz != 0:
            _fail("L3", f"pixel track palsz {palsz}")
    else:
        if nblob != 1:
            _fail("L3", f"palette track nblob {nblob}")
        if palsz != nframes * ANI_PALETTE_BYTES:
            _fail("L3", f"palette track palsz {palsz} != nframes*{ANI_PALETTE_BYTES}")

    table_end = ANI_HEADER_SIZE + nblob * 4 + nframes * 2
    if len(view) < table_end:
        _fail("L4", f"truncated tables ({len(view)}B < {table_end}B)")

    offsets = struct.unpack_from(f"<{nblob}I", view, ANI_HEADER_SIZE)
    # L4
    prev = -1
    for i, off in enumerate(offsets):
        if off < table_end:
            _fail("L4", f"offset[{i}]={off} overlaps tables (min {table_end})")
        if off >= len(view):
            _fail("L4", f"offset[{i}]={off} beyond EOF ({len(view)})")
        if off <= prev:
            _fail("L4", f"offset[{i}]={off} not greater than previous {prev}")
        prev = off

    ticks = list(struct.unpack_from(f"<{nframes}H", view, ANI_HEADER_SIZE + nblob * 4))
    # L5
    for i, t in enumerate(ticks):
        if t < 1:
            _fail("L5", f"tick[{i}]={t}")

    blobs = []
    for i, off in enumerate(offsets):
        length = mag_blob_length(view[off:])
        if length is None:
            _fail("L4", f"blob[{i}] at {off}: malformed MAG header")
        if off + length > len(view):
            _fail("L4", f"blob[{i}] at {off}: {length}B overruns EOF ({len(view)})")
        blobs.append(view[off:off + length])

    palettes = None
    if atrack == ANI_TRACK_PALETTE:
        last = offsets[-1]
        last_len = len(blobs[0])
        pal_start = last + last_len
        need = palsz
        if pal_start + need > len(view):
            _fail("L4", f"palette table needs {need}B at {pal_start}, overruns EOF")
        palettes = [view[pal_start + i * ANI_PALETTE_BYTES:
                         pal_start + (i + 1) * ANI_PALETTE_BYTES]
                    for i in range(nframes)]

    return AnimContainerDef(
        type=atype, track=atrack, width=w, height=h,
        blobs=blobs, ticks=ticks, palettes=palettes,
    )
