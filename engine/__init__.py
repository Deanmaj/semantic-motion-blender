"""
Semantic Motion Engine Package.
"""

from .semantic_parser import parse_motion_prompt, MotionProfile, PRESET_PHRASES
from .bezier_math import NormalizedBezier, profile_to_normalized_bezier, apply_bezier_to_keyframe_pair
from .physics_generator import apply_physics_to_fcurve, generate_bounce_keyframes, generate_elastic_keyframes
from .curve_analyzer import analyze_keyframe_pair

__all__ = [
    "parse_motion_prompt",
    "MotionProfile",
    "PRESET_PHRASES",
    "NormalizedBezier",
    "profile_to_normalized_bezier",
    "apply_bezier_to_keyframe_pair",
    "apply_physics_to_fcurve",
    "generate_bounce_keyframes",
    "generate_elastic_keyframes",
    "analyze_keyframe_pair",
]
