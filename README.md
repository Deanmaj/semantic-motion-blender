# Semantic Motion - Blender Animation Add-on

Control Blender animation curves and easing using **natural language motion descriptions** (e.g. *"slow start, fast ending"*, *"explosive launch with overshoot"*, *"anticipation dip to soft landing"*) and **EaseCopy/Paste**.

---

## Key Features

1. **Natural Language Motion Prompt Bar**:
   - Type plain English descriptions to shape your animation curves.
   - Recognizes acceleration behaviors, deceleration/arrival styles, and intensity modifiers (*subtle*, *extreme*, *heavy*, *snappy*, *gentle*).
   - Examples:
     - `"slow start, fast ending"` (rocket / bullet launch)
     - `"fast start, slow ending"` (braking / slide)
     - `"anticipation to overshoot"` (classic cartoon rebound)
     - `"drop and bounce with 4 rebounds"` (physics collision bounce)
     - `"elastic wobble with 5 oscillations"` (spring / jelly jiggle)
     - `"snappy"` (high-tension UI pop)

2. **Phase Builder UI (Dropdowns & Sliders)**:
   - For visual adjustment without typing:
     - **Start Phase**: `[Slow/Ease In | Fast/Explosive | Anticipation (Dip) | Linear]`
     - **End Phase**: `[Soft Landing/Ease Out | Fast/Sudden Stop | Overshoot & Settle | Physics Bounce | Elastic Wobble | Linear]`
     - **Tension & Weight Sliders**: Start tension, End tension, Overshoot amplitude.

3. **EaseCopy & EasePaste**:
   - Copy normalized Bezier easing curve parameters from any keyframe interval.
   - Paste to any selected keyframe intervals across different F-Curves, objects, or pose bones.
   - Support for **Paste Inverted / Flipped** for symmetrical return animations.

4. **Curve Analyzer ("Describe Selected Curve")**:
   - Reads the tangent handles of any selected keyframes in Blender and generates an English description and matching preset.

5. **Live Curve Graph Preview**:
   - Visual ASCII / unicode curve diagram rendered directly in the sidebar so you can see the curve shape in real time.

6. **Quick Pie Menu**:
   - Press `Shift + Alt + E` anywhere in the **Graph Editor**, **Dope Sheet**, or **3D Viewport** to access an 8-way motion recipe wheel.

---

## Installation

### For Blender 3.0 through 4.1:
1. Zip the addon folder `Animation Addon for blender`.
2. In Blender, go to **Edit > Preferences > Add-ons > Install...**
3. Select the `.zip` file and enable **"Semantic Motion"**.

### For Blender 4.2+:
1. Go to **Edit > Preferences > Get Extensions > Install from Disk...**
2. Select the folder or zip containing `blender_manifest.toml`.

---

## Where to Find in Blender

The **Semantic Motion** panel is available in the Sidebar (`N` panel) under the **Semantic Motion** tab in:
- **Graph Editor**
- **Dope Sheet / Timeline**
- **3D Viewport**

**Pie Menu Shortcut**: `Shift + Alt + E`
