"""
UI Panels for Semantic Motion Add-on.
Strict 4-tab collapsible layout:
  1. Phase Builder (Speed Sliders, Live Link, Live Property widget)
  2. Curve Utilities (Scope, Copy/Paste Ease, Anticipation Dip & Overshoot Rebound)
  3. Motion Flow (Clickable Value & Speed Graph Tabs, Vertical Resolution, Direct Flow Metrics)
  4. Natural Motion Descriptor (Natural Language text prompt & presets)

Features background selection timer for instantaneous auto-updating of speed sliders,
dip, rebound, and motion flow when 2 keyframes are selected.
"""

import bpy
import textwrap
from ..engine.curve_analyzer import analyze_keyframe_pair
from ..engine.bezier_math import motion_tools_slider_to_bezier
from .curve_preview import render_high_res_curve, render_speed_graph
from ..operators.apply_semantic_curve import get_target_fcurves
from ..properties import update_slider
from .. import properties

_LAST_SELECTION_SIG = None


# ---------------------------------------------------------------------------
# Auto-sync: Evaluates strictly when 2 keyframes are selected
# ---------------------------------------------------------------------------

def sync_selected_keyframe_pair(context, props):
    """
    Reads selected keyframes and automatically updates Start & End speed sliders,
    Anticipation Dip, Overshoot Rebound, and Motion Flow.
    Only updates when at least 2 keyframes are selected so that start (k0) and
    end (k1) can be definitively ordered by time.
    """
    global _LAST_SELECTION_SIG
    if properties._IS_SYNCING:
        return

    try:
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

            # Detect keyframes where point or handles are selected
            selected_kps = [
                k for k in keyframes
                if getattr(k, "select_control_point", False)
                or getattr(k, "select_left_handle", False)
                or getattr(k, "select_right_handle", False)
            ]

            # Strictly require 2 or more selected keyframes
            if len(selected_kps) < 2:
                continue

            # Sort chronologically: k0 is strictly start, k1 is strictly end
            selected_kps = sorted(selected_kps, key=lambda kp: kp.co[0])
            k0 = selected_kps[0]
            k1 = selected_kps[1]

            if k0 == k1:
                continue

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


def check_selection_timer():
    """Background timer to safely check selection outside the restricted UI draw loop."""
    try:
        context = bpy.context
        scene = getattr(context, "scene", None)
        if scene and hasattr(scene, "semantic_motion"):
            sync_selected_keyframe_pair(context, scene.semantic_motion)
    except Exception:
        pass
    return 0.08  # Run every 80ms for instant responsiveness


# ---------------------------------------------------------------------------
# Property display helper
# ---------------------------------------------------------------------------

def _get_active_fcurve(context):
    """Return the active or first selected editable fcurve, or None."""
    for attr in ("active_editable_fcurve", "selected_editable_fcurves"):
        val = getattr(context, attr, None)
        if val:
            return val if not hasattr(val, "__iter__") else next(iter(val), None)
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
    widget (number field, dropdown, colour, etc.) with NO 'Property:' prefix.
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

        # Check isolation / solo status of this curve
        all_curves = []
        if obj.animation_data and obj.animation_data.action:
            from ..operators.apply_semantic_curve import extract_curves_from_action
            all_curves = extract_curves_from_action(obj.animation_data.action)

        target_hidden = getattr(fc, "hide", False)
        other_curves = [c for c in all_curves if c != fc]
        any_other_hidden = any(getattr(c, "hide", False) for c in other_curves)
        is_soloed = (not target_hidden and any_other_hidden)
        eye_icon = 'RESTRICT_VIEW_OFF' if not target_hidden else 'RESTRICT_VIEW_ON'

        # Header row: Clean channel name + Eye Solo button + Auto-key toggle
        hdr = box.row(align=True)
        hdr.label(text=channel_label, icon='ANIM_DATA')

        # Eye icon placed beside Auto keying icon
        solo_op = hdr.operator(
            "semantic_motion.toggle_curve_solo",
            text="",
            icon=eye_icon,
            depress=is_soloed,
        )
        solo_op.data_path = data_path
        solo_op.array_index = array_index

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
    """Curve Utilities panel — Scope, Copy/Paste Ease, Dip & Rebound modifiers."""
    layout.prop(props, "target_scope", text="Scope")
    layout.separator(factor=0.4)

    row = layout.row(align=True)
    row.operator("semantic_motion.copy_ease",  text="Copy Ease",  icon='COPYDOWN')
    row.operator("semantic_motion.paste_ease", text="Paste Ease", icon='PASTEDOWN').mode = 'BOTH'
    if props.has_clipboard:
        layout.operator("semantic_motion.paste_ease", text="Paste Inverted", icon='ARROW_LEFTRIGHT').mode = 'INVERT'

    # Modifiers on bottom side of Curve Utilities
    layout.separator(factor=0.8)
    layout.label(text="Modifiers:", icon='MODIFIER')
    layout.prop(props, "anticipation_amount", slider=True, text="Anticipation Dip")
    layout.prop(props, "overshoot_amount",    slider=True, text="Overshoot Rebound")


def draw_motion_flow(layout, props):
    """Motion Flow panel — Clickable Value & Speed Graph Tabs and Non-Truncated Metrics."""
    # 1. Clickable View Tabs (Value Graph vs Speed Graph)
    tabs_row = layout.row(align=True)
    tabs_row.prop(props, "graph_type", expand=True)
    layout.separator(factor=0.3)

    # 2. Enhanced High-Resolution Graphical Curve with Vertical Height (8 rows = 32 subpixels)
    try:
        bezier = motion_tools_slider_to_bezier(
            props.start_speed,
            props.end_speed,
            props.anticipation_amount / 100.0,
            props.overshoot_amount / 100.0
        )
        if getattr(props, "graph_type", 'VALUE') == 'SPEED':
            graph_lines = render_speed_graph(bezier, char_width=18, char_height=8)
        else:
            graph_lines = render_high_res_curve(bezier, char_width=18, char_height=8)

        graph_box = layout.box()
        col = graph_box.column(align=True)
        col.scale_y = 0.85
        for line in graph_lines:
            col.label(text=line)
    except Exception:
        pass

    layout.separator(factor=0.4)

    # 3. Direct Clean Metrics — No redundant subtitles, dynamic text wrapping
    flow_box = layout.box()
    flow_col = flow_box.column(align=True)

    s = int(props.start_speed)
    e = int(props.end_speed)

    s_txt = f"Slow Start ({s}%)" if s <= 35 else (f"Steady Start ({s}%)" if s <= 65 else f"Fast Start ({s}%)")
    e_txt = f"Slow End ({e}%)" if e <= 35 else (f"Steady End ({e}%)" if e <= 65 else f"Fast End ({e}%)")

    if s <= 35 and e >= 65:
        traj_lines = ["Accelerating Launch", "Rocket Surge to Target"]
    elif s >= 65 and e <= 35:
        traj_lines = ["Decelerating Arrival", "High-Speed Brake Cushion"]
    elif s <= 35 and e <= 35:
        traj_lines = ["Smooth S-Curve", "Gentle Departure & Landing"]
    elif s >= 65 and e >= 65:
        traj_lines = ["Fast Continuous Surge", "Explosive Punch Through"]
    else:
        traj_lines = ["Steady Linear Progression"]

    # Start and End metrics directly shown without redundant prefixes
    flow_col.label(text=s_txt, icon='IPO_EASE_IN')
    flow_col.label(text=e_txt, icon='IPO_EASE_OUT')

    # Trajectory directly displayed line by line to guarantee zero truncation
    flow_col.separator(factor=0.3)
    for i, line in enumerate(traj_lines):
        flow_col.label(text=line, icon='FORWARD' if i == 0 else 'BLANK1')

    # Modifiers directly displayed when active
    if props.anticipation_amount > 0.5:
        flow_col.separator(factor=0.3)
        flow_col.label(text=f"Anticipation Dip ({int(props.anticipation_amount)}%)", icon='IPO_BACK')

    if props.overshoot_amount > 0.5:
        flow_col.separator(factor=0.3)
        flow_col.label(text=f"Overshoot Rebound (+{int(props.overshoot_amount)}%)", icon='IPO_BACK')


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
#  GRAPH EDITOR — Explicitly ordered panels
# ===========================================================================

class GRAPH_EDITOR_PT_semantic_motion_1_phase_builder(bpy.types.Panel):
    bl_space_type  = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Phase Builder'
    bl_order       = 0

    def draw(self, context):
        draw_phase_builder(self.layout, context, context.scene.semantic_motion)


class GRAPH_EDITOR_PT_semantic_motion_2_curve_utils(bpy.types.Panel):
    bl_space_type  = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Curve Utilities'
    bl_order       = 1
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_curve_utilities(self.layout, context, context.scene.semantic_motion)


class GRAPH_EDITOR_PT_semantic_motion_3_motion_flow(bpy.types.Panel):
    bl_space_type  = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Motion Flow'
    bl_order       = 2
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_motion_flow(self.layout, context.scene.semantic_motion)


class GRAPH_EDITOR_PT_semantic_motion_4_natural_motion(bpy.types.Panel):
    bl_space_type  = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Natural Motion Descriptor'
    bl_order       = 3
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_natural_motion(self.layout, context.scene.semantic_motion)


# ===========================================================================
#  DOPE SHEET — Explicitly ordered panels
# ===========================================================================

class DOPESHEET_PT_semantic_motion_1_phase_builder(bpy.types.Panel):
    bl_space_type  = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Phase Builder'
    bl_order       = 0

    def draw(self, context):
        draw_phase_builder(self.layout, context, context.scene.semantic_motion)


class DOPESHEET_PT_semantic_motion_2_curve_utils(bpy.types.Panel):
    bl_space_type  = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Curve Utilities'
    bl_order       = 1
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_curve_utilities(self.layout, context.scene.semantic_motion)


class DOPESHEET_PT_semantic_motion_3_motion_flow(bpy.types.Panel):
    bl_space_type  = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Motion Flow'
    bl_order       = 2
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_motion_flow(self.layout, context.scene.semantic_motion)


class DOPESHEET_PT_semantic_motion_4_natural_motion(bpy.types.Panel):
    bl_space_type  = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Natural Motion Descriptor'
    bl_order       = 3
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_natural_motion(self.layout, context.scene.semantic_motion)


# ===========================================================================
#  3D VIEWPORT — Explicitly ordered panels
# ===========================================================================

class VIEW3D_PT_semantic_motion_1_phase_builder(bpy.types.Panel):
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Phase Builder'
    bl_order       = 0

    def draw(self, context):
        draw_phase_builder(self.layout, context, context.scene.semantic_motion)


class VIEW3D_PT_semantic_motion_2_curve_utils(bpy.types.Panel):
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Curve Utilities'
    bl_order       = 1
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_curve_utilities(self.layout, context.scene.semantic_motion)


class VIEW3D_PT_semantic_motion_3_motion_flow(bpy.types.Panel):
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Motion Flow'
    bl_order       = 2
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_motion_flow(self.layout, context.scene.semantic_motion)


class VIEW3D_PT_semantic_motion_4_natural_motion(bpy.types.Panel):
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Natural Motion Descriptor'
    bl_order       = 3
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_natural_motion(self.layout, context.scene.semantic_motion)


# ===========================================================================
#  Registration
# ===========================================================================

classes = (
    # Graph Editor
    GRAPH_EDITOR_PT_semantic_motion_1_phase_builder,
    GRAPH_EDITOR_PT_semantic_motion_2_curve_utils,
    GRAPH_EDITOR_PT_semantic_motion_3_motion_flow,
    GRAPH_EDITOR_PT_semantic_motion_4_natural_motion,
    # Dope Sheet
    DOPESHEET_PT_semantic_motion_1_phase_builder,
    DOPESHEET_PT_semantic_motion_2_curve_utils,
    DOPESHEET_PT_semantic_motion_3_motion_flow,
    DOPESHEET_PT_semantic_motion_4_natural_motion,
    # 3D Viewport
    VIEW3D_PT_semantic_motion_1_phase_builder,
    VIEW3D_PT_semantic_motion_2_curve_utils,
    VIEW3D_PT_semantic_motion_3_motion_flow,
    VIEW3D_PT_semantic_motion_4_natural_motion,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    if hasattr(bpy.app, "timers") and not bpy.app.timers.is_registered(check_selection_timer):
        bpy.app.timers.register(check_selection_timer, persistent=True)


def unregister():
    if hasattr(bpy.app, "timers") and bpy.app.timers.is_registered(check_selection_timer):
        bpy.app.timers.unregister(check_selection_timer)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
