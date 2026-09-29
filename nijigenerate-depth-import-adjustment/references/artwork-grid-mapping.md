# Artwork-to-grid depth mapping

Use this reference before assigning or correcting depth values.

## Capture current evidence

1. Read each target GridDeformer’s UUID, parent, transforms, `grid_axis_x`, `grid_axis_y`, dimensions, and current depth-array length.
2. Capture the current artwork with the target mesh overlaid through `njc`, preferably with `ViewCommand_CaptureLiveScreenshot` and `overlayObjects`.
3. Read the screenshot itself. Bounds and resource data may confirm a location but must not replace visible artwork-to-grid correspondence.
4. Label rows, columns, vertices such as `V(r,c)`, cells such as `R3C4`, and visible feature regions.
5. Mark inferred positions with `?`. Do not create values for unresolved critical regions.
6. Preserve user-corrected feature positions and cell sets as authoritative until the user changes them.

## Validate the source depth image

- Confirm image dimensions, bit depth, orientation, artwork alignment, and character coverage.
- Confirm useful depth variation covers the character instead of a tiny isolated patch.
- Confirm foreground/background polarity from the pixels and import settings, not the filename.
- Reject an almost uniform white/black image when it contains no meaningful continuous character shape.
- Do not accept a file merely because it is 16-bit.

## Minimum feature inventory

Map only features that exist in the current artwork.

### Face and head

- left/right eyes and the band directly above them;
- nose, mouth, chin/jaw, cheeks, brow/forehead, skull sides;
- front hair, side hair, back hair;
- headwear, animal ears, earwear, and other face-attached accessories.

### Body

- neck top and neck base;
- shoulder line and both shoulder sockets;
- left/right chest masses separately from broad torso volume;
- ribcage, abdomen, waist/belt, pelvis, hip width;
- arm roots, leg roots, sleeve caps;
- apron/skirt front, lower torso, side wraps, and rear clothing.

### Clothing

- front panel, back panel, side wrap;
- waist/belt attachment, shoulder/neck anchor;
- hood, sleeve cap, hem, ribbons, and local accessories;
- whether each surface inherits a parent body/head GridDeformer.

## Mapping rules

- Rebuild the mapping after AutoMesh, hierarchy changes, grid-axis changes, or new artwork. Never reuse remembered row numbers.
- State whether paired values are equal, mirrored, intentionally asymmetric, inferred, or user-corrected.
- Convert a child Part’s visible point into parent-grid local coordinates before selecting cells.
- For small accessories, map the Part bounds/center to adjacent grid rows and columns, then bilinearly sample the parent surface.
- Do not assign a depth array until every critical visible region can be pointed to on the current overlay.
