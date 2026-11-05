"""
MAG (MAKI02) format constants — mirrors core/lib/mag_format.h.

Keep in sync with the C header when adding/removing constants.
"""
MAG_SIGNATURE = b"MAKI02  "
MAG_SIGNATURE_LEN = 8
MAG_SPRITE_MARKER = b"sprt"
MAG_HEADER_SIZE = 32
MAG_USER_TERM = 0x1A

MAG_MODEL_3BIT = 0x03
MAG_MODEL_5BIT = 0x68
MAG_MODEL_8BIT = 0x99
MAG_MODEL_8BIT2 = 0x88
