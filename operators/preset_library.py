"""
Operator: Quick Preset Recipes and Motion Library.
"""

import bpy
from .apply_semantic_curve import SM_OT_ApplySemanticCurve


class SM_OT_ApplyPreset(bpy.types.Operator):
    """Apply a curated motion recipe instantly"""
    bl_idname = "semantic_motion.apply_preset"
    bl_label = "Apply Motion Recipe"
    bl_description = "Applies a predefined motion curve recipe to selected keyframes"
    bl_options = {'REGISTER', 'UNDO'}

    preset_name: bpy.props.StringProperty(
        name="Preset Name",
        description="Name of the motion recipe",
        default="slow start, fast ending"
    )

    def execute(self, context):
        props = context.scene.semantic_motion
        props.prompt_text = self.preset_name
        # Apply curve immediately
        bpy.ops.semantic_motion.apply_curve(custom_prompt=self.preset_name)
        return {'FINISHED'}


classes = (
    SM_OT_ApplyPreset,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
