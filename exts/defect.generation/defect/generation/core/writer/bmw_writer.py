import io
import json
import logging
from typing import List, Optional

import numpy as np
from omni.replicator.core import AnnotatorRegistry, BackendDispatch, Writer

logger = logging.getLogger(__name__)

# Suffixes appended to a defect's semantic label by core.replicator.replicator_defect._create_defects
_LABEL_SUFFIXES = ("_projectmat", "_mesh")
_INVALID_BBOX_SIZE = 2147483647


def normalize_label(label: str) -> str:
    for suffix in _LABEL_SUFFIXES:
        if label.endswith(suffix):
            return label[: -len(suffix)]
    return label


def _array(annotator_output):
    if isinstance(annotator_output, dict):
        return annotator_output.get("data")
    return annotator_output


def _id_to_labels(annotator_output) -> dict:
    if not isinstance(annotator_output, dict):
        return {}
    info = annotator_output.get("info") or annotator_output
    return info.get("idToLabels") or {}


def _class_label(labels) -> Optional[str]:
    if isinstance(labels, dict):
        label = labels.get("class")
    else:
        label = labels
    if not label:
        return None
    # Several class labels on one prim are comma separated
    return normalize_label(str(label).split(",")[0].strip())


class BMWWriter(Writer):
    """Writes RGB images plus BMW-format bounding box JSON and remapped segmentation.

    Output layout (per render product sub-folder when more than one camera is used)::

        images/<frame>.png
        labels/json/<frame>.json
        semantic_segmentation/<frame>.npy|.json
    """

    def __init__(
            self,
            output_dir,
            rgb: bool = True,
            bounding_box_2d_tight: bool = False,
            semantic_segmentation: bool = False,
            image_output_format="png",
            defects: Optional[List[str]] = None,
    ):
        self._output_dir = output_dir
        self._backend = BackendDispatch(output_dir=output_dir)
        self.backend = self._backend
        self._frame_id = 0
        self._image_output_format = image_output_format
        self.annotators = []
        self.all_labels = {normalize_label(d) for d in (defects or [])}
        self.semantic_label_map = {}

        if rgb:
            self.annotators.append(AnnotatorRegistry.get_annotator("rgb"))

        if bounding_box_2d_tight:
            self.annotators.append(AnnotatorRegistry.get_annotator("bounding_box_2d_tight",
                                                                   init_params={"semanticTypes": ["class"]}))

        if semantic_segmentation:
            self.annotators.append(AnnotatorRegistry.get_annotator(
                "semantic_segmentation",
                init_params={
                    "colorize": False,
                    "semanticTypes": ["class"]
                }
            ))

    def check_bbox_area(self, bbox_data, size_limit):
        length = abs(bbox_data['x_min'] - bbox_data['x_max'])
        width = abs(bbox_data['y_min'] - bbox_data['y_max'])
        return length * width > size_limit

    @staticmethod
    def _render_product_postfixes(data: dict) -> List[str]:
        # Legacy data structure: a single render product uses bare annotator names,
        # multiple render products use "<annotator>-<render product name>" keys.
        render_products = [key[len("rp_"):] for key in data.keys() if key.startswith("rp_")]
        if len(render_products) <= 1:
            return [""]
        return [f"-{name}" for name in render_products]

    def _is_defect(self, labels) -> bool:
        label = _class_label(labels)
        return label is not None and label in self.all_labels

    def _bbox_json(self, bbox_output) -> list:
        bbox_data = _array(bbox_output)
        id_to_labels = _id_to_labels(bbox_output)
        json_data = []
        if bbox_data is None:
            return json_data
        for bbox in bbox_data:
            semantic_id = int(bbox["semanticId"])
            labels = id_to_labels.get(str(semantic_id), id_to_labels.get(semantic_id))
            if labels is None or not self._is_defect(labels):
                continue
            box = {"x_min": bbox["x_min"], "y_min": bbox["y_min"], "x_max": bbox["x_max"], "y_max": bbox["y_max"]}
            if not self.check_bbox_area(box, 0.5):
                continue
            width = int(abs(box["x_max"] - box["x_min"]))
            height = int(abs(box["y_max"] - box["y_min"]))
            if width == _INVALID_BBOX_SIZE or height == _INVALID_BBOX_SIZE:
                continue
            json_data.append({"Id": semantic_id,
                              "ObjectClassName": _class_label(labels),
                              "Left": int(box["x_min"]),
                              "Top": int(box["y_min"]),
                              "Right": int(box["x_max"]),
                              "Bottom": int(box["y_max"])})
        return json_data

    def _write_semantic_segmentation(self, seg_output, seg_dir: str):
        semantic_data = np.asarray(_array(seg_output))
        id_to_labels = _id_to_labels(seg_output)
        remapped_data = np.zeros(semantic_data.shape[:2], dtype=np.uint32)
        if semantic_data.ndim > 2:
            semantic_data = semantic_data.view(np.uint32).reshape(semantic_data.shape[:2])
        label_mapping = {}
        for instance_id, labels in id_to_labels.items():
            if not self._is_defect(labels):
                continue
            class_name = _class_label(labels)
            if class_name not in self.semantic_label_map:
                self.semantic_label_map[class_name] = len(self.semantic_label_map) + 1
            class_id = self.semantic_label_map[class_name]
            label_mapping[class_id] = {"class": class_name}
            remapped_data[semantic_data == int(instance_id)] = class_id

        self._backend.write_blob(f"{seg_dir}/{self._frame_id}.json", json.dumps(label_mapping).encode())
        buf = io.BytesIO()
        np.save(buf, remapped_data)
        self._backend.write_blob(f"{seg_dir}/{self._frame_id}.npy", buf.getvalue())

    def write(self, data):
        for postfix in self._render_product_postfixes(data):
            render_product_dir = f"{postfix[1:]}/" if postfix else ""
            rgb_key = f"rgb{postfix}"
            bbox_key = f"bounding_box_2d_tight{postfix}"
            seg_key = f"semantic_segmentation{postfix}"

            if rgb_key in data:
                self._backend.write_image(
                    f"{render_product_dir}images/{self._frame_id}.{self._image_output_format}",
                    _array(data[rgb_key]),
                )

            if bbox_key in data:
                self._backend.write_blob(
                    f"{render_product_dir}labels/json/{self._frame_id}.json",
                    json.dumps(self._bbox_json(data[bbox_key])).encode(),
                )

            if seg_key in data:
                self._write_semantic_segmentation(data[seg_key], f"{render_product_dir}semantic_segmentation")

        self._frame_id += 1
