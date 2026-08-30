"""
Pie Menu for Semantic Motion Add-on.
Enables rapid keyframe motion selection via hotkey (default Shift+Alt+E).
"""

import bpy


class SM_MT_PieMenu(bpy.types.Menu):
    bl_label = "Semantic Motion Recipes"
    bl_idname = "SM_MT_pie_menu"

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()

        # 4 Cardinal directions (Left, Right, Bottom, Top)
        # 1. Left (WEST): Slow Start, Fast End
        op = pie.operator("semantic_motion.apply_preset", text="Slow Start, Fast End", icon='FORWARD')
        op.preset_name = "slow start, fast ending"

        # 2. Right (EAST): Fast Start, Slow End
        op = pie.operator("semantic_motion.apply_preset", text="Fast Start, Slow End", icon='BACK')
        op.preset_name = "fast start, slow ending"

        # 3. Bottom (SOUTH): Anticipation -> Overshoot
        op = pie.operator("semantic_motion.apply_preset", text="Anticipate \u2192 Overshoot", icon='IPO_BACK')
        op.preset_name = "anticipation to overshoot"

        # 4. Top (NORTH): Snappy UI Pop
        op = pie.operator("semantic_motion.apply_preset", text="Snappy Pop", icon='SPHERE')
        op.preset_name = "snappy"

        # 4 Diagonals (NW, NE, SW, SE)
        # 5. Top-Left (NW): Explosive Blast
        op = pie.operator("semantic_motion.apply_preset", text="Explosive Blast", icon='LIGHT_SUN')
        op.preset_name = "explosive with overshoot"

        # 6. Top-Right (NE): Elastic Wobble
        op = pie.operator("semantic_motion.apply_preset", text="Elastic Wobble", icon='IPO_ELASTIC')
        op.preset_name = "elastic wobble"

        # 7. Bottom-Left (SW): Physics Bounce
        op = pie.operator("semantic_motion.apply_preset", text="Physics Bounce", icon='IPO_BOUNCE')
        op.preset_name = "bounce"

        # 8. Bottom-Right (SE): Pure Linear
        op = pie.operator("semantic_motion.apply_preset", text="Linear Constant", icon='IPO_LINEAR')
        op.preset_name = "linear"


addon_keymaps = []


def register_keymaps():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return

    # Add to Graph Editor, Dopesheet, and 3D View
    for space_type in ('Graph Editor', 'Dopesheet', '3D View'):
        km = kc.keymaps.new(name=space_type, space_type='EMPTY')
        kmi = km.keymap_items.new("wm.call_menu_pie", 'E', 'PRESS', shift=True, alt=True)
        kmi.properties.name = "SM_MT_pie_menu"
        addon_keymaps.append((km, kmi))


def unregister_keymaps():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()


classes = (
    SM_MT_PieMenu,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    register_keymaps()


def unregister():
    unregister_keymaps()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
