"""
gen_canvas_image.py — 生成 C03 / C04 示意图

输出到 naiz-guildbook/imgs/
  canvas-diagram.png      ← 200×400 画布全貌（表情可变区/对话框掩盖区/可见底部）
  region-diagram.png      ← 跨表情制图约束区域标注（精简版）
  screen-panorama.png     ← 屏幕全景：三人站位 + 对话框覆盖
"""

import os
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'naiz-guildbook', 'imgs')

# Canvas dimensions (logical)
W, H = 200, 400
DIALOG_Y = 280
DIALOG_BOTTOM = 395

# Colors
CLR_BORDER = (40, 40, 60)
CLR_TEXT = (40, 40, 60)
CLR_EMOTIONAL = (200, 230, 255, 80)
CLR_MASK = (200, 200, 200, 100)
CLR_VISIBLE = (200, 255, 200, 100)
CLR_DIALOG_LINE = (220, 80, 80)
CLR_ARROW = (120, 120, 140)

FONT_PATH = '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc'


def get_font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def draw_right_arrow(draw, x1, y, x2, color=CLR_ARROW, width=2):
    draw.line([(x1, y), (x2, y)], fill=color, width=width)
    draw.line([(x2, y), (x2-8, y-4)], fill=color, width=width)
    draw.line([(x2, y), (x2-8, y+4)], fill=color, width=width)


def draw_left_arrow(draw, x1, y, x2, color=CLR_ARROW, width=2):
    draw.line([(x1, y), (x2, y)], fill=color, width=width)
    draw.line([(x2, y), (x2+8, y-4)], fill=color, width=width)
    draw.line([(x2, y), (x2+8, y+4)], fill=color, width=width)


def generate_canvas_diagram():
    """Full sprite canvas diagram (replaces §3.2 ASCII art)."""
    S = 1.8
    cw, ch = int(W * S), int(H * S)
    margin_left = 140
    margin_top = 50
    margin_right = 130
    margin_bottom = 40
    img_w = margin_left + cw + margin_right
    img_h = margin_top + ch + margin_bottom + 40
    img = Image.new('RGBA', (img_w, img_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    canvas_x = margin_left
    canvas_y = margin_top

    draw.rectangle([canvas_x, canvas_y, canvas_x+cw, canvas_y+ch],
                   outline=CLR_BORDER, width=2)

    def cy(logical_y):
        return canvas_y + int(logical_y * S)

    def draw_dashed_line(y_pos, color, width=2):
        dash_len = 8
        gap_len = 6
        x = canvas_x
        while x < canvas_x + cw:
            xe = min(x + dash_len, canvas_x + cw)
            draw.line([(x, y_pos), (xe, y_pos)], fill=color, width=width)
            x += dash_len + gap_len

    dy280 = cy(DIALOG_Y)
    draw_dashed_line(dy280, CLR_DIALOG_LINE)

    dy395 = cy(DIALOG_BOTTOM)
    draw_dashed_line(dy395, CLR_DIALOG_LINE)

    # Zone fills
    draw.rectangle([canvas_x+1, canvas_y+1, canvas_x+cw-1, dy280-1],
                   fill=CLR_EMOTIONAL)
    draw.rectangle([canvas_x+1, dy280+1, canvas_x+cw-1, cy(396)-1],
                   fill=CLR_MASK)
    draw.rectangle([canvas_x+1, cy(396)+1, canvas_x+cw-1, canvas_y+ch-1],
                   fill=CLR_VISIBLE)

    # Right side labels
    rx = canvas_x + cw + 12
    font_sm = get_font(18)
    font_md = get_font(20)
    font_lg = get_font(24)

    draw.text((rx, canvas_y-10), 'y=0', fill=CLR_TEXT, font=font_md)
    draw.text((rx, dy280-9), 'y=280', fill=CLR_DIALOG_LINE, font=font_md)
    draw.text((rx, dy395-9), 'y=395', fill=CLR_DIALOG_LINE, font=font_md)
    draw.text((rx, canvas_y+ch-10), 'y=400', fill=CLR_TEXT, font=font_md)

    # Height arrows
    arr_font = get_font(17)
    arrow_x = canvas_x + cw + 100
    label_x = arrow_x + 10

    h_emo = dy280 - canvas_y
    y_mid_emo = canvas_y + h_emo//2
    draw_right_arrow(draw, arrow_x, y_mid_emo-20, arrow_x, CLR_ARROW)
    draw_right_arrow(draw, arrow_x, y_mid_emo+20, arrow_x, CLR_ARROW)
    draw.text((label_x, y_mid_emo-15), '280px', fill=CLR_TEXT, font=arr_font)

    h_mask = dy395 - dy280
    y_mid_mask = dy280 + h_mask//2
    draw_right_arrow(draw, arrow_x, y_mid_mask-20, arrow_x, CLR_ARROW)
    draw_right_arrow(draw, arrow_x, y_mid_mask+20, arrow_x, CLR_ARROW)
    draw.text((label_x, y_mid_mask-15), '116px', fill=CLR_TEXT, font=arr_font)

    h_vis = canvas_y+ch - cy(396)
    y_mid_vis = cy(396) + h_vis//2
    draw_right_arrow(draw, arrow_x, y_mid_vis-20, arrow_x, CLR_ARROW)
    draw_right_arrow(draw, arrow_x, y_mid_vis+20, arrow_x, CLR_ARROW)
    draw.text((label_x, y_mid_vis-15), '4px', fill=CLR_TEXT, font=arr_font)

    # Zone labels inside
    tx_emo = canvas_x + cw//2
    ty_emo = canvas_y + (dy280 - canvas_y)//2
    draw.text((tx_emo, ty_emo-14), '表情可变区', fill=(80, 80, 180),
              font=font_lg, anchor='mm')
    draw.text((tx_emo, ty_emo+16), '(脸、发型、手势等)', fill=(120, 120, 160),
              font=font_sm, anchor='mm')

    ty_mask = dy280 + (dy395 - dy280)//2
    draw.text((tx_emo, ty_mask-8), '对话框掩盖区', fill=(80, 80, 80),
              font=font_lg, anchor='mm')
    draw.text((tx_emo, ty_mask+20), '(下半身固定，同角色必一致)', fill=(120, 120, 120),
              font=font_sm, anchor='mm')

    ty_vis = cy(396) + (canvas_y+ch - cy(396))//2
    draw.text((tx_emo, ty_vis), '可见底部 4px', fill=(60, 140, 60),
              font=font_sm, anchor='mm')

    # Width label bottom
    wy = canvas_y + ch + 12
    draw_left_arrow(draw, canvas_x+cw+20, wy+20, canvas_x+cw+20, CLR_ARROW)
    draw_left_arrow(draw, canvas_x-20, wy+20, canvas_x-20, CLR_ARROW)
    draw.text((canvas_x+cw//2, wy+10), '200px', fill=CLR_TEXT,
              font=font_md, anchor='mt')

    # Title
    title_font = get_font(28)
    draw.text((img_w//2, 10), '立绘画布 (200×400)', fill=CLR_BORDER,
              font=title_font, anchor='mt')

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, 'canvas-diagram.png')
    img.save(path)
    print(f'  {path} ({img.size[0]}×{img.size[1]})')
    return path


def generate_region_diagram():
    """Simplified region constraint diagram (replaces §3.5 ASCII art)."""
    S = 1.5
    cw, ch = int(W * S), int(H * S)
    margin_left = 50
    margin_right = 160
    margin_top = 60
    margin_bottom = 40
    img_w = margin_left + cw + margin_right
    img_h = margin_top + ch + margin_bottom + 40
    img = Image.new('RGBA', (img_w, img_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    canvas_x = margin_left
    canvas_y = margin_top
    draw.rectangle([canvas_x, canvas_y, canvas_x+cw, canvas_y+ch],
                   outline=CLR_BORDER, width=2)

    def cy(logical_y):
        return canvas_y + int(logical_y * S)

    dy280 = cy(DIALOG_Y)
    dy395 = cy(DIALOG_BOTTOM)

    def draw_dashed(y_pos, color, width=3):
        dash_len = 10
        gap_len = 6
        x = canvas_x
        while x < canvas_x + cw:
            xe = min(x + dash_len, canvas_x + cw)
            draw.line([(x, y_pos), (xe, y_pos)], fill=color, width=width)
            x += dash_len + gap_len

    draw_dashed(dy280, CLR_DIALOG_LINE)
    draw_dashed(dy395, CLR_DIALOG_LINE)

    draw.rectangle([canvas_x+1, canvas_y+1, canvas_x+cw-1, dy280-1],
                   fill=CLR_EMOTIONAL)
    draw.rectangle([canvas_x+1, dy280+1, canvas_x+cw-1, cy(396)-1],
                   fill=CLR_MASK)
    draw.rectangle([canvas_x+1, cy(396)+1, canvas_x+cw-1, canvas_y+ch-1],
                   fill=CLR_VISIBLE)

    font_sm = get_font(18)
    font_md = get_font(22)
    font_lg = get_font(26)

    rx = canvas_x + cw + 10
    draw.text((rx, canvas_y-8), 'y=0', fill=CLR_TEXT, font=font_md)
    draw.text((rx, dy280-9), 'y=280', fill=CLR_DIALOG_LINE, font=font_md)
    draw.text((rx, dy395-9), 'y=395', fill=CLR_DIALOG_LINE, font=font_md)
    draw.text((rx, canvas_y+ch-8), 'y=400', fill=CLR_TEXT, font=font_md)

    cx = canvas_x + cw//2

    emo_cy = canvas_y + (dy280 - canvas_y)//2
    draw.text((cx, emo_cy-12), '表情可变区', fill=(80, 80, 180),
              font=font_lg, anchor='mm')
    draw.text((cx, emo_cy+18), '0–279 px', fill=(120, 120, 160),
              font=font_sm, anchor='mm')

    mask_cy = dy280 + (dy395 - dy280)//2
    draw.text((cx, mask_cy-12), '对话框掩盖区', fill=(80, 80, 80),
              font=font_lg, anchor='mm')
    draw.text((cx, mask_cy+18), '280–395 px', fill=(120, 120, 120),
              font=font_sm, anchor='mm')

    vis_cy = cy(396) + (canvas_y+ch - cy(396))//2
    draw.text((cx, vis_cy), '可见底部 4px', fill=(60, 140, 60),
              font=font_sm, anchor='mm')

    note_font = get_font(18)
    note_y = canvas_y + ch + 20
    draw.text((canvas_x + cw//2, note_y),
              '同角色不同表情在 y≥280 区域必须像素级完全一致',
              fill=CLR_DIALOG_LINE, font=note_font, anchor='mt')

    title_font = get_font(28)
    draw.text((img_w//2, 12), '跨表情制图约束', fill=CLR_BORDER,
              font=title_font, anchor='mt')

    path = os.path.join(OUT_DIR, 'region-diagram.png')
    img.save(path)
    print(f'  {path} ({img.size[0]}×{img.size[1]})')
    return path


def generate_screen_panorama():
    """Three-sprite layout on 640×400 screen with dialog coverage."""
    SCREEN_W = 640
    SCREEN_H = 400
    SPRITE_W = 200
    SPRITE_H = 400
    S = 0.8  # scale factor

    sw = int(SCREEN_W * S)
    sh = int(SCREEN_H * S)
    pw = int(SPRITE_W * S)
    ph = int(SPRITE_H * S)
    dialog_y = int(DIALOG_Y * S)
    dialog_bot = int(DIALOG_BOTTOM * S)

    def sx(logical_x):
        return int(logical_x * S)

    margin = 50
    img_w = sw + margin * 2
    img_h = sh + margin * 2 + 50
    img = Image.new('RGBA', (img_w, img_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    ox = margin
    oy = margin + 20

    # Screen border
    draw.rectangle([ox, oy, ox+sw, oy+sh], outline=CLR_BORDER, width=2)

    # Three sprite positions
    sprite_xs = [sx(27), sx(220), sx(413)]
    sprite_labels = ['左立绘 (27,0)', '中立绘 (220,0)', '右立绘 (413,0)']

    # Light fill for each sprite (semi-transparent)
    for i, px in enumerate(sprite_xs):
        fill = (200, 220, 255, 60)
        draw.rectangle([ox+px, oy, ox+px+pw, oy+ph], fill=fill)
        # Sprite border
        draw.rectangle([ox+px, oy, ox+px+pw, oy+ph], outline=(100, 120, 160), width=1)

    # Dialog area highlight (y=280 to y=395)
    dialog_fill = (220, 80, 80, 40)
    draw.rectangle([ox, oy+dialog_y, ox+sw, oy+dialog_bot], fill=dialog_fill)

    # Dialog coverage line at y=280
    draw_dash = []
    dash_len = 8
    gap_len = 6
    xp = ox
    while xp < ox + sw:
        xe = min(xp + dash_len, ox + sw)
        draw.line([(xp, oy+dialog_y), (xe, oy+dialog_y)], fill=CLR_DIALOG_LINE, width=2)
        xp += dash_len + gap_len
    # y=395
    xp = ox
    while xp < ox + sw:
        xe = min(xp + dash_len, ox + sw)
        draw.line([(xp, oy+dialog_bot), (xe, oy+dialog_bot)], fill=CLR_DIALOG_LINE, width=2)
        xp += dash_len + gap_len

    # Labels
    font_sm = get_font(14)
    font_md = get_font(16)

    # Sprite labels (above each sprite)
    for i, px in enumerate(sprite_xs):
        draw.text((ox+px+pw//2, oy+8), sprite_labels[i],
                  fill=CLR_TEXT, font=font_sm, anchor='mt')

    # y labels on the right side (inside the right margin)
    ly = ox + sw + 6
    draw.text((ly, oy), 'y=0', fill=CLR_TEXT, font=font_sm)
    draw.text((ly, oy+dialog_y), 'y=280', fill=CLR_DIALOG_LINE, font=font_sm)
    draw.text((ly, oy+dialog_bot), 'y=395', fill=CLR_DIALOG_LINE, font=font_sm)
    draw.text((ly, oy+sh), 'y=400', fill=CLR_TEXT, font=font_sm)

    # Dialog zone label
    dialog_mid_y = oy + (dialog_y + dialog_bot)//2
    draw.text((ox + sw//2, dialog_mid_y), '对话框覆盖区域',
              fill=CLR_DIALOG_LINE, font=font_sm, anchor='mm')

    # Screen width label (centered below screen)
    size_y = oy + sh + 8
    draw_left_arrow(draw, ox+sw-10, size_y+12, ox+sw-10, CLR_ARROW)
    draw_left_arrow(draw, ox+10, size_y+12, ox+10, CLR_ARROW)
    draw.text((ox+sw//2, size_y), '640px', fill=CLR_TEXT,
              font=font_sm, anchor='mt')

    # Title
    title_font = get_font(22)
    draw.text((img_w//2, 6), '三人站位 — 屏幕全景 (640×400)',
              fill=CLR_BORDER, font=title_font, anchor='mt')

    path = os.path.join(OUT_DIR, 'screen-panorama.png')
    img.save(path)
    print(f'  {path} ({img.size[0]}×{img.size[1]})')
    return path


if __name__ == '__main__':
    generate_canvas_diagram()
    generate_region_diagram()
    generate_screen_panorama()
