"""Composes a downloadable PNG of a staff Digital ID card.

Uses Arial (regular/bold) for text — the Brand Guidelines (p.28) name Arial
as the approved fallback wherever the licensed Dax/Monument Extended fonts
aren't available, which is exactly this situation for server-side PIL text
rendering (PIL needs TTF/OTF; the self-hosted webfonts here are woff2).
"""

import os

from PIL import Image, ImageDraw, ImageFont, ImageOps

MDX_RED = (227, 6, 19)
MDX_INDIGO = (47, 37, 82)
TEXT_MUTED = (98, 95, 107)
CARD_BG = (250, 249, 246)
CARD_W, CARD_H = 1000, 620

_FONT_DIR = "C:/Windows/Fonts"


def _font(name, size):
    try:
        return ImageFont.truetype(os.path.join(_FONT_DIR, name), size)
    except OSError:
        return ImageFont.load_default()


def _rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0], size[1]], radius=radius, fill=255)
    return mask


def _circle_crop(img, size):
    img = ImageOps.fit(img, (size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    out = Image.new("RGBA", (size, size))
    out.paste(img, (0, 0), mask)
    return out


def render_card_png(record, photo_path, qr_path, logo_path=None):
    card = Image.new("RGB", (CARD_W, CARD_H), CARD_BG)
    draw = ImageDraw.Draw(card)

    draw.rounded_rectangle([0, 0, CARD_W - 1, CARD_H - 1], radius=36, outline=(225, 219, 210), width=2)
    draw.rounded_rectangle([0, 0, CARD_W - 1, 96], radius=36, fill=MDX_INDIGO)
    draw.rectangle([0, 60, CARD_W, 96], fill=MDX_INDIGO)

    title_font = _font("arialbd.ttf", 30)
    draw.text((44, 30), "MIDDLESEX UNIVERSITY DUBAI", font=title_font, fill=(255, 255, 255))

    photo_size = 220
    photo_x, photo_y = 60, 150
    if photo_path and os.path.exists(photo_path):
        photo = Image.open(photo_path).convert("RGB")
        circ = _circle_crop(photo, photo_size)
        card.paste(circ, (photo_x, photo_y), circ)
    ring_pad = 6
    draw.ellipse(
        [photo_x - ring_pad, photo_y - ring_pad, photo_x + photo_size + ring_pad, photo_y + photo_size + ring_pad],
        outline=(255, 255, 255), width=6,
    )

    text_x = photo_x + photo_size + 50
    name_font = _font("arialbd.ttf", 46)
    role_font = _font("arial.ttf", 26)
    pill_font = _font("arialbd.ttf", 20)

    full_name = f"{record.get('First Name', '')} {record.get('Last Name', '')}".strip()
    draw.text((text_x, 160), full_name, font=name_font, fill=MDX_INDIGO)
    draw.text((text_x, 218), record.get("Job Title", ""), font=role_font, fill=TEXT_MUTED)

    pills = [
        f"Staff ID {record.get('Staff ID', '')}",
        record.get("Department", ""),
        record.get("Employment Status", ""),
        record.get("Gender", ""),
    ]
    px, py = text_x, 268
    for i, text in enumerate(pills):
        if not text:
            continue
        w = draw.textlength(text, font=pill_font) + 34
        accent = i == 0
        fill = MDX_RED if accent else (240, 236, 247)
        text_fill = (255, 255, 255) if accent else MDX_INDIGO
        draw.rounded_rectangle([px, py, px + w, py + 44], radius=22, fill=fill)
        draw.text((px + 17, py + 10), text, font=pill_font, fill=text_fill)
        px += w + 12
        if px > CARD_W - 260:
            px = text_x
            py += 56

    draw.line([(60, 470), (CARD_W - 60, 470)], fill=(225, 219, 210), width=2)

    caption_font = _font("arialbd.ttf", 16)
    secure_font = _font("arial.ttf", 15)
    draw.text((60, 500), "SCAN TO VERIFY", font=caption_font, fill=TEXT_MUTED)
    draw.text((60, 528), "\u25cf Secure Digital Identity", font=secure_font, fill=(46, 139, 87))

    qr_size = 130
    qr_x, qr_y = CARD_W - qr_size - 60, CARD_H - qr_size - 60
    if qr_path and os.path.exists(qr_path):
        qr_img = Image.open(qr_path).convert("RGB").resize((qr_size, qr_size), Image.LANCZOS)
        card.paste(qr_img, (qr_x, qr_y))
        draw.rectangle([qr_x, qr_y, qr_x + qr_size, qr_y + qr_size], outline=(225, 219, 210), width=2)

    return card
