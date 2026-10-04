"""Observe a single PSD and export embedded raster assets without semantic inference.

The success stage is PSD observation, never a fit or a completed rig. Layer PNGs
retain straight alpha; opacity, blend modes, clipping and group compositing are
explicit, unbaked properties. No external resource or linked object is opened.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

from .data import digest, json_digest, write_json


_SCHEMA = "rig-psd-source/1"
_MAX_CANVAS_PIXELS = 100_000_000
_MAX_LAYER_PIXELS = 100_000_000
_MAX_LAYERS = 10000
_METADATA_TAGS = {
    b"luni", b"lyid", b"lspf", b"lclr", b"lnsr", b"lyvr", b"shmd",
    b"lsct", b"lsdk", b"fxrp", b"lver",
}
_ADVANCED_DEFAULTS = {
    b"iOpa": 255, b"knko": 0, b"clbl": 1, b"infx": 0,
    b"lmgm": 0, b"vmgm": 0, b"tsly": 1,
}


def _key(value):
    value = getattr(value, "value", value)
    return value if isinstance(value, bytes) else str(value).encode("ascii", "backslashreplace")


def _label(value):
    return _key(value).decode("ascii", "backslashreplace")


def _bounds(value):
    values = list(value)
    if len(values) != 4 or any(type(v) is not int for v in values):
        raise ValueError("PSD bounds must contain four integer pixel edges")
    if values[2] < values[0] or values[3] < values[1]:
        raise ValueError("PSD bounds are inverted")
    return values


def _header(source):
    with source.open("rb") as stream:
        data = stream.read(26)
    if len(data) != 26:
        raise ValueError("truncated PSD header")
    signature, version, reserved, channels, height, width, depth, mode = struct.unpack(
        ">4sH6sHIIHH", data)
    if signature != b"8BPS" or version != 1 or reserved != b"\x00" * 6:
        raise ValueError("a PSD version 1 file is required; renamed images, INX and PSB are rejected")
    if not 0 < width * height <= _MAX_CANVAS_PIXELS:
        raise ValueError("PSD canvas exceeds the supported pixel limit")
    return {"width": width, "height": height, "channels": channels,
            "depth": depth, "color_mode_code": mode, "version": version}


def _image_asset(image, output, relative, *, role, canvas_bounds, icc=None):
    """Write pixels only, with explicitly retained embedded ICC bytes if present."""
    from PIL import Image
    import numpy as np

    clean = image.copy()
    clean.info.clear()
    path = output / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    options = {"compress_level": 9, "optimize": False}
    if icc:
        options["icc_profile"] = icc
    clean.save(path, format="PNG", **options)
    pixel_digest=hashlib.sha256()
    for y in range(0,clean.height,128):
        pixel_digest.update(clean.crop((0,y,clean.width,min(clean.height,y+128))).tobytes())
    result = {"path": relative, "sha256": digest(path), "bytes": path.stat().st_size,
              "role": role, "mode": clean.mode, "size": list(clean.size),
              "canvas_bounds": list(canvas_bounds),
              "pixel_sha256": pixel_digest.hexdigest()}
    if clean.mode == "RGBA":
        alpha_image = clean.getchannel("A")
        alpha = np.asarray(alpha_image, dtype=np.uint8)
        box = alpha_image.getbbox()
        result["alpha"] = {
            "encoding": "straight_unassociated_uint8", "range": [int(alpha.min()), int(alpha.max())],
            "nonzero_pixels": int(np.count_nonzero(alpha)),
            "opaque_pixels": int(np.count_nonzero(alpha == 255)),
            "sha256": hashlib.sha256(alpha.tobytes()).hexdigest(),
            "bounds_local": list(box) if box else None,
            "bounds_canvas": ([box[0] + canvas_bounds[0], box[1] + canvas_bounds[1],
                               box[2] + canvas_bounds[0], box[3] + canvas_bounds[1]] if box else None),
        }
    return result


def _simple_mask(layer, rgba, row, output, stem, issue):
    """Bake only an ordinary absolute-coordinate bitmap mask into pixel alpha.

    No approximation is made for vector, relative, density or feather semantics.
    The original bitmap is exported as separate provenance even when blocked.
    """
    from PIL import Image
    import numpy as np

    if not layer.has_mask():
        row["mask"] = {"present": False, "baked_into_alpha": False}
        return rgba
    mask = layer.mask
    if mask is None:
        issue("missing_mask_data", "PSD reports a mask but its data is unavailable", row["id"])
        row["mask"] = {"present": True, "baked_into_alpha": False}
        return rgba
    flags = mask.flags
    flag_names = ("pos_relative_to_layer", "mask_disabled", "invert_mask",
                  "user_mask_from_render", "parameters_applied",
                  "undocumented_1", "undocumented_2", "undocumented_3")
    parameters = mask.parameters
    parameter_names = ("user_mask_density", "user_mask_feather",
                       "vector_mask_density", "vector_mask_feather")
    data = {
        "present": True, "kind": "bitmap", "bounds": _bounds(mask.bbox),
        "background_color": int(mask.background_color), "disabled": bool(mask.disabled),
        "flags": {name: bool(getattr(flags, name, False)) for name in flag_names},
        "parameters": {name: getattr(parameters, name, None) for name in parameter_names},
        "combined_real_mask_present": bool(mask.has_real()), "baked_into_alpha": False,
    }
    row["mask"] = data
    bitmap = mask.topil(real=False, apply_icc=False)
    if bitmap is None:
        issue("mask_pixels_unavailable", "Mask pixels cannot be decoded", row["id"])
        return rgba
    data["asset"] = _image_asset(bitmap.convert("L"), output, f"source-mask-{stem}.png",
                                 role="original_bitmap_mask", canvas_bounds=data["bounds"])
    unsupported = []
    if data["combined_real_mask_present"]:
        unsupported.append("combined real/vector mask")
    if any(data["flags"][name] for name in ("pos_relative_to_layer", "invert_mask", "parameters_applied",
                                             "undocumented_1", "undocumented_2", "undocumented_3")):
        unsupported.append("non-default or relative mask flags")
    if any(value not in (None, default) for name, default in
           (("user_mask_density", 255), ("user_mask_feather", 0),
            ("vector_mask_density", 255), ("vector_mask_feather", 0))
           for value in [data["parameters"][name]]):
        unsupported.append("mask density/feather")
    if layer.is_group():
        unsupported.append("group bitmap mask")
    if unsupported:
        issue("unsupported_mask", ", ".join(unsupported), row["id"])
        return rgba
    if data["disabled"]:
        data["application"] = "disabled_in_source; pixels_not_masked"
        return rgba
    if rgba is None:
        issue("mask_without_pixel_asset", "Mask cannot be applied without a pixel asset", row["id"])
        return rgba
    left, top, right, bottom = data["bounds"]
    if bitmap.size != (right - left, bottom - top):
        issue("mask_bounds_mismatch", "Decoded mask size differs from its bounds", row["id"])
        return rgba
    canvas_mask = Image.new("L", rgba.size, data["background_color"])
    canvas_mask.paste(bitmap.convert("L"), (left - row["bounds"][0], top - row["bounds"][1]))
    values = np.asarray(rgba).copy()
    a = values[:, :, 3].astype(np.uint16)
    m = np.asarray(canvas_mask, dtype=np.uint16)
    values[:, :, 3] = ((a * m + 127) // 255).astype(np.uint8)
    data["baked_into_alpha"] = True
    data["application"] = "alpha=round_half_up(pixel_alpha*mask/255); absolute PSD pixel alignment"
    return Image.fromarray(values)


def _blending_metadata(layer, row, issue):
    """Retain compositing attributes and block unrepresented rendering features."""
    ranges = layer._record.blending_ranges
    values = {"composite": ranges.composite_ranges, "channels": ranges.channel_ranges}
    row["blending_ranges"] = values
    all_ranges = ([ranges.composite_ranges] if ranges.composite_ranges is not None else [])
    all_ranges += list(ranges.channel_ranges or [])
    if any(list(map(tuple, item)) != [(0, 65535), (0, 65535)] for item in all_ranges):
        issue("custom_blending_ranges", "Blend-if ranges are observed but not rasterized", row["id"])
    advanced = {}
    for tag in layer.tagged_blocks:
        key = _key(tag)
        if key in _METADATA_TAGS:
            continue
        if key in _ADVANCED_DEFAULTS:
            value = layer.tagged_blocks.get_data(tag)
            value = getattr(value, "value", value)
            if not isinstance(value, (int, bool)):
                issue("unknown_blending_value", f"Uninterpreted blending option {_label(tag)}", row["id"])
                continue
            advanced[_label(tag)] = int(value)
            if int(value) != _ADVANCED_DEFAULTS[key]:
                issue("advanced_blending", f"Non-default blending option {_label(tag)}", row["id"])
        else:
            issue("unrepresented_layer_tag", f"Layer tag {_label(tag)} is preserved only in source PSD", row["id"])
    row["advanced_blending"] = advanced


def prepare_psd(psd_path, destination):
    """Export one PSD's embedded pixels and a deterministic observation manifest.

    Both arguments are filesystem paths. PSD is the sole character input. The
    destination must be empty or owned by this PSD extraction and must not contain the source PSD.
    Unsupported rendering content produces ``psd_observation_unsupported``;
    callers must not treat that result as observation-ready. Read/format errors
    raise ValueError/OSError. Source files are never saved or altered.
    """
    if not isinstance(psd_path, (str, Path)) or not isinstance(destination, (str, Path)):
        raise TypeError("prepare_psd accepts only a PSD path and an output directory")
    source = Path(psd_path).expanduser().resolve(strict=True)
    output = Path(destination).expanduser().resolve()
    if source.suffix.lower() != ".psd" or not source.is_file():
        raise ValueError("external character input must be a .psd file")
    if source == output or source.is_relative_to(output):
        raise ValueError("output directory must not contain or replace the source PSD")
    header = _header(source)
    source_sha = digest(source)
    if output.exists() and not output.is_dir():raise ValueError('PSD output must be a directory')
    if output.exists() and next(output.iterdir(), None) is not None:
        from .data import read_json
        marker=output/'psd-extraction-input.json'
        manifest_path=output/'psd-source.json'
        if marker.is_file():
            identity=read_json(marker)
            matches=identity.get('psd_sha256')==source_sha and identity.get('psd_path')==str(source)
        elif manifest_path.is_file():
            matches=read_json(manifest_path).get('source',{}).get('sha256')==source_sha
        elif (output/'run-origin.json').is_file():
            identity=read_json(output/'run-origin.json')
            matches=identity.get('psd_sha256')==source_sha and identity.get('external_character_input')==str(source)
        else:matches=False
        if not matches:raise ValueError('PSD extraction output is not owned by this input')
    output.mkdir(parents=True,exist_ok=True)
    write_json(output/'psd-extraction-input.json',{'psd_path':str(source),'psd_sha256':source_sha})

    import numpy as np
    import PIL
    import psd_tools
    from psd_tools import PSDImage
    from psd_tools.constants import Resource

    psd = PSDImage.open(source)
    output.mkdir(parents=True, exist_ok=True)
    issues = []

    def issue(code, detail, layer_id=None):
        value = {"code": code, "detail": detail, "layer_id": layer_id}
        if value not in issues:
            issues.append(value)

    if header["depth"] != 8 or header["color_mode_code"] != 3 or header["channels"] not in (3, 4):
        issue("unsupported_document_mode", "Only RGB8 PSD with three color channels and optional merged alpha is supported")
    icc = psd.image_resources.get_data(Resource.ICC_PROFILE)
    if icc is not None and not isinstance(icc, bytes):
        issue("unsupported_embedded_icc", "Embedded ICC payload is not a byte sequence; no external profile will be read")
        icc = None
    global_mask = psd._record.layer_and_mask_information.global_layer_mask_info
    if global_mask is not None and getattr(global_mask, "overlay_color", None):
        issue("global_layer_mask", "Global layer-mask semantics are not represented")

    manifest = {
        "schema_version": _SCHEMA, "status": "psd_observation_unsupported",
        "stage": "psd_observation", "rig_complete": False, "semantic_inference_performed": False,
        "source": {"kind": "psd", "path": source.as_posix(), "sha256": source_sha,
                   "bytes": source.stat().st_size, "embedded_resources_only": True,
                   "source_modified": False},
        "generator": {"name": "riglib.psd_source.prepare_psd", "contract_version": 1,
                      "implementation_sha256": digest(Path(__file__).resolve()),
                      "psd_tools": psd_tools.__version__, "pillow": PIL.__version__, "numpy": np.__version__},
        "canvas": {**header, "coordinate_frame": "psd_canvas_pixels",
                   "origin": "top_left", "x_direction": "right", "y_direction": "down",
                   "bounds": [0, 0, header["width"], header["height"]],
                   "bounds_convention": "integer pixel edges; left/top inclusive, right/bottom exclusive",
                   "pixel_center": "pixel (x,y) has center (x+0.5,y+0.5)",
                   "layer_to_canvas": "canvas_xy = local_pixel_xy + offset_xy; no scaling or recentering"},
        "color": {"conversion": "none; embedded document RGB samples preserved",
                  "png_icc": "embedded PSD profile copied into PNGs" if icc else "none in PSD; untagged RGB remains untagged",
                  "embedded_icc_sha256": hashlib.sha256(icc).hexdigest() if icc else None,
                  "external_profiles_loaded": False},
        "identity": {"scheme": "layer:<zero-based sibling index path>",
                     "scope": "one PSD byte revision; use source sha256 plus layer id",
                     "stable_under": "repeat extraction of same layer hierarchy",
                     "changes_when": "layer insertion, deletion or sibling reordering changes positional identity",
                     "names_are_unique_keys": False, "names_are_semantic_evidence_only": True},
        "order": {"siblings": "psd_tools native bottom_to_top paint order",
                  "flat_list": "depth-first pre-order; use parent_id and sibling_index for composition"},
        "layers": [], "assets": [], "source_composite": None,
        "unsupported": issues,
        "limitations": [
            "Observation-ready does not certify structure, joints, depth, fit, engine import or a completed rig.",
            "Pixel assets exclude opacity, blend mode, clipping, ancestor masks and group compositing; apply declared metadata once.",
            "Source composite is a whole-document reference, never an individual material mask.",
            "Embedded merged preview may be stale; agreement with layer recomposition is not claimed.",
            "No linked object, external profile, sidecar evidence, separate image or model file is opened.",
            "Vector/adjustment/text/smart-object semantics, advanced effects and non-default masks are unsupported.",
        ],
    }
    # Inspect only embedded resource identifiers, never resource paths or links.
    manifest["source"]["embedded_image_resource_ids"] = sorted(int(k) for k in psd.image_resources)
    global_tags = list(psd.tagged_blocks)
    manifest["source"]["global_tagged_block_keys"] = [_label(k) for k in global_tags]
    for tag in global_tags:
        if _key(tag) not in {b"lyid", b"Patt", b"Pat2", b"Pat3"}:
            issue("unrepresented_global_tag", f"Global tag {_label(tag)} has no observation contract")

    references = {}
    rows = {}

    def visit(container, index_path=(), parent_id=None):
        for index, layer in enumerate(container):
            path = (*index_path, index)
            uid = "layer:" + "/".join(map(str, path))
            if len(manifest["layers"]) >= _MAX_LAYERS:
                raise ValueError("PSD exceeds supported layer count")
            bounds = _bounds(layer.bbox)
            record = layer._record
            row = {"id": uid, "index_path": list(path), "parent_id": parent_id,
                   "sibling_index": index, "flat_order": len(manifest["layers"]),
                   "name": layer.name, "name_evidence": "embedded_PSD_name; no semantic classification",
                   "kind": layer.kind, "is_group": bool(layer.is_group()),
                   "bounds": bounds, "offset_xy": bounds[:2],
                   "record_bounds": [record.left, record.top, record.right, record.bottom],
                   "visible_local": bool(layer.visible), "visible_effective": bool(layer.is_visible()),
                   "opacity_uint8": int(layer.opacity), "opacity_baked": False,
                   "blend_mode": _label(layer.blend_mode), "blend_mode_baked": False,
                   "clipping": bool(layer.clipping), "clipping_base_id": None,
                   "clip_layer_ids": [], "clipping_baked": False,
                   "has_pixels": bool(layer.has_pixels()), "vector_mask_present": bool(layer.has_vector_mask()),
                   "effects_present": bool(layer.has_effects(enabled=False)),
                   "tagged_block_keys": [_label(k) for k in layer.tagged_blocks],
                   "asset": None, "rasterization": "not_processed"}
            rows[uid], references[id(layer)] = row, uid
            manifest["layers"].append(row)
            if layer.kind not in ("pixel", "group"):
                issue("unsupported_layer_kind", f"Layer kind {layer.kind} is not an embedded pixel/container contract", uid)
            if row["vector_mask_present"]:
                issue("vector_mask", "Vector mask cannot be silently approximated by cached pixels", uid)
            if row["effects_present"]:
                issue("layer_effects", "Layer effects are not baked into the pixel asset", uid)
            # Raster observation retains blend metadata. Native NJC import owns
            # compositing; readiness does not assert a Python re-composition.
            allowed_blends = (b"norm", b"mul ", b"scrn", b"over", b"dark", b"lite",
                              b"div ", b"lddg", b"idiv", b"hLit", b"sLit", b"diff", b"smud", b"fsub")
            if layer.is_group():
                allowed_blends += (b"pass",)
            if _key(layer.blend_mode) not in allowed_blends:
                issue("unsupported_blend_mode", f"Blend mode {row['blend_mode']} is metadata-only", uid)
            _blending_metadata(layer, row, issue)
            rgba = None
            width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
            stem = "-".join(f"{i:04d}" for i in path)
            if not layer.is_group() and layer.has_pixels() and header["depth"] == 8 and header["color_mode_code"] == 3:
                if width * height > _MAX_LAYER_PIXELS:
                    issue("layer_pixel_limit", "Layer exceeds supported pixel limit", uid)
                else:
                    try:
                        image = layer.topil(apply_icc=False)
                        if image is None or image.mode not in ("RGB", "RGBA") or image.size != (width, height):
                            issue("pixel_decode_mismatch", "Decoded image mode/size does not match RGB layer bounds", uid)
                        else:
                            rgba = image.convert("RGBA")
                    except (ValueError, OSError, NotImplementedError) as error:
                        issue("pixel_decode_error", f"{type(error).__name__}: {error}", uid)
            elif not layer.is_group() and (width > 0 and height > 0):
                issue("pixel_asset_unavailable", "Nonempty layer has no supported embedded raster pixels", uid)
            rgba = _simple_mask(layer, rgba, row, output, stem, issue)
            if rgba is not None:
                row["asset"] = _image_asset(rgba, output, f"source-layer-{stem}.png",
                    role="isolated_layer_pixels_with_declared_bitmap_mask", canvas_bounds=bounds, icc=icc)
                row["rasterization"] = "pixel_channels_decoded; only_declared_bitmap_mask_baked"
                manifest["assets"].append(row["asset"])
            elif layer.is_group():
                row["rasterization"] = "container_only; children_remain_separate; group_not_flattened"
            else:
                row["rasterization"] = "empty_or_unsupported; see unsupported"
            if row.get("mask", {}).get("asset"):
                manifest["assets"].append(row["mask"]["asset"])
            if layer.is_group():
                visit(layer, path, uid)

    visit(psd)
    for layer in psd.descendants():
        uid = references[id(layer)]
        row = rows[uid]
        for clipped in layer.clip_layers:
            cid = references.get(id(clipped))
            if cid is None:
                issue("clipping_reference_missing", "Clip relation refers outside observed hierarchy", uid)
                continue
            row["clip_layer_ids"].append(cid)
            if rows[cid]["clipping_base_id"] not in (None, uid):
                issue("ambiguous_clipping_base", "A clipping layer has multiple bases", cid)
            rows[cid]["clipping_base_id"] = uid
    for row in manifest["layers"]:
        if row["clipping"] and row["clipping_base_id"] is None:
            issue("clipping_base_missing", "Clipping layer has no representable base in its parent scope", row["id"])
        row["representation_complete"] = not any(x["layer_id"] == row["id"] for x in issues)

    if header["depth"] == 8 and header["color_mode_code"] == 3:
        try:
            composite = psd.topil(apply_icc=False)
            method = "embedded_merged_preview"
            if composite is None:
                # Recompose only the already-inspected supported embedded data.
                if issues:
                    raise ValueError("No merged preview and unsupported layers prevent faithful fallback")
                composite = psd.composite(ignore_preview=True, apply_icc=False)
                method = "psd_tools_embedded_layer_recomposition; not Photoshop-reference-verified"
            if composite.size != psd.size or composite.mode not in ("RGB", "RGBA"):
                raise ValueError("source composite has unexpected mode or dimensions")
            asset = _image_asset(composite.convert("RGBA"), output, "source-composite.png",
                role="whole_document_reference_only", canvas_bounds=manifest["canvas"]["bounds"], icc=icc)
            manifest["source_composite"] = {**asset, "method": method,
                "separate_material_alpha": False, "layer_recomposition_verified": False}
            manifest["assets"].append(asset)
        except (ValueError, OSError, NotImplementedError, ImportError) as error:
            issue("source_composite_unavailable", f"{type(error).__name__}: {error}")
    if not manifest["layers"]:
        issue("no_layers", "PSD contains no layers; a merged image is not a layered character input")
    if digest(source) != source_sha:
        raise ValueError("source PSD changed while it was being observed; outputs are not valid")
    manifest["source"]["sha256_after"] = source_sha
    manifest["source"]["unchanged_verified"] = True
    manifest["summary"] = {
        "layers": len(manifest["layers"]), "pixel_layers": sum(x["kind"] == "pixel" for x in manifest["layers"]),
        "groups": sum(x["is_group"] for x in manifest["layers"]),
        "visible_effective_layers": sum(x["visible_effective"] for x in manifest["layers"]),
        "layer_pngs": sum(x["asset"] is not None for x in manifest["layers"]),
        "clipping_layers": sum(x["clipping"] for x in manifest["layers"]),
        "unsupported_count": len(issues),
    }
    manifest["status"] = "psd_observation_ready" if not issues else "psd_observation_unsupported"
    manifest["content_sha256"] = json_digest(manifest)
    write_json(output / "psd-source.json", manifest)
    return manifest
