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
        # Add your menu items here

class LIGHTMAPBAKER_MT_preview_context_menu(bpy.types.Menu):
    bl_label = "Preview Settings"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene.lightmap_baker_properties, "automatic_lightmap_preview", text="Automatically Preview Lightmaps", toggle=True)
        print(scene.lightmap_baker_properties.automatic_lightmap_preview)


class LIGHTMAPBAKER_PT_objects(LIGHTMAPBAKER_PT_main, bpy.types.Panel):
    bl_parent_id = "LIGHTMAPBAKER_PT_Panel"
    bl_label = "Objects"

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=False)
        row.operator("object.add_to_bake_list", text="Add Objects")
        row.operator("object.clear_bake_list", text="Clear List")
        
       
        row = layout.row(align=False)
        row.template_list("LIGHTMAPBAKER_UL_objects_list", "", context.scene, "lightmap_baker_objects",
                          context.scene.lightmap_baker_properties, "objects_index", sort_reverse=True)

        # ow = layout.column(align=False)
        # ow.operator("object.clean_all_invalid_objects", text="", icon='BRUSH_DATA')
        # ow = layout.column(align=True)
        # ow.operator("object.toggle_lightmap_preview_diffuse", text="", icon='SHADING_TEXTURE', depress=context.scene.lightmap_baker_properties.preview_diffuse)

        col = row.column(align=True)

        col.operator("object.select_all_in_list", text="", icon='RESTRICT_SELECT_OFF')
        col.separator()
        col.operator("object.clean_all_invalid_objects", icon='BRUSH_DATA', text="")
        col.separator()
        col.operator("object.toggle_lightmap_preview_diffuse", icon='SHADING_TEXTURE', text="")
        col.menu("LIGHTMAPBAKER_MT_preview_context_menu", icon='DOWNARROW_HLT', text="")

        
        # Add Lightmap UV button
        row = layout.row(align=True)
        row.operator("object.add_lightmap_uv", text="Add Lightmap UV")

        # Switch UV Index button
        row = layout.row(align=True)
        row.label(icon='GROUP_UVS', text="Active UV:")
        row.prop(context.scene.lightmap_baker_properties, "lightmap_baker_uv_map_index", text="", emboss=True)
        
        # Button to clean lightmap nodes and Lightmap UVs
        row = layout.row(align=True)
        row.operator("object.remove_lightmap_nodes", text="Remove Lightmap Nodes")

class LIGHTMAPBAKER_UL_objects_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        obj = bpy.data.objects.get(item.object)
        if obj:
            layout.label(text=obj.name, icon='CUBE')
            layout.operator("object.remove_single_from_bake_list", text="", icon='X', emboss=False).index = index  # Change here
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

class LIGHTMAPBAKER_PT_output(LIGHTMAPBAKER_PT_main, bpy.types.Panel):
    bl_parent_id = "LIGHTMAPBAKER_PT_Panel"
    bl_label = "Output"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Lightmap Baker'

    def draw(self, context):
        layout = self.layout
        self.context = context

        # Export options
        row = layout.row(align=True)
        row.enabled = False
        row.prop(context.scene.lightmap_baker_properties, "export_enabled", text="Export Texture")
        #if context.scene.lightmap_baker_properties.export_enabled:
        #    row = layout.row(align=True)
        #    row.prop(context.scene.lightmap_baker_properties.export_enabled, "export_path", text="Export Path")

        # Baking Progress
        current_index = context.scene.lightmap_baker_properties.objects_index
        total_objects = len(context.scene.lightmap_baker_objects)
        progress_value = context.scene.lightmap_baker_properties.bake_progress
        aborting = context.scene.lightmap_baker_properties.cancel_bake and context.scene.lightmap_baker_properties.bake_in_progress
        canceled = context.scene.lightmap_baker_properties.cancel_bake and not context.scene.lightmap_baker_properties.bake_in_progress
        
        # Bake and Cancel 
        row = layout.row(align=False)
        row.scale_y = 1.5 

        if not context.scene.lightmap_baker_properties.bake_in_progress and not aborting and not canceled and progress_value != 1.0:
            icon='RENDER_STILL'
            operator_text = "Bake!"
            operator_object = "object.bake_operator"
            progress_text = f"({0}/{total_objects} Objects)"

        elif aborting:
            row.enabled = False
            icon='NONE'
            operator_text = "Aborting..."
            operator_object = "object.bake_operator"
            progress_text = f"{progress_value * 100:.0f}% ({current_index}/{total_objects} Objects)"

        elif canceled:
            icon='RENDER_STILL'
            operator_text = "Bake!"
            operator_object = "object.bake_operator"
            progress_text = "Canceled!"

        elif progress_value != 1.0 and context.scene.lightmap_baker_properties.bake_in_progress:
            row.alert = True
            icon='CANCEL'
            operator_text = "Cancel"
            operator_object = "object.cancel_bake"
            progress_text = f"{progress_value * 100:.0f}% ({current_index}/{total_objects} Objects)"

        else:
            icon='RENDER_STILL'
            operator_text = "Bake!"
            operator_object = "object.bake_operator"
            progress_text = "Completed!"

        row.operator(operator_object, text=operator_text, icon=icon, emboss=True)
        layout.progress(factor=progress_value, text=progress_text)


        # Display elapsed time 00:00.00
        layout.label(text=f"Elapsed Time: {format_time(context.scene.lightmap_baker_properties.elapsed_time)}") 


def format_time(seconds):
    minutes, seconds = divmod(seconds, 60)
    return f"{int(minutes):02d}:{int(seconds):02d}.{int((seconds - int(seconds)) * 100):02d}"


classes = [
    LIGHTMAPBAKER_PT_title,
    LIGHTMAPBAKER_PT_objects,
    LIGHTMAPBAKER_UL_objects_list,
    LIGHTMAPBAKER_PT_settings,
    LIGHTMAPBAKER_PT_output,
    LightmapBakerMenu,
    LIGHTMAPBAKER_MT_preview_context_menu,
]

def register():

    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():

    for cls in classes:
        bpy.utils.unregister_class(cls)