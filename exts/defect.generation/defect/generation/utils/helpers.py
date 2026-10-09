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
import uuid
from typing import List
import omni.usd
import carb
import omni.kit.commands
import os
from pxr import Usd, Gf, Sdf
from defect.generation.domain.models.defect_generation_request import PrimDefectObject, DefectObject
import matplotlib as mpl
import json
import inspect
def get_current_stage():
    context = omni.usd.get_context()
    stage = context.get_stage()
    return stage

def check_path(path: str) -> bool:
    if not path:
        carb.log_error("No path was given")
        return False
    return True

def is_valid_prim(path: str):
    prim = get_prim(path)
    if not prim.IsValid():
        carb.log_warn(f"No valid prim at path given: {path}")
        return None
    return prim

def delete_prim(path: str):
    result = omni.kit.commands.execute('DeletePrims',
        paths=[path],
        destructive=False)
    succeeded = result[0] if isinstance(result, tuple) else result is not False
    prim = get_prim(path)
    if not succeeded or (prim and prim.IsValid()):
        raise RuntimeError(f"Failed to delete prim at {path}")

def get_prim_attr(prim_path: str, attr_name: str):
    prim = get_prim(prim_path)
    return prim.GetAttribute(attr_name).Get()

def get_textures(dir_path, png_type=".png"):
    textures = []
    dir_path += "/"
    for file in os.listdir(dir_path):
        if file.endswith(png_type):
            textures.append(dir_path + file)
    textures.sort()
    return textures

def list_mdl_materials(dir_path):
    base_url = dir_path
    mats = omni.client.list(base_url)
    list_entries = []
    for entry in mats[1]:
        if entry.relative_path != ".thumbs":
            mat_path = os.path.join(base_url, entry.relative_path)
            if mat_path.endswith(".mdl"):
                list_entries.append(mat_path)
            elif "." not in mat_path:  # Check if the entry is a directory and not .mdl file
                list_entries.extend(list_mdl_materials(mat_path))  # Recurse into subdirectory

    return list_entries


def get_prim(prim_path: str):
    stage = get_current_stage()
    prim = stage.GetPrimAtPath(prim_path)
    return prim


def get_all_children_paths(children, parent_prim: Usd.Prim):
    # Iterates over all children
    for child_prim in parent_prim.GetAllChildren():
        if child_prim.GetTypeName() == "Xform":
            get_all_children_paths(children, child_prim)
        else:
            children.append(child_prim.GetPath())
    return children


def generate_small_uuid():
    return str(uuid.uuid4())[:8]

def get_center_coordinates(prim_path: str):
    stage = omni.usd.get_context().get_stage()
    prim = stage.GetPrimAtPath(prim_path)
    matrix: Gf.Matrix4d = omni.usd.get_world_transform_matrix(prim)
    translate: Gf.Vec3d = matrix.ExtractTranslation()
    return translate

def fetch_all_defect_objects(prim_defect_list: List[PrimDefectObject]) -> List[DefectObject]:
    all_defect_objects = []
    for prim_defect in prim_defect_list:
        for defect in prim_defect.defects:
            all_defect_objects.append(defect)
    return all_defect_objects

def find_prim_defect_by_uuid(prim_defects: List[PrimDefectObject], target_uuid: str) -> PrimDefectObject:
    for prim_defect in prim_defects:
        for defect in prim_defect.defects:
            if defect.uuid == target_uuid:
                return prim_defect

def rgb_to_hex(color):
    # Check if the input color is in RGB or RGBA format
    if len(color) == 3:
        r, g, b = color
    elif len(color) == 4:
        r, g, b, _ = color
    else:
        raise ValueError("Color input must be an RGB or RGBA tuple")
    hex_color = mpl.colors.rgb2hex((r, g, b), keep_alpha=False)
    return hex_color

def get_bbox_dimensions(prim_path):
    #Get the Top, Bottom, Left, Right Coordinates of a prim based on its path
    bbox = omni.usd.get_context().compute_path_world_bounding_box(prim_path)
    min_coordinates = bbox[0]
    max_coordinates = bbox[1]
    return min_coordinates,max_coordinates


def rgba_to_rgb_list(rgba_list): 
    # Convert RGBA values in a list to RGB values.
    rgb_list = []
    for rgba in rgba_list: 
        rgb = rgba[:3]
        rgb_list.append(rgb)
    return rgb_list


def rgba_to_rgb_dict(rgba_dict):
    # Convert RGBA values in a dictionary to RGB values and returns a dictionary where each key maps to a list of RGB tuples.
    rgb_dict = {} 
    for key, rgba_list in rgba_dict.items():
        rgb_list = []  
        for rgba in rgba_list:
            # Extract the first three elements (RGB) from the RGBA tuple and append to the current RGB list
            rgb = rgba[:3]  
            rgb_list.append(rgb)  

        rgb_dict[key] = rgb_list
    return rgb_dict  

def copy_prim(path_from: str, path_to: str): 
    omni.kit.commands.execute('CopyPrim',
        path_from=path_from,
        path_to=path_to,
        exclusive_select=True,
        copy_to_introducing_layer=False)
    
    copied_path = str(omni.usd.get_context().get_selection().get_selected_prim_paths()[0])
    return copied_path

def create_prim_with_default_xform(prim_type: str, prim_path: str):
    omni.kit.commands.execute('CreatePrimWithDefaultXform',
        prim_type=prim_type,
        prim_path=prim_path,
        attributes={},
        select_new_prim=True)
    
def create_color_attr(material_path, color_attr_name, color_attr_type):
    # Creates a color attribute input with specific name and type for the material specified by material_path. 
    # This ensures that the attribute will remain linked to the material during runtime. 
    mat_prim = get_current_stage().GetPrimAtPath(Sdf.Path(material_path))

    if color_attr_type == "float3": 
        # Initialize with default RGB values
        value = (0.0, 0.0, 0.0)                
        color_type = Sdf.ValueTypeNames.Color3f
    else: 
        # Initialize with default RGBA values
        value = (0.0, 0.0, 0.0, 0.0)
        color_type = Sdf.ValueTypeNames.Color4f

    with Sdf.ChangeBlock():
        omni.usd.create_material_input(
            mat_prim,
            color_attr_name,
            value, 
            color_type
            )
            
async def create_material(material_url: str, material_name: str, material_path: str, select_new_prim: bool=False):
    # Asynchronously create a material from an mdl file. 
    omni.kit.commands.execute('CreateMdlMaterialPrimCommand',
        mtl_url=material_url,               # This can be path to local or remote MDL
        mtl_name=material_name,             # sourceAsset:subIdentifier (i.e. the name of the material within the MDL)
        mtl_path=material_path,             # Prim path for the Material to create.
        select_new_prim=select_new_prim     # If to select the new created material after creation. Default is False.
    )
    
    created_material_path = str(omni.usd.get_context().get_selection().get_selected_prim_paths()[0])
    await omni.kit.app.get_app().next_update_async()
    selection = omni.usd.get_context().get_selection()
    await omni.kit.app.get_app().next_update_async()
    return created_material_path

def bind_material(material_path, prim_path):
  # Bind original material to prim
    omni.kit.commands.execute('BindMaterial',
        material_path=str(material_path),
        prim_path=[prim_path],
        strength=['weakerThanDescendants'])

def restore_original_materials(original_materials): 
    # Restore original materials for each prim
    print(f'original materials {original_materials}')
    if original_materials is not None:
        for parent_path in original_materials: 
            parent_materials = original_materials[parent_path] 
            if parent_materials is not None and len(parent_materials)>0:
                for child_path, material_path in original_materials[parent_path].items(): 
                        bind_material(material_path, child_path)

def search_color_properties(properties_list):
    # Search for color attributes specified in the color_attributes.json file from the list of all attributes of a material. 

    # Get JSON File path
    dir_path = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
    json_file_path = os.path.join(dir_path, 'color_attributes.json')

    with open(json_file_path, 'r') as file:
        color_inputs = json.load(file)["color_inputs"]

    result = {}
    # Iterate through each property or attribute in the list of all attributes
    for property in properties_list:
        # Get this property’s name with all namespace prefixes removed
        property = property.GetBaseName()
        for color_input in color_inputs:
            # If the material's color attribute is found in the json file, append to result.
            if property == color_input["name"]:
                result[property] = color_input['type']
    return result
