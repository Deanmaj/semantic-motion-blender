bl_info = {
    "name": "Semantic Motion - Natural Language Curve & Easing",
    "author": "Dean & Antigravity",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "Graph Editor > Sidebar > Semantic Motion, Dope Sheet, 3D Viewport (Shift+Alt+E)",
    "description": "Control Blender animation curves and easing using arbitrary natural language descriptions, descriptors, and EaseCopy",
    "warning": "",
    "doc_url": "",
    "category": "Animation",
}

# Module reloading support for development
if "bpy" in locals():
    import importlib
    if "properties" in locals():
        importlib.reload(properties)
    if "operators" in locals():
        importlib.reload(operators)
    if "ui" in locals():
        importlib.reload(ui)

import bpy
from . import properties
from . import operators
from . import ui

modules = (
    properties,
    operators,
    ui,
)


def register():
    for mod in modules:
        mod.register()


def unregister():
    for mod in reversed(modules):
        mod.unregister()


if __name__ == "__main__":
    register()
