"""
Curve Analyzer Engine for Blender Animation Add-on.
Inspects keyframe handles and translates them into human-readable English descriptors
and matching MotionProfile settings.
"""

from typing import Tuple, Dict, Any, Optional


def analyze_keyframe_pair(k0, k1) -> Dict[str, Any]:
    """
    Analyzes the Bezier curve segment between k0 and k1 and returns
    detected start/end types, intensities, and a natural language description.
    """
    dt = k1.co[0] - k0.co[0]
    dv = k1.co[1] - k0.co[1]

    if abs(dt) < 1e-5:
        return {
            "start_type": "LINEAR",
            "start_intensity": 0.5,
            "end_type": "LINEAR",
            "end_intensity": 0.5,
            "overshoot_amount": 0.0,
            "description": "Zero duration keyframes",
            "prompt_suggestion": "linear"
        }

    # Normalized handle coordinates
    x1 = (k0.handle_right[0] - k0.co[0]) / dt
    x2 = (k1.handle_left[0] - k0.co[0]) / dt

    if abs(dv) > 1e-5:
        y1 = (k0.handle_right[1] - k0.co[1]) / dv
        y2 = (k1.handle_left[1] - k0.co[1]) / dv
    else:
        y1 = 0.0
        y2 = 1.0

    # 1. Analyze Start
    if y1 < -0.05:
        start_type = "ANTICIPATION"
        start_intensity = min(1.0, abs(y1) * 2.5)
        start_desc = f"Anticipation Dip ({int(start_intensity * 100)}% pullback)"
        start_prompt = "anticipation" if start_intensity < 0.6 else "heavy anticipation"
    elif x1 > 0.45 and abs(y1) < 0.25:
        start_type = "SLOW"
        start_intensity = min(1.0, (x1 - 0.33) / 0.62) if x1 > 0.33 else 0.5
        start_desc = f"Slow Start ({int(x1 * 100)}% influence)"
        start_prompt = "slow start" if start_intensity < 0.8 else "extreme slow start"
    elif x1 < 0.30 and y1 > 0.25:
        start_type = "FAST"
        start_intensity = min(1.0, y1)
        start_desc = f"Fast Launch ({int(start_intensity * 100)}% velocity)"
        start_prompt = "fast start" if start_intensity < 0.8 else "explosive start"
    elif abs(x1 - 0.333) < 0.08 and abs(y1 - 0.333) < 0.08:
        start_type = "LINEAR"
        start_intensity = 0.0
        start_desc = "Linear Start"
        start_prompt = "linear start"
    else:
        start_type = "SLOW"
        start_intensity = 0.5
        start_desc = f"Standard Start ({int(x1 * 100)}% influence)"
        start_prompt = "smooth start"

    # 2. Analyze End
    overshoot_amount = 0.0
    end_influence = 1.0 - x2

    if y2 > 1.05:
        end_type = "OVERSHOOT"
        overshoot_amount = min(1.5, (y2 - 1.0) / 0.6)
        end_intensity = 0.75
        end_desc = f"Overshoot Rebound (+{int((y2 - 1.0) * 100)}% overshoot)"
        end_prompt = "overshoot" if overshoot_amount < 0.3 else "heavy overshoot"
    elif end_influence > 0.45 and abs(y2 - 1.0) < 0.25:
        end_type = "SLOW"
        end_intensity = min(1.0, (end_influence - 0.33) / 0.62) if end_influence > 0.33 else 0.5
        end_desc = f"Soft Landing ({int(end_influence * 100)}% ease-out)"
        end_prompt = "slow ending" if end_intensity < 0.8 else "feather landing"
    elif end_influence < 0.30 and (1.0 - y2) > 0.25:
        end_type = "FAST"
        end_intensity = min(1.0, 1.0 - y2)
        end_desc = f"Sudden Stop ({int(end_intensity * 100)}% impact)"
        end_prompt = "fast ending" if end_intensity < 0.8 else "sudden stop"
    elif abs(x2 - 0.667) < 0.08 and abs(y2 - 0.667) < 0.08:
        end_type = "LINEAR"
        end_intensity = 0.0
        end_desc = "Linear End"
        end_prompt = "linear end"
    else:
        end_type = "SLOW"
        end_intensity = 0.5
        end_desc = f"Standard Landing ({int(end_influence * 100)}% ease-out)"
        end_prompt = "smooth ending"

    start_speed, end_speed, ant_amt, ovr_amt = handles_to_speeds(x1, y1, x2, y2)

    full_desc = f"{start_desc} \u2192 {end_desc}"
    suggested_prompt = f"{start_prompt}, {end_prompt}"

    return {
        "start_type": start_type,
        "start_intensity": start_intensity,
        "end_type": end_type,
        "end_intensity": end_intensity,
        "overshoot_amount": overshoot_amount,
        "start_speed": start_speed,
        "end_speed": end_speed,
        "anticipation_amount": ant_amt,
        "overshoot_amount_pct": ovr_amt,
        "description": full_desc,
        "prompt_suggestion": suggested_prompt,
        "raw_handles": (x1, y1, x2, y2)
    }


def handles_to_speeds(x1: float, y1: float, x2: float, y2: float) -> Tuple[float, float, float, float]:
    """
    Reverse solver: converts normalized handles (x1, y1, x2, y2) into
    (start_speed, end_speed, anticipation_amount, overshoot_amount).
    """
    s_x = max(0.0, min(1.0, (0.92 - x1) / 0.87))
    if y1 < -0.01:
        anticipation = min(100.0, abs(y1) / 0.45 * 100.0)
        start_speed = max(0.0, min(100.0, s_x * 100.0))
    else:
        anticipation = 0.0
        s_y = max(0.0, min(1.0, y1 / 0.95))
        start_speed = max(0.0, min(100.0, (s_x * 0.6 + s_y * 0.4) * 100.0))

    e_x = max(0.0, min(1.0, (x2 - 0.08) / 0.87))
    if y2 > 1.01:
        overshoot = min(150.0, (y2 - 1.0) / 0.55 * 100.0)
        end_speed = max(0.0, min(100.0, e_x * 100.0))
    else:
        overshoot = 0.0
        e_y = max(0.0, min(1.0, (1.0 - y2) / 0.95))
        end_speed = max(0.0, min(100.0, (e_x * 0.6 + e_y * 0.4) * 100.0))

    return (round(start_speed, 1), round(end_speed, 1), round(anticipation, 1), round(overshoot, 1))
