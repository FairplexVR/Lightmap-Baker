import bpy

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
        
                if obj and obj.data.materials:
                    # Disconnect lightmap from shader output before baking
                    for material_slot in obj.material_slots:
                        disconnect_lightmap_from_shader_output(material_slot.material)

                    # Update the property value and call the update function
                    context.scene.only_lightmap_preview.lightmap_baker_lightmap_preview = False
                    update_preview_toggle(self, context)

                    if not context.scene.lightmap_baker_texture_name:
                        self.report({'ERROR'}, "Please provide a texture name.")
                        return {'CANCELLED'}

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

                    bpy.context.scene.cycles.device = context.scene.lightmap_baker_render_device
                    bpy.context.scene.cycles.samples = sample_count

                    # Select the second UV map
                    uv_map_name = obj.data.uv_layers[1].name
                    obj.data.uv_layers.active_index = 1

                    self.bake_diffuse(context, obj, new_image, uv_map_name)

                    print(f"Baking completed for object '{obj.name}' ({index}/{len(objects_to_bake)})")

            return {'FINISHED'}


    def bake_diffuse(self, context, obj, new_image, uv_map_name):
        # Set the current object as active
        bpy.context.view_layer.objects.active = obj

        for material_slot in obj.material_slots:
            material = material_slot.material

            if material.use_nodes:
                uvmap_node = create_uvmap_node(material, uv_map_name)
                texture_node = create_texture_node(material, new_image, uvmap_node)
                material.node_tree.nodes.active = texture_node

                # Check if the nodes are created successfully
                if uvmap_node is None or texture_node is None:
                    self.report({'ERROR'},
                                f"Failed to create nodes for object '{obj.name}'. Aborting bake for this object.")
                    return {'CANCELLED'}

                # Adjust bake settings
                bpy.context.scene.render.bake.use_pass_direct = True
                bpy.context.scene.render.bake.use_pass_indirect = True

                bpy.ops.object.bake('INVOKE_DEFAULT', type='DIFFUSE')

                bpy.context.view_layer.update()

                nodes_to_remove = [node for node in material.node_tree.nodes if
                                   node.type == 'TEX_IMAGE' and node.name.startswith('BakeTextureNode_')]
                for node in nodes_to_remove:
                    material.node_tree.nodes.remove(node)

        # Print a message after each object is baked
        print(f"Object '{obj.name}' baked successfully.")

class LightmapBakerProperties(bpy.types.PropertyGroup):
    lightmap_baker_objects_index: bpy.props.IntProperty(
        name="Index",
        description="Index of the selected object in the bake list",
        default=0,
    )

    lightmap_baker_lightmap_preview: bpy.props.BoolProperty(
        name="Lightmap Preview",
        description="Toggle Lightmap Preview",
        default=False,
        update=lambda self, context: update_preview_toggle(self, context)
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
            ('GPU', 'GPU', 'Render using GPU'),
        ],
        name="Render Device",
        description="Choose render device",
        default='GPU',
    )

    lightmap_baker_sample_count: bpy.props.IntProperty(
        name="Sample Count",
        description="Number of samples for baking",
        default=128,
        min=1,
    )

class OBJECT_UL_bake_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        obj = bpy.data.objects.get(item.object)
        if obj:
            icon = 'OBJECT_DATAMODE'  # Default icon for objects
            obj_type = obj.type

            # Map Blender object types to icons
            type_icons = {
                'MESH': 'MESH_DATA',
                'CURVE': 'CURVE_DATA',
                'SURFACE': 'SURFACE_DATA',
                'META': 'META_BALL',
                'FONT': 'FONT_DATA',
                'ARMATURE': 'ARMATURE_DATA',
                'LATTICE': 'LATTICE_DATA',
                'EMPTY': 'EMPTY_DATA',
                # Add more types as needed
            }

            if obj_type in type_icons:
                icon = type_icons[obj_type]

            layout.label(text=obj.name, icon=icon)
        else:
            layout.label(text="Invalid Object", icon='ERROR')

class PT_Panel(bpy.types.Panel):
    bl_label = "Lightmap Baker"
    bl_idname = "LIGHTMAPBAKER_PT_B"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Lightmap Baker'

    def draw(self, context):
        layout = self.layout

        # Bake button goes first
        row = layout.row(align=True)
        sub_row = row.row(align=True)
        sub_row.scale_y = 1.5  # Adjust the scale factor as needed
        sub_row.operator("object.bake_operator", text="Bake!", emboss=True)
        # Add Lightmap Preview toggle button to the right of the Bake button
        sub_row.scale_x = 2.0  # Adjust the scale factor for the icon      
        sub_row.prop(context.scene.only_lightmap_preview, "lightmap_baker_lightmap_preview", text="", icon='SHADING_RENDERED', toggle=True, emboss=True)

        row = layout.row(align=True)
        row.operator("object.add_to_bake_list", text="Add Objects")
        row.operator("object.clear_bake_list", text="Clear List")

        layout.template_list("OBJECT_UL_bake_list", "", context.scene, "lightmap_baker_objects",
                             context.scene, "lightmap_baker_objects_index")
        
        # Add a button to clean all invalid objects at once
        row.operator("object.clean_all_invalid_objects", text="", icon='BRUSH_DATA')

        # Add a button to select all objects in the list
        layout.operator("object.select_all_in_list", text="Select All in List")

        row = layout.row(align=True)
        row.label(text="Texture Name:")
        row.prop(context.scene, "lightmap_baker_texture_name", text="")

        # Add Lightmap UV button
        row = layout.row(align=True)
        add_uv_button = row.operator("object.add_lightmap_uv", text="Add Lightmap UV")
    
        # Switch UV Index button inside Add Lightmap UV button
        add_uv_button = row.row(align=True)
        add_uv_button.operator("object.switch_uv_index", text="", icon='UV_SYNC_SELECT')

        # Rest of the UI elements
        row = layout.row(align=True)
        row.label(text="Resolution:")
        row.prop(context.scene, "lightmap_baker_resolution", text="")

        row = layout.row(align=True)
        row.label(text="Render Device:")
        row.prop(context.scene, "lightmap_baker_render_device", text="", toggle=True)

        row = layout.row(align=True)
        row.label(text="Sample Count:")
        row.prop(context.scene, "lightmap_baker_sample_count", text="")
        # Add space after the button using a box
        
        # Button to clean lightmap nodes and Lightmap UVs
        row = layout.row(align=True)
        row.operator("object.clean_lightmap_nodes", text="Remove Lightmap Nodes")


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


class ClearBakeListOperator(bpy.types.Operator):
    bl_idname = "object.clear_bake_list"
    bl_label = "Clear List"

    def execute(self, context):
        context.scene.lightmap_baker_objects.clear()
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

class SwitchUVIndexOperator(bpy.types.Operator):
    bl_idname = "object.switch_uv_index"
    bl_label = "Select UV"

    def execute(self, context):
        context.scene.lightmap_baker_uv_index = (context.scene.lightmap_baker_uv_index + 1) % 2
        for obj_name in context.scene.lightmap_baker_objects:
            obj = bpy.data.objects.get(obj_name.object)
            if obj:
                # Switch between the available UV maps
                uv_index = context.scene.lightmap_baker_uv_index
                uv_index = min(uv_index, len(obj.data.uv_layers) - 1)  # Ensure UV index is valid
                print(obj.name)
                obj.data.uv_layers.active_index = uv_index
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

def register():
    bpy.utils.register_class(CleanAllInvalidObjectsOperator)
    bpy.utils.register_class(AddLightmapUVOperator)
    bpy.utils.register_class(SwitchUVIndexOperator)
    bpy.utils.register_class(SelectAllInListOperator)
    bpy.utils.register_class(OBJECT_UL_bake_list)
    bpy.utils.register_class(Operator)
    bpy.utils.register_class(PT_Panel)
    bpy.utils.register_class(AddToBakeListOperator)
    bpy.utils.register_class(ClearBakeListOperator)
    bpy.utils.register_class(LightmapBakerObjectsProperty)
    bpy.utils.register_class(LightmapBakerProperties)
    bpy.types.Scene.only_lightmap_preview = bpy.props.PointerProperty(type=LightmapBakerProperties)
    bpy.utils.register_class(CleanLightmapNodesOperator)

    bpy.types.Scene.lightmap_baker_objects_index = bpy.props.IntProperty(name="Index", description="Index of the selected object in the bake list", default=0)
    bpy.types.Scene.lightmap_baker_objects = bpy.props.CollectionProperty(type=LightmapBakerObjectsProperty)
    bpy.types.Scene.lightmap_baker_lightmap_preview = bpy.props.BoolProperty(name="Lightmap Preview", description="Toggle Lightmap Preview", default=False, update=update_preview_toggle)

    bpy.types.Scene.lightmap_baker_uv_index = bpy.props.IntProperty(
        name="Select UV",
        description="Switch between UV maps",
        default=0,
        min=0,
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
            ('GPU', 'GPU', 'Render using GPU'),
        ],
        name="Render Device",
        description="Choose render device",
        default='GPU',
    )

    bpy.types.Scene.lightmap_baker_sample_count = bpy.props.IntProperty(
        name="Sample Count",
        description="Number of samples for baking",
        default=128,
        min=1,
    )

    bpy.types.Scene.lightmap_baker_lightmap_preview = bpy.props.BoolProperty(
        name="Lightmap Preview",
        description="Toggle Lightmap Preview",
        default=False,
        update=update_preview_toggle
    )


def unregister():
    bpy.utils.unregister_class(CleanAllInvalidObjectsOperator)
    bpy.utils.unregister_class(AddLightmapUVOperator)
    bpy.utils.unregister_class(SwitchUVIndexOperator)
    bpy.utils.unregister_class(SelectAllInListOperator)
    bpy.utils.unregister_class(OBJECT_UL_bake_list)
    bpy.utils.unregister_class(Operator)
    bpy.utils.unregister_class(PT_Panel)
    bpy.utils.unregister_class(AddToBakeListOperator)
    bpy.utils.unregister_class(ClearBakeListOperator)
    bpy.utils.unregister_class(LightmapBakerObjectsProperty)
    bpy.utils.unregister_class(LightmapBakerProperties)
    bpy.utils.unregister_class(CleanLightmapNodesOperator)

    del bpy.types.Scene.lightmap_baker_objects_index
    del bpy.types.Scene.lightmap_baker_objects
    del bpy.types.Scene.lightmap_baker_lightmap_preview
    del bpy.types.Scene.lightmap_baker_uv_index
    del bpy.types.Scene.lightmap_baker_resolution
    del bpy.types.Scene.lightmap_baker_texture_name
    del bpy.types.Scene.lightmap_baker_render_device
    del bpy.types.Scene.lightmap_baker_sample_count

if __name__ == '__main__':
    register()
