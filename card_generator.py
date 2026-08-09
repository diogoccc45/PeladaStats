"""
Builds a shareable player-card PNG for a given profile — same visual language
as the in-app hero card (dark background, turf-green gradient, Rajdhani-style
bold numbers), rendered server-side with Pillow so it can be downloaded and
shared outside the app (WhatsApp, Instagram, etc.).

The player's photo (if any) is center-cropped to fill its slot ("cover"
style) — it does NOT replicate the custom zoom/position the player picked in
Settings; that's a deliberate simplification, this is a bonus sharing
feature, not a pixel-perfect copy of the profile page.
"""

import io
import os
import urllib.request

from PIL import Image, ImageDraw, ImageFont, ImageOps

FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "fonts", "Rajdhani-Bold.ttf")

BG_PRIMARY = (10, 14, 23)
BG_SURFACE = (18, 26, 43)
TURF = (110, 231, 135)
TURF_DIM = (62, 143, 91)
GOLD = (245, 185, 66)
TEXT_PRIMARY = (244, 247, 252)
TEXT_MUTED = (150, 162, 192)
DARK_TEXT = (10, 22, 11)

CARD_W, CARD_H = 1000, 950


def _font(size):
    return ImageFont.truetype(FONT_PATH, size)


def _fetch_image(url, timeout=4, max_bytes=5_000_000):
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(max_bytes)
        img = Image.open(io.BytesIO(data))
        img.load()
        return img.convert("RGBA")
    except Exception:
        return None


def _rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (size[0] - 1, size[1] - 1)], radius=radius, fill=255)
    return mask


def _diagonal_gradient(size, color_a, color_b):
    w, h = size
    grad = Image.new("RGB", size)
    px = grad.load()
    denom = max(1, (w - 1) + (h - 1))
    for y in range(h):
        for x in range(w):
            t = (x + y) / denom
            px[x, y] = tuple(round(color_a[i] + (color_b[i] - color_a[i]) * t) for i in range(3))
    return grad


def _initials(name):
    parts = (name or "?").strip().split()
    return "".join(p[0].upper() for p in parts[:2]) or "?"


def _text_w(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def build_player_card(user_row, summary):
    """user_row: a users table row (or dict-like with the same keys).
    summary: a stats.get_player_summary() result. Returns PNG bytes."""

    card = Image.new("RGB", (CARD_W, CARD_H), BG_PRIMARY)
    draw = ImageDraw.Draw(card)

    margin = 50
    inner_w = CARD_W - margin * 2

    # --- Hero panel (gradient, rounded corners, subtle border) ---
    panel_h = 780
    panel = _diagonal_gradient((inner_w, panel_h), (34, 66, 47), BG_SURFACE)
    mask = _rounded_mask((inner_w, panel_h), 36)
    card.paste(panel, (margin, margin), mask)
    draw.rounded_rectangle(
        [(margin, margin), (margin + inner_w, margin + panel_h)],
        radius=36, outline=TURF, width=2,
    )

    # Wordmark
    wordmark_font = _font(34)
    draw.text((margin + 36, margin + 32), "PELADA", font=wordmark_font, fill=TEXT_PRIMARY)
    pelada_w = _text_w(draw, "PELADA", wordmark_font)
    draw.text((margin + 36 + pelada_w, margin + 32), "STATS", font=wordmark_font, fill=TURF)

    # Overall
    overall_display = int(round(user_row["overall"]))
    ovr_font = _font(150)
    draw.text((margin + 36, margin + 90), str(overall_display), font=ovr_font, fill=TURF)
    label_font = _font(26)
    draw.text((margin + 40, margin + 250), "OVERALL", font=label_font, fill=TEXT_MUTED)

    # Portrait slot (top-right of the panel)
    portrait_size = 220
    portrait_pos = (margin + inner_w - portrait_size - 36, margin + 32)
    photo = _fetch_image(user_row["favorite_player_image_url"])
    slot_mask = _rounded_mask((portrait_size, portrait_size), 28)
    if photo:
        fitted = ImageOps.fit(photo.convert("RGB"), (portrait_size, portrait_size), method=Image.LANCZOS)
        card.paste(fitted, portrait_pos, slot_mask)
    else:
        avatar = Image.new("RGB", (portrait_size, portrait_size), BG_SURFACE)
        adraw = ImageDraw.Draw(avatar)
        initials_font = _font(70)
        text = _initials(user_row["nickname"])
        tw = _text_w(adraw, text, initials_font)
        adraw.text(((portrait_size - tw) / 2, portrait_size / 2 - 42), text, font=initials_font, fill=TEXT_MUTED)
        card.paste(avatar, portrait_pos, slot_mask)

    # Nickname + form
    name_font = _font(60)
    draw.text((margin + 36, margin + 320), user_row["nickname"], font=name_font, fill=TEXT_PRIMARY)

    form = summary.get("form", {"emoji": "⚪", "label": "Sem jogos"})
    form_font = _font(28)
    draw.text((margin + 40, margin + 400), form["label"], font=form_font, fill=TEXT_MUTED)

    # Divider
    divider_y = margin + 470
    draw.line([(margin + 36, divider_y), (margin + inner_w - 36, divider_y)], fill=(255, 255, 255), width=2)

    # Stat grid: Golos / Assistências / MVP / V-D-E
    stats_row = [
        (str(summary.get("goals", 0)), "GOLOS", TEXT_PRIMARY),
        (str(summary.get("assists", 0)), "ASSIST.", TEXT_PRIMARY),
        (str(summary.get("mvp", 0)), "MVP", GOLD),
        (f"{summary.get('wins', 0)}-{summary.get('draws', 0)}-{summary.get('losses', 0)}", "V-E-D", TEXT_PRIMARY),
    ]
    col_w = inner_w // 4
    stat_num_font = _font(52)
    stat_label_font = _font(22)
    for i, (value, label, color) in enumerate(stats_row):
        cx = margin + col_w * i + col_w // 2
        vw = _text_w(draw, value, stat_num_font)
        draw.text((cx - vw / 2, divider_y + 40), value, font=stat_num_font, fill=color)
        lw = _text_w(draw, label, stat_label_font)
        draw.text((cx - lw / 2, divider_y + 110), label, font=stat_label_font, fill=TEXT_MUTED)

    # Second row: Jogos + médias
    row2_y = divider_y + 170
    row2 = [
        (str(summary.get("games", 0)), "JOGOS"),
        (f"{summary.get('avg_goals', 0):.2f}", "MÉD. GOLOS"),
        (f"{summary.get('avg_assists', 0):.2f}", "MÉD. ASSIST."),
    ]
    col_w2 = inner_w // 3
    for i, (value, label) in enumerate(row2):
        cx = margin + col_w2 * i + col_w2 // 2
        vw = _text_w(draw, value, stat_num_font)
        draw.text((cx - vw / 2, row2_y), value, font=stat_num_font, fill=TEXT_PRIMARY)
        lw = _text_w(draw, label, stat_label_font)
        draw.text((cx - lw / 2, row2_y + 70), label, font=stat_label_font, fill=TEXT_MUTED)

    # Footer watermark
    footer_font = _font(24)
    footer_text = "peladastats"
    fw = _text_w(draw, footer_text, footer_font)
    draw.text((CARD_W - margin - fw, CARD_H - margin - 10), footer_text, font=footer_font, fill=TEXT_MUTED)

    buf = io.BytesIO()
    card.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()
