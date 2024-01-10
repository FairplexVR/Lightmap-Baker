import bpy

class LIGHTMAPBAKER_PT_main():
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
        
class LightmapBakerMenu(bpy.types.Menu):
    bl_idname = "LIGHTMAPBAKER_MT_LightmapBakerMenu"
    bl_label = "Lightmap Baker Menu"

    def draw(self, context):
        layout = self.layout
        

class LIGHTMAPBAKER_PT_objects(LIGHTMAPBAKER_PT_main, bpy.types.Panel):
    bl_parent_id = "LIGHTMAPBAKER_PT_Panel"
    bl_label = "Objects"

    def draw(self, context):
        layout = self.layout
        layout.enabled = not context.scene.lightmap_baker_properties.busy

        row = layout.row(align=False)
        row.operator("object.add_to_bake_list", text="Add Objects")
        row.operator("object.clear_bake_list", text="Clear List")
        
        row = layout.row(align=False)
        row.enabled = not context.scene.lightmap_baker_properties.bake_in_progress
        row.template_list("LIGHTMAPBAKER_UL_objects_list", "", context.scene, "lightmap_baker_objects",
                          context.scene.lightmap_baker_properties, "objects_index")

        col = row.column(align=True)
        col.operator("object.select_all_in_list", text="", icon='RESTRICT_SELECT_OFF')
        col.separator()
        col.operator("object.clean_all_invalid_objects", icon='BRUSH_DATA', text="")
        col.separator()
        col.operator("object.toggle_lightmap_preview_diffuse", icon='SHADING_TEXTURE', text="", depress=context.scene.lightmap_baker_properties.preview_diffuse_enabled)
        # col.operator("object.toggle_lightmap_preview_diffuse", icon='SHADING_RENDERED', text="", depress=context.scene.lightmap_baker_properties.preview_diffuse_enabled)
        col.separator()
        col.menu("LIGHTMAPBAKER_MT_preview_context_menu", icon='DOWNARROW_HLT', text="")

class LIGHTMAPBAKER_PT_uv(bpy.types.Panel):
    bl_parent_id = "LIGHTMAPBAKER_PT_Panel"
    bl_label = "Lightmap UV"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Lightmap Baker'

    def draw(self, context):
        layout = self.layout
        layout.enabled = not context.scene.lightmap_baker_properties.busy

        # Add/Delete UVs
        row = layout.row(align=False)
        row.operator("object.add_lightmap_uv", text="Add Lightmap UVs", icon='ADD')
        row.operator("object.delete_lightmap_uv",  text="Delete Lightmap UVs", icon='REMOVE')
        
        # Rename UV
        col = layout.column(align=True)
        
        # Create a row to hold the label, property, and button
        row = col.row(align=True)
        row.label(text="UVMap Name")
        row.prop(context.scene.lightmap_baker_properties, "lightmap_baker_uv_map_name", text="")
        row.scale_x = 0.5
        row.operator("object.set_lightmap_uv_name", text="Set")

        # Switch UV Index
        row = layout.row(align=True)
        row.label(text="Active UV:")
        row.prop(context.scene.lightmap_baker_properties, "lightmap_baker_uv_map_index", text="")
        row.scale_x = 0.5
        row.operator("object.set_lightmap_uv_index", text="Set")

class LIGHTMAPBAKER_PT_filtering(LIGHTMAPBAKER_PT_main, bpy.types.Panel):
    bl_parent_id = "LIGHTMAPBAKER_PT_Panel"
    bl_label = "Filtering"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Lightmap Baker'

    def draw(self, context):
        layout = self.layout
        layout.enabled = not context.scene.lightmap_baker_properties.busy

        col  = layout.column(align=False)
        col.enabled = False
        col.prop(context.scene.lightmap_baker_properties, "filtering_denoise", text="Denoise (Not implemented yet)")
        col.prop(context.scene.lightmap_baker_properties, "filtering_bilateral_blur", text="Bilateral Blur (Not implemented yet)")

class LIGHTMAPBAKER_PT_settings(LIGHTMAPBAKER_PT_main, bpy.types.Panel):
    bl_parent_id = "LIGHTMAPBAKER_PT_Panel"
    bl_label = "Settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Lightmap Baker'

    def draw(self, context):

        layout = self.layout
        layout.enabled = not context.scene.lightmap_baker_properties.busy

        row = layout.row(align=True)
        row.label(text="Resolution:")
        row.prop(context.scene.lightmap_baker_properties, "lightmap_resolution", text="")

        row = layout.row(align=True)
        row.label(text="Device:")
        row.prop(context.scene.lightmap_baker_properties, "render_device", text="", toggle=True)
        
        row = layout.row(align=True)
        row.label(text="Sample Count:")
        row.prop(context.scene.lightmap_baker_properties, "sample_count", text="")

        # Add a margin option with a label in front
        row = layout.row(align=True)
        row.label(text="Margin:")
        row.prop(context.scene.lightmap_baker_properties, "bake_margin", text="")

        # Export options
        row = layout.row(align=True)
        row.enabled = False
        row.prop(context.scene.lightmap_baker_properties, "export_enabled", text="Export Texture (Not implemented yet)")
        #if context.scene.lightmap_baker_properties.export_enabled:
        #    row = layout.row(align=True)
        #    row.prop(context.scene.lightmap_baker_properties.export_enabled, "export_path", text="Export Path")

class LIGHTMAPBAKER_PT_bake(LIGHTMAPBAKER_PT_main, bpy.types.Panel):
    bl_parent_id = "LIGHTMAPBAKER_PT_Panel"
    bl_label = "Bake"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Lightmap Baker'

    def draw(self, context):
        layout = self.layout
        self.context = context

        # Baking Progress
        current_index = context.scene.lightmap_baker_properties.objects_index
        total_objects = len(context.scene.lightmap_baker_objects)
        progress_value = context.scene.lightmap_baker_properties.bake_progress

        # States
        idle = not context.scene.lightmap_baker_properties.busy and not progress_value == 1.0
        baking = context.scene.lightmap_baker_properties.busy and not context.scene.lightmap_baker_properties.cancel_bake
        aborting = context.scene.lightmap_baker_properties.bake_in_progress and context.scene.lightmap_baker_properties.cancel_bake
        canceled = context.scene.lightmap_baker_properties.cancel_bake and not context.scene.lightmap_baker_properties.bake_in_progress and context.scene.lightmap_baker_properties.busy
        completed = progress_value == 1.0
        # Bake and Cancel 
        row = layout.row(align=False)
        row.scale_y = 1.5 

        if idle:
            icon='RENDER_STILL'
            operator_text = "Bake!"
            operator_object = "object.bake_operator"
            progress_text = f"({0}/{total_objects} Objects)"


        elif baking:
            row.alert = True
            icon='CANCEL'
            operator_text = "Cancel"
            operator_object = "object.cancel_bake"
            progress_text = f"{progress_value * 100:.0f}% ({current_index}/{total_objects} Objects)"

        elif aborting:
            row.enabled = False
            icon='NONE'
            operator_text = "Aborting..."
            operator_object = "object.bake_operator"
            progress_text = f"{progress_value * 100:.0f}% ({current_index}/{total_objects} Objects)"

        elif canceled:
            row.enabled = True
            icon='RENDER_STILL'
            operator_text = "Bake!"
            operator_object = "object.bake_operator"
            progress_text = "Canceled!"

        elif completed:
            row.enabled = True
            icon='RENDER_STILL'
            operator_text = "Bake!"
            operator_object = "object.bake_operator"
            progress_text = "Completed!"

        row.operator(operator_object, text=operator_text, icon=icon, emboss=True)
        layout.progress(factor=progress_value, text=progress_text)

        # Display elapsed time 00:00.00
        layout.label(text=f"Elapsed Time: {format_time(context.scene.lightmap_baker_properties.elapsed_time)}") 

        
class LIGHTMAPBAKER_MT_preview_context_menu(bpy.types.Menu):
    bl_label = "Preview Settings"

    def draw(self, context):
        layout = self.layout

        layout.operator("object.remove_lightmap_nodes", text="Remove Lightmap Nodes")
        layout.prop(context.scene.lightmap_baker_properties, "automatic_lightmap_preview", text="Automatically Preview Lightmaps", toggle=True)

class LIGHTMAPBAKER_UL_objects_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        obj = bpy.data.objects.get(item.objects_list)
        if obj:
            layout.label(text=obj.name, icon='CUBE')
            layout.operator("object.remove_single_from_bake_list", text="", icon='X', emboss=False).index = index  # Change here
        else:
            layout.label(text="Invalid Object", icon='ERROR')


def format_time(seconds):
    minutes, seconds = divmod(seconds, 60)
    return f"{int(minutes):02d}:{int(seconds):02d}.{int((seconds - int(seconds)) * 100):02d}"


classes = [
    LIGHTMAPBAKER_PT_title,
    LIGHTMAPBAKER_PT_objects,
    LIGHTMAPBAKER_UL_objects_list,
    LIGHTMAPBAKER_PT_uv,
    LIGHTMAPBAKER_PT_filtering,
    LIGHTMAPBAKER_PT_settings,
    LIGHTMAPBAKER_PT_bake,
    LightmapBakerMenu,
    LIGHTMAPBAKER_MT_preview_context_menu,
]

def register():

    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():

    for cls in classes:
        bpy.utils.unregister_class(cls)