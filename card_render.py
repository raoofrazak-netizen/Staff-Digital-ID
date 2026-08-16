"""Composes the downloadable Staff Digital ID card as two images -- front
and back -- matching the official Middlesex University Dubai Staff ID
badge template (portrait CR80 badge, 2.125in x 3.375in) rather than an
invented landscape business-card layout: white body, photo box, ID
Number / Gender / Expiration column, Name / Job Title, the
scan-to-save-contact vCard QR (filling what would otherwise be empty
space below Job Title), and a solid grey category bar on the front;
IT-office terms, the university address, and a Code128 barcode of the
Staff ID on the back.

Typography uses the same self-hosted Archivo family the live site uses as
the Dax / Monument Extended stand-in (per Brand Guidelines p.24-28),
instanced to static TTF weights via fontTools since PIL can't load the
woff2 originals. Arial is kept only as a last-resort fallback if that
font file is missing.

Field labels are bilingual (English/Arabic), matching the official
template. Arabic needs bidi reshaping to render as connected script
instead of isolated letterforms -- arabic-reshaper + python-bidi handle
that; the actual Arabic glyphs come from a bundled Noto Naskh Arabic
TTF (SIL Open Font License) in static/fonts, since the self-hosted
Archivo family is Latin-only and Vercel's Linux runtime has no system
Arabic font (unlike a local Windows dev machine's Arial).
"""

import io
import os

import arabic_reshaper
import barcode
from barcode.writer import ImageWriter
from bidi.algorithm import get_display
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
_NOTO_ARABIC = os.path.join(_FONTS_DIR, "noto-naskh-arabic.ttf")

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


def _arabic_font(size):
    try:
        return ImageFont.truetype(_NOTO_ARABIC, size)
    except Exception:
        return _arial_fallback(False, size)


def _ar(text):
    """Reshape + apply bidi so Arabic draws as connected script in the
    correct visual order -- PIL has no bidi/shaping support of its own."""
    return get_display(arabic_reshaper.reshape(text))


def _draw_bilingual_label(draw, x, y, en_text, ar_text, size=15, fill=None):
    """English label, then its Arabic translation alongside it -- mirrors
    the official template's "LABEL/ARABIC" bilingual field headers."""
    fill = fill or MDX_RED
    en_font = _dax("Bold", size)
    draw.text((x, y), en_text, font=en_font, fill=fill)
    en_w = draw.textlength(en_text, font=en_font)
    ar_font = _arabic_font(size)
    draw.text((x + en_w + 8, y), _ar(ar_text), font=ar_font, fill=fill)


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
    wordmark_font = _arabic_font(15)
    wordmark = _ar("جامعة ميدلسكس دبي")
    wordmark_w = draw.textlength(wordmark, font=wordmark_font)
    draw.text(((CARD_W - wordmark_w) / 2, top), wordmark, font=wordmark_font, fill=TEXT_SECONDARY)
    top += 24

    logo_path = os.path.join(_ASSETS_DIR, "mdx-logo.jpg")
    if not os.path.exists(logo_path):
        return top
    logo = Image.open(logo_path).convert("RGB")
    logo_h = 88
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


def render_card_front(record, photo_file, qr_file=None):
    """photo_file/qr_file are file-like objects (or None) -- already-open
    local files or in-memory buffers fetched from Blob storage; the caller
    resolves whichever storage backend is active before calling this."""
    card, draw = _new_card()
    margin = 42

    y = _draw_logo(card, draw, 14)
    y += 22

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
    value_font = _dax("Medium", 20)
    fields = [
        ("ID NUMBER", "\u0631\u0642\u0645 \u0645\u0639\u0631\u0641", record.get("Staff ID", "")),
        ("GENDER", "\u0627\u0644\u062c\u0646\u0633", record.get("Gender") or "\u2014"),
        ("EXPIRATION", "\u0627\u0646\u0642\u0636\u0627\u0621", "\u2014"),
    ]
    field_y = photo_y + 6
    for label, ar_label, value in fields:
        _draw_bilingual_label(draw, field_x, field_y, label, ar_label, size=13)
        draw.text((field_x, field_y + 20), value, font=value_font, fill=BLACK)
        field_y += 62

    name_y = photo_y + photo_h + 34
    name_font = _dax("Bold", 30)
    jobtitle_font = _dax("Medium", 22)

    _draw_bilingual_label(draw, margin, name_y, "NAME", "\u0627\u0633\u0645", size=15)
    full_name = f"{record.get('First Name', '')} {record.get('Last Name', '')}".strip()
    draw.text((margin, name_y + 24), full_name, font=name_font, fill=BLACK)

    title_y = name_y + 84
    _draw_bilingual_label(draw, margin, title_y, "JOB TITLE", "\u0627\u0644\u0648\u0638\u064a\u0641\u0629", size=15)
    job_title = record.get("Job Title", "")
    max_w = CARD_W - margin * 2
    for line in _wrap_text(draw, job_title, jobtitle_font, max_w)[:2]:
        draw.text((margin, title_y + 24), line, font=jobtitle_font, fill=BLACK)
        title_y += 28

    # The gap between Job Title and the bottom category bar is otherwise
    # empty on the official layout -- the vCard QR fills it naturally
    # rather than crowding the ID/Gender/Expiration column above.
    qr_size = 190
    qr_y = title_y + 44
    qr_x = (CARD_W - qr_size) // 2
    draw.rounded_rectangle(
        [qr_x - 8, qr_y - 8, qr_x + qr_size + 8, qr_y + qr_size + 8],
        radius=10, fill=(255, 255, 255), outline=(210, 205, 200), width=2,
    )
    if qr_file:
        qr_img = Image.open(qr_file).convert("RGB").resize((qr_size, qr_size), Image.NEAREST)
        card.paste(qr_img, (qr_x, qr_y))
    caption_font = _dax("Bold", 13)
    caption_text = "SCAN TO SAVE CONTACT"
    caption_w = draw.textlength(caption_text, font=caption_font)
    draw.text(((CARD_W - caption_w) / 2, qr_y + qr_size + 18), caption_text, font=caption_font, fill=TEXT_SECONDARY)

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


def _draw_partner_mark(card, draw, x, y):
    """A simple two-ring mark standing in for the Dubai Knowledge Park
    'PARTNER' co-brand shown on the official card back."""
    teal = (31, 122, 108)
    r = 11
    draw.ellipse([x, y, x + r * 2, y + r * 2], outline=teal, width=2)
    draw.ellipse([x + r, y, x + r * 3, y + r * 2], outline=teal, width=2)
    label_font = _dax("Bold", 10)
    lines = ["DUBAI", "KNOWLEDGE PARK", "PARTNER"]
    ly = y + r * 2 + 6
    for line in lines:
        w = draw.textlength(line, font=label_font)
        draw.text((x + r * 2 - w / 2, ly), line, font=label_font, fill=teal)
        ly += 13


def render_card_back(record):
    card, draw = _new_card()
    margin = 42

    idref_font = _dax("Medium", 13)
    idref_text = f"ID Ref# {record.get('Staff ID', '')}"
    idref_w = draw.textlength(idref_text, font=idref_font)
    draw.text((CARD_W - margin - idref_w, 26), idref_text, font=idref_font, fill=BLACK)

    it_label_font = _dax("Bold", 14)
    it_value_font = _dax("Regular", 17)
    it_fields = [
        ("UK IT User ID:", record.get("UK IT User ID") or "—"),
        ("MISIS:", record.get("MISIS") or "—"),
        ("Local Login:", record.get("Local Login") or "—"),
        ("Dubai Email:", record.get("Email") or "—"),
    ]
    y = 26
    for label, value in it_fields:
        draw.text((margin, y), label, font=it_label_font, fill=MDX_RED)
        draw.text((margin, y + 18), value, font=it_value_font, fill=BLACK)
        y += 46

    y += 14
    terms_font = _dax("Regular", 15)
    for term in CARD_TERMS:
        for line in _wrap_text(draw, f"\u2022 {term}", terms_font, CARD_W - margin * 2):
            draw.text((margin, y), line, font=terms_font, fill=TEXT_SECONDARY)
            y += 22
        y += 4

    y += 14
    draw.line([(margin, y), (CARD_W - margin, y)], fill=LINE, width=2)
    y += 20

    address_top = y
    address_name_font = _dax("Bold", 19)
    address_font = _dax("Regular", 16)
    draw.text((margin, y), "Middlesex University Dubai", font=address_name_font, fill=MDX_RED)
    y += 30
    for line in UNIVERSITY_ADDRESS_LINES:
        draw.text((margin, y), line, font=address_font, fill=BLACK)
        y += 22

    _draw_partner_mark(card, draw, CARD_W - margin - 90, address_top + 4)

    y += 40
    barcode_img = _generate_barcode_image(record.get("Staff ID", ""), CARD_W - margin * 2)
    card.paste(barcode_img, (margin, y))
    y += barcode_img.height + 6
    id_font = _dax("Bold", 15)
    id_text = record.get("Staff ID", "")
    id_w = draw.textlength(id_text, font=id_font)
    draw.text(((CARD_W - id_w) / 2, y), id_text, font=id_font, fill=BLACK)

    _draw_grey_bar(card, draw, UNIVERSITY_WEBSITE)
    return card
