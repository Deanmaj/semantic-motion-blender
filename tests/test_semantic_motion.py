"""
Automated Unit Tests for Semantic Motion Add-on Engine.
Tests the natural language parser, Bezier math, curve analyzer, and physics generators.
Can run standalone with Python unittest.
"""

import unittest
import math
import sys
import os

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.semantic_parser import parse_motion_prompt, MotionProfile, PRESET_PHRASES
from engine.bezier_math import (
    NormalizedBezier,
    profile_to_normalized_bezier,
)
from engine.physics_generator import generate_bounce_keyframes, generate_elastic_keyframes
from engine.curve_analyzer import analyze_keyframe_pair


class MockKeyframe:
    """Mock Blender keyframe object for testing math and analysis."""
    def __init__(self, frame: float, value: float, h_left=None, h_right=None):
        self.co = [float(frame), float(value)]
        self.handle_left = list(h_left) if h_left else [frame - 1.0, value]
        self.handle_right = list(h_right) if h_right else [frame + 1.0, value]
        self.handle_left_type = 'FREE'
        self.handle_right_type = 'FREE'
        self.interpolation = 'BEZIER'
        self.select_control_point = True


class TestSemanticParser(unittest.TestCase):
    """Test natural language parsing of arbitrary motion descriptions."""

    def test_slow_start_fast_ending(self):
        profile = parse_motion_prompt("slow start, fast ending")
        self.assertEqual(profile.start_type, "SLOW")
        self.assertEqual(profile.end_type, "FAST")
        self.assertGreater(profile.start_intensity, 0.7)
        self.assertGreater(profile.end_intensity, 0.7)

    def test_fast_start_slow_ending(self):
        profile = parse_motion_prompt("fast start, slow ending")
        self.assertEqual(profile.start_type, "FAST")
        self.assertEqual(profile.end_type, "SLOW")

    def test_anticipation_to_overshoot(self):
        profile = parse_motion_prompt("anticipation dip with heavy overshoot")
        self.assertEqual(profile.start_type, "ANTICIPATION")
        self.assertEqual(profile.end_type, "OVERSHOOT")
        self.assertGreater(profile.overshoot_amount, 0.3)

    def test_modifiers(self):
        p_subtle = parse_motion_prompt("subtle slow start")
        p_extreme = parse_motion_prompt("extreme slow start")
        self.assertLess(p_subtle.start_intensity, p_extreme.start_intensity)

    def test_physics_bounce(self):
        profile = parse_motion_prompt("drop and bounce with 4 rebounds")
        self.assertTrue(profile.is_physics)
        self.assertEqual(profile.physics_type, "BOUNCE")
        self.assertEqual(profile.physics_bounces, 4)

    def test_elastic_wobble(self):
        profile = parse_motion_prompt("elastic wobble with 5 oscillations")
        self.assertTrue(profile.is_physics)
        self.assertEqual(profile.physics_type, "ELASTIC")
        self.assertEqual(profile.physics_bounces, 5)


class TestBezierMath(unittest.TestCase):
    """Test Bezier normalization and handle calculations."""

    def test_slow_start_fast_end_bezier(self):
        profile = parse_motion_prompt("slow start, fast ending")
        bezier = profile_to_normalized_bezier(profile)
        # Slow start should have high x1 and y1 = 0
        self.assertGreater(bezier.x1, 0.6)
        self.assertAlmostEqual(bezier.y1, 0.0, places=2)
        # Fast end should have high x2 and lower y2 (high incoming slope)
        self.assertGreater(bezier.x2, 0.7)
        self.assertLess(bezier.y2, 0.6)

    def test_anticipation_dip_bezier(self):
        profile = parse_motion_prompt("anticipation, slow ending")
        bezier = profile_to_normalized_bezier(profile)
        # Anticipation must have negative y1
        self.assertLess(bezier.y1, 0.0)

    def test_overshoot_bezier(self):
        profile = parse_motion_prompt("slow start, heavy overshoot")
        bezier = profile_to_normalized_bezier(profile)
        # Overshoot must have y2 > 1.0
        self.assertGreater(bezier.y2, 1.0)

    def test_direct_speed_sliders(self):
        from engine.bezier_math import motion_tools_slider_to_bezier
        # 20% Start (Slow) -> flat tangent with long linger
        # 80% End (Fast) -> steep entry tangent with high velocity
        bezier = motion_tools_slider_to_bezier(start_speed=20.0, end_speed=80.0)
        self.assertGreater(bezier.x1, 0.6)
        self.assertLess(bezier.y1, 0.3)
        self.assertGreater(bezier.x2, 0.6)
        self.assertLess(bezier.y2, 0.4)

    def test_curve_sampling(self):
        bezier = NormalizedBezier(0.5, 0.0, 0.5, 1.0)
        samples = bezier.sample_curve(num_samples=10)
        self.assertEqual(len(samples), 10)
        # First sample should be (0,0), last should be (1,1)
        self.assertAlmostEqual(samples[0][0], 0.0)
        self.assertAlmostEqual(samples[0][1], 0.0)
        self.assertAlmostEqual(samples[-1][0], 1.0)
        self.assertAlmostEqual(samples[-1][1], 1.0)


class TestPhysicsGenerator(unittest.TestCase):
    """Test physics-based bounce and oscillation keyframes."""

    def test_bounce_generator(self):
        points = generate_bounce_keyframes(0.0, 0.0, 60.0, 10.0, bounces=3, decay=0.5)
        self.assertGreater(len(points), 4)
        # Start at 0 and end at 60
        self.assertEqual(points[0][0], 0.0)
        self.assertEqual(points[0][1], 0.0)
        self.assertEqual(points[-1][0], 60.0)
        self.assertEqual(points[-1][1], 10.0)

    def test_elastic_generator(self):
        points = generate_elastic_keyframes(0.0, 0.0, 40.0, 10.0, oscillations=3, decay=0.45)
        self.assertGreater(len(points), 4)
        self.assertEqual(points[0][0], 0.0)
        self.assertEqual(points[-1][0], 40.0)
        self.assertEqual(points[-1][1], 10.0)


class TestCurveAnalyzer(unittest.TestCase):
    """Test reverse analysis of keyframe handles into English descriptors."""

    def test_analyze_slow_start_fast_end(self):
        # Create keyframes: k0 at frame 1 val 0, k1 at frame 31 val 10
        # dt = 30, dv = 10
        # x1 = 0.8 -> h0_right_x = 1 + 0.8*30 = 25, h0_right_y = 0
        # x2 = 0.9 -> h1_left_x = 1 + 0.9*30 = 28, y2 = 0.2 -> h1_left_y = 2
        k0 = MockKeyframe(1.0, 0.0, h_right=[25.0, 0.0])
        k1 = MockKeyframe(31.0, 10.0, h_left=[28.0, 2.0])

        res = analyze_keyframe_pair(k0, k1)
        self.assertEqual(res["start_type"], "SLOW")
        self.assertEqual(res["end_type"], "FAST")
        self.assertIn("Slow Start", res["description"])
        self.assertIn("Sudden Stop", res["description"])

    def test_handles_to_speeds(self):
        from engine.curve_analyzer import handles_to_speeds
        # Slow start (x1=0.8, y1=0.0) -> low start_speed ~ 15%
        # Fast end (x2=0.85, y2=0.1) -> high end_speed ~ 85%
        s_speed, e_speed, ant, ovr = handles_to_speeds(0.8, 0.0, 0.85, 0.1)
        self.assertLess(s_speed, 30.0)
        self.assertGreater(e_speed, 70.0)


    def test_30_bounces(self):
        profile = parse_motion_prompt("drop and bounce with 30 rebounds")
        self.assertTrue(profile.is_physics)
        self.assertEqual(profile.physics_bounces, 30)
        points = generate_bounce_keyframes(0.0, 0.0, 100.0, 10.0, bounces=30, decay=0.7)
        self.assertGreater(len(points), 10)


class TestBraillePreview(unittest.TestCase):
    """Test high-resolution Braille curve preview generator."""

    def test_braille_curve_rendering(self):
        from ui.curve_preview import render_high_res_curve, explain_motion_behavior
        bezier = NormalizedBezier(0.75, 0.0, 0.25, 1.0)
        lines = render_high_res_curve(bezier, char_width=20, char_height=5)
        self.assertGreater(len(lines), 5)
        # Verify braille characters exist
        has_braille = any(any(0x2800 <= ord(c) <= 0x28FF for c in line) for line in lines)
        self.assertTrue(has_braille)

    def test_motion_explainer(self):
        from ui.curve_preview import explain_motion_behavior
        stages = explain_motion_behavior(75.0, 75.0, 0.0, 0.0)
        self.assertEqual(len(stages), 2)
        self.assertEqual(stages[0][0], "Departure")
        self.assertEqual(stages[1][0], "Arrival")


if __name__ == "__main__":
    unittest.main()
