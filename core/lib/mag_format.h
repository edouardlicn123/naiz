#ifndef MAG_FORMAT_H
#define MAG_FORMAT_H

/*
 * MAG (MAKI02) format constants — shared between C decoder (mag.c)
 * and Python toolchain (tools/naiz_lib/mag_constants.py).
 *
 * Reference: devdocs/0.1版开发文档总结.html#doc-01 (MAG format spec), else mag.c.
 */

#define MAG_SIGNATURE      "MAKI02  "
#define MAG_SIGNATURE_LEN  8
#define MAG_SPRITE_MARKER  "sprt"
#define MAG_HEADER_SIZE    32
#define MAG_USER_TERM      0x1A

/* model_code values (palette bit-depth) */
#define MAG_MODEL_3BIT   0x03
#define MAG_MODEL_5BIT   0x68
#define MAG_MODEL_8BIT   0x99
#define MAG_MODEL_8BIT2  0x88

#endif
