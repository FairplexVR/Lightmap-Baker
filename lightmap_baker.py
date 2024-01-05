import bpy

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

    bpy.ops.object.bake('INVOKE_DEFAULT', type='DIFFUSE', use_clear=False)

def on_complete(dummy):
    global bake_in_progress
    bake_in_progress = False


def clear_baked_texture(context):
    # Clear the baked texture by setting all pixels to black
    image = bpy.data.images.get(context.scene.lightmap_baker_texture_name)
    if image:
        pixels = [0.0] * (image.size[0] * image.size[1] * 4)  # Assuming RGBA image
        image.pixels = pixels
        image.update()

def update_preview_toggle(self, context):
    for obj_name in context.scene.lightmap_baker_objects:
        obj = bpy.data.objects.get(obj_name.object)
        if obj:
            material = obj.active_material
            texture_node = material.node_tree.nodes.get("Bake_Texture_Node")

            if texture_node is None:
                # If there's no texture node, there's nothing to preview
                return

            if context.scene.only_lightmap_preview.lightmap_baker_lightmap_preview:
                connect_lightmap_to_shader_output(material, texture_node)
            else:
                disconnect_lightmap_from_shader_output(material)

def create_texture_node(mat, new_image, uvmap_node):
    nodes = mat.node_tree.nodes
    texture_node = nodes.get("Bake_Texture_Node")

    if not texture_node:
        # Add the Lightmap texture node
        texture_node = nodes.new(type='ShaderNodeTexImage')
        texture_node.name = 'Bake_Texture_Node'
        texture_node.image = new_image

    # Connect UVMap node to the lightmap image
    mat.node_tree.links.new(uvmap_node.outputs["UV"], texture_node.inputs["Vector"])

    # Set the active node within the material nodes
    mat.node_tree.nodes.active = texture_node

    return texture_node

def create_uvmap_node(mat, uv_map_name):
    nodes = mat.node_tree.nodes
    uvmap_node = nodes.get("Bake_UVMap_Node")

    if not uvmap_node:
        uvmap_node = nodes.new(type='ShaderNodeUVMap')
        uvmap_node.name = 'Bake_UVMap_Node'

        # Adjust the position relative to the texture_node
        uvmap_node.location = uvmap_node.location.x - 250.0, uvmap_node.location.y - 145.0
        uvmap_node.uv_map = uv_map_name

    return uvmap_node

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
    
class Operator(bpy.types.Operator):
    bl_idname = "object.bake_operator"
    bl_label = "Bake!"
    bl_description = "Bake objects in the list"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        global bake_in_progress

        # Reset Bake Progression and index
        context.scene.lightmap_baker_progress = 0.0
        context.scene.lightmap_baker_objects_index = 0

        clear_baked_texture(context)

        # Check if any selected object is missing the second UV map
        objects_to_bake = [obj_name.object for obj_name in context.scene.lightmap_baker_objects]

        invalid_objects = [obj_name for obj_name in objects_to_bake if bpy.data.objects.get(obj_name) is None]

        if invalid_objects:
            self.report({'ERROR'}, f"Invalid objects found in the bake list.")
            return {'CANCELLED'}

        objects_missing_uv = [obj_name for obj_name in objects_to_bake
                              if len(bpy.data.objects.get(obj_name).data.uv_layers) < 2]

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
        else:
            # Select all objects in the bake list
            bpy.ops.object.select_all(action='DESELECT')
            for obj_name in objects_to_bake:
                bpy.data.objects[obj_name].select_set(True)

            for index, obj_name in enumerate(objects_to_bake, start=1):
                obj = bpy.data.objects.get(obj_name)
                resolution_options = {
            '512': 512,
            '1024': 1024,
            '2048': 2048,
            '4096': 4096,
            }
            resolution = resolution_options.get(context.scene.lightmap_baker_resolution, 1024)
            sample_count = context.scene.lightmap_baker_sample_count
    
            existing_image = bpy.data.images.get(context.scene.lightmap_baker_texture_name)
    
            if existing_image and existing_image.size[0] == resolution and existing_image.size[1] == resolution:
                new_image = existing_image
            else:
                if existing_image:
                    bpy.data.images.remove(existing_image)
    
                new_image = bpy.data.images.new(name=context.scene.lightmap_baker_texture_name,
                                                width=resolution, height=resolution, float_buffer=True)
                new_image.colorspace_settings.name = 'Linear Rec.709'
                new_image.use_view_as_render = True
                new_image.file_format = 'OPEN_EXR'
    
            # Set the active object outside the loop
            bpy.ops.object.select_all(action='DESELECT')
            active_object = bpy.data.objects.get(objects_to_bake[0])
            active_object.select_set(True)
            context.view_layer.objects.active = active_object
    
            for obj_name in objects_to_bake:
                obj = bpy.data.objects.get(obj_name)
                
                if obj and obj.data.materials:
                
                    # Disconnect lightmap from shader output before baking
                    for material_slot in obj.material_slots:
                        material = material_slot.material
    
                        if material.use_nodes:
                            uv_map_name = obj.data.uv_layers[1].name
                            uvmap_node = create_uvmap_node(material, uv_map_name)
                            texture_node = create_texture_node(material, new_image, uvmap_node)
                            material.node_tree.nodes.active = texture_node
    
                    # Update the property value and call the update function
                    context.scene.only_lightmap_preview.lightmap_baker_lightmap_preview = False
                    update_preview_toggle(self, context)
    
                    if not context.scene.lightmap_baker_texture_name:
                        self.report({'ERROR'}, "Please provide a texture name.")
                        return {'CANCELLED'}
    
                    bpy.context.scene.cycles.device = context.scene.lightmap_baker_render_device
                    bpy.context.scene.cycles.samples = sample_count
    
                    # Select the second UV map
                    uv_map_name = obj.data.uv_layers[1].name
                    obj.data.uv_layers.active_index = 1
    
            # Bake diffuse
            bake_diffuse(context, obj)
            bpy.ops.wm.simple_modal_operator('INVOKE_DEFAULT')
            bake_in_progress = True
    
            return {'FINISHED'}

class LightmapBakerProperties(bpy.types.PropertyGroup):
    lightmap_baker_objects_index: bpy.props.IntProperty(
        name="Index",
        description="Index of the selected object in the bake list",
        default=0,
    )

    lightmap_baker_uv_map_index: bpy.props.IntProperty(
        name="Active UV Map Index",
        description="Active UV Map Index",
        default=0,
        min=0,
        max=1,
        update=update_active_uv_map_index,
    )

    lightmap_baker_lightmap_preview: bpy.props.BoolProperty(
        name="Lightmap Preview",
        description="Toggle Lightmap Preview",
        default=False,
        update=update_preview_toggle,
    )

    export_after_bake: bpy.props.BoolProperty(
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



    
class OBJECT_UL_bake_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        obj = bpy.data.objects.get(item.object)
        if obj:
            layout.label(text=obj.name, icon='OBJECT_DATAMODE')
            layout.operator("object.remove_single_from_bake_list", text="", icon='X').index = index  # Change here
        else:
            layout.label(text="Invalid Object", icon='ERROR')


class OBJECT_OT_remove_single_from_bake_list(bpy.types.Operator):
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

class OBJECT_OT_remove_all_from_bake_list(bpy.types.Operator):
    bl_idname = "object.clear_bake_list"
    bl_label = "Clear List"

    def execute(self, context):
        context.scene.lightmap_baker_objects.clear()
        return {'FINISHED'}

class MAIN_PANEL:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Main Tab"
    bl_options = {"DEFAULT_CLOSED"}

class LIGHTMAPBAKER_PT_PANEL(bpy.types.Panel):
    bl_label = "Lightmap Baker"
    bl_idname = "LIGHTMAPBAKER_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Lightmap Baker'

    def draw(self, context):
        layout = self.layout


class OBJECT_PT_PANEL(MAIN_PANEL, bpy.types.Panel):
    bl_parent_id = "LIGHTMAPBAKER_PT_Panel"
    bl_label = "Objects"

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.operator("object.add_to_bake_list", text="Add Objects")
        row.operator("object.clear_bake_list", text="Clear List")

        layout.template_list("OBJECT_UL_bake_list", "", context.scene, "lightmap_baker_objects",
                             context.scene, "lightmap_baker_objects_index")

        # Add a button to clean all invalid objects at once
        row.operator("object.clean_all_invalid_objects", text="", icon='BRUSH_DATA')

        # Add a button to select all objects in the list
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
        row.operator("object.clean_lightmap_nodes", text="Remove Lightmap Nodes")

class SETTINGS_PT_PANEL(MAIN_PANEL, bpy.types.Panel):
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

class OUTPUT_PT_PANEL(MAIN_PANEL, bpy.types.Panel):
    bl_parent_id = "LIGHTMAPBAKER_PT_Panel"
    bl_label = "Output"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Lightmap Baker'

    def draw(self, context):
        layout = self.layout

        # Export options
        row = layout.row(align=True)
        row.prop(context.scene.only_lightmap_preview, "export_after_bake", text="Export Texture")
        if context.scene.only_lightmap_preview.export_after_bake:
            row = layout.row(align=True)
            row.prop(context.scene.only_lightmap_preview, "export_path", text="Export Path")

        # Bake
        layout.separator()
        row = layout.row(align=True)
        sub_row = row.row(align=True)
        sub_row.scale_y = 1.5  # Adjust the scale factor as needed
        sub_row.operator("object.bake_operator", text="Bake!", emboss=True)

        # Add Lightmap Preview toggle button to the right of the Bake button
        sub_row.scale_x = 2.0  # Adjust the scale factor for the icon      
        sub_row.prop(context.scene.only_lightmap_preview, "lightmap_baker_lightmap_preview", text="", icon='SHADING_RENDERED', toggle=True, emboss=True)

        # Baking Progress
        current_index = context.scene.lightmap_baker_objects_index
        total_objects = len(context.scene.lightmap_baker_objects)
        progress_value = context.scene.lightmap_baker_progress * 100
           
        if bake_in_progress:
            layout.progress(factor=context.scene.lightmap_baker_progress, text=f"{progress_value:.0f}% ({current_index}/{total_objects} Objects)")
        elif progress_value == 0.0:
            layout.progress(text=f"({0}/{total_objects} Objects)")
        else:
            layout.progress(factor=context.scene.lightmap_baker_progress, text="Completed!")

        # Calculate and display elapsed time
        layout.label(text=f"Elapsed Time: ")

class AddToBakeListOperator(bpy.types.Operator):
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
    
class LightmapBakerObjectsProperty(bpy.types.PropertyGroup):
    object: bpy.props.StringProperty()

    
class CleanLightmapNodesOperator(bpy.types.Operator):
    bl_idname = "object.clean_lightmap_nodes"
    bl_label = "Clean Lightmap Nodes"

    def execute(self, context):
        all_materials = bpy.data.materials

        for material in all_materials:
            if material.use_nodes:
                texture_node = material.node_tree.nodes.get("Bake_Texture_Node")

                # Store the reference to the shader output node
                shader_output = find_shader_output_node(material)

                # Update the property value and call the update function
                context.scene.only_lightmap_preview.lightmap_baker_lightmap_preview = False
                update_preview_toggle(None, context)

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

        return {'FINISHED'}

class AddLightmapUVOperator(bpy.types.Operator):
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
                    new_uv_layer.active = True
                elif obj.data.uv_layers[1].name != "Lightmap":
                    # Rename the existing second UV map to "Lightmap"
                    obj.data.uv_layers[1].name = "Lightmap"
        return {'FINISHED'}
    
class SelectAllInListOperator(bpy.types.Operator):
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

class CleanAllInvalidObjectsOperator(bpy.types.Operator):
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

class BakeModalOperator(bpy.types.Operator):
    bl_idname = "wm.simple_modal_operator"
    bl_label = "Simple Modal Operator"

    _timer = None

    def modal(self, context, event):
        global bake_in_progress

        if event.type == 'ESC':
            print("Modal canceled.")
            self.cancel(context)
            return {'CANCELLED'}

        if not bake_in_progress:
            # Access the context to get the scene and objects list
            context = bpy.context
            scene = context.scene
            objects_list = context.scene.lightmap_baker_objects

            # Increment the index for the next object
            scene.lightmap_baker_objects_index += 1

            # Calculate progress
            total_objects = len(objects_list)
            progress_value = scene.lightmap_baker_objects_index / total_objects
            scene.lightmap_baker_progress = progress_value

            # Check if there are more objects in the list
            if scene.lightmap_baker_objects_index < total_objects:
                current_index = scene.lightmap_baker_objects_index

                next_obj_name = objects_list[current_index].object

                # Get the next object
                next_obj = bpy.data.objects.get(next_obj_name)

                if next_obj:
                    # Deselect all objects
                    bpy.ops.object.select_all(action='DESELECT')

                    # Set the next object as active and selected
                    context.view_layer.objects.active = next_obj
                    next_obj.select_set(True)

                    print(f"Baking object {scene.lightmap_baker_objects_index}/{total_objects}")

                    bake_in_progress = True

                    bake_diffuse(context, next_obj)
            else:
                if scene.lightmap_baker_objects_index >= total_objects:
                    print("Bake process complete for all objects.")

                # Reset the UV map to the initial state for all objects
                for obj_name in objects_list:
                    obj = bpy.data.objects.get(obj_name.object)
                    if obj:
                        obj.data.uv_layers.active_index = context.scene.active_uv_map_index.lightmap_baker_uv_map_index

                # Refresh the UI
                for window in bpy.context.window_manager.windows:
                    for area in window.screen.areas:
                        area.tag_redraw()

                self.cancel(context)
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(1.0, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        global bake_in_progress
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        bake_in_progress = False 

def register():
    bpy.app.handlers.object_bake_complete.append(on_complete)
    bpy.utils.register_class(OBJECT_OT_remove_single_from_bake_list)
    bpy.utils.register_class(OBJECT_OT_remove_all_from_bake_list)
    bpy.utils.register_class(BakeModalOperator)
    bpy.utils.register_class(CleanAllInvalidObjectsOperator)
    bpy.utils.register_class(AddLightmapUVOperator)
    bpy.utils.register_class(SelectAllInListOperator)
    bpy.utils.register_class(OBJECT_UL_bake_list)
    bpy.utils.register_class(Operator)

    bpy.utils.register_class(LIGHTMAPBAKER_PT_PANEL)
    bpy.utils.register_class(OBJECT_PT_PANEL)
    bpy.utils.register_class(SETTINGS_PT_PANEL)
    bpy.utils.register_class(OUTPUT_PT_PANEL)

    bpy.utils.register_class(AddToBakeListOperator)
    bpy.utils.register_class(LightmapBakerObjectsProperty)
    bpy.utils.register_class(LightmapBakerProperties)
    bpy.types.Scene.only_lightmap_preview = bpy.props.PointerProperty(type=LightmapBakerProperties)
    bpy.types.Scene.active_uv_map_index = bpy.props.PointerProperty(type=LightmapBakerProperties)
    bpy.utils.register_class(CleanLightmapNodesOperator)
    bpy.types.Scene.lightmap_baker_objects = bpy.props.CollectionProperty(type=LightmapBakerObjectsProperty)

    # Add this line outside of any class definition
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
        update=update_active_uv_map_index,
    )

    bpy.types.Scene.lightmap_baker_lightmap_preview = bpy.props.BoolProperty(
        name="Lightmap Preview",
        description="Toggle Lightmap Preview",
        default=False,
        update=update_preview_toggle,
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
        default=""
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

    

def unregister():
    bpy.app.handlers.object_bake_complete.clear()
    bpy.utils.unregister_class(OBJECT_OT_remove_single_from_bake_list)
    bpy.utils.unregister_class(OBJECT_OT_remove_all_from_bake_list)
    bpy.utils.unregister_class(BakeModalOperator)
    bpy.utils.unregister_class(CleanAllInvalidObjectsOperator)
    bpy.utils.unregister_class(AddLightmapUVOperator)
    bpy.utils.unregister_class(SelectAllInListOperator)
    bpy.utils.unregister_class(OBJECT_UL_bake_list)

    bpy.utils.unregister_class(LIGHTMAPBAKER_PT_PANEL)
    bpy.utils.unregister_class(OBJECT_PT_PANEL)
    bpy.utils.unregister_class(SETTINGS_PT_PANEL)
    bpy.utils.unregister_class(OUTPUT_PT_PANEL)

    bpy.utils.unregister_class(Operator)
    bpy.utils.unregister_class(AddToBakeListOperator)
    bpy.utils.unregister_class(LightmapBakerObjectsProperty)
    bpy.utils.unregister_class(LightmapBakerProperties)
    bpy.utils.unregister_class(CleanLightmapNodesOperator)

    del bpy.types.Scene.lightmap_baker_objects_index
    del bpy.types.Scene.lightmap_baker_objects
    del bpy.types.Scene.lightmap_baker_lightmap_preview
    del bpy.types.Scene.lightmap_baker_resolution
    del bpy.types.Scene.lightmap_baker_texture_name
    del bpy.types.Scene.lightmap_baker_render_device
    del bpy.types.Scene.lightmap_baker_sample_count
    del bpy.types.Scene.lightmap_baker_progress
    del bpy.types.Scene.lightmap_baker_uv_map_index

if __name__ == '__main__':
    register()
