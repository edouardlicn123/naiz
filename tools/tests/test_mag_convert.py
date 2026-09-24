"""normalize_near_white / filter_white path tests.

Guards the --filter-white conversion path (numpy dependency declared in
tools/env_setup/requirements.txt) against silent breakage.
"""

from PIL import Image

from naiz_conv.mag_convert import convert_image, normalize_near_white


def _rgb_img(pixels, h=1):
    img = Image.new("RGB", (len(pixels), h))
    img.putdata(pixels)
    return img


def _px(img):
    """RGB image -> flat byte list (3 per pixel)."""
    return list(img.tobytes())


def test_near_white_snapped_to_pure_white():
    src = _rgb_img([(250, 250, 248), (255, 255, 255)])
    assert _px(normalize_near_white(src)) == [255] * 6


def test_distant_colors_untouched():
    src = _rgb_img([(0, 0, 0), (200, 10, 10)])
    assert _px(normalize_near_white(src)) == [0, 0, 0, 200, 10, 10]


def test_rgba_passthrough():
    src = Image.new("RGBA", (2, 1), (250, 250, 248, 128))
    assert normalize_near_white(src) is src


def test_convert_image_filter_white_smoke():
    mag = convert_image(_rgb_img([(250, 250, 248)] * 16),
                        no_resize=True, num_colors=256, bpp=8,
                        filter_white=True)
    assert isinstance(mag, bytes) and len(mag) > 4
