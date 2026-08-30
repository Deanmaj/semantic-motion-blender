"""
Operators package initialization.
"""

from . import apply_semantic_curve
from . import analyze_curve
from . import preset_library
from . import copy_paste_ease

modules = (
    apply_semantic_curve,
    analyze_curve,
    preset_library,
    copy_paste_ease,
)


def register():
    for mod in modules:
        mod.register()


def unregister():
    for mod in reversed(modules):
        mod.unregister()
