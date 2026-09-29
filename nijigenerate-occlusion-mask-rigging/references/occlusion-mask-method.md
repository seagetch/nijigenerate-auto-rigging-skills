# Occlusion Mask Rigging Method

This reference describes the nijigenerate workflow for hiding parts that poke through foreground clothing or body surfaces by adding a separate `Mask` and registering it as a `DodgeMask`.

## Required References

Read these when the occluder is clothing or a body-attached surface:

- `nijigenerate-front-back-clothing-rigging/SKILL.md`
- `nijigenerate-front-back-clothing-rigging/references/front-back-clothing-method.md`
- `nijigenerate-post-rig-adjustment/SKILL.md`
- `nijigenerate-model-setup/SKILL.md`
- This skill's copied `references/user-doc/` files for node movement and mesh definition; use skill-local references for `Mask`, `DodgeMask`, `NodeMaskCommand_*`, `VertexCommand_DefineMesh`, `NodeCommand_ConvertTo`, and screenshot command notes.

## Diagnosis

Use screenshots at the poses where penetration appears:

```sh
njc tools call CaptureLiveScreenshot --json '{"path":"/abs/path/front.png"}'
njc tools call ViewCommand_SaveScreenshot --json '{"path":"/abs/path/yaw.png"}'
```

Check front, yaw left/right, pitch up/down, and any corner key that shows the issue. If the problem is side-specific, record which parameter value exposes it, such as `Body::Yaw-Pitch = (1, 0)` or `(-1, -1)`.

## Object Selection

Classify the objects before editing:

- `Occluder`: the visible foreground edge that should hide the protruding part, such as `Jacket::R`, `Jacket::L`, skirt hem, sleeve, hood, or cape edge.
- `Mask`: a separate invisible object created from the occluder's outside silhouette.
- `Targets`: parts that should be hidden by the mask, such as legs, boots, belt, skirt panels, tail, arms, hands, or rear clothing.

Do not register the visible occluder Part itself as the mask source. Create a dedicated `Mask` so the artwork can stay unchanged and the exclusion shape can be tuned independently.

## Placement

Put the `Mask` under the same deforming parent as the occluder:

```text
Jacket::G::Front
  Jacket::R
  Jacket::L
  Jacket::LegDodge::Mask
```

This keeps the mask aligned with the jacket edge during Body/Jacket yaw and pitch. If the occluder is controlled by a different GridDeformer or PathDeformer, place the mask there instead.

## Shape Design

Build the mask from the occluder's outer silhouette:

- Use the outside contour of the visible part, not the inside edge.
- Extend outward from the contour so hidden rear/leg parts disappear behind the occluder.
- Follow the outline as a strip or polygon. A rectangle usually fails because it cuts too much or leaves diagonal gaps.
- Make side-specific strips when left and right silhouettes differ.
- Include enough vertical coverage for all target parts that poke through.
- Expand width only where screenshots show gaps; do not globally grow the mask until it clips visible artwork.

For a jacket side edge, the strip normally has two boundaries:

```text
outer occluder contour -> outward offset contour
```

Triangulate each pair of adjacent contour points as connected quads:

```text
inner_i, inner_j, outer_j
inner_i, outer_j, outer_i
```

## Reading Coordinates

Read the occluder Part and parent GridDeformer:

```sh
njc read <occluder_uuid>
njc read <parent_grid_uuid>
```

For a simple Part transform with no rotation/scale, convert local mesh vertices to parent-local coordinates with:

```text
x_parent = x_local + transform.trans[0]
y_parent = y_local + transform.trans[1]
```

If the Part has rotation or scale, apply the full local transform before building the mask. Do not assume the mesh vertex coordinates are already in parent space.

## Safe Creation Path

Direct `VertexCommand_DefineMesh` on an empty `Mask` may fail because a mask without texture has no meshable source. Prefer this safe path:

1. Create or reuse a small opaque temporary PNG as a source image.
2. Import it as a texture-backed Part:

```sh
njc tools call FileCommand_MergeImageFiles --json '{"paths":"/abs/path/Niji_OcclusionMask_Source.png"}'
```

3. Move the imported Part under the deforming parent:

```sh
njc tools call NodeCommand_MoveNode --json '{"newParent":<parent_uuid>,"index":0,"context":{"nodes":[<source_part_uuid>]}}'
```

4. Name it clearly:

```sh
njc tools call NodeCommand_SetName --json '{"node":<source_part_uuid>,"name":"Jacket::LegDodge::Mask"}'
```

5. Define the strip/polygon mesh:

```sh
njc tools call VertexCommand_DefineMesh --json '{"context":{"nodes":[<source_part_uuid>]},"verts":[[x0,y0],[x1,y1]],"indices":[0,1,2]}'
```

6. Convert the Part to `Mask`:

```sh
njc tools call NodeCommand_ConvertTo --json '{"node":<source_part_uuid>,"className":"Mask"}'
```

`NodeCommand_ConvertTo` may return a non-array JSON warning while still succeeding. Always verify with `njc read <uuid>` that the resulting node type is `Mask`.

## Registering DodgeMask

Remove wrong or stale masks from each target before adding the new source:

```sh
njc tools call NodeMaskCommand_RemoveMask --json '{"node":<target_uuid>,"source":<old_mask_uuid>}'
njc tools call NodeMaskCommand_AddMask --json '{"node":<target_uuid>,"source":<mask_uuid>,"mode":"DodgeMask"}'
```

Register the mask on every target that can protrude. In clothing cases, targets often include secondary parts such as `Belt`, `Skirt`, `Skirt2`, `Skirt3`, straps, ribbons, or rear panels, not only limbs.

Verify after registration:

```sh
njc read <mask_uuid>
njc read <target_uuid>
```

The target should include a mask entry equivalent to:

```json
{"mode":"DodgeMask","source":<mask_uuid>}
```

## Verification Loop

1. Capture the original failing pose.
2. Capture the symmetric opposite pose.
3. Capture nearby corner poses if the problem happens under combined yaw/pitch.
4. Inspect whether the protruding target is hidden.
5. Inspect whether visible foreground artwork is accidentally cut.
6. Adjust the mask contour or target list, not the visible occluder artwork, unless the artwork itself is wrong.
7. Save only after the screenshots and readbacks are correct:

```sh
njc tools call FileCommand_SaveFile --json '{}'
```

## Common Failure Modes

- Using the visible jacket/skirt Part as the `DodgeMask` source. This couples artwork and mask coverage and makes tuning unsafe.
- Building the mask from the inner edge. The protrusion remains visible because the mask does not cover the outside silhouette.
- Using a rectangle. It hides unrelated art or leaves diagonal gaps near curved/angled edges.
- Placing the mask outside the occluder's deforming parent. The mask stays behind while the jacket/skirt moves.
- Masking only limbs while belt/skirt/accessory parts still poke through.
- Expanding both sides equally when only one yaw side fails.
- Saving without screenshot verification at the actual failing parameter keys.
