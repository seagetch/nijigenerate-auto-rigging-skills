"""Compare PSD layers with the model already imported through NJC."""
import argparse
from pathlib import Path
import numpy as np
from psd_tools import PSDImage
from riglib.data import write_json, digest, json_digest
from riglib.model import observe_model
from riglib.live import Live


def capture(psd_path, destination, *, client):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    psd = PSDImage.open(psd_path)
    observation = observe_model(client=client,require_parameters=False)
    by_name = {}
    for n in observation["nodes"]:
        if n["type"] == "Part":
            if n["name"] in by_name:
                raise ValueError("Duplicate source name requires explicit layer-path mapping")
            by_name[n["name"]] = n
    materials = []
    for layer in psd.descendants():
        if layer.is_group():
            continue
        n = by_name.get(layer.name)
        if n is None:
            raise ValueError(f"Unmapped PSD layer: {layer.name}")
        im = layer.composite(force=True)
        if im is None:
            raise ValueError(f"Missing layer pixels: {layer.name}")
        file = destination / f"{n['uuid']}.png"
        im.save(file)
        b = n["bounds"]["nominal_world_xy"]
        # Imported flat mesh bounds encode pixel centers with odd-size rounding.
        a = np.asarray(im.getchannel("A"))
        ys, xs = np.nonzero(a > 0)
        materials.append({"part": n["uuid"], "name": n["name"], "file": str(file.resolve()),
                          "sha256": digest(file), "size": list(im.size), "source_bbox": list(layer.bbox),
                          "model_bounds": b, "enabled": n["enabled_effective"],
                          "pixel_to_model": [[(b[2]-b[0])/max(1, im.width-1),0,b[0]],
                                             [0,(b[3]-b[1])/max(1, im.height-1),b[1]], [0,0,1]],
                          "alpha_pixels": int(len(xs)),
                          "alpha_bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None,
                          "draw_properties": n["draw_properties"],
                          "registration_basis": "imported-quad-corners; neutral-render validation required"})
    composite = psd.composite()
    composite.save(destination / "source-composite.png")
    result = {"schema_version": "rig-source-capture/1", "psd": str(Path(psd_path).resolve()),
              "psd_sha256": digest(psd_path), "canvas_size": list(psd.size),
              "observation_sha256": json_digest(observation), "materials": materials,
              "model_modified": False, "neutral_render_verified": False}
    write_json(destination / "source.json", result)
    print(f"Captured {len(materials)} materials at {destination}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--psd", required=True); p.add_argument("--njc", required=True); p.add_argument("--out", required=True)
    args = p.parse_args()
    capture(args.psd, args.out, client=Live(args.njc))
