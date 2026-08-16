"""Composes the downloadable Staff Digital ID card as two images -- front
and back -- matching the official Middlesex University Dubai Staff ID
badge template (portrait CR80 badge, 2.125in x 3.375in) rather than an
invented landscape business-card layout: white body, photo box, ID
Number / Gender / Expiration column, Name / Job Title, the
scan-to-save-contact vCard QR (filling what would otherwise be empty
space below Job Title), and a solid red category bar on the front;
IT-office terms, the university address, and a Code128 barcode of the
Staff ID on the back.

The card is rendered at 1.5x the on-screen badge size (RENDER_SCALE
below) and then downscaled by the browser to whatever preview size the
page needs. Rendering at native badge resolution and letting a small
<img> box shrink it looks soft/faded once the box gets much smaller
than the source -- supersampling here keeps fine text (the back-side
IT fields, terms, and address block) crisp at any preview size.

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
MDX_RED_DARK = (184, 5, 15)
BLACK = (26, 24, 34)
TEXT_SECONDARY = (98, 95, 107)
LINE = (225, 220, 210)
CARD_BG = (253, 253, 253)

RENDER_SCALE = 1.5
CARD_W, CARD_H = round(638 * RENDER_SCALE), round(1013 * RENDER_SCALE)


def _s(v):
    return round(v * RENDER_SCALE)


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
    draw.text((x + en_w + _s(8), y), _ar(ar_text), font=ar_font, fill=fill)


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


def _draw_logo(card, draw, top, left_x):
    """Logo sits left-aligned with the photo box just below it (not spanning
    the full card width) -- it reads as sitting a little above the photo
    rather than as a separate centered banner."""
    wordmark_font = _arabic_font(_s(15))
    wordmark = _ar("جامعة ميدلسكس دبي")
    draw.text((left_x, top), wordmark, font=wordmark_font, fill=TEXT_SECONDARY)
    top += _s(22)

    logo_path = os.path.join(_ASSETS_DIR, "mdx-logo.jpg")
    if not os.path.exists(logo_path):
        return top
    logo = Image.open(logo_path).convert("RGB")
    logo_h = _s(72)
    ratio = logo_h / logo.height
    logo = logo.resize((max(1, int(logo.width * ratio)), logo_h), Image.LANCZOS)
    card.paste(logo, (left_x, top))
    return top + logo_h


def _draw_category_bar(card, draw, text):
    bar_h = _s(56)
    top = CARD_H - bar_h
    draw.rectangle([0, top, CARD_W, CARD_H], fill=MDX_RED)

    max_w = CARD_W - _s(40)
    size = _s(20)
    min_size = _s(11)
    font = _monument(size)
    while size > min_size and draw.textlength(text, font=font) > max_w:
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
    margin = _s(42)

    y = _draw_logo(card, draw, _s(14), margin)
    y += _s(20)

    photo_w, photo_h = _s(168), _s(200)
    photo_x, photo_y = margin, y
    if photo_file:
        photo = Image.open(photo_file).convert("RGB")
        photo = ImageOps.fit(photo, (photo_w, photo_h), Image.LANCZOS)
        card.paste(photo, (photo_x, photo_y))
    draw.rectangle(
        [photo_x - 2, photo_y - 2, photo_x + photo_w + 2, photo_y + photo_h + 2],
        outline=(0, 0, 0), width=3,
    )

    field_x = photo_x + photo_w + _s(30)
    value_font = _dax("Medium", _s(20))
    fields = [
        ("ID NUMBER", "رقم معرف", record.get("Staff ID", "")),
        ("GENDER", "الجنس", record.get("Gender") or "—"),
    ]
    # Only full-time staff get a permanent card -- everyone else (contract,
    # part-time, visiting) has a fixed-term appointment, so their card shows
    # an expiration field. Full-time staff cards omit it entirely.
    if (record.get("Employment Status") or "").strip() != "Full-Time":
        fields.append(("EXPIRATION", "انقضاء", "—"))
    field_y = photo_y + _s(6)
    for label, ar_label, value in fields:
        _draw_bilingual_label(draw, field_x, field_y, label, ar_label, size=_s(13))
        draw.text((field_x, field_y + _s(20)), value, font=value_font, fill=BLACK)
        field_y += _s(62)

    name_y = photo_y + photo_h + _s(34)
    name_font = _dax("Bold", _s(30))
    jobtitle_font = _dax("Medium", _s(22))

    _draw_bilingual_label(draw, margin, name_y, "NAME", "اسم", size=_s(15))
    full_name = f"{record.get('First Name', '')} {record.get('Last Name', '')}".strip()
    draw.text((margin, name_y + _s(24)), full_name, font=name_font, fill=BLACK)

    title_y = name_y + _s(84)
    _draw_bilingual_label(draw, margin, title_y, "JOB TITLE", "الوظيفة", size=_s(15))
    job_title = record.get("Job Title", "")
    max_w = CARD_W - margin * 2
    for line in _wrap_text(draw, job_title, jobtitle_font, max_w)[:2]:
        draw.text((margin, title_y + _s(24)), line, font=jobtitle_font, fill=BLACK)
        title_y += _s(28)

    # The gap between Job Title and the bottom category bar is otherwise
    # empty on the official layout -- the vCard QR fills it naturally
    # rather than crowding the ID/Gender/Expiration column above.
    qr_size = _s(190)
    qr_y = title_y + _s(110)
    qr_x = (CARD_W - qr_size) // 2
    draw.rounded_rectangle(
        [qr_x - _s(8), qr_y - _s(8), qr_x + qr_size + _s(8), qr_y + qr_size + _s(8)],
        radius=_s(10), fill=(255, 255, 255), outline=(210, 205, 200), width=3,
    )
    if qr_file:
        qr_img = Image.open(qr_file).convert("RGB").resize((qr_size, qr_size), Image.NEAREST)
        card.paste(qr_img, (qr_x, qr_y))
    caption_font = _dax("Bold", _s(13))
    caption_text = "SCAN TO SAVE CONTACT"
    caption_w = draw.textlength(caption_text, font=caption_font)
    draw.text(((CARD_W - caption_w) / 2, qr_y + qr_size + _s(18)), caption_text, font=caption_font, fill=TEXT_SECONDARY)

    _draw_category_bar(card, draw, (record.get("Department") or "STAFF").upper())
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


def _draw_partner_mark(card, draw, right_x, y):
    """The Dubai Knowledge Park co-brand mark shown on the official card
    back: three tightly overlapping teal rings (the real mark's rings
    interlock closely, leaving a small rounded-triangle gap where all
    three meet -- spacing them further apart reads as three separate
    dots instead of one knot) beside a stacked "DUBAI / KNOWLEDGE / PARK"
    wordmark in dark charcoal, no border/box. right_x is the mark's right
    edge, right-aligned against the card's margin like the address block
    above it."""
    teal = (23, 106, 93)
    text_color = (58, 58, 58)
    lines = ["DUBAI", "KNOWLEDGE", "PARK"]
    label_font = _monument(_s(11))
    line_h = _s(13)
    text_block_h = line_h * len(lines)
    gap = _s(8)

    label_w = max(draw.textlength(line, font=label_font) for line in lines)
    icon_d = text_block_h
    total_w = icon_d + gap + label_w
    x0 = right_x - total_w

    icon_cx, icon_cy = x0 + icon_d / 2, y + text_block_h / 2
    r = icon_d * 0.34
    offset = r * 0.8
    ring_centers = [
        (icon_cx, icon_cy - offset),
        (icon_cx - offset * 0.87, icon_cy + offset * 0.5),
        (icon_cx + offset * 0.87, icon_cy + offset * 0.5),
    ]
    for cx, cy in ring_centers:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=teal, width=max(2, _s(2)))

    text_x = x0 + icon_d + gap
    for i, line in enumerate(lines):
        draw.text((text_x, y + i * line_h), line, font=label_font, fill=text_color)


def render_card_back(record):
    card, draw = _new_card()
    margin = _s(42)

    idref_font = _dax("Medium", _s(13))
    idref_text = f"ID Ref# {record.get('Staff ID', '')}"
    idref_w = draw.textlength(idref_text, font=idref_font)
    draw.text((CARD_W - margin - idref_w, _s(26)), idref_text, font=idref_font, fill=BLACK)

    it_label_font = _dax("Bold", _s(14))
    it_value_font = _dax("Regular", _s(17))
    it_fields = [
        ("UK IT User ID:", record.get("UK IT User ID") or "—"),
        ("MISIS:", record.get("MISIS") or "—"),
        ("Local Login:", record.get("Local Login") or "—"),
        ("Dubai Email:", record.get("Email") or "—"),
    ]
    y = _s(26)
    for label, value in it_fields:
        draw.text((margin, y), label, font=it_label_font, fill=MDX_RED)
        draw.text((margin, y + _s(18)), value, font=it_value_font, fill=BLACK)
        y += _s(46)

    y += _s(14)
    terms_font = _dax("Regular", _s(15))
    for term in CARD_TERMS:
        for line in _wrap_text(draw, f"• {term}", terms_font, CARD_W - margin * 2):
            draw.text((margin, y), line, font=terms_font, fill=TEXT_SECONDARY)
            y += _s(22)
        y += _s(4)

    y += _s(14)
    draw.line([(margin, y), (CARD_W - margin, y)], fill=LINE, width=max(2, _s(2)))
    y += _s(20)

    address_top = y
    address_name_font = _dax("Bold", _s(19))
    address_font = _dax("Regular", _s(16))
    draw.text((margin, y), "Middlesex University Dubai", font=address_name_font, fill=MDX_RED)
    y += _s(30)
    for line in UNIVERSITY_ADDRESS_LINES:
        draw.text((margin, y), line, font=address_font, fill=BLACK)
        y += _s(22)

    _draw_partner_mark(card, draw, CARD_W - margin, address_top + _s(4))

    y += _s(170)
    barcode_img = _generate_barcode_image(record.get("Staff ID", ""), CARD_W - margin * 2)
    card.paste(barcode_img, (margin, y))
    y += barcode_img.height + _s(6)
    id_font = _dax("Bold", _s(15))
    id_text = record.get("Staff ID", "")
    id_w = draw.textlength(id_text, font=id_font)
    draw.text(((CARD_W - id_w) / 2, y), id_text, font=id_font, fill=BLACK)

    _draw_category_bar(card, draw, UNIVERSITY_WEBSITE)
    return card
