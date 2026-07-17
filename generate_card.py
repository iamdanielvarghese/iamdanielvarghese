"""
Generate the neofetch-style profile card SVG (dark + light themes).

Reads:
  portrait.txt              - ASCII character grid (from ascii_portrait.py)
  portrait_brightness.txt   - per-cell brightness 0..1, same grid shape
  card_data.json            - editable field content
  stats.json                - live GitHub stats (written daily by Action)

Writes:
  card-dark.svg / card-light.svg   - animated, real deliverables
  card-dark-static.svg / card-light-static.svg - no animation, for QA preview
"""
import json
import textwrap
import copy

# ---------- layout constants ----------
PORTRAIT_CELL_W = 4.5
PORTRAIT_CELL_H = 9.0

FONT_SIZE = 11.5
CHAR_W = 7.0
LINE_H = 15.5
NAME_FONT_SIZE = 17
NAME_LINE_H = 24
BLANK_H = 9

LABEL_COL_CHARS = 17
LABEL_COL_W = LABEL_COL_CHARS * CHAR_W
VALUE_WRAP_CHARS = 42
VALUE_COL_W = VALUE_WRAP_CHARS * CHAR_W

PADDING = 22
COLUMN_GAP = 26
TOPBAR_H = 34
PROMPT_H = 24
GAP_AFTER_PROMPT = 12
GAP_BEFORE_BOTTOM = 18
BOTTOMBAR_H = 34

SPARK_W = VALUE_COL_W
SPARK_H = 34
SPARK_RESERVE_LINES = 3  # vertical space reserved in line-count terms

FONT_STACK = ("'Cascadia Code','Fira Code','JetBrains Mono',Consolas,"
              "'Liberation Mono',Menlo,monospace")

THEMES = {
    "dark": {
        "bg": "#0D1117",
        "window_bg": "#0D1117",
        "chrome_bar": "#161B22",
        "border": "#30363D",
        "rule": "#21262D",
        "text_dim": "#6E7681",
        "name": "#A78BFA",
        "section": "#56D4DD",
        "label": "#7EE787",
        "value": "#C9D1D9",
        "link": "#79C0FF",
        "prompt": "#7EE787",
        "dots": ["#FF5F56", "#FFBD2E", "#27C93F"],
        "portrait": "#A78BFA",
        "cursor": "#A78BFA",
        "spark_stroke": "#A78BFA",
        "spark_fill": "#A78BFA22",
    },
    "light": {
        "bg": "#FFFFFF",
        "window_bg": "#F6F8FA",
        "chrome_bar": "#EAEEF2",
        "border": "#D0D7DE",
        "rule": "#D8DEE4",
        "text_dim": "#6E7781",
        "name": "#6E40C9",
        "section": "#0B6E75",
        "label": "#116329",
        "value": "#24292F",
        "link": "#0969DA",
        "prompt": "#116329",
        "dots": ["#FF5F56", "#FFBD2E", "#27C93F"],
        "portrait": "#3A2A5C",
        "cursor": "#6E40C9",
        "spark_stroke": "#6E40C9",
        "spark_fill": "#6E40C922",
    },
}

REACH_LABELS = {"GitHub", "LinkedIn", "X"}


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def load_portrait():
    with open("portrait.txt") as f:
        rows = [line.rstrip("\n") for line in f]
    with open("portrait_brightness.txt") as f:
        bright = [[float(v) for v in line.strip().split(",")] for line in f]
    return rows, bright


def substitute(obj, mapping):
    if isinstance(obj, str):
        for k, v in mapping.items():
            obj = obj.replace("{{" + k + "}}", v)
        return obj
    if isinstance(obj, list):
        return [substitute(x, mapping) for x in obj]
    if isinstance(obj, dict):
        return {k: substitute(v, mapping) for k, v in obj.items()}
    return obj


def build_portrait_group(rows, bright, color, stagger=True):
    """Row-run-length-encoded, opacity-shaded portrait with per-character
    x positions for exact grid alignment (no font-dependent stretching)."""
    n_rows = len(rows)
    n_bands = 12
    band_size = max(1, -(-n_rows // n_bands))  # ceil div

    band_groups = []
    for band_start in range(0, n_rows, band_size):
        band_rows = rows[band_start: band_start + band_size]
        band_bright = bright[band_start: band_start + band_size]
        row_svgs = []
        for i, row in enumerate(band_rows):
            r = band_start + i
            y = r * PORTRAIT_CELL_H + PORTRAIT_CELL_H * 0.85
            runs = []
            col = 0
            n = len(row)
            while col < n:
                ch = row[col]
                if ch == " ":
                    col += 1
                    continue
                b = band_bright[i][col]
                density = 1.0 - b
                bucket = round(density * 5) / 5.0
                run_start = col
                run_chars = [ch]
                col += 1
                while col < n and row[col] != " ":
                    b2 = band_bright[i][col]
                    d2 = 1.0 - b2
                    bucket2 = round(d2 * 5) / 5.0
                    if bucket2 != bucket:
                        break
                    run_chars.append(row[col])
                    col += 1
                runs.append((run_start, "".join(run_chars), bucket))
            for run_start, text, bucket in runs:
                opacity = 0.32 + 0.62 * bucket
                # Explicit per-character x positions: guarantees exact grid
                # alignment with no glyph stretching, regardless of which
                # monospace font the viewer's browser actually substitutes.
                xs = " ".join(f"{(run_start+i)*PORTRAIT_CELL_W:.1f}" for i in range(len(text)))
                row_svgs.append(
                    f'<text x="{xs}" y="{y:.1f}" font-size="{PORTRAIT_CELL_H*0.92:.1f}" '
                    f'font-family="{FONT_STACK}" fill="{color}" fill-opacity="{opacity:.2f}">'
                    f'{esc(text)}</text>'
                )
        band_content = "".join(row_svgs)
        if stagger:
            band_idx = band_start // band_size
            begin = 0.15 + band_idx * 0.09
            band_groups.append(
                f'<g opacity="0">{band_content}'
                f'<animate attributeName="opacity" from="0" to="1" dur="0.5s" '
                f'begin="{begin:.2f}s" fill="freeze"/></g>'
            )
        else:
            band_groups.append(f'<g opacity="1">{band_content}</g>')

    width = len(rows[0]) * PORTRAIT_CELL_W
    height = n_rows * PORTRAIT_CELL_H
    return "".join(band_groups), width, height


def build_sparkline(values, color_stroke, color_fill, x0, y0, w, h):
    if not values or max(values) == 0:
        vmax = 1
    else:
        vmax = max(values)
    n = len(values)
    step = w / max(1, n - 1)
    pts = []
    for i, v in enumerate(values):
        px = x0 + i * step
        py = y0 + h - (v / vmax) * h
        pts.append((px, py))
    poly = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    fill_pts = f"{x0:.1f},{y0+h:.1f} " + poly + f" {x0+w:.1f},{y0+h:.1f}"
    # approximate path length for the dash-draw animation
    length = 0.0
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        dy = pts[i][1] - pts[i - 1][1]
        length += (dx ** 2 + dy ** 2) ** 0.5
    length = max(length, 1.0)
    svg = (
        f'<polygon points="{fill_pts}" fill="{color_fill}" stroke="none"/>'
        f'<polyline points="{poly}" fill="none" stroke="{color_stroke}" stroke-width="1.6" '
        f'stroke-linejoin="round" stroke-linecap="round" '
        f'stroke-dasharray="{length:.1f}" stroke-dashoffset="{length:.1f}">'
        f'<animate attributeName="stroke-dashoffset" from="{length:.1f}" to="0" '
        f'dur="1.1s" begin="2.6s" fill="freeze"/>'
        f'</polyline>'
    )
    for px, py in pts:
        svg += f'<circle cx="{px:.1f}" cy="{py:.1f}" r="1.3" fill="{color_stroke}" opacity="0.85"/>'
    return svg


class ReadoutBuilder:
    def __init__(self, theme, stagger=True):
        self.t = theme
        self.stagger = stagger
        self.y = 0.0
        self.line_idx = 0
        self.svg_parts = []

    def _line_wrapper(self, content, extra_h=0.0):
        if self.stagger:
            begin = 0.55 + self.line_idx * 0.045
            self.svg_parts.append(
                f'<g opacity="0" transform="translate(-6,0)">{content}'
                f'<animate attributeName="opacity" from="0" to="1" dur="0.28s" '
                f'begin="{begin:.2f}s" fill="freeze"/>'
                f'<animateTransform attributeName="transform" type="translate" '
                f'from="-6,0" to="0,0" dur="0.28s" begin="{begin:.2f}s" '
                f'fill="freeze" additive="sum"/></g>'
            )
        else:
            self.svg_parts.append(content)
        self.line_idx += 1
        self.y += LINE_H + extra_h

    def blank(self):
        self.y += BLANK_H

    def name(self, text):
        y = self.y + NAME_FONT_SIZE * 0.8
        content = (f'<text x="0" y="{y:.1f}" font-size="{NAME_FONT_SIZE}" '
                   f'font-weight="700" font-family="{FONT_STACK}" '
                   f'fill="{self.t["name"]}">{esc(text)}</text>')
        if self.stagger:
            self.svg_parts.append(
                f'<g opacity="0">{content}'
                f'<animate attributeName="opacity" from="0" to="1" dur="0.4s" '
                f'begin="0.05s" fill="freeze"/></g>'
            )
        else:
            self.svg_parts.append(content)
        self.y += NAME_LINE_H

    def section_title(self, title):
        y = self.y + FONT_SIZE * 0.95
        content = (f'<text x="0" y="{y:.1f}" font-size="{FONT_SIZE}" font-weight="700" '
                   f'font-family="{FONT_STACK}" fill="{self.t["section"]}">{esc(title)}</text>')
        self._line_wrapper(content)

    def field(self, label, value, is_reach=False):
        wrapped = textwrap.wrap(value, width=VALUE_WRAP_CHARS) or [""]
        first = True
        for line in wrapped:
            y = self.y + FONT_SIZE * 0.95
            parts = []
            if first:
                parts.append(
                    f'<text x="0" y="{y:.1f}" font-size="{FONT_SIZE}" '
                    f'font-family="{FONT_STACK}" fill="{self.t["label"]}">'
                    f'{esc(label)}</text>'
                )
            color = self.t["link"] if is_reach else self.t["value"]
            parts.append(
                f'<text x="{LABEL_COL_W:.1f}" y="{y:.1f}" font-size="{FONT_SIZE}" '
                f'font-family="{FONT_STACK}" fill="{color}">{esc(line)}</text>'
            )
            self._line_wrapper("".join(parts))
            first = False

    def sparkline_row(self, values, reserve_lines=SPARK_RESERVE_LINES):
        y0 = self.y
        content = build_sparkline(values, self.t["spark_stroke"], self.t["spark_fill"],
                                   LABEL_COL_W, y0, SPARK_W, SPARK_H)
        if self.stagger:
            begin = 2.4
            self.svg_parts.append(
                f'<g opacity="0">{content}'
                f'<animate attributeName="opacity" from="0" to="1" dur="0.4s" '
                f'begin="{begin:.2f}s" fill="freeze"/></g>'
            )
        else:
            self.svg_parts.append(content)
        self.y += reserve_lines * LINE_H

    def render(self):
        return "".join(self.svg_parts), self.y


def build_readout(card, theme, stagger=True):
    rb = ReadoutBuilder(theme, stagger=stagger)
    rb.name(card["name"])
    rb.blank()
    for section in card["sections"]:
        if section["type"] == "section":
            rb.section_title(section["title"])
        for label, value in section["items"]:
            rb.field(label, value, is_reach=(label in REACH_LABELS))
        if section.get("sparkline"):
            rb.sparkline_row(card.get("_sparkline_values", []))
        rb.blank()
    content, height = rb.render()
    return content, height


def build_card_svg(card, theme_name, portrait_rows, portrait_bright, animated=True):
    t = THEMES[theme_name]
    portrait_svg, p_w, p_h = build_portrait_group(portrait_rows, portrait_bright,
                                                     t["portrait"], stagger=animated)
    readout_svg, r_h = build_readout(card, t, stagger=animated)

    content_h = max(p_h, r_h)
    content_w = p_w + COLUMN_GAP + (LABEL_COL_W + VALUE_COL_W)

    total_w = PADDING * 2 + content_w
    total_h = (TOPBAR_H + PROMPT_H + GAP_AFTER_PROMPT + content_h +
               GAP_BEFORE_BOTTOM + BOTTOMBAR_H + PADDING)

    content_y = TOPBAR_H + PROMPT_H + GAP_AFTER_PROMPT

    # window chrome: dots + title
    dots = "".join(
        f'<circle cx="{20 + i*16}" cy="{TOPBAR_H/2:.1f}" r="5" fill="{c}"/>'
        for i, c in enumerate(t["dots"])
    )
    title = (f'<text x="{total_w/2:.1f}" y="{TOPBAR_H/2+4:.1f}" font-size="11.5" '
              f'font-family="{FONT_STACK}" fill="{t["text_dim"]}" text-anchor="middle">'
              f'{esc(card["window_title"])}</text>')

    # prompt line
    prompt_y = TOPBAR_H + PROMPT_H * 0.68
    prompt_text = f'\u276f {card["prompt"]}'
    if animated:
        prompt_svg = (
            f'<g opacity="0"><text x="{PADDING}" y="{prompt_y:.1f}" font-size="{FONT_SIZE}" '
            f'font-family="{FONT_STACK}" fill="{t["prompt"]}">{esc(prompt_text)}</text>'
            f'<animate attributeName="opacity" from="0" to="1" dur="0.3s" begin="0s" fill="freeze"/></g>'
        )
    else:
        prompt_svg = (f'<text x="{PADDING}" y="{prompt_y:.1f}" font-size="{FONT_SIZE}" '
                       f'font-family="{FONT_STACK}" fill="{t["prompt"]}">{esc(prompt_text)}</text>')

    # bottom bar
    bottom_y = total_h - PADDING * 0.5
    rule_y = total_h - BOTTOMBAR_H - PADDING * 0.3
    footer_text = f'\u276f {card["footer_prompt"]}'
    cursor_x = PADDING + (len(footer_text) + 1) * CHAR_W
    if animated:
        footer_svg = (
            f'<g opacity="0"><text x="{PADDING}" y="{bottom_y:.1f}" font-size="{FONT_SIZE}" '
            f'font-family="{FONT_STACK}" fill="{t["prompt"]}">{esc(footer_text)}</text>'
            f'<animate attributeName="opacity" from="0" to="1" dur="0.3s" begin="3.4s" fill="freeze"/></g>'
            f'<rect x="{cursor_x:.1f}" y="{bottom_y-10:.1f}" width="7" height="12" fill="{t["cursor"]}">'
            f'<animate attributeName="opacity" values="1;1;0;0;1" dur="1.1s" begin="3.7s" repeatCount="indefinite"/>'
            f'</rect>'
        )
    else:
        footer_svg = (f'<text x="{PADDING}" y="{bottom_y:.1f}" font-size="{FONT_SIZE}" '
                       f'font-family="{FONT_STACK}" fill="{t["prompt"]}">{esc(footer_text)}</text>')

    updated_svg = (f'<text x="{total_w-PADDING:.1f}" y="{bottom_y:.1f}" font-size="10.5" '
                    f'font-family="{FONT_STACK}" fill="{t["text_dim"]}" text-anchor="end">'
                    f'last updated {esc(card.get("_last_updated",""))}</text>')

    portrait_x = PADDING
    readout_x = PADDING + p_w + COLUMN_GAP

    svg = f'''<svg width="{total_w:.0f}" height="{total_h:.0f}" viewBox="0 0 {total_w:.0f} {total_h:.0f}"
xmlns="http://www.w3.org/2000/svg">
<defs>
<clipPath id="winclip-{theme_name}"><rect x="0" y="0" width="{total_w:.0f}" height="{total_h:.0f}" rx="12"/></clipPath>
</defs>
<g clip-path="url(#winclip-{theme_name})">
<rect x="0" y="0" width="{total_w:.0f}" height="{total_h:.0f}" fill="{t["window_bg"]}"/>
<rect x="0" y="0" width="{total_w:.0f}" height="{TOPBAR_H:.0f}" fill="{t["chrome_bar"]}"/>
{dots}
{title}
{prompt_svg}
<g transform="translate({portrait_x:.1f},{content_y:.1f})">{portrait_svg}</g>
<g transform="translate({readout_x:.1f},{content_y:.1f})">{readout_svg}</g>
<line x1="{PADDING}" y1="{rule_y:.1f}" x2="{total_w-PADDING:.1f}" y2="{rule_y:.1f}" stroke="{t["rule"]}" stroke-width="1"/>
{footer_svg}
{updated_svg}
</g>
<rect x="0.5" y="0.5" width="{total_w-1:.0f}" height="{total_h-1:.0f}" rx="12" fill="none" stroke="{t["border"]}" stroke-width="1"/>
</svg>'''
    return svg


def main():
    rows, bright = load_portrait()
    with open("card_data.json") as f:
        card_raw = json.load(f)
    with open("stats.json") as f:
        stats = json.load(f)

    mapping = {
        "contributions": stats["contributions"],
        "streak": stats["streak"],
        "longest": stats["longest"],
    }
    card = substitute(copy.deepcopy(card_raw), mapping)
    card["_sparkline_values"] = stats["sparkline"]
    card["_last_updated"] = stats["last_updated"]

    for theme_name in ("dark", "light"):
        svg_anim = build_card_svg(card, theme_name, rows, bright, animated=True)
        with open(f"card-{theme_name}.svg", "w", encoding="utf-8") as f:
            f.write(svg_anim)
        svg_static = build_card_svg(card, theme_name, rows, bright, animated=False)
        with open(f"card-{theme_name}-static.svg", "w", encoding="utf-8") as f:
            f.write(svg_static)
        print(f"wrote card-{theme_name}.svg and static variant")


if __name__ == "__main__":
    main()
