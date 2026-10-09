from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel


class LightDomainRandomizationParameters(BaseModel):
    light_intensity_min_value: Optional[float] = None
    light_intensity_max_value: Optional[float] = None
    light_rotation_min_value: Optional[float] = None
    light_rotation_max_value: Optional[float] = None
    light_scale_min_value: Optional[float] = None
    light_scale_max_value: Optional[float] = None
    light_position_min_value: Optional[float] = None
    light_position_max_value: Optional[float] = None
    light_color_min_value: Optional[List[float]] = None
    light_color_max_value: Optional[List[float]] = None
    light_count: Optional[int] = None
    active: bool = False


class CameraDomainRandomizationParameters(BaseModel):
    camera_distance_min_value: Optional[List[float]] = None
    camera_distance_max_value: Optional[List[float]] = None
    camera_prims: Optional[List[Tuple[str, Tuple[Tuple[float, float, float], ...]]]] = None
    active: bool = False

class ColorDomainRandomizationParameters(BaseModel):
    prim_colors: Optional[Dict[str, List[Tuple[float, float, float, float]]]] = None
    texture_randomization: bool = False
    active: bool = False

class MaterialDomainRandomizationParameters(BaseModel): 
    material_prims: Optional[Dict[str, List[str]]] = None
    created_materials: Optional[Dict[str, List[str]]] = None
    active: bool = False

class DomainRandomizationRequest(BaseModel):
    # Light params
    light_domain_randomization_params: LightDomainRandomizationParameters
    # Camera params
    camera_domain_randomization_params: CameraDomainRandomizationParameters
    # Color params
    color_domain_randomization_params: ColorDomainRandomizationParameters
    # Material params
    material_domain_randomization_params: MaterialDomainRandomizationParameters
