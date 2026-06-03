"""
Generates a bracket image (PNG) using Pillow.
Renders Winners bracket, Losers bracket and Grand Finals side by side.
"""

from __future__ import annotations
import io
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from tournament import Tournament, Match

# ─── visual constants ────────────────────────────────────────────────────────

BG_COLOR        = (15, 17, 26)          # dark navy
PANEL_COLOR     = (25, 28, 42)
W_HEADER        = (212, 60, 60)         # red  – winners
L_HEADER        = (60, 120, 212)        # blue – losers
GF_HEADER       = (180, 140, 20)        # gold – grand finals
MATCH_BG        = (35, 38, 55)
MATCH_BORDER    = (60, 65, 90)
WIN_COLOR       = (80, 200, 120)        # green highlight for winner
PENDING_COLOR   = (150, 155, 180)
TEXT_COLOR      = (220, 225, 240)
HEADER_TEXT     = (240, 240, 255)
LINE_COLOR      = (80, 90, 120)

SLOT_W          = 200
SLOT_H          = 28
MATCH_PAD       = 6
MATCH_W         = SLOT_W + MATCH_PAD * 2
MATCH_H         = SLOT_H * 2 + MATCH_PAD * 3  # two slots + padding
V_GAP           = 20       # vertical gap between matches in the same round
H_GAP           = 60       # horizontal gap between rounds
SECTION_GAP     = 40       # gap between W / L / GF sections
HEADER_H        = 30
MARGIN          = 20

FONT_SIZE       = 13
FONT_SMALL      = 11

try:
    _font      = ImageFont.truetype("arial.ttf", FONT_SIZE)
    _font_bold = ImageFont.truetype("arialbd.ttf", FONT_SIZE)
    _font_sm   = ImageFont.truetype("arial.ttf", FONT_SMALL)
    _font_hdr  = ImageFont.truetype("arialbd.ttf", 14)
except OSError:
    _font = _font_bold = _font_sm = _font_hdr = ImageFont.load_default()


# ─── helpers ─────────────────────────────────────────────────────────────────

def _player_label(pid: Optional[str], names: dict, winner: Optional[str]) -> tuple[str, tuple]:
    if pid is None:
        return "...", (60, 65, 90)       # slot vide, en attente
    if pid == "__BYE__":
        return "BYE", PENDING_COLOR      # bye réel (pas de joueur)
    name = names.get(pid, f"#{pid[-4:]}")
    color = WIN_COLOR if pid == winner else (TEXT_COLOR if winner is None else (130, 130, 150))
    return name[:22], color


def _draw_match(draw: ImageDraw.Draw, x: int, y: int, m: Match, names: dict):
    # Background
    draw.rectangle([x, y, x + MATCH_W, y + MATCH_H], fill=MATCH_BG, outline=MATCH_BORDER)

    # Match id label
    draw.text((x + MATCH_PAD, y + 2), f"M{m.match_id}", font=_font_sm, fill=(100, 105, 140))

    # Slot 1
    sy1 = y + MATCH_PAD + 12
    label1, col1 = _player_label(m.player1, names, m.winner)
    draw.rectangle([x + MATCH_PAD, sy1, x + MATCH_PAD + SLOT_W, sy1 + SLOT_H - 2],
                   fill=(28, 32, 48), outline=MATCH_BORDER)
    draw.text((x + MATCH_PAD + 5, sy1 + 6), label1, font=_font, fill=col1)

    # Divider
    dy = sy1 + SLOT_H + 1
    draw.line([(x + MATCH_PAD, dy), (x + MATCH_PAD + SLOT_W, dy)], fill=MATCH_BORDER)

    # Slot 2
    sy2 = dy + 2
    label2, col2 = _player_label(m.player2, names, m.winner)
    draw.rectangle([x + MATCH_PAD, sy2, x + MATCH_PAD + SLOT_W, sy2 + SLOT_H - 2],
                   fill=(28, 32, 48), outline=MATCH_BORDER)
    draw.text((x + MATCH_PAD + 5, sy2 + 6), label2, font=_font, fill=col2)


def _match_center_y(y: int) -> int:
    return y + MATCH_H // 2


def _draw_connector(draw: ImageDraw.Draw, x1: int, cy1: int, x2: int, cy2: int):
    """Draw an L-shaped connector between two matches."""
    mid_x = (x1 + x2) // 2
    draw.line([(x1, cy1), (mid_x, cy1)], fill=LINE_COLOR, width=2)
    draw.line([(mid_x, cy1), (mid_x, cy2)], fill=LINE_COLOR, width=2)
    draw.line([(mid_x, cy2), (x2, cy2)], fill=LINE_COLOR, width=2)


def _section_header(draw: ImageDraw.Draw, x: int, y: int, w: int, label: str, color: tuple):
    draw.rectangle([x, y, x + w, y + HEADER_H], fill=color)
    draw.text((x + w // 2, y + 7), label, font=_font_hdr, fill=HEADER_TEXT, anchor="mt")


# ─── layout ──────────────────────────────────────────────────────────────────

def _group_by_round(matches: list[Match]) -> dict[int, list[Match]]:
    rounds: dict[int, list[Match]] = {}
    for m in matches:
        rounds.setdefault(m.round_num, []).append(m)
    # sort within each round by match_id for stable layout
    for r in rounds:
        rounds[r].sort(key=lambda m: m.match_id)
    return rounds


def _calc_section_size(rounds: dict[int, list[Match]]) -> tuple[int, int]:
    """Returns (width, height) of a bracket section."""
    if not rounds:
        return 0, 0
    num_rounds = len(rounds)
    max_matches = max(len(v) for v in rounds.values())
    w = num_rounds * (MATCH_W + H_GAP) - H_GAP
    h = max_matches * (MATCH_H + V_GAP) - V_GAP + HEADER_H + MARGIN
    return w, h


def _draw_section(draw: ImageDraw.Draw, ox: int, oy: int,
                  rounds: dict[int, list[Match]], names: dict,
                  label: str, color: tuple) -> int:
    """Draw one section (W/L/GF). Returns the rightmost x used."""
    if not rounds:
        return ox

    sorted_rnds = sorted(rounds.keys())
    max_matches_r1 = len(rounds[sorted_rnds[0]])
    section_w, section_h = _calc_section_size(rounds)

    _section_header(draw, ox, oy, section_w, label, color)
    oy += HEADER_H + MARGIN

    # For each round, compute y positions (centered vertically)
    round_positions: dict[int, list[int]] = {}
    for rn in sorted_rnds:
        matches = rounds[rn]
        n = len(matches)
        total_h = n * MATCH_H + (n - 1) * V_GAP
        # Total canvas height for this section
        canvas_h = max_matches_r1 * (MATCH_H + V_GAP) - V_GAP
        start_y = oy + (canvas_h - total_h) // 2
        ys = [start_y + i * (MATCH_H + V_GAP) for i in range(n)]
        round_positions[rn] = ys

    # Draw connectors first (so they appear behind matches)
    for rn in sorted_rnds:
        matches = rounds[rn]
        for idx, m in enumerate(matches):
            if m.winner_goes_to is None:
                continue
            # Find the target match in the next round
            next_rn = rn + 1
            if next_rn not in rounds:
                continue
            next_matches = rounds[next_rn]
            target_idx = next(
                (i for i, nm in enumerate(next_matches) if nm.match_id == m.winner_goes_to),
                None
            )
            if target_idx is None:
                continue
            rx = ox + sorted_rnds.index(rn) * (MATCH_W + H_GAP)
            nrx = ox + sorted_rnds.index(next_rn) * (MATCH_W + H_GAP)
            cy1 = round_positions[rn][idx] + MATCH_H // 2
            cy2 = round_positions[next_rn][target_idx] + MATCH_H // 2
            _draw_connector(draw, rx + MATCH_W, cy1, nrx, cy2)

    # Draw matches
    for rn in sorted_rnds:
        matches = rounds[rn]
        rx = ox + sorted_rnds.index(rn) * (MATCH_W + H_GAP)
        for idx, m in enumerate(matches):
            my = round_positions[rn][idx]
            _draw_match(draw, rx, my, m, names)

    return ox + section_w


# ─── public API ──────────────────────────────────────────────────────────────

def generate_bracket_image(t: Tournament) -> bytes:
    """Returns PNG bytes for the current bracket state."""
    # Exclude ghost matches (BYE vs BYE auto-resolved, no real players)
    all_matches = [m for m in t.matches.values()
                   if not (m.winner == "__BYE__")]

    w_matches  = [m for m in all_matches if m.bracket == "winners"]
    l_matches  = [m for m in all_matches if m.bracket == "losers"]
    gf_matches = [m for m in all_matches if m.bracket == "grand_finals"]

    w_rounds  = _group_by_round(w_matches)
    l_rounds  = _group_by_round(l_matches)
    gf_rounds = _group_by_round(gf_matches)

    w_w,  w_h  = _calc_section_size(w_rounds)
    l_w,  l_h  = _calc_section_size(l_rounds)
    gf_w, gf_h = _calc_section_size(gf_rounds)

    total_w = w_w + (SECTION_GAP + l_w if l_w else 0) + (SECTION_GAP + gf_w if gf_w else 0) + MARGIN * 2
    total_h = max(w_h, l_h, gf_h) + MARGIN * 2 + HEADER_H

    img  = Image.new("RGB", (max(total_w, 400), max(total_h, 200)), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Title
    draw.text((MARGIN, MARGIN), "ONE PIECE TCG – Tournament Bracket",
              font=_font_hdr, fill=(220, 80, 80))

    cx = MARGIN
    cy = MARGIN + 24

    cx = _draw_section(draw, cx, cy, w_rounds,  t.player_names, "WINNERS BRACKET", W_HEADER) + SECTION_GAP
    if l_w:
        cx = _draw_section(draw, cx, cy, l_rounds, t.player_names, "LOSERS BRACKET",  L_HEADER) + SECTION_GAP
    if gf_w:
        _draw_section(draw, cx, cy, gf_rounds, t.player_names, "GRAND FINALS", GF_HEADER)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()
