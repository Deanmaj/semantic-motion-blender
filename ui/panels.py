"""
UI Panels for Semantic Motion Add-on.
Each section is a fully independent top-level collapsible panel within the
'Semantic Motion' N-panel tab — no nesting, no parent panel.
"""

import bpy
from ..engine.curve_analyzer import analyze_keyframe_pair
from ..operators.apply_semantic_curve import get_target_fcurves
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
        fcurves = get_target_fcurves(context)
        if not fcurves:
            return
        for fc in fcurves:
            keyframes = getattr(fc, "keyframe_points", getattr(fc, "points", []))
            if not keyframes or len(keyframes) < 2:
                continue
            selected_kps = [k for k in keyframes if getattr(k, "select_control_point", False)]
            if len(selected_kps) >= 2:
                k0, k1 = selected_kps[0], selected_kps[1]
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
                    finally:
                        properties._IS_SYNCING = False
                break
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Shared draw helpers
# ---------------------------------------------------------------------------

def draw_speed_sliders(layout, context, props):
    auto_sync_selection_to_sliders(context, props)

    row = layout.row(align=True)
    row.prop(props, "input_mode", expand=True)
    layout.prop(props, "live_update", text="Live Auto-Update", icon='AUTO')
    layout.separator(factor=0.5)

    if props.input_mode == 'PHASE_BUILDER':
        layout.label(text="Start Speed  (0% Slow \u2192 100% Fast):", icon='IPO_EASE_IN')
        snap_s = layout.row(align=True)
        snap_s.scale_y = 0.8
        for lbl, val in [("0%", 0.0), ("25%", 25.0), ("50%", 50.0), ("75%", 75.0), ("100%", 100.0)]:
            op = snap_s.operator("semantic_motion.set_tension_snap", text=lbl)
            op.target = 'START'
            op.value = val
        layout.prop(props, "start_speed", text="", slider=True)

        layout.separator(factor=0.8)

        layout.label(text="End Speed  (0% Slow \u2192 100% Fast):", icon='IPO_EASE_OUT')
        snap_e = layout.row(align=True)
        snap_e.scale_y = 0.8
        for lbl, val in [("0%", 0.0), ("25%", 25.0), ("50%", 50.0), ("75%", 75.0), ("100%", 100.0)]:
            op = snap_e.operator("semantic_motion.set_tension_snap", text=lbl)
            op.target = 'END'
            op.value = val
        layout.prop(props, "end_speed", text="", slider=True)

    layout.separator()
    row = layout.row(align=True)
    row.scale_y = 1.25
    row.operator("semantic_motion.apply_curve", text="Apply Motion to Keys", icon='CHECKMARK')


def draw_modifiers(layout, props):
    layout.prop(props, "anticipation_amount", slider=True, text="Anticipation Dip")
    layout.prop(props, "overshoot_amount", slider=True, text="Overshoot Rebound")


def draw_natural_motion(layout, props):
    layout.label(text="Natural Language Description:", icon='FONT_DATA')
    layout.prop(props, "prompt_text", text="", icon='EDITMODE_HLT')
    layout.separator(factor=0.5)
    layout.label(text="One-Click Recipes:", icon='BOOKMARKS')
    grid = layout.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=False, align=True)
    grid.operator("semantic_motion.apply_preset", text="Slow Start, Fast End",     icon='FORWARD'    ).preset_name = "slow start, fast ending"
    grid.operator("semantic_motion.apply_preset", text="Fast Start, Slow End",     icon='BACK'       ).preset_name = "fast start, slow ending"
    grid.operator("semantic_motion.apply_preset", text="Smooth S-Curve",           icon='SPHERE'     ).preset_name = "slow start, slow ending"
    grid.operator("semantic_motion.apply_preset", text="Anticipate \u2192 Overshoot", icon='IPO_BACK').preset_name = "anticipation to overshoot"
    grid.operator("semantic_motion.apply_preset", text="Explosive Blast",          icon='LIGHT_SUN'  ).preset_name = "explosive with overshoot"
    grid.operator("semantic_motion.apply_preset", text="Physics Bounce (30)",      icon='IPO_BOUNCE' ).preset_name = "drop and bounce with 30 rebounds"
    grid.operator("semantic_motion.apply_preset", text="Elastic Wobble",           icon='IPO_ELASTIC').preset_name = "elastic wobble"
    grid.operator("semantic_motion.apply_preset", text="Linear Constant",          icon='IPO_LINEAR' ).preset_name = "linear"
    layout.separator()
    row = layout.row(align=True)
    row.scale_y = 1.25
    row.operator("semantic_motion.apply_curve", text="Apply Motion to Keys", icon='CHECKMARK')


def draw_curve_utilities(layout, props):
    layout.prop(props, "target_scope", text="Scope")
    layout.separator(factor=0.5)
    row = layout.row(align=True)
    row.operator("semantic_motion.copy_ease",  text="Copy Ease",  icon='COPYDOWN')
    row.operator("semantic_motion.paste_ease", text="Paste Ease", icon='PASTEDOWN').mode = 'BOTH'
    if props.has_clipboard:
        layout.operator("semantic_motion.paste_ease", text="Paste Inverted", icon='ARROW_LEFTRIGHT').mode = 'INVERT'
    layout.separator(factor=0.5)
    layout.label(text="Motion Flow:", icon='INFO')
    layout.label(text=props.parsed_description)


# ===========================================================================
#  GRAPH EDITOR — 4 independent top-level panels, same category tab
# ===========================================================================

class GRAPH_EDITOR_PT_SM_SpeedSliders(bpy.types.Panel):
    bl_space_type  = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Speed Sliders'
    bl_order       = 0

    def draw(self, context):
        draw_speed_sliders(self.layout, context, context.scene.semantic_motion)


class GRAPH_EDITOR_PT_SM_Modifiers(bpy.types.Panel):
    bl_space_type  = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Modifiers (Dip & Rebound)'
    bl_order       = 1
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_modifiers(self.layout, context.scene.semantic_motion)


class GRAPH_EDITOR_PT_SM_NaturalMotion(bpy.types.Panel):
    bl_space_type  = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Natural Motion Descriptor'
    bl_order       = 2
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_natural_motion(self.layout, context.scene.semantic_motion)


class GRAPH_EDITOR_PT_SM_CurveUtils(bpy.types.Panel):
    bl_space_type  = 'GRAPH_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Curve Utilities'
    bl_order       = 3
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_curve_utilities(self.layout, context.scene.semantic_motion)


# ===========================================================================
#  DOPE SHEET — 4 independent top-level panels
# ===========================================================================

class DOPESHEET_PT_SM_SpeedSliders(bpy.types.Panel):
    bl_space_type  = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Speed Sliders'
    bl_order       = 0

    def draw(self, context):
        draw_speed_sliders(self.layout, context, context.scene.semantic_motion)


class DOPESHEET_PT_SM_Modifiers(bpy.types.Panel):
    bl_space_type  = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Modifiers (Dip & Rebound)'
    bl_order       = 1
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_modifiers(self.layout, context.scene.semantic_motion)


class DOPESHEET_PT_SM_NaturalMotion(bpy.types.Panel):
    bl_space_type  = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Natural Motion Descriptor'
    bl_order       = 2
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_natural_motion(self.layout, context.scene.semantic_motion)


class DOPESHEET_PT_SM_CurveUtils(bpy.types.Panel):
    bl_space_type  = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Curve Utilities'
    bl_order       = 3
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_curve_utilities(self.layout, context.scene.semantic_motion)


# ===========================================================================
#  3D VIEWPORT — 4 independent top-level panels
# ===========================================================================

class VIEW3D_PT_SM_SpeedSliders(bpy.types.Panel):
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Speed Sliders'
    bl_order       = 0

    def draw(self, context):
        draw_speed_sliders(self.layout, context, context.scene.semantic_motion)


class VIEW3D_PT_SM_Modifiers(bpy.types.Panel):
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Modifiers (Dip & Rebound)'
    bl_order       = 1
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_modifiers(self.layout, context.scene.semantic_motion)


class VIEW3D_PT_SM_NaturalMotion(bpy.types.Panel):
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Natural Motion Descriptor'
    bl_order       = 2
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_natural_motion(self.layout, context.scene.semantic_motion)


class VIEW3D_PT_SM_CurveUtils(bpy.types.Panel):
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = 'Semantic Motion'
    bl_label       = 'Curve Utilities'
    bl_order       = 3
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_curve_utilities(self.layout, context.scene.semantic_motion)


# ===========================================================================
#  Registration
# ===========================================================================

classes = (
    # Graph Editor
    GRAPH_EDITOR_PT_SM_SpeedSliders,
    GRAPH_EDITOR_PT_SM_Modifiers,
    GRAPH_EDITOR_PT_SM_NaturalMotion,
    GRAPH_EDITOR_PT_SM_CurveUtils,
    # Dope Sheet
    DOPESHEET_PT_SM_SpeedSliders,
    DOPESHEET_PT_SM_Modifiers,
    DOPESHEET_PT_SM_NaturalMotion,
    DOPESHEET_PT_SM_CurveUtils,
    # 3D Viewport
    VIEW3D_PT_SM_SpeedSliders,
    VIEW3D_PT_SM_Modifiers,
    VIEW3D_PT_SM_NaturalMotion,
    VIEW3D_PT_SM_CurveUtils,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
