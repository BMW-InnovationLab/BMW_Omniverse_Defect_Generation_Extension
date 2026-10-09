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
import omni.replicator.core as rep
import carb
from defect.generation.utils.helpers import get_textures, get_prim, get_all_children_paths, get_bbox_dimensions, rgba_to_rgb_dict, rgba_to_rgb_list, copy_prim, search_color_properties, create_color_attr
from defect.generation.domain.models.defect_generation_request import DefectGenerationRequest, DefectObject
from defect.generation.domain.models.domain_randomization_request import DomainRandomizationRequest, LightDomainRandomizationParameters, CameraDomainRandomizationParameters, ColorDomainRandomizationParameters, MaterialDomainRandomizationParameters
import logging
import os
import omni
import random
from defect.generation.core.writer.bmw_writer import BMWWriter
from pxr import Sdf, UsdShade, Usd, UsdGeom

logger = logging.getLogger(__name__)

def _create_randomizers():

    def move_defect(defect_objet: DefectObject, prim_path: str):

        semantic_label = defect_objet.args.get("semantic_label", "default")
        rot_x_min = defect_objet.args.get("rot_x_min", 0)
        rot_x_max = defect_objet.args.get("rot_x_max", 360)
        rot_y_min = defect_objet.args.get("rot_y_min", 0)
        rot_y_max = defect_objet.args.get("rot_y_max", 360)
        rot_z_min = defect_objet.args.get("rot_z_min", 0)
        rot_z_max = defect_objet.args.get("rot_z_max", 360)
        dim_h_min = defect_objet.args.get("dim_h_min", 0)
        dim_h_max = defect_objet.args.get("dim_h_max", 1)
        dim_w_min = defect_objet.args.get("dim_w_min", 0)
        dim_w_max = defect_objet.args.get("dim_w_max", 1)

        defects = rep.get.prims(semantics=[('uuid', defect_objet.uuid + '_mesh')])
        defect_prim = rep.get.prim_at_path(prim_path)
        with defects:
            #rep.randomizer.scatter_2d(surface_prims=[plane_samp, sphere_samp], check_for_collisions=True)
            rep.randomizer.scatter_2d(defect_prim, seed=random.randint(0, 999999))
            rep.modify.pose(
                rotation=rep.distribution.uniform(
                    (rot_x_min, rot_y_min, rot_z_min), 
                    (rot_x_max, rot_y_max, rot_z_max)
                ),
                scale=rep.distribution.uniform(
                    (1, dim_h_min,dim_w_min),
                    (1, dim_h_max, dim_w_max)
                )
            )

        return defects.node
    
    def change_defect_image(defect_objet: DefectObject, texture_dir: str):
        texture_dir = os.path.join(texture_dir, defect_objet.defect_name)
        diffuse_textures = get_textures(texture_dir, "_D.png")
        normal_textures = get_textures(texture_dir, "_N.png")
        roughness_textures = get_textures(texture_dir, "_R.png")

        projections = rep.get.prims(semantics=[('uuid', defect_objet.uuid + '_projectmat')])
        seed=random.randint(0, 999999)
        with projections:
            rep.modify.projection_material(
                diffuse=rep.distribution.choice(diffuse_textures,seed=seed),
                normal=rep.distribution.choice(normal_textures,seed=seed),
                roughness=rep.distribution.choice(roughness_textures,seed=seed))
            rep.modify.visibility(rep.distribution.choice([True, False]))
        return projections.node

    rep.randomizer.register(move_defect)
    rep.randomizer.register(change_defect_image)

    def change_light(light_randomization: LightDomainRandomizationParameters):
        lights = rep.create.light(
                    light_type="Distant",
                    color=rep.distribution.uniform(light_randomization.light_color_min_value, light_randomization.light_color_max_value),
                    intensity=rep.distribution.uniform(light_randomization.light_intensity_min_value, light_randomization.light_intensity_max_value),
                    position=rep.distribution.uniform(light_randomization.light_position_min_value, light_randomization.light_position_max_value),
                    scale=rep.distribution.uniform(light_randomization.light_scale_min_value, light_randomization.light_scale_max_value),
                    rotation =  rep.distribution.uniform(light_randomization.light_rotation_min_value, light_randomization.light_rotation_max_value),
                    count=light_randomization.light_count,
                )
        return lights.node
    rep.randomizer.register(change_light)


def _create_camera(position=None, look_at=None):
    camera = rep.create.camera(position=position, look_at=look_at, clipping_range=(0.001, 10000))
    logger.info(f"Creating Camera: {camera}")
    return camera

def _default_camera_pose(prim_paths):
    """Return a camera position/look-at pair that frames the union of the given prims' world bounds."""
    bounds = [get_bbox_dimensions(str(path)) for path in prim_paths]
    if not bounds:
        return None, None
    mins = [min(b[0][i] for b in bounds) for i in range(3)]
    maxs = [max(b[1][i] for b in bounds) for i in range(3)]
    if any(abs(v) > 1e30 for v in mins + maxs):
        return None, None
    center = tuple((lo + hi) / 2 for lo, hi in zip(mins, maxs))
    extent = max(max(hi - lo for lo, hi in zip(mins, maxs)), 1e-3)
    distance = extent * 2.0
    position = (center[0] + distance, center[1] + distance, center[2] + distance)
    return position, center

def _create_camera_randomizer():
    def change_camera(change_camera_params, prim_defects_path, camera_domain_randomization_params: CameraDomainRandomizationParameters):
        for camera_option in change_camera_params:
                camera_randomization_params = camera_option["randomization"]
                camera = camera_option["camera"]
                scatter_prim_path, look_at_coordinates = camera_randomization_params
                if not scatter_prim_path and look_at_coordinates :
                    logger.warning(f"Routed omni graph to [NO] scatter prim and [YES] look at prim...")
                    # Create a sphere scatter prim around the look at prim
                    scatter_prim_path = rep.create.sphere(position=tuple((min_val + max_val) / 2 for min_val, max_val in zip(look_at_coordinates[0], look_at_coordinates[1])), scale=camera_domain_randomization_params.camera_distance_max_value, visible=False)
                else:
                    # Using the provided scatter prim and look at prim
                    logger.warning(f"Routed omni graph to [YES] scatter prim and [YES] look at prim...")

                with camera:
                    rep.randomizer.scatter_3d(scatter_prim_path, seed=random.randint(0, 999999))
                    rep.modify.pose(look_at=rep.distribution.uniform(look_at_coordinates[0],look_at_coordinates[1]))

    rep.randomizer.register(change_camera)


def get_original_materials(path):
    """
    Get the original materials bound to mesh prims under a given path in the USD stage. It traverses the stage starting form the given path and collects the materials 
    originally bound to the found meshes. It gathers unique materials and their corresponding shader names.

    Parameters:
        path (str): The USD path to start the traversal from.

    Returns:
        Tuple[List[str], Dict[str, str], Dict[str, str]]:
            - List of children paths found under the given path and have Mesh type.
            - Dictionary mapping each mesh prim path to its bound material path.
            - Dictionary mapping each unique material path to its shader name.
    """
    stage = omni.usd.get_context().get_stage()

    original_materials = {}
    unique_materials = {}
    children_path = []

    # Get all mesh children paths
    prim = stage.GetPrimAtPath(path)

    if prim.GetTypeName() == "Xform":
        found_mats = [str(x.GetPath()) for x in Usd.PrimRange(prim) if x.IsA(UsdGeom.Mesh)]
        children_path = found_mats
    else:
        children_path = [path]

    for child_path in children_path:
        stage_prim = stage.GetPrimAtPath(child_path)
        try: 
            # Get original material bound to each child path in the stage
            bind_mat_path = UsdShade.MaterialBindingAPI(stage_prim).ComputeBoundMaterial()
            material_path = bind_mat_path[-1].GetForwardedTargets()[0]
 
            if material_path not in unique_materials:
                material_prim = stage.GetPrimAtPath(material_path)
                # Get the Shader of that material
                shader_name = material_prim.GetAllChildrenNames()[0]
                unique_materials[material_path] = shader_name

            # Store the original material
            original_materials[child_path] = str(material_path)

        except Exception as e: 
            carb.log_warn(f"Failed to get material for {child_path}: {e}.")
            original_materials[child_path] = None

    return children_path, original_materials, unique_materials


def _create_color_randomizer(color_domain_randomization_params): 
    prim_colors = color_domain_randomization_params.prim_colors
    all_original_materials = {}

    if prim_colors is not None: 
        # Get RGB color values (OmmniPBR materials use RGB colors not RGBA)
        prim_colors = rgba_to_rgb_dict(prim_colors)
        
        created_materials = {}
        # Create an OmniPBR material with each specified color
        for path in prim_colors: 
                 
            # Get all original materials of all selected prims
            children_path, original_materials, unique_materials = get_original_materials(path)

            colors = prim_colors[path]
            mats = rep.create.material_omnipbr(diffuse=rep.distribution.choice(colors, with_replacements=False), count=len(colors))
            for child_path in children_path:
                created_materials[str(child_path)] = mats
            
            all_original_materials[path] = original_materials

        seed=random.randint(0, 999999)
        def get_colors():
            for prim_path, mat in created_materials.items():
                prim = rep.get.prim_at_path(prim_path)
                # Change the material applied on each prim to change the color
                with prim:
                    rep.randomizer.materials(mat, seed=seed)
            return prim.node

        rep.randomizer.register(get_colors)
    return all_original_materials

def _create_texture_color_randomizer(color_domain_randomization_params, material_prims): 
    """
    Creates textured color randomization by creating copies of the original materials bound to the selected prims and assigning new base colors to the copies.

    Parameters:
        color_domain_randomization_params: Parameters that include prim_colors

    Returns:
        Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, List[str]]]]:
            - A dictionary mapping each prim path to its original material.
            - A dictionary mapping each parent prim path to the new created material paths and the corresponding prim paths that they should be bound to.
    """
    prim_colors = color_domain_randomization_params.prim_colors
    if not prim_colors:
        return {}, {}

    stage = omni.usd.get_context().get_stage()
    mat_idx = 0

    if prim_colors is not None:
        created_materials = {}
        omni_pbr_materials = {}
        all_original_textures = {}
        material_color_attribute = {}
        color_attribute_name = ""
        texture_colors = prim_colors

        for path in prim_colors:
            # Check if material_prims is not None and if the current path is in material_prims
            if material_prims is not None and path in material_prims:
                logger.warning(f'Skipping {path} as it is in material_prims')
                continue
            
            created_materials[path] = {}
            omni_pbr_materials[path] = {}
            all_original_textures[path] = {}

            # Get all original materials of all selected prims
            children_path, original_materials, unique_materials = get_original_materials(path)
            
            for child_path in children_path:

                # Check if original material exists
                material_path = original_materials[child_path]

                if material_path is not None:
                    # Original material exists, Create a copy of the material for each unique material
                    mat_path = f"/Replicator/Looks/OmniPBR_{mat_idx}"
                    copy_prim(material_path, mat_path)

                    # Save material color attribute name and type
                    if mat_path not in material_color_attribute: 
                        material_color_attribute[mat_path] = []
                
                    mat_prim = stage.GetPrimAtPath(material_path).GetChildren()[0]
                    color_attributes = search_color_properties(mat_prim.GetAttributes())
                    for attr_name, attr_type in color_attributes.items(): 
                        create_color_attr(mat_path,attr_name,attr_type)
                        if attr_type == "float3":
                            texture_colors[path] = rgba_to_rgb_list(prim_colors[path])
                        material_color_attribute[mat_path].append(attr_name)
                else: 
                    # Original material does not exist, Create a new OmniPBR Material
                    mat = rep.create.material_omnipbr()                 
                    mat_path = str(mat.get_input('primsIn')[0])
                    # OmniPBR Materials have "inputs:diffuse_color_constant" color property, which takes RGB values. 
                    color_attribute_name = "inputs:diffuse_color_constant"
                    texture_colors[path] = rgba_to_rgb_list(prim_colors[path])
                    material_color_attribute[mat_path] = [color_attribute_name]
                
                omni_pbr_materials[path][material_path] = mat_path
                created_materials[path][mat_path] = []
                mat_idx += 1

            # Store the OmniPBR material paths along with the prim paths that they will be bound to
            for prim_path in children_path:
                original_material = original_materials[prim_path]
                omni_pbr_path = omni_pbr_materials[path][original_material]
                created_materials[path][omni_pbr_path].append(prim_path)

            all_original_textures[path] = original_materials

        def get_colors():
            for parent_path in created_materials:
                seed = random.randint(0, 999999)                        

                for material, prim_path in created_materials[parent_path].items():
                    # Apply the color to each material using the correct color attribute
                    color_attribute_name = material_color_attribute[material]
                    mat_prim = rep.get.prim_at_path(str(material))
                    with mat_prim:
                        for attr_name in color_attribute_name:
                            # Get a random color for all prims in the parent_path
                            chosen_color = rep.distribution.choice(texture_colors[parent_path], seed=seed)
                            rep.modify.attribute(name=attr_name, value=chosen_color)

        rep.randomizer.register(get_colors)
        return all_original_textures, created_materials

def _create_material_randomizer(material_randomization_params, prim_colors):
    """
    Material randomizer that randomizes the material on a chosen prim by creating materials form the MDL urls. 
    Color randomization can also occur on the random materials provided that they have an "inputs:BaseColor" attribute. 

    Parameters:
        material_domain_randomization_params: Parameters that include material_prims and material_folders.
        prim_colors: Dictionary mapping prim_paths to a list of RGBA colors

    Returns:
        Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, List[str]]]]:
            - A dictionary mapping each prim path to its original material.
            - A dictionary mapping each parent prim path to the new created material paths and the corresponding prim paths that they should be bound to.
    """
    children_prims = {}
    all_original_materials = {}
    stage = omni.usd.get_context().get_stage()
    material_color_attrs = {}
    created_materials = material_randomization_params.created_materials or {}

    for material_prim, material_folders in (material_randomization_params.material_prims or {}).items():
        # Store the original materials of the prim_path and its children prims.
        children_path, original_materials, unique_materials = get_original_materials(material_prim)
        children_prims[material_prim] = children_path
        all_original_materials[material_prim] = original_materials
        if prim_colors:
            # If color material randomization is enabled, get and store the material's color attributes
            if material_prim not in material_color_attrs: 
                material_color_attrs[material_prim] = []

            for mat_path in created_materials.get(material_prim, []):
                # Get Material Shader path from stage
                if len(stage.GetPrimAtPath(mat_path).GetChildren())>0:
                    shader_path = str(stage.GetPrimAtPath(mat_path).GetChildren()[0].GetPath())
                else: 
                    shader_path = mat_path
                # Get all attributes from the Shader Prim and search for found color attributes. 
                material_properties = stage.GetPrimAtPath(shader_path).GetAttributes()
                change_color_attr = search_color_properties(material_properties)
                material_color_attrs[material_prim].append((str(mat_path), change_color_attr))

    def randomize_materials():
        for prim_path in material_randomization_params.material_prims or {}:
            children_paths = children_prims[prim_path]
            materials_list = created_materials.get(prim_path, [])

            materials = []
            if prim_colors:
                # If color material randomization is enabled, get the stored material and color attributes
                materials_list = material_color_attrs.get(prim_path, [])
                for mat_path, color_attr in materials_list: 
                    if color_attr != {}:
                        # If color attributes were found for the material, get the shader path to modify its attributes. 
                        if len(stage.GetPrimAtPath(mat_path).GetChildren())>0:
                            # If material prim has children (shader), get shader path
                            shader_path = str(stage.GetPrimAtPath(mat_path).GetChildren()[0].GetPath())
                        else: 
                            # Else, given material path is shader path. 
                            shader_path = mat_path    

                        # Determine if we need RGB or RGBA colors
                        use_rgba = any(attr_type == "float4" for attr_type in color_attr.values())
                        colors = prim_colors if use_rgba else rgba_to_rgb_dict(prim_colors)
                        
                        # Get a random color from the selected colors and modify the shader's respective attributes. 
                        seed=random.randint(0, 999999)                        
                        for attr_name, attr_type in color_attr.items(): 
                            chosen_color = rep.distribution.choice(colors[prim_path], seed=seed)
                            attr_name = f"inputs:{attr_name}"
                            rep.modify.attribute(name=attr_name, value=chosen_color, input_prims = shader_path)
                        
                        # Append material to list of materials that will be used for randomization                   
                        materials.append(mat_path)

                    else: 
                        logger.warning(f'Material {mat_path} has no color attributes.')
                if not materials:
                    materials = created_materials.get(prim_path, [])
            else: 
                # If color material randomization is not enabled, get the materials from the created_materials list. 
                materials = materials_list
            if not materials:
                logger.warning(f"No materials are available to randomize for {prim_path}.")
                continue
            # Randomly select a material and apply it on the input prim and all its children. 
            chosen_material = rep.distribution.choice(materials, seed=random.randint(0, 999999))
            rep.modify.material(chosen_material, input_prims=children_paths)

    rep.randomizer.register(randomize_materials)
    return all_original_materials

def _create_defects(defect_objet: DefectObject, prim_path: str):
    semantic_label = defect_objet.args.get("semantic_label", "default")
    # Get prim to place defect on
    target_prim = rep.get.prim_at_path(prim_path)
    # Create cube for projecting the material
    cube = rep.create.cube(visible=False, semantics=[('class', semantic_label + '_mesh'),('uuid', defect_objet.uuid + '_mesh')], position=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0), rotation=(0, 0, 90))
    with target_prim:
        rep.create.projection_material(cube, [('class', semantic_label + '_projectmat'),('uuid', defect_objet.uuid + '_projectmat')])


def create_defect_layer(defect_generation_request: DefectGenerationRequest, domain_randomization_request :DomainRandomizationRequest, frames: int = 1, output_dir: str = "_defects", rt_subframes: int = 0, use_seg: bool = False, use_bb: bool = True, use_bmw: bool =True):

    if len(defect_generation_request.texture_dir) <= 0:
        carb.log_error("No directory selected")
        return
    with rep.new_layer("Defect"):
        change_camera_params = []
        render_list = []
        prim_defects_path = []
        parent_prim_defects_path = []
        all_original_textures = {}
        created_textures = {}

        # Create randomizers
        _create_randomizers()
        _create_camera_randomizer()


        # Get Texture Randomization params
        if domain_randomization_request.color_domain_randomization_params.active:
            if domain_randomization_request.color_domain_randomization_params.texture_randomization:
                if domain_randomization_request.material_domain_randomization_params.active:
                    original_textures, created_textures = _create_texture_color_randomizer(domain_randomization_request.color_domain_randomization_params, domain_randomization_request.material_domain_randomization_params.material_prims)
                else: 
                    original_textures, created_textures = _create_texture_color_randomizer(domain_randomization_request.color_domain_randomization_params, None)
            else:
                original_textures = _create_color_randomizer(domain_randomization_request.color_domain_randomization_params)
            all_original_textures.update(original_textures)

        # Get material params
        if domain_randomization_request.material_domain_randomization_params.active:
            material_randomization_params = domain_randomization_request.material_domain_randomization_params
            original_textures = _create_material_randomizer(material_randomization_params, domain_randomization_request.color_domain_randomization_params.prim_colors)
            all_original_textures.update(original_textures)
        # Get camera params
        camera_randomization_params = domain_randomization_request.camera_domain_randomization_params.camera_prims or []

        # Go through every prim which has defects
        for defect_prim_objects in defect_generation_request.prim_defects:
            # Add list of meshes with derfects
            prim = get_prim(defect_prim_objects.prim_path)
            # Populate parent prim defects (Top level of defects)
            parent_prim_defects_path.append(Sdf.Path(defect_prim_objects.prim_path))

            if prim.GetTypeName() == "Xform":
                logger.info(f"{defect_prim_objects.prim_path} is an Xform")
                children = []
                prim_defects_path.extend(get_all_children_paths(children, prim))
            else:
                logger.info(f"{defect_prim_objects.prim_path} is not an Xform")
                prim_defects_path.append(Sdf.Path(defect_prim_objects.prim_path))

            # Create defects
            for defect in defect_prim_objects.defects:
                _create_defects(defect, prim_path=defect_prim_objects.prim_path)

        # Remove duplicate paths
        prim_defects_path = list(set(prim_defects_path))
        parent_prim_defects_path = list(set(parent_prim_defects_path))
        logger.warning(f"All prims with defects: {prim_defects_path}, parent prims: {parent_prim_defects_path}")   
 

        # Camera scatter prim and lookat prim randomization
        if domain_randomization_request.camera_domain_randomization_params.active:
            # If no scatter prim or look at prim specified, create a look at prim for each defect
            if len(domain_randomization_request.camera_domain_randomization_params.camera_prims) == 0:
                logger.warning(f"No camera parameters were specified, parent_paths are : {parent_prim_defects_path} ")
                for prim_defect_path in parent_prim_defects_path:
                    camera_randomization_params.append((None, get_bbox_dimensions(str(prim_defect_path))))
                logger.warning(f"No camera prims were specified, new camera params: {camera_randomization_params}")
            #Transform every (scatter_prim, None) in camera params into a scatter prim paired with every defect parent prim in the scene
            expanded_camera_params = []
            for camera_param in camera_randomization_params:
                if not camera_param[1] and camera_param[0]:
                    expanded_camera_params.extend(
                        (camera_param[0], get_bbox_dimensions(str(prim_defect_path)))
                        for prim_defect_path in parent_prim_defects_path
                    )
                else:
                    expanded_camera_params.append(camera_param)
            camera_randomization_params = expanded_camera_params
                # Create cameras with randomization information
            for camera_param in camera_randomization_params:
                camera = _create_camera()
                change_camera_params.append({"camera": camera, "randomization": camera_param})
                render_product = rep.create.render_product(camera, (1024, 1024))
                render_list.append(render_product)
            logger.warning(f"Randomization params are : {change_camera_params}")
        else:
            # If no camera domain randomization, frame all defect targets with a fixed camera
            position, look_at = _default_camera_pose(parent_prim_defects_path)
            camera = _create_camera(position=position, look_at=look_at)
            render_product = rep.create.render_product(camera, (1024, 1024))
            render_list.append(render_product)

        # Initialize and attach writer
        if use_bmw:
            # Create a list containing all the defect names present in scene.
            defect_names = []
            semantic_labels = []
            for prim_defect in defect_generation_request.prim_defects:
                for defect in prim_defect.defects:
                    if defect.defect_name not in defect_names:
                        defect_names.append(defect.defect_name)
                    if defect.args.get("semantic_label", "default") not in semantic_labels:
                        semantic_labels.append(defect.args.get("semantic_label", "default"))

                        
            rep.WriterRegistry.register(BMWWriter)
            writer = rep.WriterRegistry.get("BMWWriter")
            writer.initialize(output_dir=output_dir, rgb=True, bounding_box_2d_tight=use_bb,semantic_segmentation=use_seg, defects=semantic_labels)
        else:
            writer = rep.WriterRegistry.get("BasicWriter")
            writer.initialize(output_dir=output_dir, rgb=True, semantic_segmentation=use_seg, bounding_box_2d_tight=use_bb)
        # Attach all render products to the writer
        writer.attach(render_list)
        defect_count = sum(len(p.defects) for p in defect_generation_request.prim_defects)
        logger.warning(
            f"Replicator graph ready: {defect_count} defect projection(s), {len(render_list)} camera(s), "
            f"{frames} frame(s), output: {output_dir}"
        )

        # Setup randomization
        with rep.trigger.on_frame(max_execs=frames, rt_subframes=rt_subframes):

            # Light domain randomization
            if domain_randomization_request.light_domain_randomization_params.active:
                rep.randomizer.change_light(domain_randomization_request.light_domain_randomization_params)
            # Camera domain randomization
            if domain_randomization_request.camera_domain_randomization_params.active:
                rep.randomizer.change_camera(change_camera_params, prim_defects_path, domain_randomization_request.camera_domain_randomization_params)
            # Defects domain randomization
            for defect_prim_objects in defect_generation_request.prim_defects:
                for defect in defect_prim_objects.defects:
                    rep.randomizer.move_defect(defect_objet=defect, prim_path=defect_prim_objects.prim_path)
                    rep.randomizer.change_defect_image(defect_objet=defect, texture_dir=defect_generation_request.texture_dir)

            # Color domain randomization
            if domain_randomization_request.color_domain_randomization_params.active:
                rep.randomizer.get_colors()

            # Material domain randomization
            if domain_randomization_request.material_domain_randomization_params.active: 
                rep.randomizer.randomize_materials()

            # Texture domain randomization
            if created_textures:
                for parent_path in created_textures:
                    for material, prim_paths in created_textures[parent_path].items():
                        # Bind the material to the corresponding prim_paths
                        rep.modify.material([material], input_prims = prim_paths)
    return all_original_textures       
