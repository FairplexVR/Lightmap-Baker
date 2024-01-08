import bpy
import time
import ctypes

bake_in_progress = False

def update_active_uv_map_index(self, context):
    uv_index = context.scene.active_uv_map_index.lightmap_baker_uv_map_index

    for obj_name in context.scene.lightmap_baker_objects:
        obj = bpy.data.objects.get(obj_name.object)
        if obj:
            # Ensure UV index is valid
            uv_index = min(uv_index, len(obj.data.uv_layers) - 1) 
            obj.data.uv_layers.active_index = uv_index

def bake_diffuse(context, obj):
    # Adjust bake settings
    context.scene.render.bake.use_pass_direct = True
    context.scene.render.bake.use_pass_indirect = True
    context.scene.render.bake.margin = context.scene.lightmap_baker_margin

    bpy.ops.object.mode_set(mode='OBJECT')

    # Make the object active and select it
    bpy.ops.object.select_all(action='DESELECT')
    context.view_layer.objects.active = obj
    obj.select_set(True)

    # Invoke the bake operation
    bpy.ops.object.bake('INVOKE_DEFAULT', type='DIFFUSE', use_clear=False)

    current_index = context.scene.lightmap_baker_objects_index
    total_objects = len(context.scene.lightmap_baker_objects)
    print(f"Baking object {obj.name} {current_index + 1}/{total_objects}")

def lightmap_preview_diffuse(self, context):
    for material in bpy.data.materials:
        # Check if the material has a node tree
        if material.node_tree is not None:
            # Check if the material has the "Bake_Texture_Node"
            texture_node = material.node_tree.nodes.get("Bake_Texture_Node")

            if texture_node:
                if context.scene.lightmap_baker_preview_diffuse:
                    connect_lightmap_to_shader_output(material, texture_node)
                else:
                    disconnect_lightmap_from_shader_output(material)

def create_lightmap_nodes(context, objects_to_bake):
    resolution_options = {
        '512': 512,
        '1024': 1024,
        '2048': 2048,
        '4096': 4096,
    }

    resolution = resolution_options.get(context.scene.lightmap_baker_resolution)
    existing_image = bpy.data.images.get(context.scene.lightmap_baker_texture_name)

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
    new_image = bpy.data.images.get(context.scene.lightmap_baker_texture_name)

    if not new_image:
        new_image = bpy.data.images.new(name=context.scene.lightmap_baker_texture_name,
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

def connect_lightmap_to_shader_output(material, texture_node):
    shader_node = material.node_tree.nodes.get("Material Output")

    if shader_node:
        links = material.node_tree.links
        # Connect the lightmap node to the shader output
        links.new(texture_node.outputs["Color"], shader_node.inputs["Surface"])

def disconnect_lightmap_from_shader_output(material):
    links = material.node_tree.links

    shader_output = find_shader_output_node(material)

    if shader_output:
        # Connect the shader node to the "Surface" input
        shader_input = material.node_tree.nodes["Material Output"].inputs["Surface"]
        links.new(shader_output, shader_input)
    else:
        print("Error: Shader output not found.")

def find_shader_output_node(material):
    add_shader_nodes = [node for node in material.node_tree.nodes if node.type == 'ADD_SHADER']
    mix_shader_nodes = [node for node in material.node_tree.nodes if node.type == 'MIX_SHADER']

    if add_shader_nodes or mix_shader_nodes:
        # Use the first Add Shader or Mix Shader node found
        return (add_shader_nodes + mix_shader_nodes)[0].outputs["Shader"]

    bsdf_node = next(
        (node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED' or 'BSDF' in node.name), None)

    if bsdf_node:
        return bsdf_node.outputs["BSDF"]
    else:
        print("Error: No MIX_SHADER, ADD_SHADER, or BSDF nodes found.")
        return None

def format_time(seconds):
    minutes, seconds = divmod(seconds, 60)
    return f"{int(minutes):02d}:{int(seconds):02d}.{int((seconds - int(seconds)) * 100):02d}"

def calculate_elapsed_time():
    bpy.context.scene.lightmap_baker.elapsed_time = time.perf_counter() - bpy.context.scene.lightmap_baker.time_start
    
def on_complete(dummy):
    global bake_in_progress
    bake_in_progress = False

    # select the next object
    scene = bpy.context.scene
    scene.lightmap_baker_objects_index += 1

# The latest cancel
def on_cancel(dummy):
    global bake_in_progress
    bake_in_progress = False

    context = bpy.context
    scene = context.scene

    scene.lightmap_baker.cancel_bake = True
    scene.lightmap_baker.elapsed_time = 0.0

    # Reset the progression
    scene.lightmap_baker_progress = 0.0

    bpy.app.timers.register(refresh_ui, first_interval=0.1)
    bpy.app.handlers.object_bake_complete.clear()
    bpy.app.handlers.object_bake_cancel.clear()

def refresh_ui():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()                           
                break

# Properties
class LIGHTMAPBAKER_properties(bpy.types.PropertyGroup):
    lightmap_baker_objects_index: bpy.props.IntProperty(
        name="Index",
        description="Index of the selected object in the bake list",
        default=0,
    )

    lightmap_baker_preview_diffuse: bpy.props.BoolProperty(
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
        update=update_active_uv_map_index,
    )

    lightmap_baker_export_enabled: bpy.props.BoolProperty(
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

    lightmap_baker_resolution: bpy.props.EnumProperty(
        items=[
            ('512', '512', 'Bake at 512x512 resolution'),
            ('1024', '1024', 'Bake at 1024x1024 resolution'),
            ('2048', '2048', 'Bake at 2048x2048 resolution'),
            ('4096', '4096', 'Bake at 4096x4096 resolution'),
        ],
        name="Resolution",
        description="Choose bake resolution",
        default='1024',
    )

    lightmap_baker_texture_name: bpy.props.StringProperty(
        name="Texture Name",
        description="Name of the baked lightmap texture",
        default=""
    )

    lightmap_baker_render_device: bpy.props.EnumProperty(
        items=[
            ('CPU', 'CPU', 'Render using CPU'),
            ('GPU', 'GPU Compute', 'Render using GPU'),
        ],
        name="Device",
        description="Choose render device",
        default='GPU',
    )

    lightmap_baker_sample_count: bpy.props.IntProperty(
        name="Sample Count",
        description="Number of samples for baking",
        default=128,
        min=1,
    )

    lightmap_baker_margin = bpy.props.IntProperty(
        name="Margin",
        default=6,
        min=0,
        max=64,
        description="Extend the baked result as a post process filter",
    )

    time_start: bpy.props.FloatProperty(
    name="Time Start",
    description="Ttime when bake starts",
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
    default=True,
    )

class LIGHTMAPBAKER_objects_properties(bpy.types.PropertyGroup):
    object: bpy.props.StringProperty()

# Panel
class LIGHTMAPBAKER_PT_main:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Main Tab"
    bl_options = {"HEADER_LAYOUT_EXPAND"}

class LIGHTMAPBAKER_PT_title(bpy.types.Panel):
    bl_label = "Lightmap Baker"
    bl_idname = "LIGHTMAPBAKER_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Lightmap Baker'

    def draw(self, context):
        layout = self.layout

class LIGHTMAPBAKER_PT_objects(LIGHTMAPBAKER_PT_main, bpy.types.Panel):
    bl_parent_id = "LIGHTMAPBAKER_PT_Panel"
    bl_label = "Objects"

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=False)
        row.operator("object.add_to_bake_list", text="Add Objects")
        row.operator("object.clear_bake_list", text="Clear List")
        # Add a button to clean all invalid objects at once
        row.operator("object.clean_all_invalid_objects", text="", icon='BRUSH_DATA')
        # Create a horizontal box for the list and button
        row = layout.row(align=False)
        row.template_list("LIGHTMAPBAKER_UL_objects_list", "", context.scene, "lightmap_baker_objects",
                          context.scene, "lightmap_baker_objects_index", columns=3)
        # Lightmap Preview diffuse direct and indirect only
        row.operator("object.toggle_lightmap_preview_diffuse", text="", icon='SHADING_RENDERED', depress=context.scene.lightmap_baker_preview_diffuse)

        # Select All in the List
        layout.operator("object.select_all_in_list", text="Select All in List")

        # Add Lightmap UV button
        row = layout.row(align=True)
        row.operator("object.add_lightmap_uv", text="Add Lightmap UV")

        # Switch UV Index button
        row = layout.row(align=True)
        row.label(icon='GROUP_UVS', text="Active UV:")
        row.prop(context.scene.active_uv_map_index, "lightmap_baker_uv_map_index", text="", emboss=True)
        
        # Button to clean lightmap nodes and Lightmap UVs
        row = layout.row(align=True)
        row.operator("object.remove_lightmap_nodes", text="Remove Lightmap Nodes")

class LIGHTMAPBAKER_UL_objects_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        obj = bpy.data.objects.get(item.object)
        if obj:
            layout.label(text=obj.name, icon='OBJECT_DATAMODE')
            layout.operator("object.remove_single_from_bake_list", text="", icon='X').index = index  # Change here
        else:
            layout.label(text="Invalid Object", icon='ERROR')

class LIGHTMAPBAKER_PT_settings(LIGHTMAPBAKER_PT_main, bpy.types.Panel):
    bl_parent_id = "LIGHTMAPBAKER_PT_Panel"
    bl_label = "Settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Lightmap Baker'

    def draw(self, context):

        layout = self.layout

        row = layout.row(align=True)
        row.label(text="Resolution:")
        row.prop(context.scene, "lightmap_baker_resolution", text="")

        row = layout.row(align=True)
        row.label(text="Device:")
        row.prop(context.scene, "lightmap_baker_render_device", text="", toggle=True)
        
        row = layout.row(align=True)
        row.label(text="Sample Count:")
        row.prop(context.scene, "lightmap_baker_sample_count", text="")

        # Add a margin option with a label in front
        row = layout.row(align=True)
        row.label(text="Margin:")
        row.prop(context.scene, "lightmap_baker_margin", text="")

class LIGHTMAPBAKER_PT_output(LIGHTMAPBAKER_PT_main, bpy.types.Panel):
    bl_parent_id = "LIGHTMAPBAKER_PT_Panel"
    bl_label = "Output"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Lightmap Baker'

    def draw(self, context):
        global bake_in_progress
        layout = self.layout
        self.context = context

        # Export options
        row = layout.row(align=True)
        row.enabled = False
        row.prop(context.scene, "lightmap_baker_export_enabled", text="Export Texture")
        #if context.scene.lightmap_baker.lightmap_baker_export_enabled:
        #    row = layout.row(align=True)
        #    row.prop(context.scene.lightmap_baker_export_enabled, "export_path", text="Export Path")

        # Baking Progress
        current_index = context.scene.lightmap_baker_objects_index
        total_objects = len(context.scene.lightmap_baker_objects)
        progress_value = context.scene.lightmap_baker_progress
        aborting = context.scene.lightmap_baker.cancel_bake and bake_in_progress
        canceled = context.scene.lightmap_baker.cancel_bake and not bake_in_progress
        
        # Bake and Cancel 
        row = layout.row(align=False)
        row.scale_y = 1.5 

        if not bake_in_progress and not aborting and not canceled and progress_value != 1.0:
            operator_text = "Bake!"
            operator_object = "object.bake_operator"
            progress_text = f"({0}/{total_objects} Objects)"

        elif aborting:
            row.enabled = False
            operator_text = "Aborting..."
            operator_object = "object.bake_operator"
            progress_text = f"{progress_value * 100:.0f}% ({current_index}/{total_objects} Objects)"

        elif canceled:
            operator_text = "Bake!"
            operator_object = "object.bake_operator"
            progress_text = "Canceled!"

        elif progress_value != 1.0 and bake_in_progress:
            row.alert = True
            operator_text = "Cancel"
            operator_object = "object.cancel_bake"
            progress_text = f"{progress_value * 100:.0f}% ({current_index}/{total_objects} Objects)"

        else:
            operator_text = "Bake!"
            operator_object = "object.bake_operator"
            progress_text = "Completed!"

        row.operator(operator_object, text=operator_text, icon='RENDER_STILL', emboss=True)
        layout.progress(factor=progress_value, text=progress_text)

    
        # Display elapsed time 00:00.00
        layout.label(text=f"Elapsed Time: {format_time(context.scene.lightmap_baker.elapsed_time)}") 


# Bake Logic
class LIGHTMAPBAKER_OT_bake(bpy.types.Operator):
    bl_idname = "object.bake_operator"
    bl_label = "Bake!"
    bl_description = "Bake objects in the list"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        global bake_in_progress

        time_start = time.time()

        # Cancel if the list is empty
        if not context.scene.lightmap_baker_objects:
            self.report({'ERROR'}, "Nothing to Bake :(")
            return {'CANCELLED'}

        # Check for missing UVs
        objects_to_bake = [obj_name.object for obj_name in context.scene.lightmap_baker_objects]
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
        else:
            for index, obj_name in enumerate(objects_to_bake, start=1):
                obj = bpy.data.objects.get(obj_name)

            # Set the active object outside the loop
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            active_object = bpy.data.objects.get(objects_to_bake[0])
            active_object.select_set(True)
            context.view_layer.objects.active = active_object
    
            bpy.context.scene.cycles.device = context.scene.lightmap_baker_render_device

            sample_count = context.scene.lightmap_baker_sample_count
            bpy.context.scene.cycles.samples = sample_count
    
            # Disable lightmaps preview
            context.scene.lightmap_baker_preview_diffuse = False
            lightmap_preview_diffuse(self, context)
            create_lightmap_nodes(context, objects_to_bake)

            for obj_name in objects_to_bake:
                obj = bpy.data.objects.get(obj_name)
                
                # Select the second UV map
                obj.data.uv_layers.active_index = 1

            # Reset bake aborting
            context.scene.lightmap_baker.cancel_bake = False

            # Reset the objects to bake index
            context.scene.lightmap_baker_objects_index = 0

            # Reset aborting state

            # Reset elapsed time
            context.scene.lightmap_baker.elapsed_time = 0.0

            # Reset the progression
            context.scene.lightmap_baker_progress = 0.0

            # Start the timer
            context.scene.lightmap_baker.time_start = time.perf_counter()

            # Start Bake!
            bpy.ops.wm.bake_modal_operator('INVOKE_DEFAULT')
            bpy.ops.wm.elapsed_time_modal_operator('INVOKE_DEFAULT')

            bpy.app.handlers.object_bake_complete.append(on_complete)
            bpy.app.handlers.object_bake_cancel.append(on_cancel)

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
            scene.lightmap_baker_objects_index = min(index, len(scene.lightmap_baker_objects) - 1)

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

        context.scene.lightmap_baker_preview_diffuse = not context.scene.lightmap_baker_preview_diffuse
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
                if obj.name not in (item.object for item in context.scene.lightmap_baker_objects):
                    # Append the object to the list
                    new_item = context.scene.lightmap_baker_objects.add()
                    new_item.object = obj.name

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

                # Store the reference to the shader output node
                shader_output = find_shader_output_node(material)

                # Update the property value and call the update function
                context.scene.toggle_lightmap_preview_diffuse.lightmap_baker_preview_diffuse = False
                lightmap_preview_diffuse(None, context)

                if texture_node:
                    # Collect links connected to the texture node
                    links_to_remove = [link for link in material.node_tree.links if link.to_node == texture_node]

                    # Remove the UVMap nodes connected to the texture node
                    for link in links_to_remove:
                        uvmap_node = link.from_node
                        material.node_tree.links.remove(link)
                        material.node_tree.nodes.remove(uvmap_node)

                    # Remove the texture node
                    material.node_tree.nodes.remove(texture_node)

                # Reconnect the shader output node
                if shader_output:
                    shader_input = material.node_tree.nodes["Material Output"].inputs["Surface"]
                    material.node_tree.links.new(shader_output, shader_input)

        context.scene.lightmap_baker_preview_diffuse = False

        return {'FINISHED'}

class LIGHTMAPBAKER_OT_add_lightmap_uv(bpy.types.Operator):
    bl_idname = "object.add_lightmap_uv"
    bl_label = "Add Lightmap UV"
    
    def execute(self, context):
        for obj_name in context.scene.lightmap_baker_objects:
            obj = bpy.data.objects.get(obj_name.object)
            if obj:
                # Check if the object has a second UV map
                if len(obj.data.uv_layers) < 2:
                    # Add a new UV map named "Lightmap"
                    new_uv_layer = obj.data.uv_layers.new(name="Lightmap")
                elif obj.data.uv_layers[1].name != "Lightmap":
                    # Rename the existing second UV map to "Lightmap"
                    obj.data.uv_layers[1].name = "Lightmap"
        return {'FINISHED'}
    
class LIGHTMAPBAKER_OT_select_all_in_list(bpy.types.Operator):
    bl_idname = "object.select_all_in_list"
    bl_label = "Select All in List"
    bl_description = "Select all the objects in the list"

    def execute(self, context):
        bpy.ops.object.select_all(action='DESELECT')
        for obj_name in context.scene.lightmap_baker_objects:
            obj = bpy.data.objects.get(obj_name.object)
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
            if bpy.data.objects.get(obj_name.object) is None:
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
        global bake_in_progress

        scene = context.scene
        objects_list = scene.lightmap_baker_objects
        total_objects = len(objects_list)

        # Modal stop when task cancelled
        if scene.lightmap_baker.cancel_bake:
            self.cancel(context)
            return {'CANCELLED'}
        # Modal stop when bake is complete
        if self.bake_completed:
            self.cancel(context)
            return {'CANCELLED'}

        if not bake_in_progress and not scene.lightmap_baker.cancel_bake:
            # Check for remaining objects in the list
            if scene.lightmap_baker_objects_index < total_objects and not self.bake_completed:
                obj_data = objects_list[scene.lightmap_baker_objects_index]
                obj = bpy.data.objects.get(obj_data.object)

                bake_diffuse(context, obj)
                bake_in_progress = True
   
            # Consider Bake Done!
            elif not self.bake_completed:
                self.bake_completed = True
                self.handle_bake_completion(context)

            # calculate progress
            progress_value = scene.lightmap_baker_objects_index / len(objects_list)    
            scene.lightmap_baker_progress = progress_value

        return {'PASS_THROUGH'}

    def handle_bake_completion(self, context):
        scene = context.scene
        objects_list = scene.lightmap_baker_objects

        # Reset UVs
        for obj_data in objects_list:
            obj = bpy.data.objects.get(obj_data.object)
            if obj:
                obj.data.uv_layers.active_index = scene.active_uv_map_index.lightmap_baker_uv_map_index

        # Complete!
        self.bake_completed = True

        calculate_elapsed_time()

        # Refresh the UI
        context.area.tag_redraw()
        self.cancel(context)

        bpy.app.handlers.object_bake_complete.clear()
        bpy.app.handlers.object_bake_cancel.clear()

        return {'FINISHED'}

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
        if context.scene.lightmap_baker_progress == 1.0:
            self.cancel(context)
            return {'CANCELLED'}
        # Modal stop when task cancelled
        if context.scene.lightmap_baker.cancel_bake:
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

        context.scene.lightmap_baker.cancel_bake = True
        return {'FINISHED'}

def register():
    bpy.utils.register_class(LIGHTMAPBAKER_OT_elapsed_time_modal)
    bpy.utils.register_class(LIGHTMAPBAKER_OT_cancel_bake)
    bpy.utils.register_class(LIGHTMAPBAKER_OT_toggle_lightmap_preview_diffuse)
    bpy.utils.register_class(LIGHTMAPBAKER_OT_remove_single_from_bake_list)
    bpy.utils.register_class(LIGHTMAPBAKER_OT_remove_all_from_bake_list)
    bpy.utils.register_class(LIGHTMAPBAKER_OT_bake_modal)
    bpy.utils.register_class(LIGHTMAPBAKER_OT_clean_invalid_objects)
    bpy.utils.register_class(LIGHTMAPBAKER_OT_add_lightmap_uv)
    bpy.utils.register_class(LIGHTMAPBAKER_OT_select_all_in_list)
    bpy.utils.register_class(LIGHTMAPBAKER_UL_objects_list)
    bpy.utils.register_class(LIGHTMAPBAKER_OT_bake)

    bpy.utils.register_class(LIGHTMAPBAKER_PT_title)
    bpy.utils.register_class(LIGHTMAPBAKER_PT_objects)
    bpy.utils.register_class(LIGHTMAPBAKER_PT_settings)
    bpy.utils.register_class(LIGHTMAPBAKER_PT_output)

    bpy.utils.register_class(LIGHTMAPBAKER_OT_add_to_objects_list)
    bpy.utils.register_class(LIGHTMAPBAKER_objects_properties)
    bpy.utils.register_class(LIGHTMAPBAKER_properties)
    bpy.types.Scene.toggle_lightmap_preview_diffuse = bpy.props.PointerProperty(type=LIGHTMAPBAKER_properties)
    bpy.types.Scene.active_uv_map_index = bpy.props.PointerProperty(type=LIGHTMAPBAKER_properties)
    bpy.utils.register_class(LIGHTMAPBAKER_OT_remove_lightmap_nodes)
    bpy.types.Scene.lightmap_baker = bpy.props.PointerProperty(type=LIGHTMAPBAKER_properties)
    bpy.types.Scene.lightmap_baker_objects = bpy.props.CollectionProperty(type=LIGHTMAPBAKER_objects_properties)
    bpy.types.Scene.time_start = bpy.props.PointerProperty(type=LIGHTMAPBAKER_properties)
    bpy.types.Scene.elapsed_time = bpy.props.PointerProperty(type=LIGHTMAPBAKER_properties)
    bpy.types.Scene.cancel_bake = bpy.props.PointerProperty(type=LIGHTMAPBAKER_properties)
    

    bpy.types.Scene.lightmap_baker_margin = bpy.props.IntProperty(
        name="Margin",
        default=6,
        min=0,
        max=64,
        description="Extend the baked result as a post process filter",
    )

    bpy.types.Scene.lightmap_baker_uv_map_index = bpy.props.IntProperty(
        name="Active UV Map Index",
        description="Active UV Map Index",
        default=0,
        min=0,
        max=1,
    )

    bpy.types.Scene.lightmap_baker_objects_index = bpy.props.IntProperty(
        name="Index", 
        description="Index of the selected object in the bake list", 
        default=0
    )

    bpy.types.Scene.lightmap_baker_resolution = bpy.props.EnumProperty(
        items=[
            ('512', '512', 'Bake at 512x512 resolution'),
            ('1024', '1024', 'Bake at 1024x1024 resolution'),
            ('2048', '2048', 'Bake at 2048x2048 resolution'),
            ('4096', '4096', 'Bake at 4096x4096 resolution'),
        ],
        name="Resolution",
        description="Choose bake resolution",
        default='1024',
    )

    bpy.types.Scene.lightmap_baker_texture_name = bpy.props.StringProperty(
        name="Texture Name",
        description="Name of the baked lightmap texture",
        default="Lightmap"
    )

    bpy.types.Scene.lightmap_baker_render_device = bpy.props.EnumProperty(
        items=[
            ('CPU', 'CPU', 'Render using CPU'),
            ('GPU', 'GPU Compute', 'Render using GPU'),
        ],
        name="Device",
        description="Choose render device",
        default='GPU',
    )

    bpy.types.Scene.lightmap_baker_sample_count = bpy.props.IntProperty(
        name="Sample Count",
        description="Number of samples for baking",
        default=128,
        min=1,
    )

    bpy.types.Scene.lightmap_baker_progress = bpy.props.FloatProperty(
        name="Progress",
        description="Baking progress",
        default=0.0,
        min=0.0,
        max=1.0,
        subtype='PERCENTAGE',
    )

    bpy.types.Scene.lightmap_baker_export_enabled = bpy.props.BoolProperty(
        name="Export Texture",
        description="Export lightmap image after baking",
        default=False,
    )

    bpy.types.Scene.lightmap_baker_preview_diffuse = bpy.props.BoolProperty(
        name="Lightmap Preview",
        description="Toggle Lightmap Preview",
        default=False,
    )

def unregister():

    bpy.utils.unregister_class(LIGHTMAPBAKER_OT_elapsed_time_modal)
    bpy.utils.unregister_class(LIGHTMAPBAKER_OT_cancel_bake)
    bpy.utils.unregister_class(LIGHTMAPBAKER_OT_toggle_lightmap_preview_diffuse)
    bpy.utils.unregister_class(LIGHTMAPBAKER_OT_remove_single_from_bake_list)
    bpy.utils.unregister_class(LIGHTMAPBAKER_OT_remove_all_from_bake_list)
    bpy.utils.unregister_class(LIGHTMAPBAKER_OT_bake_modal)
    bpy.utils.unregister_class(LIGHTMAPBAKER_OT_clean_invalid_objects)
    bpy.utils.unregister_class(LIGHTMAPBAKER_OT_add_lightmap_uv)
    bpy.utils.unregister_class(LIGHTMAPBAKER_OT_select_all_in_list)
    bpy.utils.unregister_class(LIGHTMAPBAKER_UL_objects_list)

    bpy.utils.unregister_class(LIGHTMAPBAKER_PT_title)
    bpy.utils.unregister_class(LIGHTMAPBAKER_PT_objects)
    bpy.utils.unregister_class(LIGHTMAPBAKER_PT_settings)
    bpy.utils.unregister_class(LIGHTMAPBAKER_PT_output)

    bpy.utils.unregister_class(LIGHTMAPBAKER_OT_bake)
    bpy.utils.unregister_class(LIGHTMAPBAKER_OT_add_to_objects_list)
    bpy.utils.unregister_class(LIGHTMAPBAKER_objects_properties)
    bpy.utils.unregister_class(LIGHTMAPBAKER_OT_remove_lightmap_nodes)
    bpy.utils.unregister_class(LIGHTMAPBAKER_properties)

    del bpy.types.Scene.lightmap_baker
    del bpy.types.Scene.lightmap_baker_objects_index
    del bpy.types.Scene.lightmap_baker_objects
    del bpy.types.Scene.lightmap_baker_preview_diffuse
    del bpy.types.Scene.lightmap_baker_resolution
    del bpy.types.Scene.lightmap_baker_texture_name
    del bpy.types.Scene.lightmap_baker_render_device
    del bpy.types.Scene.lightmap_baker_sample_count
    del bpy.types.Scene.lightmap_baker_progress
    del bpy.types.Scene.lightmap_baker_uv_map_index
    del bpy.types.Scene.time_start
    del bpy.types.Scene.elapsed_time
    del bpy.types.Scene.cancel_bake
    del bpy.types.Scene.lightmap_baker_export_enabled

if __name__ == '__main__':
    register()
