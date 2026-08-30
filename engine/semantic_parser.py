"""
Semantic Parser Engine for Blender Animation Add-on.
Translates arbitrary natural language motion descriptions and phrases into
structured motion profiles (start/body/end phases, intensities, and physics).
"""

import re
from typing import Dict, Any, Optional, Tuple


class MotionProfile:
    """Represents a structured motion profile extracted from descriptors or prompts."""

    def __init__(
        self,
        start_type: str = "SLOW",
        start_intensity: float = 0.75,
        end_type: str = "SLOW",
        end_intensity: float = 0.75,
        overshoot_amount: float = 0.25,
        is_physics: bool = False,
        physics_type: Optional[str] = None,  # "BOUNCE" or "ELASTIC"
        physics_bounces: int = 3,
        physics_decay: float = 0.5,
        description: str = "Standard Smooth Ease",
        raw_prompt: str = ""
    ):
        self.start_type = start_type          # SLOW, FAST, ANTICIPATION, LINEAR, CONSTANT
        self.start_intensity = max(0.0, min(1.0, start_intensity))
        self.end_type = end_type              # SLOW, FAST, OVERSHOOT, LINEAR, CONSTANT
        self.end_intensity = max(0.0, min(1.0, end_intensity))
        self.overshoot_amount = max(0.0, min(1.5, overshoot_amount))
        self.is_physics = is_physics
        self.physics_type = physics_type      # "BOUNCE", "ELASTIC"
        self.physics_bounces = physics_bounces
        self.physics_decay = physics_decay
        self.description = description
        self.raw_prompt = raw_prompt

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_type": self.start_type,
            "start_intensity": self.start_intensity,
            "end_type": self.end_type,
            "end_intensity": self.end_intensity,
            "overshoot_amount": self.overshoot_amount,
            "is_physics": self.is_physics,
            "physics_type": self.physics_type,
            "physics_bounces": self.physics_bounces,
            "physics_decay": self.physics_decay,
            "description": self.description,
            "raw_prompt": self.raw_prompt,
        }

    def __repr__(self) -> str:
        if self.is_physics:
            return f"<MotionProfile Physics: {self.physics_type}, Bounces: {self.physics_bounces}, Decay: {self.physics_decay}>"
        return (
            f"<MotionProfile Start: {self.start_type} ({self.start_intensity:.2f}), "
            f"End: {self.end_type} ({self.end_intensity:.2f})"
            f"{f', Overshoot: {self.overshoot_amount:.2f}' if self.end_type == 'OVERSHOOT' else ''}>"
        )


# Modifiers and their multiplier effects
INTENSITY_MODIFIERS = {
    r"\b(subtle|slight|gentle|mild|soft|a bit|tiny|light)\b": 0.45,
    r"\b(moderate|medium|normal|regular)\b": 0.75,
    r"\b(heavy|strong|hard|steep|sharp|aggressive|intense|punchy|deep)\b": 0.92,
    r"\b(extreme|super|insane|ultra|maximum|huge|crazy|snap)\b": 1.0,
}

# Start keywords
START_SLOW_KEYWORDS = [
    r"\bslow\s+start\b", r"\bslow\s+beginning\b", r"\bgentle\s+start\b",
    r"\bsmooth\s+start\b", r"\bease\s+in\b", r"\bgradual\s+start\b",
    r"\bheavy\s+start\b", r"\bfriction\s+start\b", r"\blag\s+start\b",
    r"\bdecelerate\s+start\b", r"\bdelayed\s+start\b"
]

START_FAST_KEYWORDS = [
    r"\bfast\s+start\b", r"\bexplosive\s+start\b", r"\bquick\s+start\b",
    r"\binstant\s+start\b", r"\blaunch\b", r"\bpunchy\s+start\b",
    r"\bsharp\s+start\b", r"\brapid\s+start\b", r"\brash\s+start\b",
    r"\bsudden\s+start\b", r"\bburst\b", r"\bshoot\s+out\b"
]

START_ANTICIPATION_KEYWORDS = [
    r"\banticipat(ion|e|ed|ing)\b", r"\bdip(\s+start)?\b", r"\bwind\s*up\b",
    r"\bback(\s+start)?\b", r"\brecoil\b", r"\bcrouch\b", r"\bpull\s*back\b"
]

START_LINEAR_KEYWORDS = [
    r"\blinear\s+start\b", r"\bconstant\s+start\b", r"\bsteady\s+start\b"
]

# End keywords
END_SLOW_KEYWORDS = [
    r"\bslow\s+(end|ending|stop|finish|landing)\b", r"\bsoft\s+(end|ending|stop|finish|landing)\b",
    r"\bgentle\s+(end|ending|stop|finish|landing)\b", r"\bsmooth\s+(end|ending|stop|finish|landing)\b",
    r"\bease\s+out\b", r"\bgradual\s+(end|ending|stop|finish|landing)\b",
    r"\bfeather(\s+stop|\s+landing|\s+end)?\b", r"\bbraking\b", r"\bglide\s+stop\b"
]

END_FAST_KEYWORDS = [
    r"\bfast\s+(end|ending|stop|finish|landing)\b", r"\bsudden\s+(end|ending|stop|finish)\b",
    r"\bsharp\s+(end|ending|stop|finish)\b", r"\bhard\s+(end|ending|stop|finish)\b",
    r"\bslam(\s+stop|\s+finish|\s+end)?\b", r"\bwall\b", r"\babrupt(\s+stop|\s+end)?\b",
    r"\bquick\s+(end|ending|stop|finish)\b", r"\bimpact\b", r"\binstant\s+stop\b"
]

END_OVERSHOOT_KEYWORDS = [
    r"\bovershoot\b", r"\brebound\b", r"\bsettle\b", r"\bover\s*shoot\b",
    r"\bexceed\b", r"\bspring\s*back\b", r"\bpast\s+target\b"
]

END_BOUNCE_KEYWORDS = [
    r"\bbounce\b", r"\bbouncy\b", r"\bdrop\s+and\s+bounce\b", r"\brubber\b",
    r"\bball\s+bounce\b", r"\btrampoline\b"
]

END_ELASTIC_KEYWORDS = [
    r"\belastic\b", r"\bwobble\b", r"\bjiggle\b", r"\bspringy\b",
    r"\boscillation\b", r"\bvibrate\b", r"\bquiver\b"
]

END_LINEAR_KEYWORDS = [
    r"\blinear\s+(end|ending|stop|finish)\b", r"\bconstant\s+(end|ending|stop|finish)\b",
    r"\bsteady\s+(end|ending|stop|finish)\b"
]

# Curated Presets / Compound Phrases
PRESET_PHRASES = {
    "slow start, fast ending": MotionProfile(
        start_type="SLOW", start_intensity=0.88,
        end_type="FAST", end_intensity=0.9,
        description="Rocket / Bullet Launch (Slow start into high-speed slam)"
    ),
    "fast start, slow ending": MotionProfile(
        start_type="FAST", start_intensity=0.85,
        end_type="SLOW", end_intensity=0.9,
        description="Friction Slide / Heavy Braking (Explosive start into feather stop)"
    ),
    "slow start, slow ending": MotionProfile(
        start_type="SLOW", start_intensity=0.75,
        end_type="SLOW", end_intensity=0.75,
        description="Smooth Ease (Standard gentle S-Curve)"
    ),
    "fast start, fast ending": MotionProfile(
        start_type="FAST", start_intensity=0.8,
        end_type="FAST", end_intensity=0.8,
        description="Punch / Whip (Rapid surge through the middle)"
    ),
    "snappy": MotionProfile(
        start_type="SLOW", start_intensity=0.82,
        end_type="SLOW", end_intensity=0.82,
        description="Snappy UI Pop (High-tension ease in and ease out)"
    ),
    "anticipation to overshoot": MotionProfile(
        start_type="ANTICIPATION", start_intensity=0.7,
        end_type="OVERSHOOT", end_intensity=0.75, overshoot_amount=0.35,
        description="Classic Cartoon / Anticipation Dip into Rebound Overshoot"
    ),
    "explosive with overshoot": MotionProfile(
        start_type="FAST", start_intensity=0.85,
        end_type="OVERSHOOT", end_intensity=0.8, overshoot_amount=0.3,
        description="Explosive Blast with Elastic Settle"
    ),
    "bounce": MotionProfile(
        is_physics=True, physics_type="BOUNCE",
        physics_bounces=3, physics_decay=0.55,
        description="Physics Collision Bounce"
    ),
    "elastic wobble": MotionProfile(
        is_physics=True, physics_type="ELASTIC",
        physics_bounces=4, physics_decay=0.4,
        description="Damped Harmonic Spring / Elastic Jiggle"
    ),
    "linear": MotionProfile(
        start_type="LINEAR", start_intensity=0.0,
        end_type="LINEAR", end_intensity=0.0,
        description="Pure Linear Constant Speed"
    ),
}


def _extract_modifier_intensity(text: str, default: float = 0.75) -> float:
    """Finds any intensity modifier in text and returns the corresponding value."""
    for pattern, value in INTENSITY_MODIFIERS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return value
    return default


def parse_motion_prompt(prompt: str) -> MotionProfile:
    """
    Parses an arbitrary natural language prompt string into a MotionProfile.
    
    Examples:
        - "slow start, fast ending"
        - "heavy anticipation, explosive launch, soft landing"
        - "subtle overshoot with fast start"
        - "drop and bounce with 4 rebounds"
        - "snappy ease with extreme tension"
    """
    cleaned = prompt.strip().lower()
    if not cleaned:
        return MotionProfile(description="Default Ease (33% In / Out)", raw_prompt=prompt)

    # Check for direct preset match
    for preset_key, profile in PRESET_PHRASES.items():
        if cleaned == preset_key:
            return MotionProfile(
                start_type=profile.start_type,
                start_intensity=profile.start_intensity,
                end_type=profile.end_type,
                end_intensity=profile.end_intensity,
                overshoot_amount=profile.overshoot_amount,
                is_physics=profile.is_physics,
                physics_type=profile.physics_type,
                physics_bounces=profile.physics_bounces,
                physics_decay=profile.physics_decay,
                description=profile.description,
                raw_prompt=prompt
            )

    # Determine global / segment intensity modifiers
    base_intensity = _extract_modifier_intensity(cleaned, default=0.75)

    # Check for physics types (Bounce / Elastic)
    is_bounce = any(re.search(pat, cleaned, re.IGNORECASE) for pat in END_BOUNCE_KEYWORDS)
    is_elastic = any(re.search(pat, cleaned, re.IGNORECASE) for pat in END_ELASTIC_KEYWORDS)

    if is_bounce:
        bounces = 3
        bounce_match = re.search(r"(\d+)\s+(bounces?|rebounds?|contacts?)", cleaned)
        if bounce_match:
            bounces = max(1, min(50, int(bounce_match.group(1))))
        decay = 0.6 if "heavy" in cleaned or "high" in cleaned else 0.48
        return MotionProfile(
            is_physics=True,
            physics_type="BOUNCE",
            physics_bounces=bounces,
            physics_decay=decay,
            description=f"Physics Bounce ({bounces} rebounds)",
            raw_prompt=prompt
        )

    if is_elastic:
        oscillations = 4
        osc_match = re.search(r"(\d+)\s+(oscillations?|jiggles?|wobbles?)", cleaned)
        if osc_match:
            oscillations = max(1, min(50, int(osc_match.group(1))))
        decay = 0.35 if "long" in cleaned or "loose" in cleaned else 0.5
        return MotionProfile(
            is_physics=True,
            physics_type="ELASTIC",
            physics_bounces=oscillations,
            physics_decay=decay,
            description=f"Elastic Wobble ({oscillations} oscillations)",
            raw_prompt=prompt
        )

    # Parse Start Phase
    start_type = "SLOW"
    start_intensity = base_intensity

    if any(re.search(pat, cleaned, re.IGNORECASE) for pat in START_ANTICIPATION_KEYWORDS):
        start_type = "ANTICIPATION"
        start_intensity = base_intensity
    elif any(re.search(pat, cleaned, re.IGNORECASE) for pat in START_FAST_KEYWORDS):
        start_type = "FAST"
        start_intensity = base_intensity
    elif any(re.search(pat, cleaned, re.IGNORECASE) for pat in START_LINEAR_KEYWORDS):
        start_type = "LINEAR"
        start_intensity = 0.0
    elif any(re.search(pat, cleaned, re.IGNORECASE) for pat in START_SLOW_KEYWORDS):
        start_type = "SLOW"
        start_intensity = base_intensity
    elif "snappy" in cleaned or "pop" in cleaned:
        start_type = "SLOW"
        start_intensity = 0.85

    # Parse End Phase
    end_type = "SLOW"
    end_intensity = base_intensity
    overshoot_amount = 0.25

    if any(re.search(pat, cleaned, re.IGNORECASE) for pat in END_OVERSHOOT_KEYWORDS):
        end_type = "OVERSHOOT"
        overshoot_amount = 0.38 if "heavy" in cleaned or "big" in cleaned or "extreme" in cleaned else 0.22
    elif any(re.search(pat, cleaned, re.IGNORECASE) for pat in END_FAST_KEYWORDS):
        end_type = "FAST"
        end_intensity = base_intensity
    elif any(re.search(pat, cleaned, re.IGNORECASE) for pat in END_LINEAR_KEYWORDS):
        end_type = "LINEAR"
        end_intensity = 0.0
    elif any(re.search(pat, cleaned, re.IGNORECASE) for pat in END_SLOW_KEYWORDS):
        end_type = "SLOW"
        end_intensity = base_intensity
    elif "snappy" in cleaned or "pop" in cleaned:
        end_type = "SLOW"
        end_intensity = 0.85

    # Build human summary
    summary_parts = []
    if start_type == "SLOW":
        summary_parts.append(f"Slow Start ({int(start_intensity * 100)}% ease-in)")
    elif start_type == "FAST":
        summary_parts.append(f"Fast Launch ({int(start_intensity * 100)}% velocity)")
    elif start_type == "ANTICIPATION":
        summary_parts.append(f"Anticipation Dip ({int(start_intensity * 100)}% pullback)")
    elif start_type == "LINEAR":
        summary_parts.append("Linear Start")

    if end_type == "SLOW":
        summary_parts.append(f"Soft Landing ({int(end_intensity * 100)}% ease-out)")
    elif end_type == "FAST":
        summary_parts.append(f"Sudden Stop ({int(end_intensity * 100)}% impact)")
    elif end_type == "OVERSHOOT":
        summary_parts.append(f"Overshoot Settle (+{int(overshoot_amount * 100)}% rebound)")
    elif end_type == "LINEAR":
        summary_parts.append("Linear End")

    description = " \u2192 ".join(summary_parts)

    return MotionProfile(
        start_type=start_type,
        start_intensity=start_intensity,
        end_type=end_type,
        end_intensity=end_intensity,
        overshoot_amount=overshoot_amount,
        description=description,
        raw_prompt=prompt
    )
