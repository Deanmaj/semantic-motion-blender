"""
Physics & Harmonic Generator for Blender Animation Add-on.
Generates realistic collision bounces and damped harmonic elastic oscillations
between keyframe intervals.
"""

from typing import List, Tuple
import math


def generate_bounce_keyframes(
    t0: float, v0: float, t1: float, v1: float,
    bounces: int = 3, decay: float = 0.52
) -> List[Tuple[float, float, str]]:
    """
    Calculates intermediate keyframe points for a realistic gravity bounce.
    Returns a list of (frame, value, keyframe_type) tuples.
    keyframe_type: 'CONTACT' (vector handle) or 'PEAK' (aligned/flat handle)
    """
    total_time = t1 - t0
    total_val = v1 - v0

    if total_time <= 2:
        return [(t0, v0, 'START'), (t1, v1, 'END')]

    # Calculate time partitions using geometric series for bounce durations
    # Each bounce takes decay_t fraction of previous bounce time
    decay_t = math.sqrt(decay)
    weights = [decay_t ** i for i in range(bounces + 1)]
    sum_weights = sum(weights)

    durations = [(w / sum_weights) * total_time for w in weights]

    points = [(t0, v0, 'START')]
    current_time = t0

    # Initial drop / movement to destination
    current_time += durations[0]
    points.append((current_time, v1, 'CONTACT'))

    # Rebound bounces
    current_height = total_val
    for i in range(1, bounces + 1):
        dur = durations[i]
        current_height *= decay
        if abs(current_height) < 0.00001 or dur < 0.1:
            break

        # Halfway is peak of bounce
        peak_time = current_time + (dur * 0.5)
        peak_val = v1 - current_height
        points.append((peak_time, peak_val, 'PEAK'))

        # End of bounce returns to ground
        current_time += dur
        points.append((current_time, v1, 'CONTACT'))

    # Ensure final keyframe is exactly at (t1, v1)
    if points[-1][0] < t1:
        points.append((t1, v1, 'END'))

    return points


def generate_elastic_keyframes(
    t0: float, v0: float, t1: float, v1: float,
    oscillations: int = 4, decay: float = 0.45
) -> List[Tuple[float, float, str]]:
    """
    Calculates damped harmonic spring oscillation keyframes.
    Returns a list of (frame, value, keyframe_type) tuples.
    """
    total_time = t1 - t0
    total_val = v1 - v0

    if total_time <= 2:
        return [(t0, v0, 'START'), (t1, v1, 'END')]

    # Damped sine wave: y(t) = v1 - total_val * exp(-gamma * t) * cos(omega * t)
    points = [(t0, v0, 'START')]
    num_peaks = oscillations * 2  # alternating overshoots and undershoots
    dt_step = total_time / (num_peaks + 1)

    for i in range(1, num_peaks + 1):
        cur_t = t0 + i * dt_step
        progress = (cur_t - t0) / total_time
        # Damped amplitude
        amp = total_val * math.exp(-progress / max(0.01, decay)) * math.cos(i * math.pi)
        cur_v = v1 - amp
        points.append((cur_t, cur_v, 'OSCILLATION'))

    points.append((t1, v1, 'END'))
    return points


def apply_physics_to_fcurve(fcurve, k0_index: int, k1_index: int, profile):
    """
    Replaces the keyframe interval [k0, k1] in fcurve with generated physics keyframes.
    """
    kps = getattr(fcurve, "keyframe_points", getattr(fcurve, "points", None))
    if kps is None or len(kps) <= max(k0_index, k1_index):
        return

    k0 = kps[k0_index]
    k1 = kps[k1_index]

    t0, v0 = k0.co[0], k0.co[1]
    t1, v1 = k1.co[0], k1.co[1]

    if profile.physics_type == "BOUNCE":
        points = generate_bounce_keyframes(
            t0, v0, t1, v1,
            bounces=profile.physics_bounces,
            decay=profile.physics_decay
        )
    else:  # ELASTIC
        points = generate_elastic_keyframes(
            t0, v0, t1, v1,
            oscillations=profile.physics_bounces,
            decay=profile.physics_decay
        )

    # Insert intermediate keyframes into F-Curve
    for pt in points[1:-1]:
        frame, val, pt_type = pt
        kp = kps.insert(frame=frame, value=val)
        kp.interpolation = 'BEZIER'
        if pt_type == 'CONTACT':
            kp.handle_left_type = 'VECTOR'
            kp.handle_right_type = 'VECTOR'
        elif pt_type in ('PEAK', 'OSCILLATION'):
            kp.handle_left_type = 'AUTO_CLAMPED'
            kp.handle_right_type = 'AUTO_CLAMPED'

    if hasattr(fcurve, "update"):
        fcurve.update()
