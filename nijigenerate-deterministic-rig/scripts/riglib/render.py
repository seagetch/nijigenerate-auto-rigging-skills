"""Deterministic raster previews; source artwork is sampled without regeneration."""
from pathlib import Path
import math
import numpy as np
from PIL import Image, ImageDraw
from .data import digest


def render_sheet(fit, poses, output, cell=320, columns=3):
    if digest(fit["source"]["path"]) != fit["source"]["sha256"]:
        raise ValueError("source image changed since fit")
    if not poses:
        raise ValueError("no poses to render")
    if any("xyz" not in pose for pose in poses):
        raise ValueError("renderer requires evaluated XYZ for depth testing; reevaluate older pose artifacts")
    source = Image.open(fit["source"]["path"]).convert("RGBA")
    rest = np.asarray(fit["mesh"]["rest_xy"])
    all_xy = np.concatenate([np.asarray(p["xy"]) for p in poses])
    minimum, maximum = all_xy.min(axis=0), all_xy.max(axis=0)
    extent = np.maximum(maximum-minimum, 1)
    scale = min((cell-32)/extent[0], (cell-55)/extent[1])
    offset = np.array([(cell-extent[0]*scale)/2, 36+(cell-44-extent[1]*scale)/2])-minimum*scale
    sheet = Image.new("RGB", (columns*cell, math.ceil(len(poses)/columns)*cell), "#e4e7eb")
    indices = np.asarray(fit["mesh"]["triangles"], int)
    for number, pose in enumerate(poses):
        tile = Image.new("RGBA", (cell, cell), "#f8f8f8")
        target = np.asarray(pose["xy"])*scale+offset
        z=np.asarray(pose["xyz"])[:,2]
        zbuffer=np.full((cell,cell),-np.inf)
        culled=0
        ordered=sorted(indices.tolist(),key=lambda tri:float(z[tri].mean()))
        for tri in ordered:
            dst, src = target[tri], rest[tri]
            matrix = np.column_stack([dst, np.ones(3)])
            if np.linalg.det(matrix) <= 1e-8:
                culled+=1
                continue
            left, top = np.floor(dst.min(axis=0)).astype(int)
            right, bottom = np.ceil(dst.max(axis=0)).astype(int)+1
            left, top = max(left,0), max(top,0)
            right, bottom = min(right,cell), min(bottom,cell)
            if right <= left or bottom <= top:
                continue
            affine = np.linalg.solve(matrix, src)
            base = np.array([left,top,1.0]) @ affine
            coefficients = (affine[0,0],affine[1,0],base[0],affine[0,1],affine[1,1],base[1])
            patch = source.transform((right-left,bottom-top), Image.Transform.AFFINE,
                                     coefficients, resample=Image.Resampling.BILINEAR)
            mask = Image.new("L", patch.size, 0)
            ImageDraw.Draw(mask).polygon([tuple(p-[left,top]) for p in dst], fill=255)
            dz=np.linalg.solve(matrix,z[tri])
            yy,xx=np.mgrid[top:bottom,left:right]
            depth=xx*dz[0]+yy*dz[1]+dz[2]
            alpha=(np.asarray(patch.getchannel("A"),np.uint16)*np.asarray(mask,np.uint16)//255).astype(np.uint8)
            region=zbuffer[top:bottom,left:right]
            visible=(alpha>0)&(depth>=region-1e-8)
            region[visible]=depth[visible]
            alpha[~visible]=0
            patch.putalpha(Image.fromarray(alpha))
            tile.alpha_composite(patch,(left,top))
        draw = ImageDraw.Draw(tile)
        for tri in indices:
            draw.line([tuple(target[i]) for i in [*tri,tri[0]]], fill=(30,110,170,75),width=1)
        p = pose["pose"]
        draw.text((8,8), f"yaw {p['yaw']:g} / pitch {p['pitch']:g} / roll {p['roll']:g}", fill="#142331")
        draw.text((8,cell-14),f"Diagnostic / backfaces culled: {culled} / no clip",fill="#536779")
        sheet.paste(tile.convert("RGB"), ((number%columns)*cell,(number//columns)*cell))
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    sheet.save(output)
