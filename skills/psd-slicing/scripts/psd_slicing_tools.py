"""
PSD slicing tools.

Command line utilities for PSD file operations, powered by psd-tools.
Provides tools for listing layers, toggling visibility, isolating layers,
exporting layers, and inspecting layer information.
"""

import argparse
import io
import logging
import os
import json
import sys
from typing import Dict, Any, List, Optional, Tuple


def _ensure_utf8_stdout() -> None:
    """确保 stdout/stderr 使用 UTF-8，避免 Windows 下 --raw 中文乱码。"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if getattr(stream, "buffer", None) is None:
            continue
        enc = (getattr(stream, "encoding") or "").lower()
        if enc in ("utf-8", "utf8"):
            continue
        wrapper = io.TextIOWrapper(
            stream.buffer,
            encoding="utf-8",
            errors="replace",
            line_buffering=True,
        )
        setattr(sys, stream_name, wrapper)

from psd_tools import PSDImage
from psd_tools.constants import Tag
from PIL import Image

# 默认不写日志文件，避免只读类调用（如 list_layers）产生写盘副作用。
# 需要落盘日志时设置环境变量 PSD_SLICING_LOG_FILE 为目标路径即可。
_log_fmt = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
logger = logging.getLogger("PsdSlicingTools")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _log_path = os.environ.get("PSD_SLICING_LOG_FILE", "").strip()
    if _log_path:
        _fh = logging.FileHandler(_log_path, encoding="utf-8")
        _fh.setLevel(logging.DEBUG)
        _fh.setFormatter(logging.Formatter(_log_fmt))
        logger.addHandler(_fh)
    else:
        _null = logging.NullHandler()
        logger.addHandler(_null)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open_psd(file_path: str) -> PSDImage:
    """Open a PSD file, raising a clear error on failure."""
    path = os.path.abspath(file_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"PSD file not found: {path}")
    return PSDImage.open(path)


def _find_layer(psd: PSDImage, layer_path: str):
    """
    Find a layer by its path (slash-separated names from root).
    Example: "Group1/SubGroup/LayerName"
    Also supports a simple layer name (searches recursively).
    """
    parts = [p.strip() for p in layer_path.replace("\\", "/").split("/") if p.strip()]

    if len(parts) == 1:
        return _find_layer_by_name(psd, parts[0])

    current = psd
    for part in parts:
        found = None
        for layer in current:
            if layer.name == part:
                found = layer
                break
        if found is None:
            raise ValueError(f"Layer not found at path segment '{part}' in '{layer_path}'")
        current = found
    return current


def _find_layer_by_name(parent, name: str):
    """Recursively search for a layer by name (depth-first)."""
    for layer in parent:
        if layer.name == name:
            return layer
        if layer.is_group():
            try:
                result = _find_layer_by_name(layer, name)
                if result is not None:
                    return result
            except Exception:
                pass
    return None


def _layer_path(layer) -> str:
    """Build the full path of a layer from root."""
    parts = []
    cur = layer
    while cur is not None and hasattr(cur, "name") and cur.name is not None:
        parts.append(cur.name)
        cur = cur.parent
    parts.reverse()
    return "/".join(parts)


def _layer_kind(layer) -> str:
    """Return a human-readable kind string."""
    if layer.is_group():
        return "group"
    return layer.kind


def _layer_summary(layer, depth: int = 0) -> Dict[str, Any]:
    """Return a summary dict for a single layer."""
    info: Dict[str, Any] = {
        "name": layer.name,
        "path": _layer_path(layer),
        "kind": _layer_kind(layer),
        "visible": layer.visible,
        "opacity": layer.opacity,
        "blend_mode": str(layer.blend_mode),
        "bbox": list(layer.bbox) if hasattr(layer, "bbox") else None,
        "size": [layer.width, layer.height] if hasattr(layer, "width") else None,
        "depth": depth,
    }
    if layer.is_group():
        info["children_count"] = len(list(layer))
    return info


def _build_layer_tree_text(parent, depth: int = 0) -> List[str]:
    """Build a compact text tree: one line per layer, indentation for hierarchy.

    Format per line:  ``{indent}{name} ({kind}){hidden_mark}``
    Hidden layers appended with `` [H]``, visible ones have no mark.
    """
    lines: List[str] = []
    indent = "  " * depth
    for layer in parent:
        kind = _layer_kind(layer)
        hidden = "" if layer.visible else " [H]"
        lines.append(f"{indent}{layer.name} ({kind}){hidden}")
        if layer.is_group():
            lines.extend(_build_layer_tree_text(layer, depth + 1))
    return lines


def _iter_all_layers(parent):
    """Yield top-level layers and all descendants."""
    for layer in parent:
        yield layer
        if layer.is_group():
            yield from _iter_all_layers(layer)


def _get_visible_content_bbox(image: Image.Image) -> Optional[Tuple[int, int, int, int]]:
    """Get the bbox of transparent/empty-trimmed content."""
    bbox = None

    # Prefer alpha-based crop because PSD composite may keep RGB data
    # in transparent pixels, which makes Image.getbbox() return full-canvas.
    if "A" in image.getbands():
        bbox = image.getchannel("A").getbbox()

    if bbox is None:
        bbox = image.getbbox()

    if bbox:
        return tuple(int(v) for v in bbox)
    return None


def _crop_to_visible_content(image: Image.Image) -> Image.Image:
    """Crop transparent/empty margins from a composited image."""
    bbox = _get_visible_content_bbox(image)
    if bbox:
        return image.crop(bbox)
    return image


def _open_image(file_path: str) -> Image.Image:
    """Open a regular image file and return a detached PIL image."""
    path = os.path.abspath(file_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Image file not found: {path}")

    with Image.open(path) as image:
        detached = image.copy()
        detached.load()
    return detached


def _resolve_image_format(file_path: str, image_format: str = "") -> str:
    """Resolve image format from explicit input or file extension."""
    if image_format and image_format.strip():
        return image_format.strip().upper()

    ext = os.path.splitext(file_path)[1].lower()
    mapping = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".bmp": "BMP",
        ".tga": "TGA",
        ".webp": "WEBP",
        ".gif": "GIF",
        ".tif": "TIFF",
        ".tiff": "TIFF",
    }
    return mapping.get(ext, "PNG")


def _save_image(image: Image.Image, output_path: str, image_format: str = "") -> str:
    """Save an image to disk with basic format compatibility handling."""
    abs_output = os.path.abspath(output_path)
    _ensure_dir(abs_output)

    fmt = _resolve_image_format(abs_output, image_format)
    save_kwargs: Dict[str, Any] = {}
    save_image = image

    if fmt == "JPEG":
        if save_image.mode in ("RGBA", "LA") or ("A" in save_image.getbands()):
            bg = Image.new("RGB", save_image.size, (255, 255, 255))
            alpha = save_image.getchannel("A") if "A" in save_image.getbands() else None
            bg.paste(save_image.convert("RGB"), mask=alpha)
            save_image = bg
        elif save_image.mode != "RGB":
            save_image = save_image.convert("RGB")
        save_kwargs["quality"] = 95
    elif fmt == "WEBP":
        save_kwargs["quality"] = 95
        save_kwargs["lossless"] = False

    save_image.save(abs_output, format=fmt, **save_kwargs)
    return abs_output


def _get_text_info(layer) -> Optional[Dict[str, Any]]:
    """Extract text-engine data from a type layer."""
    info: Dict[str, Any] = {}
    try:
        if hasattr(layer, "text") and layer.text:
            info["text"] = layer.text
    except Exception:
        pass

    type_data = None
    if hasattr(layer, "tagged_blocks"):
        for tag_key in (Tag.TYPE_TOOL_OBJECT_SETTING, Tag.TYPE_TOOL_INFO):
            block = layer.tagged_blocks.get_data(tag_key)
            if block is not None:
                type_data = block
                break

    if type_data is None:
        return info if info else None

    try:
        engine_data = type_data.engine_data
        if engine_data:
            # Extract text
            if "Editor" in engine_data and "Text" in engine_data["Editor"]:
                info["text"] = engine_data["Editor"]["Text"].rstrip("\x00\r\n")
            # Font info
            if "ResourceDict" in engine_data:
                rd = engine_data["ResourceDict"]
                if "FontSet" in rd:
                    fonts = []
                    for font_set in rd["FontSet"]:
                        if "Name" in font_set:
                            fonts.append(font_set["Name"])
                    if fonts:
                        info["fonts"] = fonts
            # Style runs
            if "EngineDict" in engine_data:
                ed = engine_data["EngineDict"]
                if "StyleRun" in ed and "RunArray" in ed["StyleRun"]:
                    styles = []
                    for run in ed["StyleRun"]["RunArray"]:
                        style_entry: Dict[str, Any] = {}
                        sheet = run.get("StyleSheet", {}).get("StyleSheetData", {})
                        if "FontSize" in sheet:
                            style_entry["font_size"] = sheet["FontSize"]
                        if "FillColor" in sheet:
                            style_entry["fill_color"] = _convert_color(sheet["FillColor"])
                        if "Font" in sheet:
                            style_entry["font_index"] = sheet["Font"]
                        if "Leading" in sheet:
                            style_entry["leading"] = sheet["Leading"]
                        if "Tracking" in sheet:
                            style_entry["tracking"] = sheet["Tracking"]
                        if "AutoLeading" in sheet:
                            style_entry["auto_leading"] = sheet["AutoLeading"]
                        if "FontCaps" in sheet:
                            style_entry["font_caps"] = sheet["FontCaps"]
                        if "StrokeColor" in sheet:
                            style_entry["stroke_color"] = _convert_color(sheet["StrokeColor"])
                        if style_entry:
                            styles.append(style_entry)
                    if styles:
                        info["styles"] = styles
    except Exception as e:
        logger.debug(f"Could not fully parse type engine data: {e}")

    # Fallback: try document_resources for font info
    if "fonts" not in info:
        try:
            if hasattr(type_data, "document_resources") and type_data.document_resources:
                fonts = []
                for res in type_data.document_resources:
                    if hasattr(res, "font_name"):
                        fonts.append(res.font_name)
                    elif isinstance(res, dict) and "Name" in res:
                        fonts.append(res["Name"])
                if fonts:
                    info["fonts"] = fonts
        except Exception:
            pass

    # Transform matrix
    try:
        if hasattr(type_data, "transform"):
            info["transform"] = list(type_data.transform)
    except Exception:
        pass

    return info if info else None


def _convert_color(color_data) -> Optional[List[float]]:
    """Convert psd-tools color data to a list of floats."""
    try:
        if hasattr(color_data, "Values"):
            return [float(v) for v in color_data.Values]
        if isinstance(color_data, (list, tuple)):
            return [float(v) for v in color_data]
    except Exception:
        pass
    return None


def _get_shape_info(layer) -> Optional[Dict[str, Any]]:
    """Extract shape/vector info from a shape layer."""
    info: Dict[str, Any] = {}
    try:
        if hasattr(layer, "tagged_blocks"):
            vstk = layer.tagged_blocks.get_data(Tag.VECTOR_STROKE_DATA)
            if vstk:
                info["has_stroke"] = True
            vmsf = layer.tagged_blocks.get_data(Tag.VECTOR_MASK_SETTING1)
            if vmsf:
                info["has_vector_mask"] = True
            solid_fill = layer.tagged_blocks.get_data(Tag.SOLID_COLOR_SHEET_SETTING)
            if solid_fill:
                info["has_solid_fill"] = True
    except Exception:
        pass

    try:
        if hasattr(layer, "vector_mask") and layer.vector_mask:
            info["vector_mask_paths"] = len(layer.vector_mask)
    except Exception:
        pass

    return info if info else None


def _get_smart_object_info(layer) -> Optional[Dict[str, Any]]:
    """Extract smart object info."""
    info: Dict[str, Any] = {}
    try:
        if hasattr(layer, "smart_object") and layer.smart_object:
            so = layer.smart_object
            if hasattr(so, "filename"):
                info["filename"] = so.filename
            if hasattr(so, "filetype"):
                info["filetype"] = str(so.filetype)
            if hasattr(so, "resolution"):
                info["resolution"] = so.resolution
    except Exception:
        pass
    return info if info else None


def _get_effects_info(layer) -> Optional[List[str]]:
    """List applied layer effects/styles."""
    effects = []
    try:
        if hasattr(layer, "effects") and layer.effects:
            for effect in layer.effects:
                effects.append(str(effect.__class__.__name__))
    except Exception:
        pass

    try:
        if hasattr(layer, "tagged_blocks"):
            for tag_key in (Tag.OBJECT_BASED_EFFECTS_LAYER_INFO,
                            Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V0,
                            Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V1):
                block = layer.tagged_blocks.get_data(tag_key)
                if block is not None:
                    effects.append("object_based_effects")
                    break
    except Exception:
        pass

    return effects if effects else None


def _set_visible_safe(layer, visible: bool) -> bool:
    """Set layer visibility, returning True on success."""
    try:
        layer.visible = visible
        return True
    except (AttributeError, Exception):
        return False


def _make_layer_tree_visible(layer):
    """Make a layer and all its ancestors visible."""
    cur = layer
    while cur is not None:
        if hasattr(cur, "visible") and not isinstance(cur, PSDImage):
            _set_visible_safe(cur, True)
        cur = getattr(cur, "parent", None)


def _parse_layer_list(value: str) -> List[str]:
    """Parse layer arguments from JSON array, newline list, or CSV."""
    if not value:
        return []

    text = value.strip()
    if not text:
        return []

    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            logger.warning("Failed to parse layer list as JSON array, falling back to text parsing")

    if "\n" in text:
        return [line.strip() for line in text.splitlines() if line.strip()]

    return [part.strip() for part in text.split(",") if part.strip()]


def _get_layer_bbox(layer) -> Optional[Tuple[int, int, int, int]]:
    """Return the best export bbox for a layer, preferring mask bounds when present."""
    bbox = getattr(layer, "bbox", None)
    try:
        if hasattr(layer, "mask") and layer.mask and hasattr(layer.mask, "bbox"):
            mask_bbox = tuple(layer.mask.bbox)
            if len(mask_bbox) == 4 and mask_bbox[2] > mask_bbox[0] and mask_bbox[3] > mask_bbox[1]:
                bbox = mask_bbox
    except Exception:
        pass

    if not bbox or len(bbox) != 4:
        return None

    left, top, right, bottom = [int(v) for v in bbox]
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _merge_bboxes(bboxes: List[Tuple[int, int, int, int]]) -> Optional[Tuple[int, int, int, int]]:
    """Merge multiple bboxes into a single union bbox."""
    if not bboxes:
        return None

    left = min(b[0] for b in bboxes)
    top = min(b[1] for b in bboxes)
    right = max(b[2] for b in bboxes)
    bottom = max(b[3] for b in bboxes)
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _collect_export_bbox(psd: PSDImage, layer_paths: List[str]) -> Optional[Tuple[int, int, int, int]]:
    """Collect a union bbox for export targets."""
    bboxes: List[Tuple[int, int, int, int]] = []
    for target in layer_paths:
        layer = _find_layer(psd, target)
        if layer is None:
            continue
        bbox = _get_layer_bbox(layer)
        if bbox:
            bboxes.append(bbox)
    return _merge_bboxes(bboxes)


def _composite_with_transparency(
    psd: PSDImage,
    viewport: Optional[Tuple[int, int, int, int]] = None,
):
    """Composite PSD with a transparent backdrop instead of psd-tools' default white."""
    return psd.composite(
        viewport=viewport,
        force=True,
        color=0.0,
        alpha=0.0,
        ignore_preview=True,
    )


def _ensure_dir(file_path: str):
    """Create parent directories for a file path if they don't exist."""
    d = os.path.dirname(os.path.abspath(file_path))
    if d:
        os.makedirs(d, exist_ok=True)


def _resolve_anchor(anchor: str) -> Tuple[float, float]:
    """Resolve a nine-grid anchor string into normalized offsets."""
    key = (anchor or "center").strip().lower().replace("_", "-")
    anchors = {
        "top-left": (0.0, 0.0),
        "top": (0.5, 0.0),
        "top-center": (0.5, 0.0),
        "top-right": (1.0, 0.0),
        "left": (0.0, 0.5),
        "center-left": (0.0, 0.5),
        "middle-left": (0.0, 0.5),
        "center": (0.5, 0.5),
        "middle": (0.5, 0.5),
        "right": (1.0, 0.5),
        "center-right": (1.0, 0.5),
        "middle-right": (1.0, 0.5),
        "bottom-left": (0.0, 1.0),
        "bottom": (0.5, 1.0),
        "bottom-center": (0.5, 1.0),
        "bottom-right": (1.0, 1.0),
    }
    if key not in anchors:
        supported = ", ".join(sorted(anchors.keys()))
        raise ValueError(f"Unsupported anchor '{anchor}'. Supported anchors: {supported}")
    return anchors[key]


def _calculate_canvas_offset(
    canvas_size: Tuple[int, int],
    image_size: Tuple[int, int],
    anchor: str,
) -> Tuple[int, int]:
    """Calculate paste offset for the image within a larger canvas."""
    canvas_w, canvas_h = canvas_size
    image_w, image_h = image_size
    anchor_x, anchor_y = _resolve_anchor(anchor)
    offset_x = int((canvas_w - image_w) * anchor_x)
    offset_y = int((canvas_h - image_h) * anchor_y)
    return offset_x, offset_y


def _normalize_crop_box(
    image_size: Tuple[int, int],
    left: Optional[int],
    top: Optional[int],
    right: Optional[int],
    bottom: Optional[int],
) -> Optional[Tuple[int, int, int, int]]:
    """Validate and clamp an explicit crop box."""
    values = [left, top, right, bottom]
    if all(v is None for v in values):
        return None
    if any(v is None for v in values):
        raise ValueError("left, top, right, bottom must all be provided together")

    img_w, img_h = image_size
    crop_left = max(0, min(int(left), img_w))
    crop_top = max(0, min(int(top), img_h))
    crop_right = max(0, min(int(right), img_w))
    crop_bottom = max(0, min(int(bottom), img_h))

    if crop_right <= crop_left or crop_bottom <= crop_top:
        raise ValueError("Crop area is empty after clamping to image bounds")
    return crop_left, crop_top, crop_right, crop_bottom


def _isolate(psd: PSDImage, layer_paths: str, mode: str = "show") -> Tuple[List[str], List[str]]:
    """Core logic for isolate_layers: toggle all, then flip specified layers.

    When showing a target group, preserve the group's original descendant
    visibility instead of forcing every child visible. This keeps the PSD's
    authored state intact while still making the target path compositable.

    Returns (found_names, not_found_names).
    """
    targets = _parse_layer_list(layer_paths)
    original_visibility = {id(layer): bool(layer.visible) for layer in _iter_all_layers(psd)}
    default_vis = mode != "show"
    for layer in _iter_all_layers(psd):
        _set_visible_safe(layer, default_vis)

    found: List[str] = []
    not_found: List[str] = []
    for t in targets:
        layer = _find_layer(psd, t)
        if layer is None:
            not_found.append(t)
            continue
        target_vis = (mode == "show")
        _set_visible_safe(layer, target_vis)
        if target_vis:
            _make_layer_tree_visible(layer)
            if layer.is_group():
                for desc in layer.descendants():
                    _set_visible_safe(desc, original_visibility.get(id(desc), False))
        found.append(t)
    return found, not_found


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def list_layers(file_path: str) -> str:
    """
    List all layers in a PSD file as a compact text tree (one line per layer).

    Format: each line is ``{indent}{name} ({kind})`` with 2-space indent per depth.
    Hidden layers are marked with ``[H]``. Use get_layer_info for full details.

    Args:
        file_path: Absolute path to the PSD file.

    Returns:
        A multi-line string: first line is canvas info, followed by the layer tree.
    """
    try:
        psd = _open_psd(file_path)
        header = f"[{psd.width}x{psd.height}] {len(list(psd.descendants()))} layers"
        tree_lines = _build_layer_tree_text(psd)
        return header + "\n" + "\n".join(tree_lines)
    except Exception as e:
        logger.error(f"list_layers error: {e}")
        return f"[error] {e}"


def get_layer_info(
    file_path: str,
    layer_path: str,
) -> Dict[str, Any]:
    """
    Get detailed information about a specific layer.

    For text layers: returns text content, font names, font sizes, colors, etc.
    For shape layers: returns vector mask, stroke, fill info.
    For smart objects: returns linked file info.
    For all layers: returns name, kind, visibility, opacity, blend mode, bbox, effects.

    Args:
        file_path: Absolute path to the PSD file.
        layer_path: Layer name or slash-separated path (e.g. "Group1/TextLayer").

    Returns:
        Dict with detailed layer information.
    """
    try:
        psd = _open_psd(file_path)
        layer = _find_layer(psd, layer_path)
        if layer is None:
            return {"success": False, "message": f"Layer not found: {layer_path}"}

        info = _layer_summary(layer)
        info["success"] = True

        kind = _layer_kind(layer)

        if kind == "type":
            text_info = _get_text_info(layer)
            if text_info:
                info["text_info"] = text_info

        if kind == "shape":
            shape_info = _get_shape_info(layer)
            if shape_info:
                info["shape_info"] = shape_info

        if kind == "smartobject":
            so_info = _get_smart_object_info(layer)
            if so_info:
                info["smart_object_info"] = so_info

        effects = _get_effects_info(layer)
        if effects:
            info["effects"] = effects

        if layer.is_group():
            info["children"] = [_layer_summary(child) for child in layer]

        # Mask info
        try:
            if hasattr(layer, "mask") and layer.mask:
                info["has_mask"] = True
                if hasattr(layer.mask, "bbox"):
                    info["mask_bbox"] = list(layer.mask.bbox)
        except Exception:
            pass

        return info

    except Exception as e:
        logger.error(f"get_layer_info error: {e}")
        return {"success": False, "message": str(e)}


def set_layer_visibility(
    file_path: str,
    show: str = "",
    hide: str = "",
    save: bool = True,
    output_path: str = "",
) -> Dict[str, Any]:
    """
    Set visibility of multiple layers in one call.

    Args:
        file_path: Absolute path to the PSD file.
        show: Layer names/paths to make visible. Supports newline list or CSV.
        hide: Layer names/paths to hide. Supports newline list or CSV.
        save: Whether to save the PSD after modification (default True).
        output_path: Save to this path instead of overwriting the original (optional).

    Returns:
        Dict with results of the operation.
    """
    try:
        psd = _open_psd(file_path)
        results = []

        for t in _parse_layer_list(show):
            layer = _find_layer(psd, t)
            if layer is None:
                results.append({"layer": t, "ok": False, "msg": "not found"})
                continue
            layer.visible = True
            results.append({"layer": t, "visible": True})

        for t in _parse_layer_list(hide):
            layer = _find_layer(psd, t)
            if layer is None:
                results.append({"layer": t, "ok": False, "msg": "not found"})
                continue
            layer.visible = False
            results.append({"layer": t, "visible": False})

        saved_to = ""
        if save:
            saved_to = output_path if output_path else file_path
            psd.save(saved_to)

        return {"success": True, "results": results, "saved": saved_to or False}

    except Exception as e:
        logger.error(f"set_layer_visibility error: {e}")
        return {"success": False, "message": str(e)}


def isolate_layers(
    file_path: str,
    layer_paths: str,
    mode: str = "show",
    save: bool = True,
    output_path: str = "",
) -> Dict[str, Any]:
    """
    Only keep the specified layers visible (or hidden), toggling all others.

    mode="show" (default): hide ALL layers, then show only the specified ones (+ their parent groups).
    mode="hide": show ALL layers, then hide only the specified ones.

    Args:
        file_path: Absolute path to the PSD file.
        layer_paths: Layer names/paths. Supports newline list or CSV.
        mode: "show" = only these visible, "hide" = only these hidden.
        save: Whether to save the PSD after modification (default True).
        output_path: Save to this path instead of overwriting the original (optional).

    Returns:
        Dict with found/not_found layers and save path.
    """
    try:
        psd = _open_psd(file_path)
        found, not_found = _isolate(psd, layer_paths, mode)

        if not found:
            return {"success": False, "message": f"No layers found: {not_found}"}

        saved_to = ""
        if save:
            saved_to = output_path if output_path else file_path
            _ensure_dir(saved_to)
            psd.save(saved_to)

        return {
            "success": True,
            "mode": mode,
            "found": found,
            "not_found": not_found,
            "saved": saved_to or False,
        }

    except Exception as e:
        logger.error(f"isolate_layers error: {e}")
        return {"success": False, "message": str(e)}


def export_layer(
    file_path: str,
    layer_paths: str,
    output_path: str,
    format: str = "png",
    scale: float = 1.0,
    cleanup_psd: bool = False,
) -> Dict[str, Any]:
    """
    Export one or more layers as a single composited image.

    Internally hides all layers, shows only the specified ones (+ parent groups),
    then composites the PSD using the targets' union bbox for reliable cropping.
    Use "__all__" to composite the entire PSD as-is.

    Args:
        file_path: Absolute path to the PSD file.
        layer_paths: Layer names/paths to export. Supports newline list or CSV.
            Use "__all__" for full composite.
        output_path: Destination file path for the exported image.
        format: Image format - "png" (default), "jpg", "bmp", "tga", "webp".
        scale: Scale factor (default 1.0). 0.5 = half size, 2.0 = double size.
        cleanup_psd: If True, delete the source PSD file after successful export.
            Intended for temporary PSD cleanup after export.

    Returns:
        Dict with export results including output path, dimensions, and layers info.
    """
    try:
        psd = _open_psd(file_path)

        if layer_paths.strip() == "__all__":
            image = _composite_with_transparency(psd)
            found, not_found = ["__all__"], []
            export_bbox = None
        else:
            original_vis: List[Tuple[Any, bool]] = []
            for layer in _iter_all_layers(psd):
                original_vis.append((layer, layer.visible))

            found, not_found = _isolate(psd, layer_paths, mode="show")
            if not found:
                for layer, vis in original_vis:
                    _set_visible_safe(layer, vis)
                return {"success": False, "message": f"No layers found: {not_found}"}

            export_bbox = _collect_export_bbox(psd, found)
            image = _composite_with_transparency(psd, viewport=export_bbox)

            for layer, vis in original_vis:
                _set_visible_safe(layer, vis)

        if image is None:
            return {"success": False, "message": "Composite resulted in empty image"}

        image = _crop_to_visible_content(image)

        if scale != 1.0 and scale > 0:
            new_w = max(1, int(image.width * scale))
            new_h = max(1, int(image.height * scale))
            image = image.resize((new_w, new_h), Image.LANCZOS)

        _ensure_dir(output_path)

        fmt = format.lower().strip()
        save_kwargs: Dict[str, Any] = {}
        if fmt in ("png", "webp") and "A" not in image.getbands():
            try:
                image.background = (0, 0, 0, 0)
                image.info["background"] = (0, 0, 0, 0)
            except Exception:
                pass
        if fmt in ("jpg", "jpeg"):
            if image.mode == "RGBA":
                bg = Image.new("RGB", image.size, (255, 255, 255))
                bg.paste(image, mask=image.split()[3])
                image = bg
            save_kwargs["quality"] = 95
        elif fmt == "webp":
            save_kwargs["quality"] = 95
            save_kwargs["lossless"] = False

        image.save(output_path, **save_kwargs)
        logger.info(f"Exported layers {found} to {output_path}")

        psd_cleaned = False
        if cleanup_psd:
            abs_psd = os.path.abspath(file_path)
            try:
                del psd
                os.remove(abs_psd)
                psd_cleaned = True
                logger.info(f"Cleaned up PSD: {abs_psd}")
            except Exception as ce:
                logger.warning(f"Failed to cleanup PSD {abs_psd}: {ce}")

        result: Dict[str, Any] = {
            "success": True,
            "layers": found,
            "not_found": not_found,
            "output_path": os.path.abspath(output_path),
            "size": [image.width, image.height],
            "format": fmt,
        }
        if export_bbox:
            result["bbox"] = list(export_bbox)
        if cleanup_psd:
            result["psd_cleaned"] = psd_cleaned
        return result

    except Exception as e:
        logger.error(f"export_layer error: {e}")
        return {"success": False, "message": str(e)}


def resize_image_canvas(
    file_path: str,
    output_path: str,
    width: int,
    height: int,
    anchor: str = "center",
) -> Dict[str, Any]:
    """
    Expand an image canvas with a transparent background.

    Args:
        file_path: Absolute path to the source image file.
        output_path: Destination image path.
        width: Target canvas width. Must be >= original width.
        height: Target canvas height. Must be >= original height.
        anchor: Nine-grid placement of the original image inside the new canvas.
            Default is "center". Supported values include "top-left", "top",
            "top-right", "left", "center", "right", "bottom-left", "bottom",
            "bottom-right".

    Returns:
        Dict with output path, original size, new size, and placement offset.
    """
    try:
        image = _open_image(file_path)
        src_w, src_h = image.size
        dst_w = int(width)
        dst_h = int(height)

        if dst_w < src_w or dst_h < src_h:
            return {
                "success": False,
                "message": "Target canvas must not be smaller than the source image",
            }
        if dst_w == src_w and dst_h == src_h:
            return {
                "success": False,
                "message": "Target canvas must be larger than the source image in at least one dimension",
            }

        canvas = Image.new("RGBA", (dst_w, dst_h), (0, 0, 0, 0))
        source = image.convert("RGBA")
        offset_x, offset_y = _calculate_canvas_offset(canvas.size, source.size, anchor)
        canvas.alpha_composite(source, dest=(offset_x, offset_y))

        saved_to = _save_image(canvas, output_path)
        return {
            "success": True,
            "output_path": saved_to,
            "original_size": [src_w, src_h],
            "size": [dst_w, dst_h],
            "offset": [offset_x, offset_y],
            "anchor": anchor,
        }
    except Exception as e:
        logger.error(f"resize_image_canvas error: {e}")
        return {"success": False, "message": str(e)}


def scale_image(
    file_path: str,
    output_path: str,
    scale: float,
) -> Dict[str, Any]:
    """
    Scale an image by a numeric ratio.

    Args:
        file_path: Absolute path to the source image file.
        output_path: Destination image path.
        scale: Scale ratio. Must be greater than 0.

    Returns:
        Dict with output path, original size, new size, and scale.
    """
    try:
        if scale <= 0:
            return {"success": False, "message": "scale must be greater than 0"}

        image = _open_image(file_path)
        src_w, src_h = image.size
        dst_w = max(1, int(round(src_w * scale)))
        dst_h = max(1, int(round(src_h * scale)))
        resized = image.resize((dst_w, dst_h), Image.LANCZOS)

        saved_to = _save_image(resized, output_path)
        return {
            "success": True,
            "output_path": saved_to,
            "original_size": [src_w, src_h],
            "size": [dst_w, dst_h],
            "scale": scale,
        }
    except Exception as e:
        logger.error(f"scale_image error: {e}")
        return {"success": False, "message": str(e)}


def get_image_size(file_path: str) -> Dict[str, Any]:
    """
    Get the dimensions of an image file.

    Args:
        file_path: Absolute path to the image file.

    Returns:
        Dict with image dimensions and basic metadata.
    """
    try:
        abs_path = os.path.abspath(file_path)
        with Image.open(abs_path) as image:
            return {
                "success": True,
                "file_path": abs_path,
                "size": [image.width, image.height],
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "format": image.format,
            }
    except Exception as e:
        logger.error(f"get_image_size error: {e}")
        return {"success": False, "message": str(e)}


def crop_image(
    file_path: str,
    output_path: str,
    left: Optional[int] = None,
    top: Optional[int] = None,
    right: Optional[int] = None,
    bottom: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Crop an image either by transparent content bounds or an explicit rectangle.

    Args:
        file_path: Absolute path to the source image file.
        output_path: Destination image path.
        left: Crop left edge (optional).
        top: Crop top edge (optional).
        right: Crop right edge (optional).
        bottom: Crop bottom edge (optional).
            If all four edges are omitted, the tool trims transparent/empty margins.

    Returns:
        Dict with output path, original size, new size, and crop box.
    """
    try:
        image = _open_image(file_path)
        src_w, src_h = image.size
        crop_box = _normalize_crop_box(image.size, left, top, right, bottom)

        if crop_box is None:
            detected_bbox = _get_visible_content_bbox(image)
            if detected_bbox is None:
                crop_box = [0, 0, src_w, src_h]
                cropped = image
            else:
                crop_box = list(detected_bbox)
                cropped = image.crop(detected_bbox)
        else:
            cropped = image.crop(crop_box)
            crop_box = list(crop_box)

        saved_to = _save_image(cropped, output_path)
        return {
            "success": True,
            "output_path": saved_to,
            "original_size": [src_w, src_h],
            "size": [cropped.width, cropped.height],
            "crop_box": crop_box,
            "mode": "content" if left is None and top is None and right is None and bottom is None else "explicit",
        }
    except Exception as e:
        logger.error(f"crop_image error: {e}")
        return {"success": False, "message": str(e)}


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------

CLI_TOOLS = {
    "list_layers": list_layers,
    "get_layer_info": get_layer_info,
    "set_layer_visibility": set_layer_visibility,
    "isolate_layers": isolate_layers,
    "export_layer": export_layer,
    "resize_image_canvas": resize_image_canvas,
    "scale_image": scale_image,
    "get_image_size": get_image_size,
    "crop_image": crop_image,
}


def _parse_bool(value: str) -> bool:
    """Parse a bool from common CLI text values."""
    text = value.strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def _join_cli_list(values: Optional[List[str]]) -> str:
    """Join repeated CLI args into the newline list format expected internally."""
    return "\n".join([value for value in (values or []) if value])


def _normalize_cli_result(result: Any) -> Dict[str, Any]:
    """Normalize tool results into a JSON-friendly dict."""
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        return {"success": True, "result": result}
    return {"success": True, "result": result}


def _run_cli_tool(tool_name: str, params: Dict[str, Any], raw: bool = False) -> int:
    """Run one tool directly from CLI for easier skill invocation."""
    if tool_name not in CLI_TOOLS:
        supported = ", ".join(sorted(CLI_TOOLS.keys()))
        raise ValueError(f"Unsupported tool '{tool_name}'. Supported tools: {supported}")

    result = CLI_TOOLS[tool_name](**params)

    if raw and isinstance(result, str):
        sys.stdout.write(result)
        if not result.endswith("\n"):
            sys.stdout.write("\n")
        return 0

    payload = _normalize_cli_result(result)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return 0 if payload.get("success", True) else 1


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(
        description="PSD slicing command line tools for skill-side calls.",
    )
    subparsers = parser.add_subparsers(dest="tool_name", required=True)

    list_layers_parser = subparsers.add_parser("list_layers", help="List PSD layers as a text tree.")
    list_layers_parser.add_argument("--file-path", required=True, help="Absolute path to the PSD file.")
    list_layers_parser.add_argument("--raw", action="store_true", help="Print raw string output.")

    get_layer_info_parser = subparsers.add_parser("get_layer_info", help="Get detailed info for one layer.")
    get_layer_info_parser.add_argument("--file-path", required=True, help="Absolute path to the PSD file.")
    get_layer_info_parser.add_argument("--layer-path", required=True, help="Layer name or slash-separated path.")
    get_layer_info_parser.add_argument("--raw", action="store_true", help="Print raw string output when applicable.")

    set_visibility_parser = subparsers.add_parser("set_layer_visibility", help="Show or hide layers and save PSD.")
    set_visibility_parser.add_argument("--file-path", required=True, help="Absolute path to the PSD file.")
    set_visibility_parser.add_argument("--show-layer", action="append", default=[], help="Layer path to show. Repeat to pass multiple layers.")
    set_visibility_parser.add_argument("--hide-layer", action="append", default=[], help="Layer path to hide. Repeat to pass multiple layers.")
    set_visibility_parser.add_argument("--save", type=_parse_bool, default=True, help="Whether to save changes. true/false.")
    set_visibility_parser.add_argument("--output-path", default="", help="Optional output PSD path.")
    set_visibility_parser.add_argument("--raw", action="store_true", help="Print raw string output when applicable.")

    isolate_parser = subparsers.add_parser("isolate_layers", help="Only keep specified layers visible or hidden.")
    isolate_parser.add_argument("--file-path", required=True, help="Absolute path to the PSD file.")
    isolate_parser.add_argument("--layer-path", action="append", default=[], help="Layer path to isolate. Repeat to pass multiple layers.")
    isolate_parser.add_argument("--mode", default="show", choices=["show", "hide"], help="Isolation mode.")
    isolate_parser.add_argument("--save", type=_parse_bool, default=True, help="Whether to save changes. true/false.")
    isolate_parser.add_argument("--output-path", default="", help="Optional output PSD path.")
    isolate_parser.add_argument("--raw", action="store_true", help="Print raw string output when applicable.")

    export_parser = subparsers.add_parser("export_layer", help="Export one or more layers to an image.")
    export_parser.add_argument("--file-path", required=True, help="Absolute path to the PSD file.")
    export_target_group = export_parser.add_mutually_exclusive_group(required=True)
    export_target_group.add_argument("--layer-path", action="append", default=[], help="Layer path to export. Repeat to pass multiple layers.")
    export_target_group.add_argument("--all", action="store_true", help="Export the full PSD composite.")
    export_parser.add_argument("--output-path", required=True, help="Destination image path.")
    export_parser.add_argument("--format", default="png", help="Image format, e.g. png, jpg, webp.")
    export_parser.add_argument("--scale", type=float, default=1.0, help="Scale factor.")
    export_parser.add_argument("--cleanup-psd", type=_parse_bool, default=False, help="Delete source PSD after export. true/false.")
    export_parser.add_argument("--raw", action="store_true", help="Print raw string output when applicable.")

    resize_parser = subparsers.add_parser("resize_image_canvas", help="Expand image canvas with transparent padding.")
    resize_parser.add_argument("--file-path", required=True, help="Absolute path to the source image.")
    resize_parser.add_argument("--output-path", required=True, help="Destination image path.")
    resize_parser.add_argument("--width", required=True, type=int, help="Target canvas width.")
    resize_parser.add_argument("--height", required=True, type=int, help="Target canvas height.")
    resize_parser.add_argument("--anchor", default="center", help="Anchor position.")
    resize_parser.add_argument("--raw", action="store_true", help="Print raw string output when applicable.")

    scale_parser = subparsers.add_parser("scale_image", help="Scale an image by a numeric ratio.")
    scale_parser.add_argument("--file-path", required=True, help="Absolute path to the source image.")
    scale_parser.add_argument("--output-path", required=True, help="Destination image path.")
    scale_parser.add_argument("--scale", required=True, type=float, help="Scale ratio.")
    scale_parser.add_argument("--raw", action="store_true", help="Print raw string output when applicable.")

    size_parser = subparsers.add_parser("get_image_size", help="Get image dimensions.")
    size_parser.add_argument("--file-path", required=True, help="Absolute path to the image.")
    size_parser.add_argument("--raw", action="store_true", help="Print raw string output when applicable.")

    crop_parser = subparsers.add_parser("crop_image", help="Crop image by content or explicit rectangle.")
    crop_parser.add_argument("--file-path", required=True, help="Absolute path to the source image.")
    crop_parser.add_argument("--output-path", required=True, help="Destination image path.")
    crop_parser.add_argument("--left", type=int, default=None, help="Left edge.")
    crop_parser.add_argument("--top", type=int, default=None, help="Top edge.")
    crop_parser.add_argument("--right", type=int, default=None, help="Right edge.")
    crop_parser.add_argument("--bottom", type=int, default=None, help="Bottom edge.")
    crop_parser.add_argument("--raw", action="store_true", help="Print raw string output when applicable.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for direct CLI mode."""
    _ensure_utf8_stdout()
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    raw = getattr(args, "raw", False)
    tool_name = args.tool_name
    params = vars(args).copy()
    params.pop("tool_name", None)
    params.pop("raw", None)
    if tool_name == "set_layer_visibility":
        params["show"] = _join_cli_list(params.pop("show_layer", []))
        params["hide"] = _join_cli_list(params.pop("hide_layer", []))
    elif tool_name == "isolate_layers":
        layer_paths = _join_cli_list(params.pop("layer_path", []))
        if not layer_paths:
            parser.error("isolate_layers requires at least one --layer-path")
        params["layer_paths"] = layer_paths
    elif tool_name == "export_layer":
        layer_paths = _join_cli_list(params.pop("layer_path", []))
        export_all = bool(params.pop("all", False))
        if not export_all and not layer_paths:
            parser.error("export_layer requires --all or at least one --layer-path")
        params["layer_paths"] = "__all__" if export_all else layer_paths

    normalized_params = {key: value for key, value in params.items() if value is not None and value != []}
    return _run_cli_tool(
        tool_name=tool_name,
        params=normalized_params,
        raw=raw,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(main())
