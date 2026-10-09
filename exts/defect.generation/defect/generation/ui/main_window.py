# SPDX-FileCopyrightText: Copyright (c) 2023 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import carb
from typing import List
import json
import os
import omni
import omni.replicator.core as rep
import omni.ui as ui
from omni.ui import DockPreference
from omni.kit.window.file_exporter import get_file_exporter
from omni.kit.window.filepicker import FilePickerDialog
from defect.generation.ui.style import default_defect_main
from defect.generation.ui.widgets import CustomDirectory
from defect.generation.core.replicator.replicator_defect import create_defect_layer
from defect.generation.utils.replicator_utils import rep_preview, does_defect_layer_exist, rep_run, get_defect_layer
from defect.generation.ui.prim_widgets import ObjectParameters
from defect.generation.ui.defects.defect_types_factory import DefectUIFactory
from defect.generation.utils.helpers import delete_prim, is_valid_prim, generate_small_uuid, restore_original_materials
from defect.generation.ui.domain_randomization_widget import RandomizerParameters
from defect.generation.utils.file_picker import open_file_dialog, click_open_json_startup
from defect.generation.domain.models.defect_generation_request import DefectGenerationRequest, DefectObject, PrimDefectObject
from omni.kit.notification_manager import post_notification, NotificationStatus
from pathlib import Path
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)
MAX_NUMBER_PRIM_PATH_CHARACTERS_TO_SHOW = 50
# Get delete Icon
@lru_cache()
def _ui_get_delete_glyph():
    return omni.ui.get_custom_glyph_code("${glyphs}/menu_delete.svg")

# Get Folder Icon
@lru_cache()
def _ui_get_open_folder_glyph():
    return ui.get_custom_glyph_code("${glyphs}/folder_open.svg")

class MainWindow(ui.Window):
    def __init__(self, title: str, dockPreference: DockPreference = DockPreference.DISABLED, **kwargs) -> None:
        super().__init__(title, dockPreference, **kwargs)
        # Models
        self.frames = ui.SimpleIntModel(1, min=1)
        self.rt_subframes = ui.SimpleIntModel(1, min=1)
        # Widgets
        self.defect_params = None
        self.object_params = None
        self.output_dir = None
        self.frame_change = None
        self._replicator_task = None
        
        # List that stores all the defect parameters to be applied
        self.defect_parameters_list = {}

        # Object params
        self.object_params = ObjectParameters(self.defect_parameters_list)
        
        # Defects UI
        self.defect_ui_factory = DefectUIFactory()
        self.defect_methods_ui = self.defect_ui_factory.get_all_defect_method_ui()
        self.defect_methods_ui = sorted(self.defect_methods_ui, key=lambda x: x.defect_name)
        for defect_method_ui in self.defect_methods_ui:
            defect_method_ui.set_object_params(self.object_params)
        
        # Randomizers UI
        self.randomizer_params = RandomizerParameters()
        
        # List that stores all the target prims
        self.default_params_text = "Target Prim"

        self.frame.set_build_fn(self._build_frame)

    # Function to update the UI of the list of prims
    def update_object_params_list_ui(self): 
        # Clear the UI of the target prims and their defect methods
        self.object_params_list_ui.clear() 
        self.object_params_frame_ui.clear()

        with self.object_params_list_ui: 
            # If there are no selected prim paths, display default Target Prim UI
            if not self.defect_parameters_list:
                with ui.CollapsableFrame(self.default_params_text):
                    with ui.VStack():
                        with ui.HStack(spacing=2):
                            ui.Label("Defect Name", width=150)
                            ui.Label("Args", width=150)

                        with ui.HStack():
                            ui.Line(height=ui.Length(20))

            # Loop over the selected prims and create a collapsable frame with defects for each in the UI
            for i, (prim_path, defects) in enumerate(self.defect_parameters_list.items()):
                with ui.HStack(spacing=3): 
                    self.object_params_frame_ui = ui.CollapsableFrame(f"{str(prim_path)[:MAX_NUMBER_PRIM_PATH_CHARACTERS_TO_SHOW]}{'...' if len(str(prim_path))>MAX_NUMBER_PRIM_PATH_CHARACTERS_TO_SHOW else ''}")
                    with self.object_params_frame_ui:
                        self.defect_parameters_list_ui = ui.VStack()
                        with self.defect_parameters_list_ui:
                            with ui.HStack(spacing=2):
                                ui.Label("Defect Name", width=150)
                                ui.Label("Args", width=150)

                            with ui.HStack():
                                ui.Line(height=ui.Length(20))

                            # Loop over each appended defect method, and format the content in the UI
                            for i, defect in enumerate(defects):

                                args_formatted = []
                                for k, v in defect["args"].items():
                                    args_formatted.append(f"{k}: {v}" if not isinstance(v,float) else f"{k}: {v:.2f}")
                                args_formatted = '\n'.join(args_formatted)
                                with ui.HStack(height=0):

                                    ui.Label(defect["defect_name"], width=150, word_wrap=True, style={"color": 0xFF777777})
                                    ui.Label(args_formatted, word_wrap=True, style={"color": 0xFF777777})
                                    ui.Button(
                                        f"{_ui_get_delete_glyph()}",
                                        width=20,
                                        clicked_fn=lambda idx=i, path =prim_path: self.delete_dm(idx, path),
                                        tooltip="Remove entry",
                                    )
                                with ui.HStack():
                                    ui.Line(height = 10)

                        # with ui.HStack():
                        #     ui.Line(height=ui.Length(20))
                    
                    ui.Button(
                        "Select",
                        width=20,
                        height=0,
                        clicked_fn= lambda pth = prim_path : self.object_params.set_current_selected_prim(pth),
                        tooltip="Select entry",
                    ) 
                    ui.Button(
                        "Export",
                        width=20,
                        height=0,
                        clicked_fn= lambda pth = prim_path : self.open_export_dm_dialog(pth),
                        tooltip="Export list of defects",
                    ) 
                    ui.Button(
                        "Load",
                        width=20,
                        height=0,
                        clicked_fn= lambda pth = prim_path : self.open_load_dm_dialog(pth),
                        tooltip="Load list of defects",
                    ) 
                    ui.Button(
                        f"{_ui_get_delete_glyph()}",
                        width=20,
                        height=0,
                        clicked_fn= lambda pth = prim_path : self.delete_tp(pth),
                        tooltip="Remove entry",
                    )


                        
    # Function to be called when the delete target prim icon is pressed
    def delete_tp(self, pth):
        logger.warning(f"Deleting target prim: {pth}")
        self.defect_parameters_list.pop(pth, None)
        self.object_params.set_current_selected_prim("")
        # self.object_params_frame_ui.title=self.default_params_text
        self.update_object_params_list_ui()

    # Function to be called when the delete defect method icon is pressed
    def delete_dm(self, idx, path):
        logger.warning(f"Deleting defect method {idx} from target prim {path} ")
        if path in self.defect_parameters_list:
            if len(self.defect_parameters_list[path]) > idx:
                self.defect_parameters_list[path].pop(idx)
        # After updating the list, re-update the UI
        self.update_object_params_list_ui()
    
    # Export  defect methods logic
    def generate_export_handler(self, prim_path = None):
        def _export_dm_handler(filename: str, dirname: str, extension: str, selections: List[str]):
            try:
                full_path = os.path.join(dirname, f"{filename}{extension}")
                if self.defect_parameters_list:
                    with open(full_path, 'w') as defect_file:
                        json.dump(self.defect_parameters_list if not prim_path else self.defect_parameters_list[prim_path], defect_file)
                    logger.info(f"Exported defect data to '{full_path}'")

            except Exception as e:
                logger.error(f"Error exporting defect methods: {e}")
        return _export_dm_handler
    
    # Open export defect methods dialog
    def open_export_dm_dialog(self, prim_path = None):
        file_exporter = get_file_exporter()
        file_exporter.show_window(
            title="Export As ...",
            export_button_label="Save",
            export_handler=self.generate_export_handler(prim_path=prim_path),
            filename_url="prim_defect_methods.json" if not prim_path else "defect_methods.json",  # Default filename
            file_extension_types=[(".json", "JSON Files")]
        )

    # Load defect methods logic
    def generate_load_handler(self, prim_path = None):
        def _load_dm_handler(filename: str, dirname: str, extension: str, selections: List[str]):
            try:
                def _set_defects(defect, prim_path):
                    if not prim_path:
                        self.defect_parameters_list.clear()
                        self.defect_parameters_list.update(defect)
                    else:
                        self.defect_parameters_list[prim_path] = defect
                    logger.warning(defect)
                    self.update_object_params_list_ui()

                def _validate_defects(defects):
                    for defect in defects:
                        if not all(key in defect for key in ('defect_name','args')):
                                    raise ValueError(
                                        "Invalid JSON structure. Each dictionary must have 'defect_name and 'args' keys.")
                def _validate_json_structure(data, prim_path):
                    if not prim_path:
                        for prim_path, defects  in data.items():
                            _validate_defects(defects)
                    else:
                        _validate_defects(data)

                defect_path = os.path.join(dirname, f"{filename}{extension}")
                with open(defect_path, 'r') as file:
                    defect = json.load(file)
                    # Validate the JSON structure
                    try:
                        _validate_json_structure(defect, prim_path)
                        logger.info("JSON structure is valid.")
                        _set_defects(defect, prim_path)
                        
                        self.info_defect.text = f"{len(defect)} {'prim(s) with defects' if not prim_path else 'defect(s)'} loaded ..."
    
                    except ValueError as e:
                        logger.error("Invalid JSON structure:", e)

            except Exception as e:
                logger.error(f"Error loading defect methods: {e}")
        return _load_dm_handler
    
    # Open load defect methods dialog
    def open_load_dm_dialog(self, prim_path = None):
        file_exporter = get_file_exporter()
        file_exporter.show_window(
            title="Load ...",
            export_button_label="Load",
            export_handler=self.generate_load_handler(prim_path=prim_path),
            filename_url="prim_defect_methods.json" if not prim_path else "defect_methods.json",  # Default filename
            file_extension_types=[(".json", "JSON Files")]
        )


    ###############################
    # UI
    ###############################
    def _build_collapse_base(self, label: str, collapsed: bool = False):
        v_stack = None
        with ui.CollapsableFrame(label, height=0, collapsed=collapsed):
            with ui.ZStack():
                ui.Rectangle()
                v_stack = ui.VStack()
        return v_stack

    def _build_frame(self):
        with self.frame:
            with ui.ScrollingFrame(style=default_defect_main):
                with ui.VStack(style={"margin": 3}):
                    self._build_object_param()               
                    self._build_defect_param()
                    self._build_randomizer_param()
                    self._build_replicator_param()

    def _build_object_param(self):
        with self._build_collapse_base("Object Parameters"):
            self.object_params.build_ui()

    def _build_defect_param(self):
        def on_click_open_defect(dialog: FilePickerDialog, filename: str, dirname: str):
            _, fullpath = click_open_json_startup(dialog, filename, dirname)
            self.defect_path.model.set_value(fullpath)

        def click_open_file_dialog_defect():
            open_file_dialog(on_click_open_defect, "json")





        with self._build_collapse_base("Defect Parameters"):

            TEXTURE_DIR = os.path.join(Path(__file__).parents[3], "data", "example")
            self.defect_text = CustomDirectory("Defect Texture Folder",
                            default_dir=str(TEXTURE_DIR),
                            tooltip="A folder location containing a single or set of textures (.png)")

            for defect_method_ui in self.defect_methods_ui:
                # Preparing defect method UIs
                defect_method_ui.set_defect_parameters_list(self.defect_parameters_list)
                defect_method_ui.on_add(self.update_object_params_list_ui)
                with ui.CollapsableFrame(defect_method_ui.defect_name, height=0) as frame:
                    with ui.Frame():
                        with ui.VStack():
                            logger.info(f"Building ui: {defect_method_ui.defect_name}")
                            defect_method_ui.build_ui()

            with self._build_collapse_base("Params"): 
                self.object_params_list_ui = ui.VStack(height=0)
                self.object_params_frame_ui = ui.CollapsableFrame(self.default_params_text)

                self.object_params.on_add(self.update_object_params_list_ui)
                with self.object_params_list_ui:
                    with self.object_params_frame_ui:
                        self.defect_parameters_list_ui = ui.VStack(spacing=5)
                        with self.defect_parameters_list_ui:
                            with ui.HStack(spacing=2):
                                ui.Label("Defect Name", width=150)
                                ui.Label("Args", width=200)

                            with ui.HStack():
                                ui.Line(height=ui.Length(20))
                
            with ui.Frame():
                with ui.VStack():
                    with ui.HStack(spacing=5):
                        ui.Button("Load Defect Methods", clicked_fn=lambda: self.open_load_dm_dialog())
                        ui.Button("Export Defect Methods", clicked_fn=lambda: self.open_export_dm_dialog())
                    self.info_defect = ui.Label("", style={"color": ui.color(255, 255, 0)})
    def _build_randomizer_param(self): 
        with self._build_collapse_base("Randomizer Parameters"): 
            self.randomizer_params.build_randomization_ui()

    def _build_replicator_param(self):
        self.original_materials = None
        def _create_defect_layer(**kwargs):
            if len(self.defect_text.directory) == 0 :
                post_notification(
                    f"Defect Texture Directory Cannot be Empty",
                    hide_after_timeout=True, duration=5, status=NotificationStatus.WARNING)
                carb.log_error("Defect Texture Directory Cannot be Empty")
            else:
                prim_defect_objects = []
                for prim_path, defects in self.defect_parameters_list.items():
                    # If prim not valid, skip it
                    if not is_valid_prim(prim_path):
                        continue
                    # If primvars not applied, apply them
                    self.object_params.apply(prim_path)
                    for d in defects:
                        for _ in range(int(d['args']['count'])):
                            prim_defect_objects.append(PrimDefectObject(prim_path=prim_path, defects=[DefectObject(defect_name=d['defect_name'], args=d['args'], uuid=generate_small_uuid())]))

                defect_generation_request = DefectGenerationRequest(
                            texture_dir=self.defect_text.directory,
                            prim_defects = prim_defect_objects
                        )
                domain_randomization_request = self.randomizer_params.prepare_domain_randomization_request()
                self.original_materials = create_defect_layer(defect_generation_request, domain_randomization_request, **kwargs)
                post_notification(f"Created defect layer with {len(self.defect_parameters_list)} total prims/groups and {sum(int(defect['args']['count']) for defects in self.defect_parameters_list.values() for defect in defects)} combined defects.", hide_after_timeout=True, duration=5, status=NotificationStatus.INFO)
       
        def _graph_kwargs(**overrides):
            kwargs = {
                "output_dir": self.output_dir.directory,
                "rt_subframes": max(1, self.rt_subframes.get_value_as_int()),
                "use_seg": self._use_seg.as_bool,
                "use_bb": self._use_bb.as_bool,
                "use_bmw": self._use_bmw.as_bool,
            }
            kwargs.update(overrides)
            return kwargs

        async def preview_data():
            await rep.orchestrator.stop_async()
            if not does_defect_layer_exist():
                _create_defect_layer(**_graph_kwargs())
                self.rep_layer_button.text = "Recreate Replicator Graph"
            rep_preview()
        
        # TODO: Fix that so it supports target_prim
        async def remove_replicator_graph():
            await rep.orchestrator.stop_async()
            restore_original_materials(self.original_materials)
            if get_defect_layer() is not None:
                layer, pos = get_defect_layer()
                omni.kit.commands.execute('RemoveSublayer',
                                          layer_identifier=layer.identifier,
                                          sublayer_position=pos)


            # Remove replicator
            if is_valid_prim('/Replicator'):
                delete_prim('/Replicator')
                logger.warning(f"Deleting : /Replicator")
            
            #Remove projections
            for prim_path in list(self.defect_parameters_list.keys()):
                if is_valid_prim(f"{prim_path}/Projection"):
                    delete_prim(f"{prim_path}/Projection")
                    logger.warning(f"Deleting : {prim_path}/Projection")


        async def delete_replicator_graph():
            await rep.orchestrator.stop_async()
            restore_original_materials(self.original_materials)
            self.randomizer_params.created_materials = {}
            if get_defect_layer() is not None:
                layer, pos = get_defect_layer()
                omni.kit.commands.execute('RemoveSublayer',
                                          layer_identifier=layer.identifier,
                                          sublayer_position=pos)

            # Remove replicator
            if is_valid_prim('/Replicator'):
                delete_prim('/Replicator')
                logger.warning(f"Deleting : /Replicator")
            
            #Remove projections
            for prim_path in list(self.defect_parameters_list.keys()):
                if is_valid_prim(f"{prim_path}/Projection"):
                    delete_prim(f"{prim_path}/Projection")
                    logger.warning(f"Deleting : {prim_path}/Projection")

            #Remove Created materials
            if is_valid_prim("/Created_Materials"):
                delete_prim('/Created_Materials')
                logger.warning(f"Deleting : /Created_Materials")
                
            #Remove Copied materials
            if is_valid_prim("/Copied_Stage_Materials"):
                delete_prim('/Copied_Stage_Materials')
                logger.warning(f"Deleting : /Copied_Stage_Materials")


        async def run_replicator():
            await remove_replicator_graph()
            total_frames = self.frames.get_value_as_int()
            subframes = self.rt_subframes.get_value_as_int()
            if subframes < 1:
                post_notification(
                    f"Number of Subframes {subframes} Needs to Be Greater than 0. Setting the Value to 1",
                    hide_after_timeout=True, duration=5, status=NotificationStatus.WARNING)
                subframes = 1
            if total_frames > 0:
                post_notification(f"Running replicator with {total_frames} total frames and {subframes} subframes.", hide_after_timeout=True, duration=5, status=NotificationStatus.INFO)
                _create_defect_layer(**_graph_kwargs(frames=total_frames, rt_subframes=subframes))
                self.rep_layer_button.text = "Recreate Replicator Graph"
                rep_run()
            else:
                post_notification(
                    f"Number of frames is {total_frames}. Input value needs to be greater than 0.",
                    hide_after_timeout=True, duration=5, status=NotificationStatus.WARNING)
                carb.log_error(f"Number of frames is {total_frames}. Input value needs to be greater than 0.")
        
        async def create_replicator_graph():
            await remove_replicator_graph()
            _create_defect_layer(**_graph_kwargs(frames=max(1, self.frames.get_value_as_int())))
            self.rep_layer_button.text = "Recreate Replicator Graph"

        def set_text(label, model):
            label.text = model.as_string

        with self._build_collapse_base("Replicator Parameters"):
            home_dir = Path.home()
            valid_out_dir = home_dir / "omni.replicator_out"
            self.output_dir = CustomDirectory("Output Directory", default_dir=str(valid_out_dir.as_posix()), tooltip="Directory to specify where the output files will be stored. Default is [DRIVE/Users/USER/omni.replicator_out]")
            with ui.HStack(height=0, tooltip="Check off the BMW format if you want the output to be in JSON"):
                ui.Label("BMW Format: ", width=0)
                self._use_bmw = ui.CheckBox().model

            with ui.HStack(height=0, tooltip="Check off which annotator you want to use; You can also use both"):
                ui.Label("Annotations: ", width=0)
                ui.Spacer()
                ui.Label("Segmentation", width=0)
                self._use_seg = ui.CheckBox().model
                ui.Label("Bounding Box", width=0)
                self._use_bb = ui.CheckBox().model
                ui.Spacer()
            with ui.HStack(height=0):
                ui.Label("Render Subframe Count: ", width=0,
                         tooltip="Defines how many subframes of rendering occur before going to the next frame")
                ui.Spacer(width=ui.Fraction(0.25))
                ui.IntField(model=self.rt_subframes)
            with ui.HStack(height=0):
                self.rep_layer_button = ui.Button("Create Replicator Layer", 
                                                clicked_fn=lambda: self._schedule_replicator_action(create_replicator_graph),
                                                tooltip="Creates/Recreates the Replicator Graph, based on the current Defect Parameters")
                self.rep_delete_layer_button = ui.Button("Delete Replicator Layer", 
                                        clicked_fn=lambda: self._schedule_replicator_action(delete_replicator_graph),
                                        tooltip="Deletes the Replicator Graph and all relevant components")
            with ui.HStack(height=0):
                ui.Button("Preview", width=0, clicked_fn=lambda: self._schedule_replicator_action(preview_data),
                          tooltip="Preview a Replicator Scene")
                ui.Label("or", width=0)
                ui.Button("Run for", width=0, clicked_fn=lambda: self._schedule_replicator_action(run_replicator),
                          tooltip="Run replicator for so many frames")
            
                with ui.ZStack(width=0):
                    l = ui.Label("", style={"color": ui.color.transparent, "margin_width": 10})
                    self.frame_change = ui.StringField(model=self.frames)
                    self.frame_change_cb = self.frame_change.model.add_value_changed_fn(lambda m, l=l: set_text(l, m))
                ui.Label("frame(s)")

    ###############################
    # End UI
    ###############################

        
    def _schedule_replicator_action(self, action):
        if self._replicator_task is not None and not self._replicator_task.done():
            post_notification(
                "A Replicator operation is already in progress.",
                duration=5, status=NotificationStatus.WARNING,
            )
            return
        self._replicator_task = asyncio.ensure_future(action())
        self._replicator_task.add_done_callback(self._replicator_action_finished)

    def _replicator_action_finished(self, task):
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error(
                "Replicator operation failed: %s", error,
                exc_info=(type(error), error, error.__traceback__),
            )
            post_notification(
                f"Replicator operation failed: {error}",
                duration=10, status=NotificationStatus.WARNING,
            )

    def destroy(self) -> None:
        if self._replicator_task is not None and not self._replicator_task.done():
            self._replicator_task.cancel()
        self.frames = None
        self.defect_semantic = None
        if self.frame_change is not None:
            self.frame_change.model.remove_value_changed_fn(self.frame_change_cb)
        if self.defect_params is not None:
            self.defect_params.destroy()
            self.defect_params = None
        if self.object_params is not None:
            self.object_params.destroy()
            self.object_params = None
        if self.defect_text is not None:
            self.defect_text.destroy()
            self.defect_text = None
        return super().destroy()
