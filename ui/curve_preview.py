"""
High-Resolution Graphical Curve Preview & Motion Analyzer for Blender UI.
Uses a 2x4 Subpixel Braille Canvas (60x24 virtual resolution) to render smooth
curves directly in Blender sidebar labels, accompanied by intuitive English motion breakdowns.
"""

from typing import List, Tuple
try:
    from ..engine.bezier_math import NormalizedBezier
except (ImportError, ValueError):
    from engine.bezier_math import NormalizedBezier


def _braille_char(subgrid: List[List[bool]]) -> str:
    """
    Converts a 2x4 subpixel boolean matrix into a Unicode Braille character (U+2800 - U+28FF).
    Dots mapping:
    (0,0)=1 (0x1), (0,1)=2 (0x2), (0,2)=3 (0x4), (0,3)=7 (0x40)
    (1,0)=4 (0x8), (1,1)=5 (0x10), (1,2)=6 (0x20), (1,3)=8 (0x80)
    """
    code = 0x2800
    dot_map = [
        [(0, 0, 0x1), (0, 1, 0x2), (0, 2, 0x4), (0, 3, 0x40)],
        [(1, 0, 0x8), (1, 1, 0x10), (1, 2, 0x20), (1, 3, 0x80)],
    ]
    for x in range(2):
        for y in range(4):
            if subgrid[x][y]:
                code |= dot_map[x][y][2]
    return chr(code)


def render_high_res_curve(bezier: NormalizedBezier, char_width: int = 24, char_height: int = 6) -> List[str]:
    """
    Renders a smooth high-resolution curve using subpixel Braille dots.
    Virtual resolution = (char_width * 2) x (char_height * 4) = 48 x 24 subpixels.
    """
    pixel_w = char_width * 2
    pixel_h = char_height * 4

    # Create pixel buffer
    pixels = [[False for _ in range(pixel_h)] for _ in range(pixel_w)]

    # Sample Bezier curve finely
    num_samples = pixel_w * 3
    samples = bezier.sample_curve(num_samples=num_samples)

    # Determine Y-bounds to support overshoot (y > 1) and anticipation (y < 0)
    all_y = [s[1] for s in samples]
    min_y = min(-0.1, min(all_y))
    max_y = max(1.1, max(all_y))
    y_range = max(0.01, max_y - min_y)

    for i in range(len(samples) - 1):
        x0, y0 = samples[i]
        x1, y1 = samples[i + 1]

        # Map to pixel coords
        px0 = int(x0 * (pixel_w - 1))
        px1 = int(x1 * (pixel_w - 1))

        # Y mapping (0 at bottom, pixel_h-1 at top)
        py0 = int(((y0 - min_y) / y_range) * (pixel_h - 1))
        py1 = int(((y1 - min_y) / y_range) * (pixel_h - 1))

        px0 = max(0, min(pixel_w - 1, px0))
        px1 = max(0, min(pixel_w - 1, px1))
        py0 = max(0, min(pixel_h - 1, py0))
        py1 = max(0, min(pixel_h - 1, py1))

        # Line drawing between samples for smooth line
        dx = px1 - px0
        dy = py1 - py0
        steps = max(abs(dx), abs(dy), 1)
        for s in range(steps + 1):
            cur_x = int(px0 + (dx * s / steps))
            cur_y = int(py0 + (dy * s / steps))
            cur_x = max(0, min(pixel_w - 1, cur_x))
            cur_y = max(0, min(pixel_h - 1, cur_y))
            # Invert Y for braille indexing (0 is top)
            inv_y = (pixel_h - 1) - cur_y
            pixels[cur_x][inv_y] = True

    # Pack pixels into braille characters
    lines = []
    for cy in range(char_height):
        line_chars = []
        for cx in range(char_width):
            subgrid = [[False for _ in range(4)] for _ in range(2)]
            for bx in range(2):
                for by in range(4):
                    gx = cx * 2 + bx
                    gy = cy * 4 + by
                    if gx < pixel_w and gy < pixel_h:
                        subgrid[bx][by] = pixels[gx][gy]
            line_chars.append(_braille_char(subgrid))

        # Add Y-axis labels
        if cy == 0:
            prefix = "Value 100% ┤ "
        elif cy == char_height // 2:
            prefix = "       50% ┤ "
        elif cy == char_height - 1:
            prefix = "        0% ┤ "
        else:
            prefix = "           │ "

        lines.append(prefix + "".join(line_chars))

    # Bottom Time Axis
    axis_bar = "           └" + "─" * (char_width // 2) + "┬" + "─" * (char_width - (char_width // 2) - 1) + "┘"
    time_label = "             0% (Start)        100% (End)"
    lines.append(axis_bar)
    lines.append(time_label)

    return lines


def explain_motion_behavior(start_tension: float, end_tension: float, anticipation: float = 0.0, overshoot: float = 0.0) -> List[Tuple[str, str, str]]:
    """
    Returns intuitive, easy-to-understand motion behavior explanations for the UI.
    Returns list of (Stage Name, Icon, Description).
    """
    s = int(start_tension)
    e = int(end_tension)

    # 1. Start Phase explanation
    if anticipation > 1.0:
        start_desc = f"Anticipates by pulling back {int(anticipation)}% before blasting off."
        start_icon = 'IPO_BACK'
    elif s == 0:
        start_desc = "Instant launch: full starting speed with zero lag."
        start_icon = 'FORWARD'
    elif s <= 35:
        start_desc = f"Gentle ease-in ({s}%): subtle, natural departure."
        start_icon = 'IPO_EASE_IN'
    elif s <= 75:
        start_desc = f"Snappy departure ({s}%): holds briefly, then surges with power."
        start_icon = 'SPHERE'
    else:
        start_desc = f"Extreme magnetic lag ({s}%): lingers long before exploding forward."
        start_icon = 'LIGHT_SUN'

    # 2. End Phase explanation
    if overshoot > 1.0:
        end_desc = f"Shoots +{int(overshoot)}% past target, then snaps into place."
        end_icon = 'IPO_BACK'
    elif e == 0:
        end_desc = "Sudden wall slam: zero braking, hits target at top velocity."
        end_icon = 'CANCEL'
    elif e <= 35:
        end_desc = f"Gentle ease-out ({e}%): standard smooth landing."
        end_icon = 'IPO_EASE_OUT'
    elif e <= 75:
        end_desc = f"Snappy deceleration ({e}%): high-speed glide into a crisp stop."
        end_icon = 'CHECKMARK'
    else:
        end_desc = f"Feather landing ({e}%): extended magnetic cushion into the final frame."
        end_icon = 'RESTRICT_VIEW_OFF'

    return [
        ("Departure", start_icon, start_desc),
        ("Arrival", end_icon, end_desc),
    ]
