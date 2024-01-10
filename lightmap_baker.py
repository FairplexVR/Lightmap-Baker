import bpy
import time
import ctypes
# from bpy.app.handlers import persistent

# Reset variables in case blender exited in a bad baking state? yea it happend more than once :P

def on_file_opened(dummy):
    properties = bpy.context.scene.lightmap_baker_properties

    properties.busy = False
    properties.bake_in_progress = False
    properties.cancel_bake = False
    properties.bake_progress = 0.0


def on_post_bake(dummy):  
    # select the next object
    scene = bpy.context.scene
    scene.lightmap_baker_properties.bake_in_progress = False
    scene.lightmap_baker_properties.objects_index += 1

    pack_lightmap_texture()


def on_bake_cancel(dummy):
    context = bpy.context
    scene = context.scene

    scene.lightmap_baker_properties.bake_in_progress = False
    scene.lightmap_baker_properties.cancel_bake = True
    scene.lightmap_baker_properties.elapsed_time = 0.0
    scene.lightmap_baker_properties.bake_progress = 0.0
    # Freedom is real
    scene.lightmap_baker_properties.busy = False

    bpy.app.handlers.object_bake_complete.remove(on_post_bake)
    bpy.app.handlers.object_bake_cancel.remove(on_bake_cancel)

    refresh_ui()

# When the bake started...
def bake_diffuse(context, obj):
    # Adjust bake settings
    bpy.types.BakeSettings.use_pass_direct = True
    bpy.types.BakeSettings.use_pass_indirect = True
    bpy.types.BakeSettings.use_pass_color = False

    context.scene.render.bake.margin = context.scene.lightmap_baker_properties.bake_margin

    bpy.ops.object.mode_set(mode='OBJECT')

    # Make the object active and select it
    bpy.ops.object.select_all(action='DESELECT')
    context.view_layer.objects.active = obj
    obj.select_set(True)

    # Invoke the bake operation
    bpy.ops.object.bake('INVOKE_DEFAULT', type='DIFFUSE', use_clear=False)

    current_index = context.scene.lightmap_baker_properties.objects_index
    total_objects = len(context.scene.lightmap_baker_objects)
    print(f"Baking object {obj.name} {current_index + 1}/{total_objects}")

def create_lightmap_nodes(context, objects_to_bake):
    resolution_options = {
        '64': 64,
        '128': 128,
        '256': 256,
        '512': 512,
        '1024': 1024,
        '2048': 2048,
        '4096': 4096,
        '8192': 8192,
    }

    resolution = resolution_options.get(context.scene.lightmap_baker_properties.lightmap_resolution)
    existing_image = bpy.data.images.get(context.scene.lightmap_baker_properties.lightmap_name)

    # Check if lightmap already exists
    if existing_image:
        # Check if the resolution doesn't match
        if existing_image.size[0] != resolution:
            # Remove the existing image if resolution is different
            bpy.data.images.remove(existing_image, do_unlink=True)
            print("Lightmap resolution updated")
        else:
            bpy.data.images.remove(existing_image, do_unlink=True)
    # Create a new lightmap image or reuse existing one
    new_image = bpy.data.images.get(context.scene.lightmap_baker_properties.lightmap_name)

    if not new_image:
        new_image = bpy.data.images.new(name=context.scene.lightmap_baker_properties.lightmap_name,
                                        width=resolution, height=resolution, float_buffer=True)

        new_image.colorspace_settings.name = 'Linear Rec.709'
        new_image.use_view_as_render = True
        new_image.file_format = 'OPEN_EXR'

    for obj_name in objects_to_bake:
        obj = bpy.data.objects.get(obj_name)
        if obj and obj.data.materials:
            for material_slot in obj.material_slots:
                obj_material = material_slot.material

                # Check if a ShaderNodeTexImage already exists
                texture_node = obj_material.node_tree.nodes.get("Bake_Texture_Node")
                if not texture_node:
                    # Add the Lightmap texture node if not present
                    texture_node = obj_material.node_tree.nodes.new(type='ShaderNodeTexImage')
                    texture_node.name = 'Bake_Texture_Node'
                    texture_node.location = (0, -50)

                # Set the image for the texture node
                texture_node.image = new_image

                # Check if a UVMap node already exists
                uvmap_node = obj_material.node_tree.nodes.get("UVMap_Node")
                if not uvmap_node:
                    uvmap_node = obj_material.node_tree.nodes.new(type='ShaderNodeUVMap')
                    uvmap_node.name = 'UVMap_Node'
                    uvmap_node.uv_map = obj.data.uv_layers[1].name
                    uvmap_node.location = (-250, -200)

                obj_material.node_tree.links.new(uvmap_node.outputs["UV"], texture_node.inputs["Vector"])
                obj_material.node_tree.nodes.active = texture_node
    
    return {'FINISHED'}


# Preview Lightmaps
def lightmap_preview_diffuse(self, context):
    if context.scene.lightmap_baker_properties.preview_diffuse_enabled:
        connect_lightmap_to_shader_output(context)
    else:
        disconnect_lightmap_to_shader_output(context)

def connect_lightmap_to_shader_output(context):
    objects_list = context.scene.lightmap_baker_objects
    processed_materials = set()

    for obj_name in objects_list:
        obj = bpy.data.objects.get(obj_name.objects_list)
        if obj and obj.data.materials:
            for material_slot in obj.material_slots:
                obj_material = material_slot.material

                if obj_material not in processed_materials:
                    nodes_dict = {key: value for key, value in (entry.split(':') for entry in obj_name.nodes_dictionary.split(',') if ':' in entry)}

                    texture_node = obj_material.node_tree.nodes.get("Bake_Texture_Node")
                    material_output = find_material_output_node(obj_material)

                    if texture_node and material_output:
                        # Save linked node here
                        nodes_dict[obj_material.name] = find_shader_connected_to_material_output(obj_material).name

                        # Mark material as processed
                        processed_materials.add(obj_material)

                        # Connect the lightmap
                        obj_material.node_tree.links.new(texture_node.outputs[0], material_output.inputs[0])

                    # Update the nodes_dictionary in obj_name with the modified dictionary
                    obj_name.nodes_dictionary = ','.join(f"{key}:{value}" for key, value in nodes_dict.items())


def disconnect_lightmap_to_shader_output(context):
    objects_list = context.scene.lightmap_baker_objects
    for obj_name in objects_list:
        obj = bpy.data.objects.get(obj_name.objects_list)
        if obj and obj.data.materials:
            for material_slot in obj.material_slots:
                obj_material = material_slot.material
                links = obj_material.node_tree.links

                nodes_dict = dict(entry.split(':') for entry in obj_name.nodes_dictionary.split(',') if entry)

                connected_node_name = nodes_dict.get(obj_material.name)
                if connected_node_name:
                    original_shader_node = obj_material.node_tree.nodes.get(connected_node_name)
                    if original_shader_node:
                        print(f"Restored Node {original_shader_node.name} in Material {obj_material.name}")
                        material_output = find_material_output_node(obj_material)
                        links.new(original_shader_node.outputs[0], material_output.inputs[0])


def find_shader_connected_to_material_output(material):
    material_output = find_material_output_node(material)
    
    for n_input in material_output.inputs:
        for node_link in n_input.links:
            return node_link.from_node
        return None

def find_material_output_node(obj_material):
    for node in obj_material.node_tree.nodes:
        if node.type == 'OUTPUT_MATERIAL':
            return node
    return None


# What we do when bake is done?
def calculate_elapsed_time():
    bpy.context.scene.lightmap_baker_properties.elapsed_time = time.perf_counter() - bpy.context.scene.lightmap_baker_properties.time_start

def pack_lightmap_texture():
    image_name = bpy.context.scene.lightmap_baker_properties.lightmap_name
    image = bpy.data.images[image_name]
    image.pack()

def handle_bake_completion(context):  
        # Automatic Lightmap Preview
        if context.scene.lightmap_baker_properties.automatic_lightmap_preview:
            context.scene.lightmap_baker_properties.preview_diffuse_enabled = True

        context.scene.lightmap_baker_properties.bake_in_progress = False
        context.scene.lightmap_baker_properties.cancel_bake = False
        # Freedom is real
        context.scene.lightmap_baker_properties.busy = False
        # Refresh the UI
        context.area.tag_redraw()
        
        pack_lightmap_texture()
        calculate_elapsed_time()

        bpy.app.handlers.object_bake_complete.remove(on_post_bake)
        bpy.app.handlers.object_bake_cancel.remove(on_bake_cancel)

        return {'FINISHED'}


def refresh_ui():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'UI':
                        region.tag_redraw()
                        break

# Properties
class LIGHTMAPBAKER_properties(bpy.types.PropertyGroup):
    busy: bpy.props.BoolProperty(
        name="Busy",
        description="General State of the bake", #used for the UI lock
        default=False,
    )

    bake_in_progress: bpy.props.BoolProperty(
        name="Bake In Progress",
        description="",
        default=False,
    )

    objects_index: bpy.props.IntProperty(
        name="Index",
        description="Index of the selected object in the bake list",
        default=0,
    )

    preview_diffuse_enabled: bpy.props.BoolProperty(
        name="Toggle Lightmap Preview",
        description="Show only lightmaps on the surface",
        default=False,
    )

    lightmap_baker_uv_map_index: bpy.props.IntProperty(
        name="Active UV Map Index",
        description="Active UV Map Index",
        default=0,
        min=0,
        max=1,
    )

    lightmap_baker_uv_map_name: bpy.props.StringProperty(
        name="UV Map Name",
        description="Set the lightmap uv name",
        default="Lightmap",
    )

    export_enabled: bpy.props.BoolProperty(
        name="Export Texture",
        description="Export lightmap image after baking",
        default=False,
    )

    export_path: bpy.props.StringProperty(
        name="Export Path",
        description="Path for exporting lightmap image",
        default="",
        subtype='FILE_PATH',
    )

    automatic_lightmap_preview: bpy.props.BoolProperty(
        name="Automatic Lightmap Preview",
        description="Automatically preview lightmaps",
    )

    lightmap_resolution: bpy.props.EnumProperty(
        items=[
            ('64', '64', 'Bake at 512x512 resolution'),
            ('128', '128', 'Bake at 512x512 resolution'),
            ('256', '256', 'Bake at 512x512 resolution'),
            ('512', '512', 'Bake at 512x512 resolution'),
            ('1024', '1024', 'Bake at 1024x1024 resolution'),
            ('2048', '2048', 'Bake at 2048x2048 resolution'),
            ('4096', '4096', 'Bake at 4096x4096 resolution'),
            ('8192', '8192', 'Bake at 4096x4096 resolution'),
        ],
        name="Resolution",
        description="Choose bake resolution",
        default='1024',
    )

    lightmap_name: bpy.props.StringProperty(
        name="Lightmap Name",
        description="Name of the baked lightmap texture",
        default="Lightmap"
    )

    render_device: bpy.props.EnumProperty(
        items=[
            ('CPU', 'CPU', 'Render using CPU'),
            ('GPU', 'GPU Compute', 'Render using GPU'),
        ],
        name="Device",
        description="Choose render device",
        default='GPU',
    )

    sample_count: bpy.props.IntProperty(
        name="Sample Count",
        description="Number of samples for baking",
        default=128,
        min=1,
    )

    bake_margin: bpy.props.IntProperty(
        name="Bake Margin",
        default=6,
        min=0,
        max=64,
        description="Extend the baked result as a post process filter",
    )

    time_start: bpy.props.FloatProperty(
    name="Time Start",
    description="Time when bake starts",
    default=0.00000,
    )

    elapsed_time: bpy.props.FloatProperty(
    name="Elapsed Time",
    description="Time elapsed to complete the bake process",
    default=0.0,
    )

    cancel_bake: bpy.props.BoolProperty(
    name="Cancel Bake",
    description="Cancel Bake",
    default=False,
    )

    bake_progress: bpy.props.FloatProperty(
    name="Bake Progress",
    description="this is the current progression",
    default=0.0,
    )

    filtering_denoise: bpy.props.BoolProperty(
    name="Cancel Bake",
    description="Cancel Bake",
    default=False,
    )

    filtering_bilateral_blur: bpy.props.BoolProperty(
    name="Bilateral Blur",
    description="",
    default=False,
    )

class LIGHTMAPBAKER_objects_properties(bpy.types.PropertyGroup):
    objects_list: bpy.props.StringProperty(
        name="Objects List"
    )

    nodes_dictionary: bpy.props.StringProperty(
        name="Original Shader Node Name",
        description="Original shader node name for storing links",
        default=""
    )

# Bake Logic
class LIGHTMAPBAKER_OT_bake(bpy.types.Operator):
    bl_idname = "object.bake_operator"
    bl_label = "Bake!"
    bl_description = "Bake objects in the list"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        time_start = time.time()

        # Cancel if the list is empty
        if not context.scene.lightmap_baker_objects:
            self.report({'ERROR'}, "Nothing to Bake :(")
            return {'CANCELLED'}

        # Check for missing UVs
        objects_to_bake = [obj_name.objects_list for obj_name in context.scene.lightmap_baker_objects]
        objects_missing_uv = [obj_name for obj_name in objects_to_bake if len(bpy.data.objects.get(obj_name).data.uv_layers) < 2]

        if objects_missing_uv:
            # Deselect all objects first
            bpy.ops.object.select_all(action='DESELECT')

            # Select only the objects missing the second UV map
            for obj_name in objects_missing_uv:
                bpy.data.objects[obj_name].select_set(True)

            context.view_layer.objects.active = bpy.data.objects[objects_missing_uv[0]]

            # Display an error message in the info area
            self.report({'ERROR'}, f"Selected objects missing a second UV map: {', '.join(objects_missing_uv)}")
            return {'CANCELLED'}

        # Check for missing materials in any object in the list
        objects_missing_materials = [obj_name for obj_name in objects_to_bake if not bpy.data.objects.get(obj_name).data.materials]
        if objects_missing_materials:
            # Deselect all objects first
            bpy.ops.object.select_all(action='DESELECT')

            # Select only the objects missing materials
            for obj_name in objects_missing_materials:
                bpy.data.objects[obj_name].select_set(True)

            context.view_layer.objects.active = bpy.data.objects[objects_missing_materials[0]]

            # Display an error message in the info area
            self.report({'ERROR'}, f"Selected objects missing materials: {', '.join(objects_missing_materials)}")
            return {'CANCELLED'}

        objects_with_unused_slots = [obj_name for obj_name in objects_to_bake
                                     if bpy.data.objects.get(obj_name).data.materials and
                                     any(not slot.material for slot in bpy.data.objects.get(obj_name).material_slots)]

        if objects_with_unused_slots:
            # Deselect all objects first
            bpy.ops.object.select_all(action='DESELECT')

            # Select only the objects with unused material slots
            for obj_name in objects_with_unused_slots:
                bpy.data.objects[obj_name].select_set(True)

            context.view_layer.objects.active = bpy.data.objects[objects_with_unused_slots[0]]

            # Display an error message in the info area
            self.report({'ERROR'}, f"Selected objects have unused material slots: {', '.join(objects_with_unused_slots)}")
            return {'CANCELLED'}
        
        if bpy.context.scene.render.engine == 'BLENDER_EEVEE':
            self.report({'ERROR'}, "Only Cycles render is supported!")
            return {'CANCELLED'}

        else:
            # Set the active object outside the loop
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            active_object = bpy.data.objects.get(objects_to_bake[0])
            active_object.select_set(True)
            context.view_layer.objects.active = active_object
    
            bpy.context.scene.cycles.device = context.scene.lightmap_baker_properties.render_device

            sample_count = context.scene.lightmap_baker_properties.sample_count
            bpy.context.scene.cycles.samples = sample_count
    
            # Disable lightmaps preview
            context.scene.lightmap_baker_properties.preview_diffuse_enabled = False
            lightmap_preview_diffuse(self, context)
            create_lightmap_nodes(context, objects_to_bake)

            for obj_name in objects_to_bake:
                obj = bpy.data.objects.get(obj_name)
                obj.data.uv_layers.active_index = 1

            # Reset bake aborting
            context.scene.lightmap_baker_properties.cancel_bake = False
            # Reset the objects to bake index
            context.scene.lightmap_baker_properties.objects_index = 0
            # Reset elapsed time
            context.scene.lightmap_baker_properties.elapsed_time = 0.0
            # Reset the progression
            context.scene.lightmap_baker_properties.bake_progress = 0.0
            # Start the timer
            context.scene.lightmap_baker_properties.time_start = time.perf_counter()
            # We are now busy!
            context.scene.lightmap_baker_properties.busy = True
            # Start Bake!
            bpy.ops.wm.bake_modal_operator('INVOKE_DEFAULT')
            bpy.ops.wm.elapsed_time_modal_operator('INVOKE_DEFAULT')

            bpy.app.handlers.object_bake_complete.append(on_post_bake)
            bpy.app.handlers.object_bake_cancel.append(on_bake_cancel)

            print("My Script Finished: %.4f sec" % (time.time() - time_start))
            return {'FINISHED'}

class LIGHTMAPBAKER_OT_remove_single_from_bake_list(bpy.types.Operator):
    bl_idname = "object.remove_single_from_bake_list"
    bl_label = "Remove Object from Bake List"

    index: bpy.props.IntProperty()
    scene: bpy.props.StringProperty()

    def execute(self, context):
        scene = context.scene
        if scene:
            # Ensure the index is within the valid range
            index = min(max(0, self.index), len(scene.lightmap_baker_objects) - 1)

            # Remove the object from the collection
            scene.lightmap_baker_objects.remove(index)

            # Update the index after removal
            scene.lightmap_baker_properties.objects_index = min(index, len(scene.lightmap_baker_objects) - 1)

        return {'FINISHED'}

class LIGHTMAPBAKER_OT_remove_all_from_bake_list(bpy.types.Operator):
    bl_idname = "object.clear_bake_list"
    bl_label = "Clear List"

    def execute(self, context):
        context.scene.lightmap_baker_objects.clear()
        return {'FINISHED'}

class LIGHTMAPBAKER_OT_toggle_lightmap_preview_diffuse(bpy.types.Operator):
    bl_idname = "object.toggle_lightmap_preview_diffuse"
    bl_label = "Toggle Lightmap Diffuse Only"

    def execute(self, context):
        has_lightmap = False

        # Loop through all objects in the scene
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH':
                material = obj.active_material
                if material:
                    texture_node = material.node_tree.nodes.get("Bake_Texture_Node")
                    if texture_node:
                        has_lightmap = True
                        break  # Exit the loop if at least one object has a lightmap

        if not has_lightmap:
            self.report({'ERROR'}, "Nothing to preview :(")
            return {'CANCELLED'}

        context.scene.lightmap_baker_properties.preview_diffuse_enabled = not context.scene.lightmap_baker_properties.preview_diffuse_enabled
        lightmap_preview_diffuse(self, context)
        return {'FINISHED'}

class LIGHTMAPBAKER_OT_add_to_objects_list(bpy.types.Operator):
    bl_idname = "object.add_to_bake_list"
    bl_label = "Add Object"

    def execute(self, context):
        selected_objects = bpy.context.selected_objects

        for obj in selected_objects:
            if obj.type == 'MESH':
                # Check if the object is not already in the list
                if obj.name not in (item.objects_list for item in context.scene.lightmap_baker_objects):
                    # Append the object to the list
                    new_item = context.scene.lightmap_baker_objects.add()
                    new_item.objects_list = obj.name

        return {'FINISHED'}

class LIGHTMAPBAKER_OT_remove_lightmap_nodes(bpy.types.Operator):
    bl_idname = "object.remove_lightmap_nodes"
    bl_label = "Remove Lightmap Nodes"
    bl_description = "Remove lightmap nodes"

    def execute(self, context):
        all_materials = bpy.data.materials

        for material in all_materials:
            if material.use_nodes:
                texture_node = material.node_tree.nodes.get("Bake_Texture_Node")

                if texture_node:
                    # Collect links connected to the texture node
                    links_to_remove = [link for link in material.node_tree.links if link.to_node == texture_node]

                    # Remove the UVMap nodes connected to the texture node
                    for link in links_to_remove:
                        uvmap_node = link.from_node
                        material.node_tree.nodes.remove(uvmap_node)
                        material.node_tree.nodes.remove(texture_node)

        # Reconnect original nodes
        disconnect_lightmap_to_shader_output(context)
        context.scene.lightmap_baker_properties.preview_diffuse_enabled = False
        return {'FINISHED'}

class LIGHTMAPBAKER_OT_add_lightmap_uv(bpy.types.Operator):
    bl_idname = "object.add_lightmap_uv"
    bl_label = "Add Lightmap UVs"
    
    def execute(self, context):
        for obj_name in context.scene.lightmap_baker_objects:
            obj = bpy.data.objects.get(obj_name.objects_list)
            if obj:
                # Check if the object has a second UV map
                if len(obj.data.uv_layers) < 2:
                    # Add a new UV map named "Lightmap"
                    obj.data.uv_layers.new(name="Lightmap")
                    obj.data.uv_layers.active_index = 1
                else:
                    # Rename the existing second UV map to "Lightmap"
                    obj.data.uv_layers[1].name = "Lightmap"
                    obj.data.uv_layers.active_index = 1
        return {'FINISHED'}

class LIGHTMAPBAKER_OT_delete_lightmap_uv(bpy.types.Operator):
    bl_idname = "object.delete_lightmap_uv"
    bl_label = "Remove Lightmap UVs"
    
    def execute(self, context):

        for obj_name in context.scene.lightmap_baker_objects:
            obj = bpy.data.objects.get(obj_name.objects_list)
            if obj:
                # Check if there are UV maps before trying to remove one
                if len(obj.data.uv_layers) > 1:
                    obj.data.uv_layers.remove(obj.data.uv_layers[1])
        for area in bpy.context.screen.areas:
            if area.type == 'PROPERTIES':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()
                        break
                    
        return {'FINISHED'}

class LIGHTMAPBAKER_OT_set_lightmap_uv_name(bpy.types.Operator):
    bl_idname = "object.set_lightmap_uv_name"
    bl_label = "Rename Lightmap UVs"
    
    def execute(self, context):

        for obj_name in context.scene.lightmap_baker_objects:
            obj = bpy.data.objects.get(obj_name.objects_list)
            if obj:
                # Check if there are UV maps before trying to rename
                if len(obj.data.uv_layers) > 1:
                    # Check if the current name is different from the new name
                    if obj.data.uv_layers[1].name != context.scene.lightmap_baker_properties.lightmap_baker_uv_map_name:
                        # Set the new name for the second UV map
                        obj.data.uv_layers[1].name = context.scene.lightmap_baker_properties.lightmap_baker_uv_map_name

        return {'FINISHED'}

class LIGHTMAPBAKER_OT_set_lightmap_uv_index(bpy.types.Operator):
    bl_idname = "object.set_lightmap_uv_index"
    bl_label = "Rename Lightmap UVs"
    
    def execute(self, context):

        uv_index = context.scene.lightmap_baker_properties.lightmap_baker_uv_map_index

        for obj_name in context.scene.lightmap_baker_objects:
            obj = bpy.data.objects.get(obj_name.objects_list)
            if obj:
                # Check if the object has more UV maps than the desired index
                if len(obj.data.uv_layers) > uv_index:
                    # Check if the current active index is different from the desired index
                    if obj.data.uv_layers.active_index != uv_index:
                        obj.data.uv_layers.active_index = uv_index

        return {'FINISHED'}

class LIGHTMAPBAKER_OT_select_all_in_list(bpy.types.Operator):
    bl_idname = "object.select_all_in_list"
    bl_label = "Select All in List"
    bl_description = "Select all the objects in the list"

    def execute(self, context):
        bpy.ops.object.select_all(action='DESELECT')
        for obj_name in context.scene.lightmap_baker_objects:
            obj = bpy.data.objects.get(obj_name.objects_list)
            if obj:
                obj.select_set(True)
        return {'FINISHED'}

class LIGHTMAPBAKER_OT_clean_invalid_objects(bpy.types.Operator):
    bl_idname = "object.clean_all_invalid_objects"
    bl_label = "Clean All Invalid Objects"
    bl_description = "Clean All Invalid Objects"

    def execute(self, context):
        # Create a list to store indices of invalid objects
        invalid_indices = []

        for index, obj_name in enumerate(context.scene.lightmap_baker_objects):
            if bpy.data.objects.get(obj_name.objects_list) is None:
                invalid_indices.append(index)

        # Remove invalid objects from the collection
        for index in reversed(invalid_indices):
            context.scene.lightmap_baker_objects.remove(index)

        return {'FINISHED'}

class LIGHTMAPBAKER_OT_bake_modal(bpy.types.Operator):
    bl_idname = "wm.bake_modal_operator"
    bl_label = "Bake Modal Operator"

    _timer = None
    bake_started = False
    bake_completed = False

    def modal(self, context, event):
        scene = context.scene
        objects_list = scene.lightmap_baker_objects
        total_objects = len(objects_list)

        # Modal stop when task cancelled
        if scene.lightmap_baker_properties.cancel_bake:
            self.cancel(context)
            return {'CANCELLED'}
        # Modal stop when bake is complete
        if self.bake_completed:
            self.cancel(context)
            return {'CANCELLED'}

        if not scene.lightmap_baker_properties.bake_in_progress and not scene.lightmap_baker_properties.cancel_bake:
            # Check for remaining objects in the list
            if scene.lightmap_baker_properties.objects_index < total_objects and not self.bake_completed:
                obj_data = objects_list[scene.lightmap_baker_properties.objects_index]
                obj = bpy.data.objects.get(obj_data.objects_list)

                bake_diffuse(context, obj)
                scene.lightmap_baker_properties.bake_in_progress = True
   
            # Consider Bake Done!
            elif not self.bake_completed:
                self.bake_completed = True
                self.cancel(context)
                
                handle_bake_completion(context)

                # Automatic lightmap preview
                lightmap_preview_diffuse(self, context)

            # calculate progress
            progress_value = scene.lightmap_baker_properties.objects_index / len(objects_list)    
            scene.lightmap_baker_properties.bake_progress = progress_value

        return {'PASS_THROUGH'}

    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)

class LIGHTMAPBAKER_OT_elapsed_time_modal(bpy.types.Operator):
    bl_idname = "wm.elapsed_time_modal_operator"
    bl_label = "Elapsed Time Modal Operator"

    _timer = None
    counter = 0.0
    interval = 0.1

    def modal(self, context, event):
        # Modal stop when task completed
        if context.scene.lightmap_baker_properties.bake_progress == 1.0:
            self.cancel(context)
            return {'CANCELLED'}
        # Modal stop when task cancelled
        if context.scene.lightmap_baker_properties.cancel_bake:
            self.cancel(context)
            return {'CANCELLED'}

        # Check if the interval has passed
        if time.time() - self.counter > self.interval:
            self.counter = time.time()

            calculate_elapsed_time()
            refresh_ui()

        return {'PASS_THROUGH'}


    def invoke(self, context, event):
        self._timer = context.window_manager.event_timer_add(self.interval, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)

class LIGHTMAPBAKER_OT_cancel_bake(bpy.types.Operator):
    bl_idname = "object.cancel_bake"
    bl_label = "Cancel Bake"
    bl_description = "Cancel Bake"

    def execute(self, context):
        # Define virtual key code for ESC
        VK_ESCAPE = 0x1B
        KEYEVENTF_KEYDOWN = 0x0000
        KEYEVENTF_KEYUP = 0x0002
        # Simulate ESC pressed and released
        ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYDOWN, 0)
        ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)

        context.scene.lightmap_baker_properties.cancel_bake = True
        return {'FINISHED'}



classes = [
    LIGHTMAPBAKER_properties,
    LIGHTMAPBAKER_objects_properties,
    LIGHTMAPBAKER_OT_elapsed_time_modal,
    LIGHTMAPBAKER_OT_cancel_bake,
    LIGHTMAPBAKER_OT_toggle_lightmap_preview_diffuse,
    LIGHTMAPBAKER_OT_remove_single_from_bake_list,
    LIGHTMAPBAKER_OT_remove_all_from_bake_list,
    LIGHTMAPBAKER_OT_bake_modal,
    LIGHTMAPBAKER_OT_clean_invalid_objects,
    LIGHTMAPBAKER_OT_add_lightmap_uv,
    LIGHTMAPBAKER_OT_delete_lightmap_uv,
    LIGHTMAPBAKER_OT_set_lightmap_uv_name,
    LIGHTMAPBAKER_OT_set_lightmap_uv_index,
    LIGHTMAPBAKER_OT_select_all_in_list,
    LIGHTMAPBAKER_OT_bake,
    LIGHTMAPBAKER_OT_add_to_objects_list,
    LIGHTMAPBAKER_OT_remove_lightmap_nodes,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # bpy.app.handlers.load_post.append(on_file_opened)
    # bpy.app.handlers.object_bake_complete.append(on_post_bake)
    # bpy.app.handlers.object_bake_cancel.append(on_bake_cancel)

    bpy.types.Scene.lightmap_baker_properties = bpy.props.PointerProperty(type=LIGHTMAPBAKER_properties)
    bpy.types.Scene.lightmap_baker_objects = bpy.props.CollectionProperty(type=LIGHTMAPBAKER_objects_properties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    #bpy.app.handlers.load_post.remove(on_file_opened)
    #bpy.app.handlers.object_bake_complete.remove(on_post_bake)
    #bpy.app.handlers.object_bake_cancel.remove(on_bake_cancel)
    
    del bpy.types.Scene.lightmap_baker_properties
    del bpy.types.Scene.lightmap_baker_objects

if __name__ == '__main__':
    register()

