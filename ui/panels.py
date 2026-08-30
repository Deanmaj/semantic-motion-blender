"""
UI Panels for Semantic Motion Add-on.
Independent top-level collapsible panels:
  1. Phase Builder (Speed Sliders, Live Link, Live Property widget)
  2. Curve Utilities (Scope, Copy/Paste Ease, 2-line Motion Flow, Anticipation Dip & Overshoot Rebound)
  3. Natural Motion Descriptor (Natural Language text prompt & presets)
"""

import bpy
from ..engine.curve_analyzer import analyze_keyframe_pair
from ..operators.apply_semantic_curve import get_target_fcurves
from ..properties import update_slider
from .. import properties

_LAST_SELECTION_SIG = None


# ---------------------------------------------------------------------------
# Auto-sync: reads selected handles -> updates sliders silently, no curve edit
# ---------------------------------------------------------------------------

def auto_sync_selection_to_sliders(context, props):
    global _LAST_SELECTION_SIG
    if properties._IS_SYNCING:
        return
    try:
        # Find candidate fcurves (active fcurve first, or selected editable fcurves)
        target_fcurve = _get_active_fcurve(context)
        candidate_fcurves = []
        if target_fcurve:
            candidate_fcurves.append(target_fcurve)
        for fc in get_target_fcurves(context):
            if fc not in candidate_fcurves:
                candidate_fcurves.append(fc)

        if not candidate_fcurves:
            return

        for fc in candidate_fcurves:
            keyframes = getattr(fc, "keyframe_points", getattr(fc, "points", []))
            if not keyframes or len(keyframes) < 2:
                continue

            selected_kps = [k for k in keyframes if getattr(k, "select_control_point", False)]

            k0, k1 = None, None
            if len(selected_kps) >= 2:
                # User selected 2 or more keyframes
                k0, k1 = selected_kps[0], selected_kps[1]
            elif len(selected_kps) == 1:
                # User selected 1 keyframe: pick the interval adjacent to it
                sel_kp = selected_kps[0]
                idx = -1
                for i, kp in enumerate(keyframes):
                    if kp == sel_kp or (abs(kp.co[0] - sel_kp.co[0]) < 0.001 and abs(kp.co[1] - sel_kp.co[1]) < 0.001):
                        idx = i
                        break
                if idx >= 0:
                    if idx < len(keyframes) - 1:
                        k0, k1 = keyframes[idx], keyframes[idx + 1]
                    elif idx > 0:
                        k0, k1 = keyframes[idx - 1], keyframes[idx]
            else:
                # User selected/clicked the fcurve channel (no explicit keyframes selected)
                # Find keyframe pair around the current timeline frame
                curr_frame = getattr(context.scene, "frame_current", 0)
                prev_kps = [k for k in keyframes if k.co[0] <= curr_frame]
                next_kps = [k for k in keyframes if k.co[0] > curr_frame]
                if prev_kps and next_kps:
                    k0 = prev_kps[-1]
                    k1 = next_kps[0]
                elif prev_kps and len(prev_kps) >= 2:
                    k0 = prev_kps[-2]
                    k1 = prev_kps[-1]
                elif next_kps and len(next_kps) >= 2:
                    k0 = next_kps[0]
                    k1 = next_kps[1]
                else:
                    k0 = keyframes[0]
                    k1 = keyframes[1]

            if k0 and k1 and k0 != k1:
                sig = (
                    getattr(fc, "data_path", ""),
                    getattr(fc, "array_index", 0),
                    round(k0.co[0], 2), round(k0.co[1], 4),
                    round(k0.handle_right[0], 2), round(k0.handle_right[1], 4),
                    round(k1.co[0], 2), round(k1.co[1], 4),
                    round(k1.handle_left[0], 2), round(k1.handle_left[1], 4)
                )
                if sig != _LAST_SELECTION_SIG:
                    _LAST_SELECTION_SIG = sig
                    res = analyze_keyframe_pair(k0, k1)
                    properties._IS_SYNCING = True
                    try:
                        props.start_speed = res.get("start_speed", 20.0)
                        props.end_speed = res.get("end_speed", 80.0)
                        props.anticipation_amount = res.get("anticipation_amount", 0.0)
                        props.overshoot_amount = res.get("overshoot_amount_pct", 0.0)
                        update_slider(props, context)
                    finally:
                        properties._IS_SYNCING = False
                break
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Property display helper
# ---------------------------------------------------------------------------

def _get_active_fcurve(context):
    """Return the active or first selected editable fcurve, or None."""
    for attr in ("active_editable_fcurve", "selected_editable_fcurves"):
        val = getattr(context, attr, None)
        if val:
            return val if not hasattr(val, "__iter__") else next(iter(val), None)
    # Fall back: search active object's action
    obj = getattr(context, "active_object", None)
    if obj and obj.animation_data and obj.animation_data.action:
        from ..operators.apply_semantic_curve import extract_curves_from_action
        for fc in extract_curves_from_action(obj.animation_data.action):
            if getattr(fc, "select", False):
                return fc
    return None


def _fcurve_channel_label(fc, owner=None):
    """
    Build a human-readable label for an fcurve, e.g. 'Z Euler Rotation'.
    Uses RNA metadata when available, falls back to a prettified data_path.
    """
    AXIS = ["X", "Y", "Z", "W"]
    data_path = fc.data_path
    array_index = fc.array_index

    tail = data_path.rsplit(".", 1)[-1]
    if "[" in tail:
        tail = tail[:tail.index("[")]

    if owner is not None:
        try:
            rna_prop = owner.bl_rna.properties.get(tail)
            if rna_prop:
                base = rna_prop.name
                if getattr(rna_prop, "array_length", 0) > 1 and array_index < len(AXIS):
                    return f"{AXIS[array_index]} {base}"
                return base
        except Exception:
            pass

    pretty = tail.replace("_", " ").title()
    if array_index >= 0 and array_index < len(AXIS):
        return f"{AXIS[array_index]} {pretty}"
    return pretty


def draw_live_property(layout, context):
    """
    Render the live value of the active fcurve's property as a native Blender
    widget (number field, dropdown, colour, etc.) without any 'Property:' prefix.
    """
    box = layout.box()

    obj = getattr(context, "active_object", None)
    fc = _get_active_fcurve(context)

    if not fc or not obj:
        box.label(text="Select an F-Curve Channel", icon='INFO')
        return

    data_path = fc.data_path
    array_index = fc.array_index

    try:
        if "." in data_path:
            owner_path, prop_attr = data_path.rsplit(".", 1)
            owner = obj.path_resolve(owner_path)
        else:
            owner = obj
            prop_attr = data_path

        if "[" in prop_attr:
            prop_attr = prop_attr[:prop_attr.index("[")]

        channel_label = _fcurve_channel_label(fc, owner)

        # Header row: Clean channel name (no "Property:" prefix) + auto-key toggle
        hdr = box.row(align=True)
        hdr.label(text=channel_label, icon='ANIM_DATA')
        hdr.prop(
            context.scene.tool_settings,
            "use_keyframe_insert_auto",
            text="",
            icon='REC',
        )

        # Live editable value widget
        val_row = box.row(align=True)
        try:
            val_row.prop(owner, prop_attr, index=array_index, text="")
        except TypeError:
            val_row.prop(owner, prop_attr, text="")

        # Manual key-here button
        key_op = val_row.operator(
            "semantic_motion.key_property",
            text="",
            icon='KEY_HLT',
        )
        key_op.data_path = data_path
        key_op.array_index = array_index

    except Exception:
        box.label(text=f"{data_path}[{array_index}]", icon='PROPERTIES')


# ---------------------------------------------------------------------------
# Shared draw helpers
# ---------------------------------------------------------------------------

def draw_phase_builder(layout, context, props):
    """Phase Builder panel — speed sliders, live link, live property widget."""
    auto_sync_selection_to_sliders(context, props)

    # Live Link toggle
    layout.prop(props, "live_update", text="Live Link", icon='LINKED')
    layout.separator(factor=0.4)

    # Live Property display (clean property name without 'Property:' tag)
    draw_live_property(layout, context)
    layout.separator(factor=0.6)

    # --- START SPEED ---
    layout.label(text="Start Speed  (0%  Slow \u2192  100%  Fast):", icon='IPO_EASE_IN')
    snap_s = layout.row(align=True)
    snap_s.scale_y = 0.8
    for lbl, val in [("0%", 0.0), ("25%", 25.0), ("50%", 50.0), ("75%", 75.0), ("100%", 100.0)]:
        op = snap_s.operator("semantic_motion.set_tension_snap", text=lbl)
        op.target = 'START'
        op.value = val
    layout.prop(props, "start_speed", text="", slider=True)

    layout.separator(factor=0.8)

    # --- END SPEED ---
    layout.label(text="End Speed  (0%  Slow \u2192  100%  Fast):", icon='IPO_EASE_OUT')
    snap_e = layout.row(align=True)
    snap_e.scale_y = 0.8
    for lbl, val in [("0%", 0.0), ("25%", 25.0), ("50%", 50.0), ("75%", 75.0), ("100%", 100.0)]:
        op = snap_e.operator("semantic_motion.set_tension_snap", text=lbl)
        op.target = 'END'
        op.value = val
    layout.prop(props, "end_speed", text="", slider=True)

    layout.separator()
    apply_row = layout.row(align=True)
    apply_row.scale_y = 1.25
    op = apply_row.operator("semantic_motion.apply_curve", text="Apply Motion to Keys", icon='CHECKMARK')
    op.force_mode = 'PHASE_BUILDER'


def draw_curve_utilities(layout, context, props):
    """Curve Utilities panel — Scope, Copy/Paste Ease, 2-line Motion Flow, Dip & Rebound."""
    auto_sync_selection_to_sliders(context, props)

    layout.prop(props, "target_scope", text="Scope")
    layout.separator(factor=0.4)

    row = layout.row(align=True)
    row.operator("semantic_motion.copy_ease",  text="Copy Ease",  icon='COPYDOWN')
    row.operator("semantic_motion.paste_ease", text="Paste Ease", icon='PASTEDOWN').mode = 'BOTH'
    if props.has_clipboard:
        layout.operator("semantic_motion.paste_ease", text="Paste Inverted", icon='ARROW_LEFTRIGHT').mode = 'INVERT'

    layout.separator(factor=0.6)
    layout.label(text="Motion Flow:", icon='INFO')

    # Break motion flow into two lines to prevent ellipsis truncation
    desc = props.parsed_description or "Smooth Motion"
    if " — " in desc:
        flow_part, style_part = desc.split(" — ", 1)
        layout.label(text=flow_part)
        layout.label(text=style_part)
    elif " → " in desc:
        start_part, end_part = desc.split(" → ", 1)
        layout.label(text=f"{start_part} \u2192")
        layout.label(text=end_part)
    else:
        import textwrap
        lines = textwrap.wrap(desc, width=32)
        for line in (lines[:2] if lines else [desc]):
            layout.label(text=line)

    # Modifiers on the bottom side of Curve Utilities
    layout.separator(factor=0.8)
    layout.label(text="Modifiers:", icon='MODIFIER')
    layout.prop(props, "anticipation_amount", slider=True, text="Anticipation Dip")
    layout.prop(props, "overshoot_amount",    slider=True, text="Overshoot Rebound")


def draw_natural_motion(layout, props):
    """Natural Motion Descriptor panel — prompt input and presets."""
    layout.label(text="Natural Language Description:", icon='FONT_DATA')
    layout.prop(props, "prompt_text", text="", icon='EDITMODE_HLT')
    layout.separator(factor=0.5)
    layout.label(text="One-Click Recipes:", icon='BOOKMARKS')
    grid = layout.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=False, align=True)
    grid.operator("semantic_motion.apply_preset", text="Slow Start, Fast End",      icon='FORWARD'    ).preset_name = "slow start, fast ending"
    grid.operator("semantic_motion.apply_preset", text="Fast Start, Slow End",      icon='BACK'       ).preset_name = "fast start, slow ending"
    grid.operator("semantic_motion.apply_preset", text="Smooth S-Curve",            icon='SPHERE'     ).preset_name = "slow start, slow ending"
    grid.operator("semantic_motion.apply_preset", text="Anticipate \u2192 Overshoot", icon='IPO_BACK' ).preset_name = "anticipation to overshoot"
    grid.operator("semantic_motion.apply_preset", text="Explosive Blast",           icon='LIGHT_SUN'  ).preset_name = "explosive with overshoot"
    grid.operator("semantic_motion.apply_preset", text="Physics Bounce (30)",       icon='IPO_BOUNCE' ).preset_name = "drop and bounce with 30 rebounds"
    grid.operator("semantic_motion.apply_preset", text="Elastic Wobble",            icon='IPO_ELASTIC').preset_name = "elastic wobble"
    grid.operator("semantic_motion.apply_preset", text="Linear Constant",           icon='IPO_LINEAR' ).preset_name = "linear"
    layout.separator()
    apply_row = layout.row(align=True)
    apply_row.scale_y = 1.25
    op = apply_row.operator("semantic_motion.apply_curve", text="Apply Motion to Keys", icon='CHECKMARK')
    op.force_mode = 'PROMPT'


# ===========================================================================
#  GRAPH EDITOR — 3 independent collapsible panels in requested order
# ===========================================================================

class GRAPH_EDITOR_PT_SM_PhaseBuilder(bpy.types.Panel):
    bl_space_type  = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Phase Builder'
    bl_order       = 0

    def draw(self, context):
        draw_phase_builder(self.layout, context, context.scene.semantic_motion)


class GRAPH_EDITOR_PT_SM_CurveUtils(bpy.types.Panel):
    bl_space_type  = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Curve Utilities'
    bl_order       = 1
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_curve_utilities(self.layout, context, context.scene.semantic_motion)


class GRAPH_EDITOR_PT_SM_NaturalMotion(bpy.types.Panel):
    bl_space_type  = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Natural Motion Descriptor'
    bl_order       = 2
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_natural_motion(self.layout, context.scene.semantic_motion)


# ===========================================================================
#  DOPE SHEET — 3 independent collapsible panels in requested order
# ===========================================================================

class DOPESHEET_PT_SM_PhaseBuilder(bpy.types.Panel):
    bl_space_type  = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Phase Builder'
    bl_order       = 0

    def draw(self, context):
        draw_phase_builder(self.layout, context, context.scene.semantic_motion)


class DOPESHEET_PT_SM_CurveUtils(bpy.types.Panel):
    bl_space_type  = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Curve Utilities'
    bl_order       = 1
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_curve_utilities(self.layout, context, context.scene.semantic_motion)


class DOPESHEET_PT_SM_NaturalMotion(bpy.types.Panel):
    bl_space_type  = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Natural Motion Descriptor'
    bl_order       = 2
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_natural_motion(self.layout, context.scene.semantic_motion)


# ===========================================================================
#  3D VIEWPORT — 3 independent collapsible panels in requested order
# ===========================================================================

class VIEW3D_PT_SM_PhaseBuilder(bpy.types.Panel):
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Phase Builder'
    bl_order       = 0

    def draw(self, context):
        draw_phase_builder(self.layout, context, context.scene.semantic_motion)


class VIEW3D_PT_SM_CurveUtils(bpy.types.Panel):
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Curve Utilities'
    bl_order       = 1
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_curve_utilities(self.layout, context.scene.semantic_motion)


class VIEW3D_PT_SM_NaturalMotion(bpy.types.Panel):
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Natural Motion Descriptor'
    bl_order       = 2
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_natural_motion(self.layout, context.scene.semantic_motion)


# ===========================================================================
#  Registration
# ===========================================================================

classes = (
    # Graph Editor
    GRAPH_EDITOR_PT_SM_PhaseBuilder,
    GRAPH_EDITOR_PT_SM_CurveUtils,
    GRAPH_EDITOR_PT_SM_NaturalMotion,
    # Dope Sheet
    DOPESHEET_PT_SM_PhaseBuilder,
    DOPESHEET_PT_SM_CurveUtils,
    DOPESHEET_PT_SM_NaturalMotion,
    # 3D Viewport
    VIEW3D_PT_SM_PhaseBuilder,
    VIEW3D_PT_SM_CurveUtils,
    VIEW3D_PT_SM_NaturalMotion,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
