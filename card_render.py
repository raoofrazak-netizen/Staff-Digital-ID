"""Composes a downloadable PNG of a staff Digital ID card.

Matches the look of the official Middlesex University Dubai business card:
white background, black body text, the red shield crest, red for the
university name/website, and the same real address footer — extended with
a photo, live role/department info, and a QR code so it still works as a
Digital ID, not just a static business card.

Typography uses the same self-hosted Archivo family the live site uses as
the Dax / Monument Extended stand-in (per Brand Guidelines p.24-28 — Dax for
body/wordmark text, Monument Extended for bold display tags), instanced to
static TTF weights via fontTools since PIL can't load the woff2 originals.
Arial is kept only as a last-resort fallback if that font file is missing.
"""

import os

from PIL import Image, ImageDraw, ImageFont, ImageOps

MDX_RED = (227, 6, 19)
BLACK = (20, 20, 20)
GREY = (90, 90, 90)
LINE = (60, 60, 60)
CARD_BG = (255, 255, 255)
CARD_W, CARD_H = 1050, 650

_WIN_FONT_DIR = "C:/Windows/Fonts"
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ASSETS_DIR = os.path.join(_BASE_DIR, "static", "images")
_FONTS_DIR = os.path.join(_BASE_DIR, "static", "fonts")
_ARCHIVO_VAR = os.path.join(_FONTS_DIR, "archivo-var.ttf")
_ARCHIVO_BLACK = os.path.join(_FONTS_DIR, "archivo-black.ttf")

UNIVERSITY_ADDRESS_LINES = [
    "Blocks 15, 16, 17 & 19",
    "Dubai Knowledge Park",
    "PO Box 500697, Dubai, UAE",
]
UNIVERSITY_WEBSITE = "www.mdx.ac.ae"


def _arial_fallback(bold, size):
    try:
        return ImageFont.truetype(os.path.join(_WIN_FONT_DIR, "arialbd.ttf" if bold else "arial.ttf"), size)
    except OSError:
        return ImageFont.load_default()


def _dax(weight, size):
    """Body/wordmark text — Dax stand-in (Archivo instanced to a named weight)."""
    try:
        font = ImageFont.truetype(_ARCHIVO_VAR, size)
        font.set_variation_by_name(weight)
        return font
    except Exception:
        return _arial_fallback(weight != "Regular", size)


def _monument(size):
    """Bold display tags only — Monument Extended stand-in (Archivo Black)."""
    try:
        return ImageFont.truetype(_ARCHIVO_BLACK, size)
    except Exception:
        return _arial_fallback(True, size)


def _circle_crop(img, size):
    img = ImageOps.fit(img, (size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    out = Image.new("RGBA", (size, size))
    out.paste(img, (0, 0), mask)
    return out


def render_card_png(record, photo_file, qr_file):
    """photo_file / qr_file are file-like objects (or None) — already-open
    local files or in-memory buffers fetched from Blob storage; the caller
    resolves whichever storage backend is active before calling this."""
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

    uni_font = _dax("Black", 26)
    line_h = 31
    for i, word in enumerate(("Middlesex", "University", "Dubai")):
        draw.text((wordmark_x, 36 + i * line_h), word, font=uni_font, fill=BLACK)

    tag_font = _monument(14)
    tag_text = "STAFF DIGITAL ID"
    tag_w = draw.textlength(tag_text, font=tag_font)
    draw.text((CARD_W - margin - tag_w, 60), tag_text, font=tag_font, fill=MDX_RED)

    draw.line([(margin, 132), (CARD_W - margin, 132)], fill=LINE, width=2)

    # --- Main content: photo, name/title/department, QR ---
    photo_size = 150
    photo_x, photo_y = margin, 165
    if photo_file:
        photo = Image.open(photo_file).convert("RGB")
        circ = _circle_crop(photo, photo_size)
        card.paste(circ, (photo_x, photo_y), circ)
    draw.ellipse(
        [photo_x - 3, photo_y - 3, photo_x + photo_size + 3, photo_y + photo_size + 3],
        outline=(210, 210, 210), width=2,
    )

    text_x = photo_x + photo_size + 40
    name_font = _dax("Bold", 34)
    role_font = _dax("Medium", 22)
    dept_font = _dax("Regular", 19)

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
    # physical card's "Email: / Tel:" layout. Mobile is only shown when the
    # staff member provided one; Staff ID always stands in for a work Tel
    # line since staff phone extensions aren't collected by this portal.
    label_font = _dax("Bold", 18)
    value_font = _dax("Regular", 18)
    contact_rows = [("Email:", record.get("Email", ""))]
    if record.get("Mobile Number"):
        contact_rows.append(("Mobile:", record.get("Mobile Number")))
    contact_rows.append(("Staff ID:", record.get("Staff ID", "")))

    contact_y = photo_y + photo_size + 26
    row_h = 28
    value_x = text_x + 92
    draw.line(
        [(value_x - 14, contact_y), (value_x - 14, contact_y + row_h * (len(contact_rows) - 1) + 22)],
        fill=(210, 210, 210), width=2,
    )
    for i, (label, value) in enumerate(contact_rows):
        y = contact_y + i * row_h
        draw.text((text_x, y), label, font=label_font, fill=BLACK)
        draw.text((value_x, y), value, font=value_font, fill=GREY)

    qr_size = 170
    qr_x, qr_y = CARD_W - margin - qr_size, 165
    draw.rounded_rectangle(
        [qr_x - 10, qr_y - 10, qr_x + qr_size + 10, qr_y + qr_size + 10],
        radius=10, fill=(255, 255, 255), outline=(210, 210, 210), width=2,
    )
    if qr_file:
        qr_img = Image.open(qr_file).convert("RGB").resize((qr_size, qr_size), Image.NEAREST)
        card.paste(qr_img, (qr_x, qr_y))
    caption_font = _dax("Bold", 13)
    caption_text = "SCAN TO SAVE CONTACT"
    caption_w = draw.textlength(caption_text, font=caption_font)
    draw.text((qr_x + (qr_size - caption_w) / 2, qr_y + qr_size + 18), caption_text, font=caption_font, fill=GREY)

    # --- Footer: real university name/address, matching the physical card ---
    footer_top = CARD_H - 150
    draw.line([(margin, footer_top), (CARD_W - margin, footer_top)], fill=LINE, width=2)

    footer_name_font = _dax("Bold", 22)
    footer_font = _dax("Regular", 17)
    website_font = _dax("Bold", 17)

    draw.text((margin, footer_top + 22), "Middlesex University Dubai", font=footer_name_font, fill=MDX_RED)
    line_y = footer_top + 58
    for line in UNIVERSITY_ADDRESS_LINES:
        draw.text((margin, line_y), line, font=footer_font, fill=BLACK)
        line_y += 24

    website_w = draw.textlength(UNIVERSITY_WEBSITE, font=website_font)
    draw.text((CARD_W - margin - website_w, footer_top + 22), UNIVERSITY_WEBSITE, font=website_font, fill=MDX_RED)

    return card
