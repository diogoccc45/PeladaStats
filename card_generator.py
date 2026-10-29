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


# ---------------------------------------------------------------------------
# Match result card — a "FULL-TIME" broadcast-style graphic for a confirmed
# match: score plate between the two team badges, both line-ups with their
# goals/assists, and the MVP / Golo da Jornada. Text-only on purpose (no
# remote photos), so it renders identically everywhere — including hosts
# that can't make outbound requests.
# ---------------------------------------------------------------------------

PLATE_GOLD = (240, 200, 110)
BAR_BG = (8, 11, 19)
BAR_BORDER = (40, 48, 66)
TEAM_B_A = (87, 100, 140)
TEAM_B_B = (51, 62, 99)

MATCH_CARD_W = 1000


def _fit_text(draw, text, font, max_w):
    """Shortens text with an ellipsis until it fits max_w pixels."""
    if _text_w(draw, text, font) <= max_w:
        return text
    while len(text) > 1 and _text_w(draw, text + "…", font) > max_w:
        text = text[:-1]
    return text + "…"


def _star_points(cx, cy, r_outer, r_inner):
    import math
    pts = []
    for i in range(10):
        r = r_outer if i % 2 == 0 else r_inner
        ang = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def _stat_text(goals, assists):
    parts = []
    if goals:
        parts.append(f"{goals} golo{'s' if goals != 1 else ''}")
    if assists:
        parts.append(f"{assists} ass.")
    return " · ".join(parts)


def build_match_card(match, rows, mvp_nickname=None, golo_nickname=None):
    """match: a matches table row. rows: match_stats rows joined with the
    players' nickname (needs team, goals, assists, nickname). The MVP / Golo
    da Jornada nicknames are only passed when there's a single, unambiguous
    winner. Returns PNG bytes."""
    score_a, score_b = match["team_a_score"], match["team_b_score"]

    def team_rows(letter):
        mine = [r for r in rows if r["team"] == letter]
        return sorted(mine, key=lambda r: (-r["goals"], -r["assists"], r["nickname"].lower()))

    team_a, team_b = team_rows("A"), team_rows("B")
    n_rows = max(len(team_a), len(team_b), 1)

    margin = 50
    inner_w = MATCH_CARD_W - margin * 2
    row_h = 62
    awards = [a for a in (("mvp", mvp_nickname), ("golo", golo_nickname)) if a[1]]

    bar_top = 215
    bar_h = 170
    lineups_top = bar_top + bar_h + 138
    lineups_h = 70 + n_rows * row_h
    awards_h = 110 if awards else 0
    card_h = lineups_top + lineups_h + awards_h + 90

    card = Image.new("RGB", (MATCH_CARD_W, card_h), BG_PRIMARY)
    draw = ImageDraw.Draw(card)

    # Subtle green glow in the top-left, same mood as the player card
    glow = _diagonal_gradient((MATCH_CARD_W, 420), (24, 48, 36), BG_PRIMARY)
    fade = Image.linear_gradient("L").resize((MATCH_CARD_W, 420)).transpose(Image.FLIP_TOP_BOTTOM)
    card.paste(glow, (0, 0), fade)
    draw = ImageDraw.Draw(card)

    # Wordmark
    wordmark_font = _font(34)
    draw.text((margin, margin - 4), "PELADA", font=wordmark_font, fill=TEXT_PRIMARY)
    draw.text((margin + _text_w(draw, "PELADA", wordmark_font), margin - 4), "STATS", font=wordmark_font, fill=TURF)

    # FULL-TIME pill
    pill_w, pill_h = 300, 70
    pill_x = (MATCH_CARD_W - pill_w) // 2
    pill_y = 105
    draw.rounded_rectangle([(pill_x, pill_y), (pill_x + pill_w, pill_y + pill_h)], radius=pill_h // 2, fill=BAR_BG, outline=PLATE_GOLD, width=3)
    draw.text((MATCH_CARD_W // 2, pill_y + pill_h // 2 + 1), "FULL-TIME", font=_font(44), fill=TEXT_PRIMARY, anchor="mm")

    # Scoreboard bar
    draw.rounded_rectangle([(margin, bar_top), (margin + inner_w, bar_top + bar_h)], radius=40, fill=BAR_BG, outline=BAR_BORDER, width=2)
    cy = bar_top + bar_h // 2

    badge = 112
    badge_font = _font(60)
    bx_left = margin + 34
    bx_right = margin + inner_w - 34 - badge
    for x, letter, (c1, c2), txt_color in (
        (bx_left, "A", (TURF, TURF_DIM), (4, 22, 11)),
        (bx_right, "B", (TEAM_B_A, TEAM_B_B), TEXT_PRIMARY),
    ):
        grad = _diagonal_gradient((badge, badge), c1, c2)
        card.paste(grad, (x, cy - badge // 2), _rounded_mask((badge, badge), 28))
        draw.text((x + badge // 2, cy - 2), letter, font=badge_font, fill=txt_color, anchor="mm")

    score_font = _font(128)
    score_text = f"{score_a} : {score_b}"
    plate_w = max(380, _text_w(draw, score_text, score_font) + 90)
    plate_h = 134
    plate_x = (MATCH_CARD_W - plate_w) // 2
    draw.rounded_rectangle([(plate_x, cy - plate_h // 2), (plate_x + plate_w, cy + plate_h // 2)], radius=26, fill=PLATE_GOLD)
    draw.text((MATCH_CARD_W // 2, cy + 4), score_text, font=score_font, fill=BG_PRIMARY, anchor="mm")

    # Result caption + date/place
    if score_a == score_b:
        caption, caption_color = "EMPATE", GOLD
    else:
        caption = f"VITÓRIA DA EQUIPA {'A' if score_a > score_b else 'B'}"
        caption_color = TURF
    draw.text((MATCH_CARD_W // 2, bar_top + bar_h + 42), caption, font=_font(36), fill=caption_color, anchor="mm")
    where = str(match["match_date"]) + (f" · {match['location']}" if match["location"] else "")
    where = _fit_text(draw, where, _font(28), inner_w)
    draw.text((MATCH_CARD_W // 2, bar_top + bar_h + 88), where, font=_font(28), fill=TEXT_MUTED, anchor="mm")

    # Line-ups
    gap = 50
    col_w = (inner_w - gap) // 2
    name_font = _font(38)
    stat_font = _font(28)
    for col, (letter, players, accent) in enumerate((("A", team_a, TURF), ("B", team_b, (140, 156, 205)))):
        x0 = margin + col * (col_w + gap)
        draw.text((x0, lineups_top), f"EQUIPA {letter}", font=_font(30), fill=accent)
        draw.line([(x0, lineups_top + 46), (x0 + col_w, lineups_top + 46)], fill=BAR_BORDER, width=2)
        y = lineups_top + 70
        if not players:
            draw.text((x0, y + row_h // 2), "Sem jogadores da app", font=stat_font, fill=TEXT_MUTED, anchor="lm")
        for r in players:
            stat = _stat_text(r["goals"], r["assists"])
            stat_w = _text_w(draw, stat, stat_font) if stat else 0
            name = _fit_text(draw, r["nickname"], name_font, col_w - stat_w - (24 if stat else 0))
            draw.text((x0, y + row_h // 2), name, font=name_font, fill=TEXT_PRIMARY, anchor="lm")
            if stat:
                draw.text((x0 + col_w, y + row_h // 2 + 2), stat, font=stat_font, fill=TEXT_MUTED, anchor="rm")
            y += row_h

    # Awards strip
    if awards:
        ay = lineups_top + lineups_h + 20
        award_w = (inner_w - gap) // 2 if len(awards) == 2 else inner_w
        for i, (kind, nick) in enumerate(awards):
            ax = margin + i * (award_w + gap)
            color = GOLD if kind == "mvp" else TURF
            draw.rounded_rectangle([(ax, ay), (ax + award_w, ay + 84)], radius=22, fill=BG_SURFACE, outline=color, width=2)
            icon_cx, icon_cy = ax + 44, ay + 42
            if kind == "mvp":
                draw.polygon(_star_points(icon_cx, icon_cy, 20, 8.5), fill=color)
                label = "MVP"
            else:
                draw.ellipse([(icon_cx - 19, icon_cy - 19), (icon_cx + 19, icon_cy + 19)], outline=color, width=4)
                draw.ellipse([(icon_cx - 7, icon_cy - 7), (icon_cx + 7, icon_cy + 7)], fill=color)
                label = "GOLO DA JORNADA"
            draw.text((ax + 82, ay + 25), label, font=_font(22), fill=color, anchor="lm")
            draw.text((ax + 82, ay + 57), _fit_text(draw, nick, _font(36), award_w - 100), font=_font(36), fill=TEXT_PRIMARY, anchor="lm")

    # Footer
    footer_font = _font(24)
    footer_text = "peladastats"
    draw.text((MATCH_CARD_W - margin, card_h - margin + 8), footer_text, font=footer_font, fill=TEXT_MUTED, anchor="rm")

    buf = io.BytesIO()
    card.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()
