"""
UI Panels for Semantic Motion Add-on.
Strict 4-tab collapsible layout:
  1. Phase Builder (Speed Sliders, Live Link, Live Property widget with Eye Solo & Auto-Key)
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
# Persistent tracked pair — survives handle grabs that deselect control points
_TRACKED_FC = None          # The fcurve object
_TRACKED_K0_FRAME = None    # Frame number of first keyframe
_TRACKED_K1_FRAME = None    # Frame number of second keyframe


# ---------------------------------------------------------------------------
# Auto-sync: Evaluates strictly when 2 keyframes are selected
# ---------------------------------------------------------------------------

def _find_keyframe_at_frame(fc, frame):
    """Find a keyframe on the given fcurve at the given frame number (±0.5 tolerance)."""
    keyframes = getattr(fc, "keyframe_points", getattr(fc, "points", []))
    for k in keyframes:
        if abs(k.co[0] - frame) < 0.5:
            return k
    return None


def sync_selected_keyframe_pair(context, props):
    """
    Reads selected keyframes and automatically updates Start & End speed sliders,
    Anticipation Dip, Overshoot Rebound, and Motion Flow.

    When 2+ keyframes are selected, uses them as the active pair AND stores them.
    When fewer are selected (e.g. user is dragging a bezier handle), falls back
    to the stored pair and keeps updating from their current handle positions.
    Only clears the stored pair when a genuinely new pair is selected.
    """
    global _LAST_SELECTION_SIG, _TRACKED_FC, _TRACKED_K0_FRAME, _TRACKED_K1_FRAME
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

        # --- 1. Try to find a new pair from current selection ---
        k0 = None
        k1 = None
        active_fc = None

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

            if len(selected_kps) >= 2:
                selected_kps = sorted(selected_kps, key=lambda kp: kp.co[0])
                k0 = selected_kps[0]
                k1 = selected_kps[-1]
                if k0 != k1:
                    active_fc = fc
                    # Store this as the tracked pair
                    _TRACKED_FC = fc
                    _TRACKED_K0_FRAME = round(k0.co[0], 2)
                    _TRACKED_K1_FRAME = round(k1.co[0], 2)
                    break

        # --- 2. Fall back to tracked pair if no new selection found ---
        if not k0 or not k1:
            if _TRACKED_FC is not None and _TRACKED_K0_FRAME is not None:
                try:
                    k0 = _find_keyframe_at_frame(_TRACKED_FC, _TRACKED_K0_FRAME)
                    k1 = _find_keyframe_at_frame(_TRACKED_FC, _TRACKED_K1_FRAME)
                    active_fc = _TRACKED_FC
                except Exception:
                    k0 = k1 = None

        if not k0 or not k1 or k0 == k1:
            return

        # --- 3. Build signature and update if changed ---
        sig = (
            getattr(active_fc, "data_path", ""),
            getattr(active_fc, "array_index", 0),
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
    # 1. Direct context attributes (Graph Editor / Dope Sheet provide these)
    for attr in ("active_editable_fcurve", "selected_editable_fcurves"):
        val = getattr(context, attr, None)
        if val:
            if hasattr(val, "__iter__"):
                for item in val:
                    if item:
                        return item
            else:
                return val

    # 2. Search active object's action
    obj = getattr(context, "active_object", None)
    if obj and getattr(obj, "animation_data", None) and getattr(obj.animation_data, "action", None):
        from ..operators.apply_semantic_curve import extract_curves_from_action
        all_curves = extract_curves_from_action(obj.animation_data.action)
        for fc in all_curves:
            if getattr(fc, "select", False):
                return fc
            kps = getattr(fc, "keyframe_points", getattr(fc, "points", []))
            if any(getattr(k, "select_control_point", False) for k in kps):
                return fc
        if all_curves:
            return all_curves[0]

    return None


def _iter_all_animated_ids():
    """
    Yield (id_block, id_type_str) for every Blender ID data block that has
    animation_data with an action. This covers objects, materials, worlds,
    cameras, lights, node trees, meshes, shape keys, scenes, etc.
    """
    id_collections = [
        (bpy.data.objects,     'OBJECT'),
        (bpy.data.materials,   'MATERIAL'),
        (bpy.data.worlds,      'WORLD'),
        (bpy.data.cameras,     'CAMERA'),
        (bpy.data.lights,      'LIGHT'),
        (bpy.data.node_groups, 'NODETREE'),
        (bpy.data.meshes,      'MESH'),
        (bpy.data.curves,      'CURVE'),
        (bpy.data.armatures,   'ARMATURE'),
        (bpy.data.lattices,    'LATTICE'),
        (bpy.data.scenes,      'SCENE'),
    ]
    if hasattr(bpy.data, 'speakers'):
        id_collections.append((bpy.data.speakers, 'SPEAKER'))

    for collection, id_type in id_collections:
        try:
            for block in collection:
                anim_data = getattr(block, "animation_data", None)
                if anim_data and getattr(anim_data, "action", None):
                    yield block, id_type
        except Exception:
            pass

    # Inline node trees (world, material, light) — not in bpy.data.node_groups
    for world in bpy.data.worlds:
        nt = getattr(world, "node_tree", None)
        if nt:
            anim_data = getattr(nt, "animation_data", None)
            if anim_data and getattr(anim_data, "action", None):
                yield nt, 'WORLD_NODETREE'

    for mat in bpy.data.materials:
        nt = getattr(mat, "node_tree", None)
        if nt:
            anim_data = getattr(nt, "animation_data", None)
            if anim_data and getattr(anim_data, "action", None):
                yield nt, 'MATERIAL_NODETREE'

    for light in bpy.data.lights:
        nt = getattr(light, "node_tree", None)
        if nt:
            anim_data = getattr(nt, "animation_data", None)
            if anim_data and getattr(anim_data, "action", None):
                yield nt, 'LIGHT_NODETREE'

    # Shape keys live on mesh/curve data
    if hasattr(bpy.data, 'shape_keys'):
        try:
            for sk in bpy.data.shape_keys:
                anim_data = getattr(sk, "animation_data", None)
                if anim_data and getattr(anim_data, "action", None):
                    yield sk, 'KEY'
        except Exception:
            pass


def _find_fcurve_owner(fc):
    """
    Given an F-Curve, find the ID data block that owns it by searching all
    animated data blocks. Returns (id_block, id_type_str) or (None, None).
    """
    from ..operators.apply_semantic_curve import extract_curves_from_action
    for block, id_type in _iter_all_animated_ids():
        action = block.animation_data.action
        curves = extract_curves_from_action(action)
        for c in curves:
            if c == fc:
                return block, id_type
    return None, None


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


def _resolve_fcurve_prop(fc, id_block):
    """
    Resolve an F-Curve's data_path against a known ID data block to get:
    (owner, prop_attr_name, channel_label).
    Returns (None, None, None) on failure.
    """
    data_path = fc.data_path

    try:
        if "." in data_path:
            owner_path, prop_attr = data_path.rsplit(".", 1)
            try:
                owner = id_block.path_resolve(owner_path)
            except Exception:
                owner = id_block
                prop_attr = data_path
        else:
            owner = id_block
            prop_attr = data_path

        if "[" in prop_attr:
            prop_attr = prop_attr[:prop_attr.index("[")]

        channel_label = _fcurve_channel_label(fc, owner)
        return owner, prop_attr, channel_label
    except Exception:
        return None, None, None


def draw_live_property(layout, context):
    """
    Render the live value of the active fcurve's property as a native Blender
    widget (number field, dropdown, colour, etc.) with Eye Solo & Auto-Key buttons.
    Supports properties on any data block: objects, materials, worlds, cameras,
    lights, node trees, shape keys, etc.
    """
    box = layout.box()

    fc = _get_active_fcurve(context)

    if not fc:
        box.label(text="Select an F-Curve Channel", icon='INFO')
        return

    data_path = fc.data_path
    array_index = fc.array_index

    # --- Discover the owner ID data block ---
    # 1. Try active object first (most common case)
    obj = getattr(context, "active_object", None)
    id_block = None
    id_type = ''

    if obj:
        # Try direct resolution on the object
        try:
            if "." in data_path:
                obj.path_resolve(data_path.rsplit(".", 1)[0])
            else:
                obj.path_resolve(data_path)
            id_block = obj
            id_type = 'OBJECT'
        except Exception:
            pass

        # Try object's mesh/curve data (shape keys, modifiers)
        if not id_block and getattr(obj, "data", None):
            try:
                obj_data = obj.data
                if "." in data_path:
                    obj_data.path_resolve(data_path.rsplit(".", 1)[0])
                else:
                    obj_data.path_resolve(data_path)
                id_block = obj_data
                id_type = type(obj_data).__name__.upper()
            except Exception:
                pass

            # Try object data's node tree (light/camera node trees)
            if not id_block:
                nt = getattr(obj.data, "node_tree", None)
                if nt:
                    try:
                        if "." in data_path:
                            nt.path_resolve(data_path.rsplit(".", 1)[0])
                        else:
                            nt.path_resolve(data_path)
                        id_block = nt
                        id_type = 'LIGHT_NODETREE'
                    except Exception:
                        pass

        # Try object's material slots and their node trees
        if not id_block:
            for slot in getattr(obj, "material_slots", []):
                mat = getattr(slot, "material", None)
                if mat:
                    try:
                        if "." in data_path:
                            mat.path_resolve(data_path.rsplit(".", 1)[0])
                        else:
                            mat.path_resolve(data_path)
                        id_block = mat
                        id_type = 'MATERIAL'
                        break
                    except Exception:
                        pass
                    # Try material's node tree
                    nt = getattr(mat, "node_tree", None)
                    if nt:
                        try:
                            if "." in data_path:
                                nt.path_resolve(data_path.rsplit(".", 1)[0])
                            else:
                                nt.path_resolve(data_path)
                            id_block = nt
                            id_type = 'MATERIAL_NODETREE'
                            break
                        except Exception:
                            pass

    # 2. Try world and world's node tree
    if not id_block:
        world = getattr(context.scene, "world", None)
        if world:
            try:
                if "." in data_path:
                    world.path_resolve(data_path.rsplit(".", 1)[0])
                else:
                    world.path_resolve(data_path)
                id_block = world
                id_type = 'WORLD'
            except Exception:
                pass
            # Try world's node tree (Easy HDRI, etc.)
            if not id_block:
                nt = getattr(world, "node_tree", None)
                if nt:
                    try:
                        if "." in data_path:
                            nt.path_resolve(data_path.rsplit(".", 1)[0])
                        else:
                            nt.path_resolve(data_path)
                        id_block = nt
                        id_type = 'WORLD_NODETREE'
                    except Exception:
                        pass

    # 3. Try scene
    if not id_block:
        try:
            scene = context.scene
            if "." in data_path:
                scene.path_resolve(data_path.rsplit(".", 1)[0])
            else:
                scene.path_resolve(data_path)
            id_block = scene
            id_type = 'SCENE'
        except Exception:
            pass

    # 4. Exhaustive search across all animated data blocks
    if not id_block:
        id_block, id_type = _find_fcurve_owner(fc)

    # 5. Last resort: active object
    if not id_block:
        id_block = obj
        id_type = 'OBJECT'

    if not id_block:
        box.label(text="Select an F-Curve Channel", icon='INFO')
        return

    try:
        owner, prop_attr, channel_label = _resolve_fcurve_prop(fc, id_block)

        if not owner or not prop_attr:
            box.label(text=data_path, icon='PROPERTIES')
            return

        # Check isolation / solo status of curves
        all_curves = []
        # Gather curves from the id_block's action
        if getattr(id_block, "animation_data", None) and getattr(id_block.animation_data, "action", None):
            from ..operators.apply_semantic_curve import extract_curves_from_action
            all_curves = extract_curves_from_action(id_block.animation_data.action)
        # Also check active object if different
        if obj and obj != id_block and getattr(obj, "animation_data", None) and getattr(obj.animation_data, "action", None):
            from ..operators.apply_semantic_curve import extract_curves_from_action
            obj_curves = extract_curves_from_action(obj.animation_data.action)
            for c in obj_curves:
                if c not in all_curves:
                    all_curves.append(c)

        selected_curves = [c for c in all_curves if getattr(c, "select", False)]
        if fc not in selected_curves:
            selected_curves.append(fc)

        unselected_curves = [c for c in all_curves if c not in selected_curves]
        any_unselected_hidden = any(getattr(c, "hide", False) for c in unselected_curves) if unselected_curves else False
        target_hidden = getattr(fc, "hide", False)

        is_soloed = (not target_hidden and any_unselected_hidden)
        eye_icon = 'HIDE_OFF' if not target_hidden else 'HIDE_ON'

        # Header row: Clean channel name + Eye Solo button
        hdr = box.row(align=True)
        hdr.label(text=channel_label, icon='ANIM_DATA')

        solo_op = hdr.operator(
            "semantic_motion.toggle_curve_solo",
            text="",
            icon=eye_icon,
            depress=is_soloed,
        )
        solo_op.data_path = data_path
        solo_op.array_index = array_index

        # Live editable value widget + Key Property + Auto-Keying
        val_row = box.row(align=True)
        try:
            val_row.prop(owner, prop_attr, index=array_index, text="")
        except Exception:
            try:
                val_row.prop(owner, prop_attr, text="")
            except Exception:
                val_row.label(text=f"Frame: {context.scene.frame_current}")

        # Manual key-here button with owner identity
        key_op = val_row.operator(
            "semantic_motion.key_property",
            text="",
            icon='KEY_HLT',
        )
        key_op.data_path = data_path
        key_op.array_index = array_index
        # For inline node trees, store the parent's name (world/material/light)
        # since _resolve_owner_id needs to find bpy.data.worlds[name].node_tree etc.
        if id_type == 'WORLD_NODETREE':
            # Find which world owns this node tree
            for w in bpy.data.worlds:
                if getattr(w, "node_tree", None) == id_block:
                    key_op.owner_id_name = w.name
                    break
        elif id_type == 'MATERIAL_NODETREE':
            for m in bpy.data.materials:
                if getattr(m, "node_tree", None) == id_block:
                    key_op.owner_id_name = m.name
                    break
        elif id_type == 'LIGHT_NODETREE':
            for l in bpy.data.lights:
                if getattr(l, "node_tree", None) == id_block:
                    key_op.owner_id_name = l.name
                    break
        else:
            key_op.owner_id_name = getattr(id_block, "name", "")
        key_op.owner_id_type = id_type

        # Auto-keying toggle beside the Key Property button
        val_row.prop(
            context.scene.tool_settings,
            "use_keyframe_insert_auto",
            text="",
            icon='REC',
        )

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
        draw_curve_utilities(self.layout, context, context.scene.semantic_motion)


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
        draw_curve_utilities(self.layout, context, context.scene.semantic_motion)


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
