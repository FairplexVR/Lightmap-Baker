import bpy

# Select the first mesh object in the scene
bpy.ops.object.select_all(action='DESELECT')

bpy.context.scene.objects[0].select_set(True)
bpy.context.scene.objects[0].active