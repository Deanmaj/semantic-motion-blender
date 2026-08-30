"""
Properties module for Semantic Motion Blender Add-on.
Defines PropertyGroups for storing UI states, prompt text, speed sliders, and clipboard data.
"""

import bpy
from bpy.props import (
    StringProperty,
    FloatProperty,
    IntProperty,
    EnumProperty,
    BoolProperty,
    FloatVectorProperty,
    PointerProperty
)
from .engine.semantic_parser import parse_motion_prompt


_IS_SYNCING = False


def apply_live_update(props, context):
    """Applies the curve live to selected keyframes whenever a slider is scrubbed."""
    global _IS_SYNCING
    if _IS_SYNCING or not props.live_update or not context:
        return
    try:
        from .operators.apply_semantic_curve import apply_motion_tools_curve_to_context
        apply_motion_tools_curve_to_context(context, props)
    except Exception:
        pass


def update_prompt(self, context):
    """Callback when user edits the text prompt to update live description badge."""
    try:
        profile = parse_motion_prompt(self.prompt_text)
        self.parsed_description = profile.description
        if not profile.is_physics:
            # Map prompt profile to speed sliders
            # Slow start -> low speed (e.g. 20%), Fast start -> high speed (e.g. 85%)
            if profile.start_type == 'SLOW':
                self.start_speed = max(5.0, (1.0 - profile.start_intensity) * 40.0)
            elif profile.start_type == 'FAST':
                self.start_speed = min(95.0, 50.0 + profile.start_intensity * 45.0)
            else:
                self.start_speed = 50.0

            if profile.end_type == 'SLOW':
                self.end_speed = max(5.0, (1.0 - profile.end_intensity) * 40.0)
            elif profile.end_type == 'FAST':
                self.end_speed = min(95.0, 50.0 + profile.end_intensity * 45.0)
            else:
                self.end_speed = 50.0

            self.overshoot_amount = profile.overshoot_amount * 100.0
            self.anticipation_amount = (profile.start_intensity * 50.0) if profile.start_type == 'ANTICIPATION' else 0.0
        apply_live_update(self, context)
    except Exception as e:
        self.parsed_description = f"Error: {e}"


def update_slider(self, context):
    """Callback when user drags Start/End speed sliders."""
    s = int(self.start_speed)
    e = int(self.end_speed)

    s_txt = f"Slow Start ({s}%)" if s <= 35 else (f"Steady Start ({s}%)" if s <= 65 else f"Fast Start ({s}%)")
    e_txt = f"Slow End ({e}%)" if e <= 35 else (f"Steady End ({e}%)" if e <= 65 else f"Fast End ({e}%)")

    if s <= 35 and e >= 65:
        motion_type = "Accelerating / Rocket"
    elif s >= 65 and e <= 35:
        motion_type = "Decelerating / Braking"
    elif s <= 35 and e <= 35:
        motion_type = "Smooth S-Curve (Gentle)"
    elif s >= 65 and e >= 65:
        motion_type = "Fast Surge / Punch"
    else:
        motion_type = "Steady Progression"

    extra = []
    if self.anticipation_amount > 1.0:
        extra.append(f"Anticipation ({int(self.anticipation_amount)}%)")
    if self.overshoot_amount > 1.0:
        extra.append(f"Overshoot (+{int(self.overshoot_amount)}%)")

    extra_str = f" + [{', '.join(extra)}]" if extra else ""
    self.parsed_description = f"{s_txt} \u2192 {e_txt} \u2014 {motion_type}{extra_str}"
    apply_live_update(self, context)


class SemanticMotionProperties(bpy.types.PropertyGroup):
    """Holds all active properties for the Semantic Motion addon."""

    input_mode: EnumProperty(
        name="Control Mode",
        description="Choose between Speed Sliders or Text Prompt",
        items=[
            ('PHASE_BUILDER', "Speed Sliders", "Direct Start/End speed sliders (Left=Slow, Right=Fast)", 'PROPERTIES', 0),
            ('PROMPT', "Text Prompt", "Type motion descriptions in plain English", 'TEXT', 1),
        ],
        default='PHASE_BUILDER'
    )

    live_update: BoolProperty(
        name="Live Update",
        description="Instantly update keyframes in the Graph Editor / Viewport as you scrub sliders",
        default=True
    )

    graph_type: EnumProperty(
        name="Graph View",
        description="Choose graph visualization type",
        items=[
            ('VALUE', "Value Graph", "Shows the positional value curve over time", 'IPO_BEZIER', 0),
            ('SPEED', "Speed Graph", "Shows velocity / speed progression over time", 'IPO_EASE_IN_OUT', 1),
        ],
        default='VALUE'
    )

    prompt_text: StringProperty(
        name="Motion Prompt",
        description="Describe how you want the animation curve to behave (e.g. 'slow start, fast ending', 'explosive start with overshoot')",
        default="slow start, fast ending",
        update=update_prompt
    )

    parsed_description: StringProperty(
        name="Parsed Understanding",
        description="Live feedback of how the engine interprets your motion description",
        default="Slow Start (20%) \u2192 Fast End (80%) \u2014 Accelerating / Rocket"
    )

    # Direct Speed Sliders (Left 0% = Slow, Right 100% = Fast)
    start_speed: FloatProperty(
        name="Start Speed",
        description="Left (0%) = Slow departure (lingering ease-in), Right (100%) = Fast departure (explosive launch)",
        min=0.0,
        max=100.0,
        default=20.0,
        subtype='PERCENTAGE',
        update=update_slider
    )

    end_speed: FloatProperty(
        name="End Speed",
        description="Left (0%) = Slow arrival (feather landing), Right (100%) = Fast arrival (high-speed slam)",
        min=0.0,
        max=100.0,
        default=80.0,
        subtype='PERCENTAGE',
        update=update_slider
    )

    # Aliases for backward compatibility
    @property
    def start_tension(self):
        return self.start_speed

    @start_tension.setter
    def start_tension(self, val):
        self.start_speed = val

    @property
    def end_tension(self):
        return self.end_speed

    @end_tension.setter
    def end_tension(self, val):
        self.end_speed = val

    anticipation_amount: FloatProperty(
        name="Anticipation (Dip)",
        description="Pulls back in reverse before launching forward",
        min=0.0,
        max=100.0,
        default=0.0,
        subtype='PERCENTAGE',
        update=update_slider
    )

    overshoot_amount: FloatProperty(
        name="Overshoot (Rebound)",
        description="Exceeds destination keyframe value and rebounds back",
        min=0.0,
        max=150.0,
        default=0.0,
        subtype='PERCENTAGE',
        update=update_slider
    )

    # Physics Modes
    is_physics_mode: BoolProperty(
        name="Physics Simulation",
        description="Generate collision bounce or elastic wobble keyframes",
        default=False
    )

    physics_type: EnumProperty(
        name="Physics Type",
        items=[
            ('BOUNCE', "Collision Bounce", "Gravity rebounds", 'IPO_BOUNCE', 0),
            ('ELASTIC', "Elastic Wobble", "Damped harmonic spring oscillations", 'IPO_ELASTIC', 1),
        ],
        default='BOUNCE'
    )

    physics_bounces: IntProperty(
        name="Bounces / Oscillations",
        description="Number of bounce contacts or harmonic oscillations",
        min=1,
        max=50,
        default=3
    )

    physics_decay: FloatProperty(
        name="Energy Decay",
        description="Rate of energy dissipation per rebound",
        min=0.1,
        max=0.9,
        default=0.52
    )

    # Application Scope
    target_scope: EnumProperty(
        name="Apply To",
        description="Which keyframes to apply the motion curve to",
        items=[
            ('SELECTED_KEYS', "Selected Keyframes Only", "Only modifies channels and keyframes that are explicitly selected", 'RESTRICT_SELECT_OFF', 0),
            ('ALL_SELECTED_FCURVES', "All Keys on Selected Channels", "Applies to all keyframes across the selected channel curves", 'ANIM_DATA', 1),
        ],
        default='SELECTED_KEYS'
    )

    # EaseCopy Clipboard
    clipboard_handles: FloatVectorProperty(
        name="Clipboard Handles",
        size=4,
        default=(0.333, 0.0, 0.667, 1.0)
    )

    has_clipboard: BoolProperty(
        name="Has Copied Ease",
        default=False
    )

    clipboard_description: StringProperty(
        name="Clipboard Info",
        default=""
    )


classes = (
    SemanticMotionProperties,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.semantic_motion = PointerProperty(type=SemanticMotionProperties)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    if hasattr(bpy.types.Scene, "semantic_motion"):
        del bpy.types.Scene.semantic_motion
