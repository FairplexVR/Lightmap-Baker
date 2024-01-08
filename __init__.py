bl_info = {
    "name": "Lightmap Baker",
    "author": "Fairplex",
    "version": (0, 1, 5),
    "blender": (4, 0, 0),
    "location": "3DView > Render > BakeTool",
    "description": "Bake Solution for Cycles",
    "wiki_url": "",
    "warning": "",
    "category": "Render"
}

from .lightmap_baker import register, unregister

if __name__ == '__main__':
    
    register()
