"""Composes a downloadable PNG of a staff Digital ID card.

Matches the look of the official Middlesex University Dubai business card:
white background, black body text, the red shield crest, red for the
university name/website, and the same real address footer — extended with
a photo, live role/department info, and a QR code so it still works as a
Digital ID, not just a static business card.

Uses Arial (regular/bold/italic) for text — the Brand Guidelines (p.28) name
Arial as the approved fallback wherever the licensed Dax/Monument Extended
fonts aren't available, which is exactly this situation for server-side PIL
text rendering (PIL needs TTF/OTF; the self-hosted webfonts here are woff2).
"""

import os

from PIL import Image, ImageDraw, ImageFont, ImageOps

MDX_RED = (227, 6, 19)
BLACK = (20, 20, 20)
GREY = (90, 90, 90)
LINE = (60, 60, 60)
CARD_BG = (255, 255, 255)
CARD_W, CARD_H = 1050, 650

_FONT_DIR = "C:/Windows/Fonts"
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "images")

UNIVERSITY_ADDRESS_LINES = [
    "Blocks 15, 16, 17 & 19",
    "Dubai Knowledge Park",
    "PO Box 500697, Dubai, UAE",
]
UNIVERSITY_WEBSITE = "www.mdx.ac.ae"


def _font(name, size):
    try:
        return ImageFont.truetype(os.path.join(_FONT_DIR, name), size)
    except OSError:
        return ImageFont.load_default()


def _circle_crop(img, size):
    img = ImageOps.fit(img, (size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    out = Image.new("RGBA", (size, size))
    out.paste(img, (0, 0), mask)
    return out


def render_card_png(record, photo_path, qr_path):
    card = Image.new("RGB", (CARD_W, CARD_H), CARD_BG)
    draw = ImageDraw.Draw(card)

    margin = 55

    # --- Header: crest + official 3-line wordmark ("Middlesex" / "University"
    # / "Dubai"), matching the physical card's exact lockup — the crest is
    # sized to span the full height of the stacked text, not just one line. ---
    crest_path = os.path.join(_ASSETS_DIR, "mdx-shield.png")
    crest_h = 96
    if os.path.exists(crest_path):
        crest = Image.open(crest_path).convert("RGBA")
        ratio = crest_h / crest.height
        crest = crest.resize((max(1, int(crest.width * ratio)), crest_h), Image.LANCZOS)
        card.paste(crest, (margin, 36), crest)
        wordmark_x = margin + crest.width + 24
    else:
        wordmark_x = margin

    uni_font = _font("arialbd.ttf", 26)
    line_h = 31
    for i, word in enumerate(("Middlesex", "University", "Dubai")):
        draw.text((wordmark_x, 36 + i * line_h), word, font=uni_font, fill=BLACK)

    tag_font = _font("arialbd.ttf", 15)
    tag_text = "STAFF DIGITAL ID"
    tag_w = draw.textlength(tag_text, font=tag_font)
    draw.text((CARD_W - margin - tag_w, 60), tag_text, font=tag_font, fill=MDX_RED)

    draw.line([(margin, 132), (CARD_W - margin, 132)], fill=LINE, width=2)

    # --- Main content: photo, name/title/department, QR ---
    photo_size = 150
    photo_x, photo_y = margin, 165
    if photo_path and os.path.exists(photo_path):
        photo = Image.open(photo_path).convert("RGB")
        circ = _circle_crop(photo, photo_size)
        card.paste(circ, (photo_x, photo_y), circ)
    draw.ellipse(
        [photo_x - 3, photo_y - 3, photo_x + photo_size + 3, photo_y + photo_size + 3],
        outline=(210, 210, 210), width=2,
    )

    text_x = photo_x + photo_size + 40
    name_font = _font("arialbd.ttf", 34)
    role_font = _font("arial.ttf", 22)
    dept_font = _font("ariali.ttf", 19)

    full_name = f"{record.get('First Name', '')} {record.get('Last Name', '')}".strip()
    draw.text((text_x, 170), full_name, font=name_font, fill=BLACK)
    draw.text((text_x, 214), record.get("Job Title", ""), font=role_font, fill=MDX_RED)

    department = record.get("Department", "")
    max_dept_width = CARD_W - margin - 210 - text_x  # keep clear of the QR column
    if draw.textlength(department, font=dept_font) > max_dept_width:
        while department and draw.textlength(department + "…", font=dept_font) > max_dept_width:
            department = department[:-1]
        department = (department + "…") if department else ""
    draw.text((text_x, 250), department, font=dept_font, fill=GREY)

    # Contact block — label:value columns with a divider, styled after the
    # physical card's "Email: / Tel:" layout (Staff ID stands in for Tel,
    # since staff phone numbers aren't collected by this portal).
    label_font = _font("arialbd.ttf", 18)
    value_font = _font("arial.ttf", 18)
    contact_y = photo_y + photo_size + 26
    draw.text((text_x, contact_y), "Email:", font=label_font, fill=BLACK)
    draw.text((text_x, contact_y + 28), "Staff ID:", font=label_font, fill=BLACK)
    value_x = text_x + 92
    draw.line([(value_x - 14, contact_y), (value_x - 14, contact_y + 50)], fill=(210, 210, 210), width=2)
    draw.text((value_x, contact_y), record.get("Email", ""), font=value_font, fill=GREY)
    draw.text((value_x, contact_y + 28), record.get("Staff ID", ""), font=value_font, fill=GREY)

    qr_size = 170
    qr_x, qr_y = CARD_W - margin - qr_size, 165
    draw.rounded_rectangle(
        [qr_x - 10, qr_y - 10, qr_x + qr_size + 10, qr_y + qr_size + 10],
        radius=10, fill=(255, 255, 255), outline=(210, 210, 210), width=2,
    )
    if qr_path and os.path.exists(qr_path):
        qr_img = Image.open(qr_path).convert("RGB").resize((qr_size, qr_size), Image.NEAREST)
        card.paste(qr_img, (qr_x, qr_y))
    caption_font = _font("arialbd.ttf", 13)
    caption_text = "SCAN TO SAVE CONTACT"
    caption_w = draw.textlength(caption_text, font=caption_font)
    draw.text((qr_x + (qr_size - caption_w) / 2, qr_y + qr_size + 18), caption_text, font=caption_font, fill=GREY)

    # --- Footer: real university name/address, matching the physical card ---
    footer_top = CARD_H - 150
    draw.line([(margin, footer_top), (CARD_W - margin, footer_top)], fill=LINE, width=2)

    footer_name_font = _font("arialbd.ttf", 22)
    footer_font = _font("arial.ttf", 17)
    website_font = _font("arialbd.ttf", 17)

    draw.text((margin, footer_top + 22), "Middlesex University Dubai", font=footer_name_font, fill=MDX_RED)
    line_y = footer_top + 58
    for line in UNIVERSITY_ADDRESS_LINES:
        draw.text((margin, line_y), line, font=footer_font, fill=BLACK)
        line_y += 24

    website_w = draw.textlength(UNIVERSITY_WEBSITE, font=website_font)
    draw.text((CARD_W - margin - website_w, footer_top + 22), UNIVERSITY_WEBSITE, font=website_font, fill=MDX_RED)

    return card
