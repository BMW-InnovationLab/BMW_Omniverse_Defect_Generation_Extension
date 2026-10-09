import omni.ui as ui
from omni.ui import color as cl
import omni.kit.notification_manager as nm
from pxr import Sdf
import asyncio
from defect.generation.ui.widgets import MinMaxWidget, PathWidget, RGBMinMaxWidget, PositionMinMaxWidget, CustomDirectory
from defect.generation.utils import helpers
from defect.generation.domain.models.domain_randomization_request import DomainRandomizationRequest, LightDomainRandomizationParameters, CameraDomainRandomizationParameters, ColorDomainRandomizationParameters, MaterialDomainRandomizationParameters
MAX_NUMBER_PRIM_PATH_CHARACTERS_TO_SHOW = 30

class RandomizerParameters():
    def __init__(self) -> None:
        # Light Params
        self.light_intensity = None
        self.light_rotation = None
        self.light_color = None
        self.light_scale = None
        self.light_position = None
        self.light_count_model = ui.SimpleIntModel(1)

        # Camera Params
        self.camera_params_list = []
        self.camera_distance = None

        # Color Params
        self.prim_colors = {}
        
        # Material Params 
        self.material_prims = {} 
        self.created_materials = {}

    def prepare_domain_randomization_request(self) -> DomainRandomizationRequest:
        light_domain_randomization_params = LightDomainRandomizationParameters()
        camera_domain_randomization_params = CameraDomainRandomizationParameters()

        color_domain_randomization_params = ColorDomainRandomizationParameters()
        material_domain_randomization_params = MaterialDomainRandomizationParameters()

        if self.light_cb.get_value_as_bool():
                light_domain_randomization_params.active = True
                if self.light_intensity is not None:
                    light_domain_randomization_params.light_intensity_min_value = self.light_intensity.min_value
                    light_domain_randomization_params.light_intensity_max_value = self.light_intensity.max_value
                if self.light_rotation is not None:
                    light_domain_randomization_params.light_rotation_min_value = self.light_rotation.min_value
                    light_domain_randomization_params.light_rotation_max_value = self.light_rotation.max_value
                if self.light_color is not None:
                    light_domain_randomization_params.light_color_min_value = self.light_color.min_values
                    light_domain_randomization_params.light_color_max_value = self.light_color.max_values
                if self.light_scale is not None:
                    light_domain_randomization_params.light_scale_min_value = self.light_scale.min_value
                    light_domain_randomization_params.light_scale_max_value = self.light_scale.max_value
                if self.light_position is not None:
                    light_domain_randomization_params.light_position_min_value = self.light_position.min_value
                    light_domain_randomization_params.light_position_max_value = self.light_position.max_value
                if self.light_count_model.as_int < 1:
                    nm.post_notification("The Number of Lights Cannot be Less Than 1, Setting the Count to 1", duration=5,
                                      status=nm.NotificationStatus.WARNING)
                    light_domain_randomization_params.light_count = 1
                else:
                    light_domain_randomization_params.light_count = self.light_count_model.as_int
        if self.camera_cb.get_value_as_bool():
            camera_domain_randomization_params.active = True
            if self.camera_distance is not None:
                camera_domain_randomization_params.camera_distance_min_value = self.camera_distance.min_value
                if self.camera_distance.max_value < 0 :
                    nm.post_notification("The Camera Distance Cannot be Negative, Setting it to 5",
                                      duration=5,
                                      status=nm.NotificationStatus.WARNING)
                    camera_domain_randomization_params.camera_distance_max_value = 5
                else:
                    camera_domain_randomization_params.camera_distance_max_value = self.camera_distance.max_value
            if len(self.camera_params_list) != 0:
                # Send the lookat directly if the coordinates were manually specified, or calculate bbox coordinates if a path is given.
                camera_domain_randomization_params.camera_prims = [
    (scatter_prim, lookat_path if lookat_path == "" or isinstance(lookat_path, tuple) else helpers.get_bbox_dimensions(lookat_path))
    for scatter_prim, lookat_path in self.camera_params_list]
            else:
                camera_domain_randomization_params.camera_prims = []

        if self.color_cb.get_value_as_bool(): 
            color_domain_randomization_params.active = True
            if len(self.prim_colors) != 0:
                color_domain_randomization_params.prim_colors = self.prim_colors   
                if self.texture_randomization_cb.get_value_as_bool():
                    color_domain_randomization_params.texture_randomization = True        
            else: 
                color_domain_randomization_params.prim_colors = {}

        if self.material_cb.get_value_as_bool(): 
            material_domain_randomization_params.active = True
            if len(self.material_prims) != 0:
                material_domain_randomization_params.material_prims = self.material_prims   
            else: 
                material_domain_randomization_params.material_prims = {}
            material_domain_randomization_params.created_materials = self.created_materials

        return DomainRandomizationRequest(
            light_domain_randomization_params=light_domain_randomization_params,
            camera_domain_randomization_params=camera_domain_randomization_params,
            color_domain_randomization_params=color_domain_randomization_params,
            material_domain_randomization_params=material_domain_randomization_params
        )

    def add_randomization_checkbox(self, name, callback):
        container = ui.VStack(height=0)
        with container:
            with ui.HStack():
                ui.Label(f"{name} Randomizations")
                cb = ui.CheckBox(name=f"{name} Randomization", width=200).model
                cb.add_value_changed_fn(callback)
        return container, cb
    
    # Check Scatter and Look at Prim values and add them to list. 
    def add_camera_params(self): 
        scattering_prim_path = self.scattering_prim.path_value
        if self.lookat_cb.get_value_as_bool():
            lookat_prim = self.get_manual_lookat()
        else:
            lookat_prim = self.lookat_prim.path_value


        
        # Check if scattering prim path is added and is valid
        if scattering_prim_path:
            if helpers.is_valid_prim(scattering_prim_path):
                scattering_prim_valid = True
            else:
                scattering_prim_valid = False
                nm.post_notification(f"There is no '{scattering_prim_path}' Prim in the stage", hide_after_timeout=True, duration=5, status=nm.NotificationStatus.WARNING)
        # Valid if not provided
        else:
            scattering_prim_valid = True 

        # Check if lookat prim path is added and is valid
        if not self.lookat_cb.get_value_as_bool():
            if lookat_prim:
                if helpers.is_valid_prim(lookat_prim):
                    lookat_prim_valid = True
                else:
                    lookat_prim_valid = False
                    nm.post_notification(f"There is no '{lookat_prim}' Prim in the stage.", hide_after_timeout=True, duration=5, status=nm.NotificationStatus.WARNING)
            # Valid if not provided
            else:
                lookat_prim_valid = True
        else:
            lookat_prim_valid = True

        if not self.lookat_cb.get_value_as_bool():
            if scattering_prim_valid and lookat_prim_valid:
                # Selected Scatter and Look at Prims have to be different.
                if self.scattering_prim.path_value != self.lookat_prim.path_value:
                    new_camera_params = (self.scattering_prim.path_value, self.lookat_prim.path_value)
                    if new_camera_params not in self.camera_params_list:
                        self.camera_params_list.append(new_camera_params)
                        self.view_added_params()

                # If Scatter and Look At prims are the same, send notification and do not add to list.
                else:
                    nm.post_notification("Scatter Prim and Look At Prim cannot be the same.", hide_after_timeout=True, duration=5, status=nm.NotificationStatus.WARNING)
        else:
            new_camera_params = (self.scattering_prim.path_value,lookat_prim)
            if new_camera_params not in self.camera_params_list:
                self.camera_params_list.append(new_camera_params)
                self.view_added_params()

    # Display the added Scatter and Look at Prims in the UI. 
    def view_added_params(self): 
        with self.camera_params: 
            with self.camera_params_frame:
                with ui.VStack(height=0):
                    self.camera_distance = MinMaxWidget("Camera Distance", min_value=0, max_value=10,
                                                        tooltip="Set camera distance if no scattering and look at prims will be provided.")
                    with ui.HStack(height=0):
                        self.scattering_prim = PathWidget("Scattering Prim")
                        self.lookat_prim = PathWidget("Look At Prim")
                    with ui.HStack(height=0):
                        self.lookat_frame = ui.CollapsableFrame("Look at Manual Radnomization Parameters", height=0)
                        with self.lookat_frame:
                            with ui.VStack(height=0):
                                with ui.HStack(height=0):
                                    ui.Label("Use Manual Look At Randomization")
                                    self.lookat_cb = ui.CheckBox(name="Use Manual Coordinates", width=200).model
                                self.x = PositionMinMaxWidget("Manual Coordinate X", min_value=0, max_value=10)
                                self.y = PositionMinMaxWidget("Manual Coordinate Y", min_value=0, max_value=10)
                                self.z = PositionMinMaxWidget("Manual Coordinate Z", min_value=0, max_value=10)
                    
                    with ui.HStack(): 
                        ui.Button("Add", clicked_fn=lambda: self.add_camera_params(), tooltip="Add the Current Scattering Prim and LookAt Prim")
                        ui.Button("Reset", clicked_fn=lambda: self.reset_current_camera_params(), tooltip="Reset the Scattering Prim and LookAt Prim")
                    if self.camera_params_list != []:
                        self.added_camera_params_frame = ui.CollapsableFrame("Added Camera Params")
                        with self.added_camera_params_frame:
                            self.camera_params_list_ui = ui.VStack()
                            with self.camera_params_list_ui: 
                                with ui.HStack(spacing=2):
                                    ui.Label("Scattering Prim", width = 150)
                                    ui.Label("Look At Prim", width = 150)
                                    ui.Label("Look At Prim Center", width = 150)
                            self.update_added_camera_params_ui()
           
    def update_added_camera_params_ui(self):
        def format_number(num):
            return f"{num:.3f}".rstrip('0').rstrip('.')

        with self.added_camera_params_frame: 
            self.camera_params_list_ui.clear()

            with self.camera_params_list_ui:
                with ui.HStack(height=0, spacing=2):
                    ui.Label("Scattering Prim", width = 225)
                    ui.Label("Look At", width = 225)
                    ui.Label("Look At Center", width = 225)

                with ui.HStack():
                    ui.Line(height=ui.Length(20))
                
                for scattering, lookat in self.camera_params_list:
                    with ui.HStack(height=0):
                        ui.Label(f"{str(scattering)[:MAX_NUMBER_PRIM_PATH_CHARACTERS_TO_SHOW]}{'...' if len(str(scattering))>MAX_NUMBER_PRIM_PATH_CHARACTERS_TO_SHOW else ''}", width=225, style={"color": 0xFF777777},tooltip=str(scattering))
                        if not isinstance(lookat, tuple):
                            ui.Label(
                                f"{str(lookat)[:MAX_NUMBER_PRIM_PATH_CHARACTERS_TO_SHOW]}{'...' if len(str(lookat)) > MAX_NUMBER_PRIM_PATH_CHARACTERS_TO_SHOW else ''}",
                                width=225, style={"color": 0xFF777777},tooltip=str(lookat))
                            if lookat != "":
                                look_at_range = helpers.get_bbox_dimensions(lookat)
                                center_coords = tuple( round((min_val + max_val) /2,3) for min_val, max_val in zip(look_at_range[0], look_at_range[1]))
                                ui.Label(f"({center_coords})", width=225, style={"color": 0xFF777777})
                        else:
                            formatted_lookat = "\n".join([f"({format_number(x)}, {format_number(y)}, {format_number(z)})" for x, y, z in lookat])
                            formatted_string = f"{formatted_lookat}"
                            ui.Label(
                                formatted_string,
                                width=225, style={"color": 0xFF777777}
                            )
                            center_coords = tuple(
                                round((min_val + max_val) / 2, 3) for min_val, max_val in zip(lookat[0], lookat[1])
                            )

                            ui.Label(f"({center_coords})", width=225, style={"color": 0xFF777777})
                    ui.Line(height=ui.Length(20))

                ui.Button("Reset All", clicked_fn=lambda: self.reset_all_camera_params(), tooltip="Reset all added Scattering Prim and LookAt Prim")
    
    # Reset Scattering and Look At Path Widgets.
    def reset_current_camera_params(self): 
        with self.camera_params:
            self.scattering_prim._path_model.set_value("")
            self.lookat_prim._path_model.set_value("")
                            
    # Reset all added camera params
    def reset_all_camera_params(self): 
        self.camera_params_list = []
        self.view_added_params()

    def get_manual_lookat(self):
        return ((self.x.min_value, self.y.min_value, self.z.min_value),(self.x.max_value, self.y.max_value, self.z.max_value) )

#--------------------------------------------------------end camera fns---------------------------------------------------------------------------------------#
    def get_color_values(self):

        r_abs, g_abs, b_abs, a_abs = self.rgb_color_values.get_item_children()

        # Get the selected color
        r = self.rgb_color_values.get_item_value_model(r_abs).as_float
        g = self.rgb_color_values.get_item_value_model(g_abs).as_float
        b = self.rgb_color_values.get_item_value_model(b_abs).as_float
        a = self.rgb_color_values.get_item_value_model(a_abs).as_float

        return (r,g,b,a)
    
    def add_color(self):
        r, g, b, a = self.get_color_values()
        # Assign the color to all selected prims
        self.color_prim_path = self.color_prim.path_value
        if self.color_prim_path!= "":
            if self.color_prim_path not in self.prim_colors:
                self.prim_colors[self.color_prim_path] = [(r, g, b, a)]
            else:
                # Add the color to the path if it is not already present  
                if (r, g, b, a) not in self.prim_colors[self.color_prim_path]:
                    self.prim_colors[self.color_prim_path].append((r, g, b, a))
                    nm.post_notification(f"Added new color: r={r:.4f}, g={g:.4f}, b={b:.4f} to {self.color_prim_path}", hide_after_timeout=True, duration=5, status=nm.NotificationStatus.INFO)
                else:
                    nm.post_notification(f"Color: r={r:.4f}, g={g:.4f}, b={b:.4f} already exists for {self.color_prim_path}", hide_after_timeout=True, duration=5, status=nm.NotificationStatus.WARNING)
            self.update_added_colors_ui()

    def update_added_colors_ui(self): 
        self.added_color_params_frame.visible=True
        with self.added_color_params_frame: 
            self.color_params_list_ui.clear()

            with self.color_params_list_ui:
                with ui.HStack(spacing=2):
                    ui.Label("Prim Path", width = ui.Percent(33))
                    ui.Label("RGB Value", width = ui.Percent(33))
                    ui.Label("RGB Color", width = ui.Percent(33))

                ui.Line(height=ui.Length(20))
                for i, (path, colors_list) in enumerate(self.prim_colors.items()):
                    with ui.HStack(height=0):
                        ui.Label(f"{str(path)[:MAX_NUMBER_PRIM_PATH_CHARACTERS_TO_SHOW]}{'...' if len(str(path)) > MAX_NUMBER_PRIM_PATH_CHARACTERS_TO_SHOW else ''}", width= ui.Percent(33), style={"color": 0xFF777777},tooltip=str(path))
                        with ui.VStack():
                            for color in colors_list: 
                                color_formatted = f"{color[0]:.2f}, {color[1]:.2f}, {color[2]:.2f}"
                                ui.Label(color_formatted, width= ui.Percent(33), style={"color": 0xFF777777})
                        with ui.VStack(width=ui.Percent(33)):
                            for color in colors_list: 
                                color_hex = helpers.rgb_to_hex(color)
                                ui.Rectangle(
                                width=21,
                                height=21,
                                style={
                                    "background_color": cl(str(color_hex))
                                },
                                )
                    ui.Line(height=ui.Length(20))
                ui.Button("Reset all", tooltip="Reset all picked colors and all prims", clicked_fn=self.reset_all)

    def reset_colors(self):
        # Remove all colors for the selected prims

        if self.color_prim.path_value in self.prim_colors:
            del self.prim_colors[self.color_prim.path_value]
            self.update_added_colors_ui()

    def reset_all(self):
        # Remove all colors and all their prims
            self.prim_colors = {}
            self.update_added_colors_ui()

#--------------------------------------------------------end color fns---------------------------------------------------------------------------------------#
    def update_added_materials_ui(self):
        self.added_material_params_frame.visible=True
        with self.added_material_params_frame: 
            self.materials_params_list_ui.clear()

            with self.materials_params_list_ui:
                with ui.HStack(spacing=2):
                    ui.Label("Prim Path", width = ui.Percent(50))
                    ui.Label("Materials Path", width = ui.Percent(50))


                ui.Line(height=ui.Length(20))
                print(self.material_prims)
                for prim_path, folder_paths in self.material_prims.items(): 
                    with ui.HStack(height=0):
                        ui.Label(f"{str(prim_path)[:MAX_NUMBER_PRIM_PATH_CHARACTERS_TO_SHOW]}{'...' if len(str(prim_path))>MAX_NUMBER_PRIM_PATH_CHARACTERS_TO_SHOW else ''}", width=ui.Percent(50), style={"color": 0xFF777777},tooltip=str(prim_path))
                        with ui.VStack():
                            for folder_path in folder_paths: 
                                ui.Label(f"{str(folder_path)[:MAX_NUMBER_PRIM_PATH_CHARACTERS_TO_SHOW]}{'...' if len(str(folder_path))>MAX_NUMBER_PRIM_PATH_CHARACTERS_TO_SHOW else ''}", width=ui.Percent(50), style={"color": 0xFF777777}, tooltip=str(folder_path))

                    ui.Line(height=ui.Length(20))
                with ui.HStack():
                    ui.Button("Load Materials", tooltip="Load all materials in the stage", clicked_fn=self.load_all_materials)
                    ui.Button("Reset all", tooltip="Reset all materials and all prims", clicked_fn=self.reset_all_materials)

    def add_material(self):
        # Add Material Randomization 
        self.material_prim_path = self.material_prim.path_value
        if self.from_stage_cb.get_value_as_bool():
            self.material_stage_path = self.material_folder_stage.path_value
        else: 
            self.material_stage_path = ""
        self.material_folder_path = self.material_folder.directory
        if (self.material_prim_path!= "" and self.material_folder_path != "") or (self.material_prim_path!="" and self.material_stage_path !=""): 
            if self.material_prim_path not in self.material_prims:
                if self.material_folder_path != "":
                    self.material_prims[self.material_prim_path] = [self.material_folder_path]
                if self.material_stage_path != "": 
                    self.material_prims[self.material_prim_path] = [self.material_stage_path]
            else:
                if self.material_folder_path not in self.material_prims[self.material_prim_path]:
                    self.material_prims[self.material_prim_path].append(self.material_folder_path)

            nm.post_notification(f"Added new material randomization from folder {self.material_folder_path} to {self.material_prim_path}", hide_after_timeout=True, duration=5, status=nm.NotificationStatus.INFO)
            self.update_added_materials_ui()
        else:             
            nm.post_notification("Please Select a Prim and a Materials Folder before Adding",  hide_after_timeout=True, duration=5, status=nm.NotificationStatus.WARNING)

    def reset_material(self):
        # Remove all materials for the selected prims

        if self.material_prim.path_value in self.material_prims:
            del self.material_prims[self.material_prim.path_value]
            self.update_added_materials_ui()

    def reset_all_materials(self):
        # Remove all selected prims and all their materials folder paths
            self.material_prims = {}
            self.created_materials = {}
            self.update_added_materials_ui()
            if helpers.is_valid_prim('/Created_Materials'):
                helpers.delete_prim('/Created_Materials')
            if helpers.is_valid_prim('/Copied_Stage_Materials'):
                helpers.delete_prim('/Copied_Stage_Materials')

    def select_from_stage(self): 
        if self.from_stage_cb.get_value_as_bool(): 
            self.stage_materials_frame.visible = True
            with self.stage_materials_frame:
                self.material_folder_stage = PathWidget("Materials From Stage", tooltip="Select the materials you want to randomize from the stage")
        else: 
            self.stage_materials_frame.visible = False
            self.stage_materials_frame.clear()

    def load_all_materials(self): 
        async def go():
            for material_prim, material_folders in self.material_prims.items():
                if material_prim not in self.created_materials:
                    self.created_materials[material_prim] = []
                    found_mats=[]
                
                # List all .mdl material urls in the material_folders and create MDL material prims from them
                for material_folder in material_folders:
                    # If stage materials: 
                    if helpers.is_valid_prim(material_folder): 
                        # Get all mesh children paths
                        prim = helpers.get_current_stage().GetPrimAtPath(material_folder)
                        # If one material was selected not a folder
                        if prim.GetTypeName() == 'Material': 
                            found_mats = [prim.GetPath()]
                        else:
                            found_mats = helpers.get_all_children_paths([], prim)
                        # Create scope prim that will jold the copied materials 
                        helpers.create_prim_with_default_xform("Scope", "/Copied_Stage_Materials")
                        for mat in found_mats:
                            # Iterate through every material in selected stage materials and copy to created scope.
                            material_name = str(mat).split("/")[-1]
                            copied_path = helpers.copy_prim(mat, f"/Copied_Stage_Materials/{material_name}")
                            self.created_materials[material_prim].append(copied_path)

                    # If materials are from a browsed directory, create them in the stage
                    else: 
                        material_paths = helpers.list_mdl_materials(material_folder)
                        for material_url in material_paths:
                            material_name = str(material_url).split("/")[-1].split(".")[0]
                            material_path = Sdf.Path(f'/Created_Materials/{material_name}')
                            # Asynchrounously create the listed materials in the stage under Created_Materials folder
                            created_material_path = await helpers.create_material(str(material_url), material_name, material_path, True)
                            # Get actual stage path of the created material's shader and append it to list of created materials. 
                            created_material_shader = str(helpers.get_current_stage().GetPrimAtPath(created_material_path).GetChildren()[0].GetPath())
                            self.created_materials[material_prim].append(created_material_path)
                print(f"created_materials {self.created_materials}")
                nm.post_notification(f"Loaded Materials from {material_folder}", hide_after_timeout=True, duration=5, status=nm.NotificationStatus.INFO)

        # When Load Materials button is pressed, schedule the create materials coroutine (go()) to be executed asynchrounously without blocking the main thread. 
        asyncio.ensure_future(go())

#--------------------------------------------------------end material fns---------------------------------------------------------------------------------------#

    # Build the Light Params in the UI when the Light Checkbox is clicked. 
    def build_light_ui(self):        
        # If Light Randomization is Checked
        if self.light_cb.get_value_as_bool():                                  
            with self.light_params:
                with ui.CollapsableFrame("Light Randomization Parameters", height=0):
                    with ui.VStack():
                        self.light_intensity = MinMaxWidget("Light Intensity", min_value=500, max_value=5000)
                        self.light_rotation = MinMaxWidget("Light Rotation",min_value=0, max_value=360)
                        self.light_color = RGBMinMaxWidget("Light Color")
                        self.light_scale = MinMaxWidget("Light Scale", min_value=5, max_value=10)
                        self.light_position = PositionMinMaxWidget("Light position", min_value=-30, max_value=30)
                        with ui.HStack(height = 0):
                            ui.Label("Count")
                            ui.IntDrag(model=self.light_count_model ,min = 0)
        
        # If Light Randomization is Unchecked
        else:                                                           
            self.light_params.clear()
            with self.light_params:
                with ui.HStack():
                    ui.Label("Light Randomizations")
                    self.light_cb = ui.CheckBox(name = "Light Randomization", width=200, enabled=True, checked=False).model
                    self.light_cb.add_value_changed_fn(lambda _: self.build_light_ui())


    # Build the Camera Params in the UI when the Camera Checkbox is clicked.
    def build_camera_ui(self):
        # If Camera Randomization is checked
        if self.camera_cb.get_value_as_bool():
            with self.camera_params:
                self.camera_params_frame = ui.CollapsableFrame("Camera Randomization Parameters", height=0)
                with self.camera_params_frame:
                    with ui.VStack(height=0):
                        if self.camera_params_list == []:
                            self.camera_distance = MinMaxWidget("Camera Distance", min_value=0, max_value=10, tooltip="Set camera distance if no scattering and look at prims will be provided.")
                        with ui.HStack(height=0):
                            self.scattering_prim = PathWidget("Scattering Prim")
                            self.lookat_prim = PathWidget("Look At Prim")
                        with ui.HStack(height = 0):
                            self.lookat_frame = ui.CollapsableFrame("Look at Manual Radnomization Parameters", height=0)
                            with self.lookat_frame:
                                with ui.VStack(height = 0):
                                    with ui.HStack(height = 0):
                                        ui.Label("Use Manual Look At Randomization")
                                        self.lookat_cb = ui.CheckBox(name="Use Manual Coordinates", width=200).model
                                    self.x = MinMaxWidget("X", min_value=0, max_value=10)
                                    self.y = MinMaxWidget("Y", min_value=0, max_value=10)
                                    self.z = MinMaxWidget("Z", min_value=0, max_value=10)

                        with ui.HStack():
                            ui.Button("Add", clicked_fn=lambda: self.add_camera_params(), tooltip="Add the Current Scattering Prim and LookAt Prim")
                            ui.Button("Reset", clicked_fn=lambda: self.reset_current_camera_params(), tooltip="Reset the Scattering Prim and LookAt Prim")

                        self.added_camera_params_frame = ui.CollapsableFrame("Added Camera Params", visible=False)
                        with self.added_camera_params_frame:
                            self.camera_params_list_ui = ui.VStack()
                            with self.camera_params_list_ui:
                                with ui.HStack(spacing=2):
                                    ui.Label("Scattering Prim", width = 150)
                                    ui.Label("Look At Prim", width = 150)
                                    ui.Label("Look At Prim Center", width = 150)

                        if self.camera_params_list != []:
                            self.view_added_params()

        # If Camera Randomization is Unchecked
        else:
            self.camera_params.clear()
            with self.camera_params:
                with ui.HStack():
                    ui.Label("Camera Randomizations")
                    self.camera_cb = ui.CheckBox(name = "Camera Randomization", width=200).model
                    self.camera_cb.add_value_changed_fn(lambda _: self.build_camera_ui())

    # Build the Color Params in the UI when the Color Checkbox is clicked.
    def build_color_ui(self):
        # If Color Randomization is Checked
        if self.color_cb.get_value_as_bool():
            with self.color_params:
                self.color_params_frame = ui.CollapsableFrame("Color Randomization Parameters", height=0)
                with self.color_params_frame: 
                    with ui.VStack(height=0):
                        with ui.HStack():
                            ui.Label("Texture Color Randomization", alignment=ui.Alignment.LEFT, tooltip="Keeps the texture of materials during color randomization. Note: Consider increasing subframes value as the process needs more time between frames.")
                            self.texture_randomization_cb = ui.CheckBox(name="Texture Color Randomization",width=190).model

                        with ui.HStack(style={"margin": 3}, height=0, spacing=5):
                            self.color_prim = PathWidget("Color Prim")
                            ui.Label("RGB Color Picker", width=70, tooltip="Select color to be added to the current prim path.")
                            self.rgb_color_values = ui.ColorWidget(width=25, height=0, style={"margin":6}).model

                        with ui.HStack():
                            ui.Button("Add", tooltip="Add picked color", clicked_fn=self.add_color)
                            ui.Button("Reset", tooltip="Reset picked colors of this prim", clicked_fn=self.reset_colors)

                        self.added_color_params_frame = ui.CollapsableFrame("Added Color Params", visible=False)
                        with self.added_color_params_frame:
                            self.color_params_list_ui = ui.VStack()
                            with self.color_params_list_ui:
                                with ui.HStack(spacing=2):
                                    ui.Label("Prim Path", width = ui.Percent(25))
                                    ui.Label("RGB Value", width = ui.Percent(25))
                                    ui.Label("RGB Color", width = ui.Percent(25))
                                ui.Line(height=ui.Length(20))
                        if self.prim_colors != {}: 
                            self.update_added_colors_ui()

        # If Color Randomization is Unchecked
        else: 
            self.color_params.clear()
            with self.color_params: 
                with ui.HStack():
                    ui.Label("Color Randomizations")
                    self.color_cb = ui.CheckBox(name = "Color Randomization", width=200).model
                    self.color_cb.add_value_changed_fn(lambda _: self.build_color_ui())
    
    def build_materials_ui(self):
        # If Materials Randomization is Checked
        if self.material_cb.get_value_as_bool(): 
            with self.material_params: 
                self.material_params_frame = ui.CollapsableFrame("Materials Randomization Parameters", height=0)
                with self.material_params_frame:
                    with ui.VStack(height=0):
                        with ui.HStack():
                            ui.Label("Select Materials From Stage")
                            self.from_stage_cb = ui.CheckBox(name="From Stage", width=ui.Percent(54)).model
                            self.from_stage_cb.add_value_changed_fn(lambda _: self.select_from_stage())
                        self.stage_materials_frame = ui.VStack(visible = False)

                        self.material_folder = CustomDirectory("Material Folder",
                                default_dir=str(),
                                tooltip="A folder location containing a single or set of materials (.mdl)")
                        
                        self.material_prim = PathWidget("Material Prim", tooltip="Prim to apply materials randomization on.")

                        with ui.HStack():
                            ui.Button("Add", tooltip="Add Material Randomization", clicked_fn=self.add_material)
                            ui.Button("Reset", tooltip="Reset Material Randomization", clicked_fn=self.reset_material)
                
                        self.added_material_params_frame = ui.CollapsableFrame("Added Material Params", visible=False)
                        with self.added_material_params_frame:
                            self.materials_params_list_ui = ui.VStack()
                            with self.materials_params_list_ui:
                                with ui.HStack(spacing=2):
                                    ui.Label("Prim Path", width = 150)
                                    ui.Label("Materials Folder Path", width = 150)
                                ui.Line(height=ui.Length(20))
                        if self.material_prims != {}: 
                            self.update_added_materials_ui()

        # If Color Randomization is Unchecked
        else: 
            self.material_params.clear()
            with self.material_params: 
                with ui.HStack():
                    ui.Label("Material Randomizations")
                    self.material_cb = ui.CheckBox(name = "Material Randomization", width=200).model
                    self.material_cb.add_value_changed_fn(lambda _: self.build_materials_ui())




    def build_randomization_ui(self):
        self.light_params, self.light_cb = self.add_randomization_checkbox("Light", lambda _: self.build_light_ui())
        self.camera_params, self.camera_cb = self.add_randomization_checkbox("Camera", lambda _: self.build_camera_ui())
        self.color_params, self.color_cb = self.add_randomization_checkbox("Color", lambda _: self.build_color_ui())
        self.material_params, self.material_cb = self.add_randomization_checkbox("Material", lambda _: self.build_materials_ui())