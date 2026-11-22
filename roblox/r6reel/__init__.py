"""r6reel - Roblox R6 storytime video renderer (library + CLI).

Modules are imported lazily so a half-built tree still imports.
"""
__version__ = "0.1.0"
import importlib as _il

_LAZY = {"Mesh": "mesh", "Renderer": "renderer", "Avatar": "avatar", "Rig": "rig",
         "Camera": "camera", "Scene": "scene", "faces": "faces"}


def __getattr__(name):
    if name in _LAZY:
        mod = _il.import_module(f"r6reel.{_LAZY[name]}")
        return mod if name == "faces" else getattr(mod, name)
    raise AttributeError(name)
