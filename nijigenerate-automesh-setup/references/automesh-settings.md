# AutoMesh Settings

This file contains the concrete settings and heuristics for `nijigenerate-automesh-setup`.

## Processor Map

- `GridDeformer` -> `grid`
- `PathDeformer` -> `skeleton`
- ordinary `Part` -> `optimum`
- thin or silhouette-critical `Part` fallback -> `contour`

This mapping combines this skill's copied `references/user-doc/` rules with practical heuristics for `PathDeformer` and thin Parts.

## Good Starting Settings

These are starting points, not universal truth. Adjust only after reading back the actual result.

### GridDeformer

Use `AutoMesh_SetSimple_grid`.

Good defaults:

- `mask_threshold = 15`
- `margin = 0.1`

Good density starts:

- Face / back hair broad mass: `x_segments = 8`, `y_segments = 8`
- Body broad mass: `x_segments = 10`, `y_segments = 14`
- Front hair, chest, medium broad cloth: start around `6x8` to `8x8`
- Front/back skirt or coat panels: start around `8x10` to `10x14`

Use lower density when:

- the grid covers only a small local area
- the shape does not need many bend bands

Use higher density only when:

- the surface must bend across multiple distinct rows or columns
- a later depth rig genuinely needs more control bands

Do not increase density to fix:

- wrong hierarchy
- missing children under the grid
- wrong shoulder, waist, or neck placement

Example:

```sh
njc tools call AutoMesh_SetSimple_grid --json '{
  "mask_threshold": 15,
  "x_segments": 8,
  "y_segments": 8,
  "margin": 0.1
}'
njc tools call AutoMesh_Apply_grid --json '{
  "context": { "nodes": [GRID_UUID] }
}'
```

### PathDeformer

Use `AutoMesh_SetSimple_skeleton`.

Good defaults:

- `mask_threshold = 15`

Good `target_point_count` starts:

- simple arm or leg path: `3`
- limb that needs one extra bend band: `4`
- hair strand, tail, ribbon, or long cloth strip: `5` to `8`
- very long, highly flexible strand: `8` to `12`

Prefer the smallest count that matches the intended bend model. More points are not automatically better.

Use fewer points when:

- the chain should behave like root-mid-tip
- later rigging will drive the path by broad bends only

Use more points when:

- the path is long and visibly curves in several places
- physics will need more than one local bend

Do not use `grid` or `optimum` on a `PathDeformer`.

Example:

```sh
njc tools call AutoMesh_SetSimple_skeleton --json '{
  "mask_threshold": 15,
  "target_point_count": 3
}'
njc tools call AutoMesh_Apply_skeleton --json '{
  "context": { "nodes": [PATH_UUID] }
}'
```

### Ordinary Part

Use `AutoMesh_SetPreset_optimum` first. `optimum` is the default for normal Parts.

Useful presets:

- `Normal parts`: first choice for most Parts
- `Detailed mesh`: Parts that distort strongly or need more internal control
- `Large parts`: large cloth or body-adjacent Parts without an outer grid
- `Small parts`: small accessories
- `Thin and minimum parts`: narrow strips and minimum-area Parts
- `Preserve edges`: sharp-corner silhouettes

Raw simple defaults in source:

- `scales = [0.5, 0.0]`
- `min_distance = 10`
- `mask_threshold = 1`
- `div_per_part = 12`

Example:

```sh
njc tools call AutoMesh_SetPreset_optimum --json '{
  "preset": "Normal parts"
}'
njc tools call AutoMesh_Apply_optimum --json '{
  "context": { "nodes": [PART_UUID] }
}'
```

### Contour Fallback

Use `contour` only when `optimum` is structurally wrong for the Part.

Typical cases:

- thin silhouette strips
- outline-sensitive Parts
- `optimum` bridges gaps or overfills holes

Useful presets:

- `Normal parts`
- `Detailed mesh`
- `Small parts`
- `Thin and minimum parts`
- `Preserve edges`

Raw preset tendencies from source:

- `Normal parts`: `sampling_step = 50`, `min_distance = 16`
- `Detailed mesh`: `sampling_step = 32`, `min_distance = 16`
- `Large parts`: `sampling_step = 80`, `min_distance = 24`
- `Small parts`: `sampling_step = 24`, `min_distance = 12`
- `Thin and minimum parts`: `sampling_step = 12`, `min_distance = 4`

Example:

```sh
njc tools call AutoMesh_SetPreset_contour --json '{
  "preset": "Thin and minimum parts"
}'
njc tools call AutoMesh_Apply_contour --json '{
  "context": { "nodes": [PART_UUID] }
}'
```

## Active Processor Workflow

Use this only when repeating the same processor many times in sequence.

```sh
njc tools call AutoMesh_SetActive --json '{ "processorId": "grid" }'
njc tools call AutoMesh_SetValues --json '{
  "processorId": "grid",
  "level": "Simple",
  "updates": "{\"x_segments\":8,\"y_segments\":8,\"margin\":0.1,\"mask_threshold\":15}"
}'
njc tools call AutoMesh_ApplyActive --json '{
  "context": { "nodes": [GRID_UUID] }
}'
```

Prefer typed `AutoMesh_SetSimple_*` calls when only one target or one processor class is involved.

## Verification Checklist

- The chosen processor matches the node type.
- Grid targets have the expected broad-surface band count.
- Path targets have the intended root-mid-tip or multi-bend control count.
- Part meshes cover the visible alpha without obvious holes or wasteful density.
- Left/right symmetric targets stayed symmetric.
- AutoMesh was re-applied after any structure or child-set change.
