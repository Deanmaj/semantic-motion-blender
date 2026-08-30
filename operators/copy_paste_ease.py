"""
Operator: EaseCopy & EasePaste for Blender F-Curves.
Allows copying normalized Bezier easing curve shapes from any keyframe pair
and pasting them to any other keyframe intervals across channels and objects.
"""

import bpy
from .apply_semantic_curve import get_target_fcurves
from ..engine.bezier_math import NormalizedBezier, apply_bezier_to_keyframe_pair


class SM_OT_CopyEase(bpy.types.Operator):
    """Copy normalized easing values from selected keyframe pair"""
    bl_idname = "semantic_motion.copy_ease"
    bl_label = "Copy Easing"
    bl_description = "Copies the normalized Bezier easing curve handles from the selected keyframe interval"
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.semantic_motion
        fcurves = get_target_fcurves(context)

        if not fcurves:
            self.report({'WARNING'}, "No active F-Curves found.")
            return {'CANCELLED'}

        copied = False
        for fc in fcurves:
            keyframes = getattr(fc, "keyframe_points", getattr(fc, "points", []))
            if not keyframes:
                continue
            selected = [k for k in keyframes if getattr(k, "select_control_point", False)]

            if len(selected) >= 2:
                k0 = selected[0]
                k1 = selected[1]
                dt = k1.co[0] - k0.co[0]
                dv = k1.co[1] - k0.co[1]

                if abs(dt) < 1e-5:
                    continue

                x1 = (k0.handle_right[0] - k0.co[0]) / dt
                x2 = (k1.handle_left[0] - k0.co[0]) / dt

                if abs(dv) > 1e-5:
                    y1 = (k0.handle_right[1] - k0.co[1]) / dv
                    y2 = (k1.handle_left[1] - k0.co[1]) / dv
                else:
                    y1 = 0.0
                    y2 = 1.0

                props.clipboard_handles = (x1, y1, x2, y2)
                props.has_clipboard = True
                props.clipboard_description = f"Handles: ({x1:.2f}, {y1:.2f}) \u2192 ({x2:.2f}, {y2:.2f})"
                copied = True
                self.report({'INFO'}, f"Copied Ease Curve: {props.clipboard_description}")
                break

        if not copied:
            self.report({'WARNING'}, "Please select at least 2 keyframes to copy easing from.")
            return {'CANCELLED'}

        return {'FINISHED'}


class SM_OT_PasteEase(bpy.types.Operator):
    """Paste copied easing values to target keyframes"""
    bl_idname = "semantic_motion.paste_ease"
    bl_label = "Paste Easing"
    bl_description = "Pastes copied easing curve to selected keyframes"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="Paste Mode",
        items=[
            ('BOTH', "Paste Both (In & Out)", "Applies the complete curve shape"),
            ('IN_ONLY', "Paste In-Ease Only", "Applies only incoming handle easing"),
            ('OUT_ONLY', "Paste Out-Ease Only", "Applies only outgoing handle easing"),
            ('INVERT', "Paste Inverted / Flipped", "Flips the curve horizontally and vertically"),
        ],
        default='BOTH'
    )

    def execute(self, context):
        props = context.scene.semantic_motion
        if not props.has_clipboard:
            self.report({'WARNING'}, "No easing copied to clipboard yet. Select 2 keyframes and click 'Copy Ease'.")
            return {'CANCELLED'}

        x1, y1, x2, y2 = props.clipboard_handles

        if self.mode == 'INVERT':
            # Flipped normalized bezier: P1' = (1 - x2, 1 - y2), P2' = (1 - x1, 1 - y1)
            bezier = NormalizedBezier(x1=1.0 - x2, y1=1.0 - y2, x2=1.0 - x1, y2=1.0 - y1)
        else:
            bezier = NormalizedBezier(x1=x1, y1=y1, x2=x2, y2=y2)

        fcurves = get_target_fcurves(context, scope=props.target_scope)
        if not fcurves:
            self.report({'WARNING'}, "No active or editable F-Curves found.")
            return {'CANCELLED'}

        applied_count = 0
        for fc in fcurves:
            keyframes = getattr(fc, "keyframe_points", getattr(fc, "points", []))
            if not keyframes:
                continue
            selected_indices = [i for i, k in enumerate(keyframes) if getattr(k, "select_control_point", False)]

            if len(selected_indices) >= 2:
                for idx in range(len(selected_indices) - 1):
                    i0 = selected_indices[idx]
                    i1 = selected_indices[idx + 1]
                    if i1 - i0 >= 1:
                        apply_bezier_to_keyframe_pair(keyframes[i0], keyframes[i1], bezier, fcurve=fc)
                        applied_count += 1
            if hasattr(fc, "update"):
                fc.update()

        if applied_count > 0:
            self.report({'INFO'}, f"Pasted easing to {applied_count} interval(s).")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "Please select target keyframes to paste easing.")
            return {'CANCELLED'}


classes = (
    SM_OT_CopyEase,
    SM_OT_PasteEase,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
