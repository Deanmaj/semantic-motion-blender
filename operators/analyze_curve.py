"""
Operator: Analyze Selected Keyframes into English Motion Descriptors.
Purely read-only: inspects selected handles and updates UI fields without modifying any curves.
"""

import bpy
from ..engine.curve_analyzer import analyze_keyframe_pair
from .apply_semantic_curve import get_target_fcurves
from .. import properties


class SM_OT_AnalyzeCurve(bpy.types.Operator):
    """Analyze the selected keyframe curve and generate an English motion description"""
    bl_idname = "semantic_motion.analyze_curve"
    bl_label = "Describe Selected Curve"
    bl_description = "Reads the handles of the selected keyframe curve and describes it without modifying the curve"
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.semantic_motion
        fcurves = get_target_fcurves(context)

        if not fcurves:
            self.report({'WARNING'}, "No F-Curves found to analyze.")
            return {'CANCELLED'}

        analyzed = False
        for fc in fcurves:
            keyframes = getattr(fc, "keyframe_points", getattr(fc, "points", []))
            if not keyframes:
                continue
            selected_indices = [i for i, k in enumerate(keyframes) if getattr(k, "select_control_point", False)]

            if len(selected_indices) >= 2:
                i0 = selected_indices[0]
                i1 = selected_indices[1]
                res = analyze_keyframe_pair(keyframes[i0], keyframes[i1])

                # Lock live updates while reading to guarantee zero curve modification
                properties._IS_SYNCING = True
                try:
                    props.start_speed = res.get("start_speed", 20.0)
                    props.end_speed = res.get("end_speed", 80.0)
                    props.anticipation_amount = res.get("anticipation_amount", 0.0)
                    props.overshoot_amount = res.get("overshoot_amount_pct", 0.0)
                    props.parsed_description = res["description"]
                    props.prompt_text = res["prompt_suggestion"]
                finally:
                    properties._IS_SYNCING = False

                analyzed = True
                self.report({'INFO'}, f"Analyzed Curve: {res['description']}")
                break

        if not analyzed:
            self.report({'WARNING'}, "Please select at least 2 adjacent keyframes to describe.")
            return {'CANCELLED'}

        return {'FINISHED'}


classes = (
    SM_OT_AnalyzeCurve,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
