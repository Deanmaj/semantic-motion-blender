"""
Bezier Math Engine for Blender Animation Add-on.
Handles normalization, conversion from MotionProfile to Bezier handles,
and applying handle coordinates to Blender F-Curves.
"""

from typing import Tuple, List, Optional
import math


class NormalizedBezier:
    """
    Represents a normalized 2D cubic Bezier curve segment from (0,0) to (1,1).
    P0 = (0, 0)
    P1 = (x1, y1)  -> outgoing handle from start keyframe
    P2 = (x2, y2)  -> incoming handle to end keyframe
    P3 = (1, 1)
    """

    def __init__(self, x1: float = 0.333, y1: float = 0.0, x2: float = 0.667, y2: float = 1.0):
        self.x1 = max(0.0, min(1.0, float(x1)))
        self.y1 = float(y1)
        self.x2 = max(0.0, min(1.0, float(x2)))
        self.y2 = float(y2)

    def to_tuple(self) -> Tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)

    def evaluate(self, t: float) -> Tuple[float, float]:
        """Evaluates (x(t), y(t)) for t in [0, 1]."""
        t = max(0.0, min(1.0, t))
        omt = 1.0 - t
        omt2 = omt * omt
        omt3 = omt2 * omt
        t2 = t * t
        t3 = t2 * t

        # B(t) = (1-t)^3 * P0 + 3(1-t)^2 * t * P1 + 3(1-t) * t^2 * P2 + t^3 * P3
        # P0=(0,0), P3=(1,1)
        x = 3.0 * omt2 * t * self.x1 + 3.0 * omt * t2 * self.x2 + t3
        y = 3.0 * omt2 * t * self.y1 + 3.0 * omt * t2 * self.y2 + t3
        return (x, y)

    def sample_curve(self, num_samples: int = 32) -> List[Tuple[float, float]]:
        """Generates a list of (x, y) coordinates along the curve for visual preview."""
        return [self.evaluate(i / float(num_samples - 1)) for i in range(num_samples)]

    def __repr__(self) -> str:
        return f"<NormalizedBezier P1=({self.x1:.3f}, {self.y1:.3f}), P2=({self.x2:.3f}, {self.y2:.3f})>"


def motion_tools_slider_to_bezier(
    start_speed: float,
    end_speed: float,
    anticipation: float = 0.0,
    overshoot: float = 0.0
) -> NormalizedBezier:
    """
    Converts direct Speed sliders (Left 0% = Slow, Right 100% = Fast)
    into an absolute normalized Bezier curve.

    start_speed: 0% (Slow start / lingering) -> 100% (Fast start / explosive launch)
    end_speed:   0% (Slow end / feather landing) -> 100% (Fast end / high-speed slam)
    anticipation: 0.0 to 1.0 (pullback dip)
    overshoot: 0.0 to 1.5 (rebound past target)
    """
    s = max(0.0, min(100.0, float(start_speed))) / 100.0
    e = max(0.0, min(100.0, float(end_speed))) / 100.0

    # Start Handle P1 (x1, y1)
    # s = 0.0 (Slow): x1 = 0.92, y1 = 0.0 (flat horizontal tangent, long linger)
    # s = 0.5 (Mid):  x1 = 0.40, y1 = 0.40 (steady/linear slope)
    # s = 1.0 (Fast): x1 = 0.05, y1 = 0.95 (steep vertical tangent, instant velocity)
    x1 = 0.92 * (1.0 - s) + 0.05 * s
    if anticipation > 0.01:
        y1 = -(anticipation * 0.45)
    else:
        y1 = 0.0 * (1.0 - s) + 0.95 * s

    # End Handle P2 (x2, y2)
    # e = 0.0 (Slow): x2 = 0.08, y2 = 1.0 (flat horizontal tangent, long feather landing)
    # e = 0.5 (Mid):  x2 = 0.60, y2 = 0.60 (steady/linear arrival)
    # e = 1.0 (Fast): x2 = 0.95, y2 = 0.05 (steep vertical entry tangent, high impact speed)
    x2 = 0.08 * (1.0 - e) + 0.95 * e
    if overshoot > 0.01:
        y2 = 1.0 + (overshoot * 0.55)
    else:
        y2 = 1.0 * (1.0 - e) + 0.05 * e

    return NormalizedBezier(x1=x1, y1=y1, x2=x2, y2=y2)


def profile_to_normalized_bezier(profile) -> NormalizedBezier:
    """
    Converts a MotionProfile instance into a NormalizedBezier (x1, y1, x2, y2).
    """
    # 1. Compute Start Handle P1 (x1, y1)
    if profile.start_type == "SLOW":
        # Slow start: flat horizontal handle, influence scales from 0.33 to 0.95
        x1 = 0.33 + profile.start_intensity * 0.62
        y1 = 0.0
    elif profile.start_type == "FAST":
        # Fast start: steep vertical handle, short x-duration, high initial y-velocity
        x1 = 0.04 + (1.0 - profile.start_intensity) * 0.22
        y1 = 0.40 + profile.start_intensity * 0.55
    elif profile.start_type == "ANTICIPATION":
        # Anticipation: dips below 0 on the y-axis before rising
        x1 = 0.22 + profile.start_intensity * 0.20
        y1 = -(0.10 + profile.start_intensity * 0.30)
    elif profile.start_type == "LINEAR":
        x1 = 0.333
        y1 = 0.333
    else:  # DEFAULT / CUSTOM
        x1 = 0.333
        y1 = 0.0

    # 2. Compute End Handle P2 (x2, y2)
    if profile.end_type == "SLOW":
        # Slow end / Soft landing: flat horizontal handle, incoming influence from right
        x2 = 1.0 - (0.33 + profile.end_intensity * 0.62)
        y2 = 1.0
    elif profile.end_type == "FAST":
        # Fast end / Sudden stop: steep incoming slope, keyframe reached with high velocity
        x2 = 1.0 - (0.04 + (1.0 - profile.end_intensity) * 0.22)
        y2 = 1.0 - (0.40 + profile.end_intensity * 0.55)
    elif profile.end_type == "OVERSHOOT":
        # Overshoot: handle goes above 1.0 on y-axis, then eases back to 1.0
        x2 = 0.68 - profile.end_intensity * 0.18
        y2 = 1.0 + (0.12 + profile.overshoot_amount * 0.60)
    elif profile.end_type == "LINEAR":
        x2 = 0.667
        y2 = 0.667
    else:  # DEFAULT / CUSTOM
        x2 = 0.667
        y2 = 1.0

    return NormalizedBezier(x1=x1, y1=y1, x2=x2, y2=y2)


def apply_bezier_to_keyframe_pair(k0, k1, bezier: NormalizedBezier, fcurve=None):
    """
    Applies the normalized Bezier parameters to a pair of Blender keyframes (k0 and k1).
    k0: start keyframe
    k1: end keyframe
    bezier: NormalizedBezier instance
    """
    dt = k1.co[0] - k0.co[0]
    dv = k1.co[1] - k0.co[1]

    # Don't modify if keyframes are on the exact same frame
    if abs(dt) < 1e-5:
        return

    # Handle right of k0
    h0_x = k0.co[0] + bezier.x1 * dt
    h0_y = k0.co[1] + bezier.y1 * dv

    # Handle left of k1
    h1_x = k0.co[0] + bezier.x2 * dt
    h1_y = k0.co[1] + bezier.y2 * dv

    # Update Blender Keyframe properties
    k0.handle_right_type = 'FREE'
    k1.handle_left_type = 'FREE'

    k0.handle_right[0] = h0_x
    k0.handle_right[1] = h0_y

    k1.handle_left[0] = h1_x
    k1.handle_left[1] = h1_y

    k0.interpolation = 'BEZIER'

    if fcurve:
        fcurve.update()
