"""
High-Resolution Graphical Curve & Speed Preview for Blender UI.
Uses a 2x4 Subpixel Braille Canvas (up to 56x32 virtual resolution) to render smooth
Value and Speed/Time graphs directly inside the Blender sidebar.
"""

from typing import List, Tuple
import math
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


def _draw_samples_on_canvas(samples: List[Tuple[float, float]], min_y: float, max_y: float, char_width: int, char_height: int) -> List[List[bool]]:
    """Plots a series of (x, y) coordinates onto a subpixel boolean buffer."""
    pixel_w = char_width * 2
    pixel_h = char_height * 4
    pixels = [[False for _ in range(pixel_h)] for _ in range(pixel_w)]
    y_range = max(0.001, max_y - min_y)

    for i in range(len(samples) - 1):
        x0, y0 = samples[i]
        x1, y1 = samples[i + 1]

        px0 = max(0, min(pixel_w - 1, int(x0 * (pixel_w - 1))))
        px1 = max(0, min(pixel_w - 1, int(x1 * (pixel_w - 1))))

        py0 = max(0, min(pixel_h - 1, int(((y0 - min_y) / y_range) * (pixel_h - 1))))
        py1 = max(0, min(pixel_h - 1, int(((y1 - min_y) / y_range) * (pixel_h - 1))))

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

    return pixels


def _pack_braille_lines(pixels: List[List[bool]], char_width: int, char_height: int, y_axis_labels: List[Tuple[int, str]], bottom_label: str) -> List[str]:
    """Packs subpixel buffer into braille character strings with axis ticks."""
    pixel_w = char_width * 2
    pixel_h = char_height * 4
    lines = []

    label_dict = dict(y_axis_labels)

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

        prefix = label_dict.get(cy, "          │ ")
        lines.append(prefix + "".join(line_chars))

    axis_bar = "          └" + "─" * (char_width // 2) + "┬" + "─" * (char_width - (char_width // 2) - 1) + "┘"
    lines.append(axis_bar)
    lines.append(bottom_label)
    return lines


def render_high_res_curve(bezier: NormalizedBezier, char_width: int = 22, char_height: int = 8) -> List[str]:
    """
    Renders the Position / Value Curve Y(t) over Time with vertical depth and subpixel precision.
    """
    pixel_w = char_width * 2
    num_samples = pixel_w * 4
    samples = bezier.sample_curve(num_samples=num_samples)

    all_y = [s[1] for s in samples]
    min_y = min(-0.15, min(all_y))
    max_y = max(1.15, max(all_y))

    pixels = _draw_samples_on_canvas(samples, min_y, max_y, char_width, char_height)

    # Multi-level Y-axis labels
    mid_cy = char_height // 2
    y_labels = [
        (0, " 100% (End) ┤ "),
        (mid_cy, "  50% (Mid) ┤ "),
        (char_height - 1, "0% (Origin) ┤ "),
    ]
    if char_height >= 8:
        y_labels.insert(1, (mid_cy // 2, "        75% ┤ "))
        y_labels.insert(3, (mid_cy + (char_height - 1 - mid_cy) // 2, "        25% ┤ "))

    bottom = "            0% (Start)         100% (End)"
    return _pack_braille_lines(pixels, char_width, char_height, y_labels, bottom)


def render_speed_graph(bezier: NormalizedBezier, char_width: int = 22, char_height: int = 8) -> List[str]:
    """
    Renders the Velocity / Speed Graph (dY/dX over time) with vertical depth and subpixel precision.
    Shows the acceleration, peak velocity burst, and deceleration deceleration curve.
    """
    pixel_w = char_width * 2
    num_samples = max(64, pixel_w * 4)
    raw_samples = bezier.sample_curve(num_samples=num_samples)

    # Compute instantaneous velocities dY/dX
    speed_samples = []
    max_speed = 0.001

    for i in range(len(raw_samples) - 1):
        x0, y0 = raw_samples[i]
        x1, y1 = raw_samples[i + 1]
        dx = max(1e-5, x1 - x0)
        dy = abs(y1 - y0)
        speed = dy / dx
        mid_x = (x0 + x1) * 0.5
        speed_samples.append((mid_x, speed))
        if speed > max_speed:
            max_speed = speed

    # Normalize speed into [0, 1] range
    norm_samples = [(x, min(1.0, spd / max_speed)) for x, spd in speed_samples]
    if not norm_samples:
        norm_samples = [(0.0, 0.0), (1.0, 0.0)]

    min_y = 0.0
    max_y = 1.05

    pixels = _draw_samples_on_canvas(norm_samples, min_y, max_y, char_width, char_height)

    mid_cy = char_height // 2
    y_labels = [
        (0, "  Max Speed ┤ "),
        (mid_cy, "  50% Speed ┤ "),
        (char_height - 1, "   0 (Rest) ┤ "),
    ]
    if char_height >= 8:
        y_labels.insert(1, (mid_cy // 2, "  75% Speed ┤ "))
        y_labels.insert(3, (mid_cy + (char_height - 1 - mid_cy) // 2, "  25% Speed ┤ "))

    bottom = "            0% (Start)         100% (End)"
    return _pack_braille_lines(pixels, char_width, char_height, y_labels, bottom)


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
