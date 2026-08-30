"""
UI Package Initialization.
"""

try:
    import bpy
    from . import panels
    from . import pie_menu

    modules = (
        panels,
        pie_menu,
    )

    def register():
        for mod in modules:
            mod.register()

    def unregister():
        for mod in reversed(modules):
            mod.unregister()

except ImportError:
    # Running in standalone/headless test environment without bpy
    def register():
        pass

    def unregister():
        pass
