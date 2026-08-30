"""
Operator: Apply Semantic Motion Curve to Keyframes.
Supports Motion Tools Pro dual sliders (0-100%), prompt text, and absolute curve override.
"""

import bpy
from ..engine.semantic_parser import parse_motion_prompt, MotionProfile
from ..engine.bezier_math import (
    profile_to_normalized_bezier,
    motion_tools_slider_to_bezier,
    apply_bezier_to_keyframe_pair,
    NormalizedBezier
)
from ..engine.physics_generator import apply_physics_to_fcurve


def extract_curves_from_action(action):
    """Safely extracts all editable curve objects from an Action across all Blender versions (3.x, 4.x, 5.0+)."""
    if not action:
        return []

    curves = []

    # 1. Legacy F-Curves (Blender 2.80 - 4.3)
    if hasattr(action, "fcurves"):
        try:
            for fc in action.fcurves:
                if not getattr(fc, "mute", False) and not getattr(fc, "lock", False):
                    curves.append(fc)
        except Exception:
            pass

    # 2. Modern Action Curves (Blender 4.4 / 5.0+)
    if hasattr(action, "curves"):
        try:
            for fc in action.curves:
                if not getattr(fc, "mute", False) and not getattr(fc, "lock", False):
                    curves.append(fc)
        except Exception:
            pass

    # 3. Layered Actions (Blender 5.0+ Layers & Strips & Channelbags)
    if hasattr(action, "layers"):
        try:
            for layer in action.layers:
                if getattr(layer, "mute", False) or getattr(layer, "lock", False):
                    continue
                for strip in getattr(layer, "strips", []):
                    for bag in getattr(strip, "channelbags", []):
                        for c in (getattr(bag, "curves", None) or getattr(bag, "fcurves", None) or []):
                            if not getattr(c, "mute", False) and not getattr(c, "lock", False):
                                curves.append(c)
        except Exception:
            pass

    # 4. Slotted Actions (Blender 4.4 / 5.0+ Slots)
    if hasattr(action, "slots"):
        try:
            for slot in action.slots:
                for c in (getattr(slot, "curves", None) or getattr(slot, "fcurves", None) or []):
                    if not getattr(c, "mute", False) and not getattr(c, "lock", False):
                        curves.append(c)
        except Exception:
            pass

    return curves


def get_target_fcurves(context, scope: str = 'SELECTED_KEYS'):
    """Collects all relevant F-Curves from active object, pose bones, or animation editors."""
    fcurves = []

    # 1. From Graph Editor / Dope Sheet active context
    if context.area and context.area.type in ('GRAPH_EDITOR', 'DOPESHEET_EDITOR'):
        if hasattr(context, "selected_editable_fcurves") and context.selected_editable_fcurves:
            return list(context.selected_editable_fcurves)
        if hasattr(context, "editable_fcurves") and context.editable_fcurves:
            return list(context.editable_fcurves)
        if hasattr(context, "selected_fcurves") and context.selected_fcurves:
            return list(context.selected_fcurves)

    # 2. From Active Object Animation Data
    obj = context.active_object
    if obj and obj.animation_data and obj.animation_data.action:
        action_curves = extract_curves_from_action(obj.animation_data.action)
        fcurves.extend(action_curves)

    # 3. From Selected Objects Animation Data
    for selected_obj in context.selected_objects:
        if selected_obj != obj and selected_obj.animation_data and selected_obj.animation_data.action:
            action_curves = extract_curves_from_action(selected_obj.animation_data.action)
            for fc in action_curves:
                if fc not in fcurves:
                    fcurves.append(fc)

    return fcurves


def apply_motion_tools_curve_to_context(context, props) -> int:
    """
    Directly and absolutely overrides curves on selected keyframes in real time.
    Used by live slider scrubbing and operator execution.
    """
    if props.is_physics_mode:
        profile = MotionProfile(
            is_physics=True,
            physics_type=props.physics_type,
            physics_bounces=props.physics_bounces,
            physics_decay=props.physics_decay
        )
        bezier = None
    elif props.input_mode == 'PROMPT':
        profile = parse_motion_prompt(props.prompt_text)
        bezier = None if profile.is_physics else profile_to_normalized_bezier(profile)
    else:
        # Direct Speed Sliders (Left=Slow, Right=Fast)
        bezier = motion_tools_slider_to_bezier(
            start_speed=props.start_speed,
            end_speed=props.end_speed,
            anticipation=props.anticipation_amount / 100.0,
            overshoot=props.overshoot_amount / 100.0
        )
        profile = None

    fcurves = get_target_fcurves(context, scope=props.target_scope)
    if not fcurves:
        return 0

    applied_count = 0
    for fc in fcurves:
        keyframes = getattr(fc, "keyframe_points", getattr(fc, "points", []))
        if not keyframes or len(keyframes) < 2:
            continue

        selected_indices = [i for i, k in enumerate(keyframes) if getattr(k, "select_control_point", False)]

        # If no keyframes are selected on this specific curve, check scope
        if not selected_indices:
            if props.target_scope == 'ALL_SELECTED_FCURVES' and getattr(fc, "select", False):
                selected_indices = list(range(len(keyframes)))
            else:
                # Do NOT touch curves that have no selected keyframes!
                continue

        # Apply to consecutive selected keyframe pairs (Absolute Override)
        if len(selected_indices) >= 2:
            for idx in range(len(selected_indices) - 1):
                i0 = selected_indices[idx]
                i1 = selected_indices[idx + 1]
                if i1 - i0 >= 1:
                    if profile and profile.is_physics:
                        apply_physics_to_fcurve(fc, i0, i1, profile)
                    elif bezier:
                        apply_bezier_to_keyframe_pair(keyframes[i0], keyframes[i1], bezier, fcurve=fc)
                    applied_count += 1
        elif len(selected_indices) == 1 and bezier:
            i0 = selected_indices[0]
            if i0 < len(keyframes) - 1:
                apply_bezier_to_keyframe_pair(keyframes[i0], keyframes[i0 + 1], bezier, fcurve=fc)
                applied_count += 1
            elif i0 > 0:
                apply_bezier_to_keyframe_pair(keyframes[i0 - 1], keyframes[i0], bezier, fcurve=fc)
                applied_count += 1

        if hasattr(fc, "update"):
            fc.update()

    return applied_count


class SM_OT_ApplySemanticCurve(bpy.types.Operator):
    """Apply the semantic motion curve to selected keyframes"""
    bl_idname = "semantic_motion.apply_curve"
    bl_label = "Apply Motion Curve"
    bl_description = "Evaluates the motion description and reshapes keyframe curve handles"
    bl_options = {'REGISTER', 'UNDO'}

    custom_prompt: bpy.props.StringProperty(
        name="Custom Prompt",
        description="Override prompt to apply directly",
        default=""
    )

    force_mode: bpy.props.StringProperty(
        name="Force Mode",
        description="Override input_mode for this execution: PHASE_BUILDER or PROMPT",
        default=""
    )

    def execute(self, context):
        props = context.scene.semantic_motion
        if self.custom_prompt:
            props.prompt_text = self.custom_prompt

        original_mode = props.input_mode
        if self.force_mode in ('PHASE_BUILDER', 'PROMPT'):
            props.input_mode = self.force_mode

        count = apply_motion_tools_curve_to_context(context, props)

        if self.force_mode:
            props.input_mode = original_mode

        if count > 0:
            self.report({'INFO'}, f"Applied motion curve to {count} interval(s).")
            return {'FINISHED'}
        else:
            self.report({'INFO'}, "No keyframes selected. Please select the keyframe(s) or channel(s) you want to modify.")
            return {'CANCELLED'}


class SM_OT_SetSliderSnap(bpy.types.Operator):
    """Snap Start or End speed slider to preset percentage"""
    bl_idname = "semantic_motion.set_tension_snap"
    bl_label = "Snap Speed"
    bl_description = "Quickly sets the slider speed value"
    bl_options = {'REGISTER', 'UNDO'}

    target: bpy.props.EnumProperty(
        items=[('START', "Start", ""), ('END', "End", ""), ('BOTH', "Both", "")],
        default='START'
    )
    value: bpy.props.FloatProperty(name="Value", default=50.0)

    def execute(self, context):
        props = context.scene.semantic_motion
        if self.target == 'START':
            props.start_speed = self.value
        elif self.target == 'END':
            props.end_speed = self.value
        elif self.target == 'BOTH':
            props.start_speed = self.value
            props.end_speed = self.value
        return {'FINISHED'}


class SM_OT_KeyProperty(bpy.types.Operator):
    """Insert a keyframe for the active fcurve property at the current frame"""
    bl_idname = "semantic_motion.key_property"
    bl_label = "Key Property"
    bl_description = "Insert a keyframe for this property at the current timeline position"
    bl_options = {'REGISTER', 'UNDO'}

    data_path: bpy.props.StringProperty(name="Data Path", default="")
    array_index: bpy.props.IntProperty(name="Array Index", default=-1)
    owner_id_name: bpy.props.StringProperty(name="Owner ID Name", default="")
    owner_id_type: bpy.props.StringProperty(name="Owner ID Type", default="")

    def execute(self, context):
        if not self.data_path:
            self.report({'WARNING'}, "No data path specified.")
            return {'CANCELLED'}

        frame = context.scene.frame_current

        # 1. Try resolving via stored owner identity
        owner = _resolve_owner_id(self.owner_id_type, self.owner_id_name)

        # 2. Fallback: try active object
        if not owner:
            owner = context.active_object

        if not owner:
            self.report({'WARNING'}, "No owner data block found.")
            return {'CANCELLED'}

        try:
            owner.keyframe_insert(
                data_path=self.data_path,
                index=self.array_index,
                frame=frame
            )
            self.report({'INFO'}, f"Keyframe inserted at frame {frame}.")
            return {'FINISHED'}
        except Exception:
            # Property may not be an array (enums, booleans, single floats) —
            # retry without index
            try:
                owner.keyframe_insert(
                    data_path=self.data_path,
                    frame=frame
                )
                self.report({'INFO'}, f"Keyframe inserted at frame {frame}.")
                return {'FINISHED'}
            except Exception as e:
                self.report({'ERROR'}, f"Could not insert keyframe: {e}")
                return {'CANCELLED'}


def _resolve_owner_id(id_type, id_name):
    """Resolve a Blender ID data block by type string and name."""
    if not id_type or not id_name:
        return None
    type_map = {
        'OBJECT': bpy.data.objects,
        'MESH': bpy.data.meshes,
        'MATERIAL': bpy.data.materials,
        'WORLD': bpy.data.worlds,
        'CAMERA': bpy.data.cameras,
        'LIGHT': bpy.data.lights,
        'CURVE': bpy.data.curves,
        'ARMATURE': bpy.data.armatures,
        'LATTICE': bpy.data.lattices,
        'SPEAKER': bpy.data.speakers,
        'SCENE': bpy.data.scenes,
        'NODETREE': bpy.data.node_groups,
        'KEY': bpy.data.shape_keys if hasattr(bpy.data, 'shape_keys') else None,
        'PARTICLE': bpy.data.particles if hasattr(bpy.data, 'particles') else None,
    }
    collection = type_map.get(id_type)
    if collection is not None:
        return collection.get(id_name)
    return None


class SM_OT_ToggleCurveSolo(bpy.types.Operator):
    """Solo / Isolate the selected F-Curves (hide all other curves, or unhide all if already isolated)"""
    bl_idname = "semantic_motion.toggle_curve_solo"
    bl_label = "Solo Curve Graph"
    bl_description = "Solo/Isolate selected curve(s) in the Graph Editor (hide other curves, or unhide all)"
    bl_options = {'REGISTER', 'UNDO'}

    data_path: bpy.props.StringProperty(name="Data Path", default="")
    array_index: bpy.props.IntProperty(name="Array Index", default=-1)

    def execute(self, context):
        obj = context.active_object
        if not obj or not getattr(obj, "animation_data", None) or not getattr(obj.animation_data, "action", None):
            self.report({'WARNING'}, "No active animation data found.")
            return {'CANCELLED'}

        all_curves = extract_curves_from_action(obj.animation_data.action)
        if not all_curves:
            self.report({'WARNING'}, "No F-Curves found.")
            return {'CANCELLED'}

        # 1. Collect all explicitly selected curves
        selected_curves = [fc for fc in all_curves if getattr(fc, "select", False)]

        # Also find target curve from data_path if specified
        target_curve = None
        if self.data_path:
            for fc in all_curves:
                if getattr(fc, "data_path", "") == self.data_path and getattr(fc, "array_index", -1) == self.array_index:
                    target_curve = fc
                    break

        if not target_curve:
            target_curve = getattr(context, "active_editable_fcurve", None)

        if target_curve and target_curve not in selected_curves:
            selected_curves.append(target_curve)

        if not selected_curves and all_curves:
            selected_curves = [all_curves[0]]

        unselected_curves = [fc for fc in all_curves if fc not in selected_curves]
        all_selected_visible = all(not getattr(fc, "hide", False) for fc in selected_curves)
        any_unselected_hidden = any(getattr(fc, "hide", False) for fc in unselected_curves) if unselected_curves else False

        if all_selected_visible and any_unselected_hidden:
            # Already soloed -> Un-hide ALL curves (re-open everything)
            for fc in all_curves:
                fc.hide = False
            self.report({'INFO'}, "Removed curve isolation (all curves visible).")
        else:
            # Isolate all selected curves -> Make selected visible, hide unselected
            for fc in selected_curves:
                fc.hide = False
            for fc in unselected_curves:
                fc.hide = True
            count = len(selected_curves)
            self.report({'INFO'}, f"Soloed {count} selected curve{'s' if count != 1 else ''}.")

        # Tag editors for redraw
        for area in getattr(context.screen, "areas", []):
            if area.type in ('GRAPH_EDITOR', 'DOPESHEET_EDITOR', 'VIEW_3D'):
                area.tag_redraw()

        return {'FINISHED'}


classes = (
    SM_OT_ApplySemanticCurve,
    SM_OT_SetSliderSnap,
    SM_OT_KeyProperty,
    SM_OT_ToggleCurveSolo,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

