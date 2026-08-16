"""Composes the downloadable Staff Digital ID card as two images -- front
and back -- matching the official Middlesex University Dubai Staff ID
badge template (portrait CR80 badge, 2.125in x 3.375in) rather than an
invented landscape business-card layout: white body, photo box, ID
Number / Gender / Expiration column, Name / Job Title, and a solid grey
category bar on the front; IT-office terms, the university address, the
scan-to-save-contact vCard QR, and a Code128 barcode of the Staff ID on
the back.

Typography uses the same self-hosted Archivo family the live site uses as
the Dax / Monument Extended stand-in (per Brand Guidelines p.24-28),
instanced to static TTF weights via fontTools since PIL can't load the
woff2 originals. Arial is kept only as a last-resort fallback if that
font file is missing.

Note: the official template carries bilingual (English/Arabic) field
labels. Rendering Arabic correctly in Pillow needs bidi reshaping
(arabic-reshaper + python-bidi) that this project doesn't otherwise
depend on, so the generated card intentionally renders English labels
only -- adding those libraries purely for a duplicate label was judged
not worth the extra dependency weight.
"""

import io
import os

import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont, ImageOps

MDX_RED = (227, 6, 19)
GREY_BAR = (118, 118, 118)
BLACK = (26, 24, 34)
TEXT_SECONDARY = (98, 95, 107)
LINE = (225, 220, 210)
CARD_BG = (253, 253, 253)
CARD_W, CARD_H = 638, 1013

_WIN_FONT_DIR = "C:/Windows/Fonts"
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ASSETS_DIR = os.path.join(_BASE_DIR, "static", "images")
_FONTS_DIR = os.path.join(_BASE_DIR, "static", "fonts")
_ARCHIVO_VAR = os.path.join(_FONTS_DIR, "archivo-var.ttf")
_ARCHIVO_BLACK = os.path.join(_FONTS_DIR, "archivo-black.ttf")

UNIVERSITY_ADDRESS_LINES = [
    "Dubai Knowledge Park Block 16",
    "PO Box 500697, Dubai, UAE",
    "Tel. No. 04 367 8100",
]
UNIVERSITY_WEBSITE = "www.mdx.ac.ae"
CARD_TERMS = [
    "This card is non-transferable.",
    "It serves as the bearer's proof of employment in the university.",
    "It must be surrendered to the I.T. Office upon leaving the university.",
    "If found, please contact and return to the address below.",
]


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


def _wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _new_card():
    card = Image.new("RGB", (CARD_W, CARD_H), CARD_BG)
    return card, ImageDraw.Draw(card)


def _draw_logo(card, draw, top):
    logo_path = os.path.join(_ASSETS_DIR, "mdx-logo.jpg")
    if not os.path.exists(logo_path):
        return top
    logo = Image.open(logo_path).convert("RGB")
    logo_h = 92
    ratio = logo_h / logo.height
    logo = logo.resize((max(1, int(logo.width * ratio)), logo_h), Image.LANCZOS)
    card.paste(logo, ((CARD_W - logo.width) // 2, top))
    return top + logo_h


def _draw_grey_bar(card, draw, text):
    bar_h = 56
    top = CARD_H - bar_h
    draw.rectangle([0, top, CARD_W, CARD_H], fill=GREY_BAR)

    max_w = CARD_W - 40
    size = 20
    font = _monument(size)
    while size > 11 and draw.textlength(text, font=font) > max_w:
        size -= 1
        font = _monument(size)
    if draw.textlength(text, font=font) > max_w:
        truncated = text
        while truncated and draw.textlength(truncated + "…", font=font) > max_w:
            truncated = truncated[:-1].rstrip()
        text = (truncated + "…") if truncated else text

    w = draw.textlength(text, font=font)
    text_h = font.getbbox(text)[3] - font.getbbox(text)[1]
    draw.text(((CARD_W - w) / 2, top + (bar_h - text_h) / 2), text, font=font, fill=(255, 255, 255))


def render_card_front(record, photo_file):
    """photo_file is a file-like object (or None) -- an already-open local
    file or in-memory buffer fetched from Blob storage; the caller resolves
    whichever storage backend is active before calling this."""
    card, draw = _new_card()
    margin = 42

    y = _draw_logo(card, draw, 34)
    y += 28

    photo_w, photo_h = 168, 200
    photo_x, photo_y = margin, y
    if photo_file:
        photo = Image.open(photo_file).convert("RGB")
        photo = ImageOps.fit(photo, (photo_w, photo_h), Image.LANCZOS)
        card.paste(photo, (photo_x, photo_y))
    draw.rectangle(
        [photo_x - 1, photo_y - 1, photo_x + photo_w + 1, photo_y + photo_h + 1],
        outline=(200, 195, 205), width=2,
    )

    field_x = photo_x + photo_w + 30
    label_font = _dax("Bold", 15)
    value_font = _dax("Medium", 20)
    fields = [
        ("ID NUMBER", record.get("Staff ID", "")),
        ("GENDER", record.get("Gender") or "\u2014"),
        ("EXPIRATION", "\u2014"),
    ]
    field_y = photo_y + 6
    for label, value in fields:
        draw.text((field_x, field_y), label, font=label_font, fill=MDX_RED)
        draw.text((field_x, field_y + 22), value, font=value_font, fill=BLACK)
        field_y += 62

    name_y = photo_y + photo_h + 34
    name_font = _dax("Bold", 30)
    jobtitle_label_font = _dax("Bold", 15)
    jobtitle_font = _dax("Medium", 22)

    draw.text((margin, name_y), "NAME", font=label_font, fill=MDX_RED)
    full_name = f"{record.get('First Name', '')} {record.get('Last Name', '')}".strip()
    draw.text((margin, name_y + 24), full_name, font=name_font, fill=BLACK)

    title_y = name_y + 84
    draw.text((margin, title_y), "JOB TITLE", font=jobtitle_label_font, fill=MDX_RED)
    job_title = record.get("Job Title", "")
    max_w = CARD_W - margin * 2
    for line in _wrap_text(draw, job_title, jobtitle_font, max_w)[:2]:
        draw.text((margin, title_y + 24), line, font=jobtitle_font, fill=BLACK)
        title_y += 28

    _draw_grey_bar(card, draw, (record.get("Department") or "STAFF").upper())
    return card


def _generate_barcode_image(staff_id, width):
    code128 = barcode.get_barcode_class("code128")
    buf = io.BytesIO()
    writer_options = {"write_text": False, "module_height": 14.0, "quiet_zone": 2.0, "module_width": 0.35}
    code128(staff_id or "0", writer=ImageWriter()).write(buf, options=writer_options)
    buf.seek(0)
    img = Image.open(buf).convert("RGB")
    ratio = width / img.width
    return img.resize((width, max(1, int(img.height * ratio))), Image.LANCZOS)


def render_card_back(record, qr_file):
    card, draw = _new_card()
    margin = 42

    terms_font = _dax("Regular", 15)
    y = 50
    for term in CARD_TERMS:
        for line in _wrap_text(draw, f"\u2022 {term}", terms_font, CARD_W - margin * 2):
            draw.text((margin, y), line, font=terms_font, fill=TEXT_SECONDARY)
            y += 22
        y += 4

    y += 14
    draw.line([(margin, y), (CARD_W - margin, y)], fill=LINE, width=2)
    y += 20

    address_name_font = _dax("Bold", 19)
    address_font = _dax("Regular", 16)
    draw.text((margin, y), "Middlesex University Dubai", font=address_name_font, fill=MDX_RED)
    y += 30
    for line in UNIVERSITY_ADDRESS_LINES:
        draw.text((margin, y), line, font=address_font, fill=BLACK)
        y += 22

    y += 24
    qr_size = 168
    if qr_file:
        qr_img = Image.open(qr_file).convert("RGB").resize((qr_size, qr_size), Image.NEAREST)
        card.paste(qr_img, (margin, y))
    draw.rectangle([margin - 2, y - 2, margin + qr_size + 2, y + qr_size + 2], outline=(210, 210, 210), width=2)
    caption_font = _dax("Bold", 13)
    caption_text = "SCAN TO\nSAVE CONTACT"
    caption_y = y + 4
    for line in caption_text.split("\n"):
        draw.text((margin + qr_size + 22, caption_y), line, font=caption_font, fill=TEXT_SECONDARY)
        caption_y += 18

    y += qr_size + 36
    barcode_img = _generate_barcode_image(record.get("Staff ID", ""), CARD_W - margin * 2)
    card.paste(barcode_img, (margin, y))
    y += barcode_img.height + 6
    id_font = _dax("Bold", 15)
    id_text = record.get("Staff ID", "")
    id_w = draw.textlength(id_text, font=id_font)
    draw.text(((CARD_W - id_w) / 2, y), id_text, font=id_font, fill=BLACK)

    _draw_grey_bar(card, draw, UNIVERSITY_WEBSITE)
    return card
