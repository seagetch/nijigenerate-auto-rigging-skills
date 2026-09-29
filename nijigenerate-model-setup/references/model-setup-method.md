# Model Setup Method Reference

This reference summarizes the `user-doc`-based workflow used for early nijigenerate model setup: structure, mesh, and initial parameter definition.

## Copied User Docs

Read the copied docs under this skill before modifying the corresponding area.

Model structuring:

- `references/user-doc/model-structuring/01-overview.md`
- `references/user-doc/model-structuring/02-decision-guide.md`
- `references/user-doc/model-structuring/04-step-1-root-blocks.md`
- `references/user-doc/model-structuring/05-step-2-face-hierarchy.md`
- `references/user-doc/model-structuring/06-step-3-chain-parts.md`
- `references/user-doc/model-structuring/07-step-4-insert-helper-nodes.md`
- `references/user-doc/model-structuring/08-step-5-grid-deformer.md`
- `references/user-doc/model-structuring/09-step-6-front-hair-chest-clothes.md`
- `references/user-doc/model-structuring/10-step-7-automesh.md`
- `references/user-doc/model-structuring/11-step-8-symmetry-pairs.md`
- `references/user-doc/model-structuring/12-checklist-and-tree.md`

Parameter definition:

- `references/user-doc/parameter-definition/01-overview.md`
- `references/user-doc/parameter-definition/02-values-and-keys.md`
- `references/user-doc/parameter-definition/03-basic-editing-flow.md`
- `references/user-doc/parameter-definition/04-face.md`
- `references/user-doc/parameter-definition/05-body.md`
- `references/user-doc/parameter-definition/05-body-yaw.md`
- `references/user-doc/parameter-definition/05-body-pitch.md`
- `references/user-doc/parameter-definition/05-body-roll-check.md`
- `references/user-doc/parameter-definition/06-expression.md`
- `references/user-doc/parameter-definition/07-physics-and-checklist.md`

Use these copied references as the required baseline.

## Reference Script

Use `references/model_setup_reference.py` as a command-pattern reference. It is not a drop-in migration; adapt node UUIDs, names, tool names, and payloads after inspecting the active model.

## Structure Procedure

1. Inspect the current tree and classify each item as `Part`, `Node`, `GridDeformer`, `Composite`, or `DynamicComposite`.
2. Build Root-level blocks first: Body/root torso block, separate left/right leg roots, arms, tail/wings/ribbons/accessories when independent.
3. Preserve visual Part relationships:
   - Body Part -> Neck Part.
   - Neck Part -> Face Part.
   - Face Part -> eyes, mouth, ears, face-attached hair.
   - Base Part -> helper root Node -> chain base -> chain tip for limbs, tail, wings, ribbons, and back hair.
4. Insert helper Nodes as parent only when an independent pivot is needed. Prefer insert over add when inserting a parent into an existing chain.
5. Convert existing helper Nodes to `GridDeformer` or `DynamicComposite` when the hierarchy exists but the node type is wrong.
6. For `DynamicComposite` converted from Node, toggle `autoResizedMode` twice if bounds/display are stale.
7. Keep shadows under the object they shadow.

## Specific Correction Patterns

- Tail must not be a Face child. It belongs under an appropriate body/leg/root block.
- Left and right legs should have their own roots rather than sharing one leg node.
- Limb root Nodes must be placed at anatomical roots, not at the visual part center. A-pose arms require X and Y root placement; near-vertical legs mainly require Y.
- When moving an existing root Node with children, LockToRoot all children first, move the parent Node, then release child LockToRoot.
- Neck Part should remain in the Body/Body::G visual chain; helper `*Neck` Node should be under Neck Part when a neck pivot is needed.
- Iris, teeth, and tongue drawing mode should be `ClipToLower` when they must be clipped by the lower layer.

## GridDeformer Placement

Use GridDeformer for broad surfaces only:

- `Face::G`
- `BackHair::G`
- `SideHair::G`
- `FrontHair::G`
- `Body::G`
- `Chest::G` when chest is a separate local surface
- Other broad clothing groups when needed

Do not put GridDeformer everywhere. A grid should own a meaningful surface region and have all intended child Parts under it.

## AutoMesh Procedure

1. Confirm the hierarchy and child set first.
2. For GridDeformer, use Grid AutoMesh.
3. For Part, use Optimum AutoMesh.
4. For Face/back hair, start around 8x8 intervals.
5. For Body, start around 10x14 intervals, then adjust to aspect ratio and actual controlled region.
6. Use about 10% margin as a starting point for broad grids.
7. Inspect actual result: vertex count, coverage, margin, centerline, and left/right symmetry.

Important: AutoMesh can produce a different actual vertex count than the requested segment count. Always read back the actual `grid_axis_x` and `grid_axis_y`.

## Mesh Symmetry

For symmetric grids:

- Verify left/right vertex coordinates are mirrored around the intended center.
- If the model center should be `x=0`, ensure the central axis is actually at `x=0`.
- Verify `Body::G` centerline after AutoMesh, especially after adding Neck or moving Parts.
- Check both topology and deformation values; symmetric mesh with asymmetric key values still fails.

## Initial Parameter Set

Recommended base parameters:

- `Face::Yaw-Pitch`: 2D, min `(-1,-1)`, default `(0,0)`, max `(1,1)`.
- `Face::Roll`: 1D, min `-1`, default `0`, max `1`.
- `Body::Yaw-Pitch`: 2D, min `(-1,-1)`, default `(0,0)`, max `(1,1)`.
- `Body::Roll`: 1D, min `-1`, default `0`, max `1`.
- `Eye::L::Blink` / `Eye::R::Blink`: 2D, X `0..1`, Y `-1..1`.
- `Eye::L::X-Y` / `Eye::R::X-Y`: 2D, `-1..1`.
- `Eyebrow::L` / `Eyebrow::R`: 2D, `-1..1`.
- `Mouth::Open`: 2D, X `0..1`, Y `-1..1`.
- `<Part>::Physics`: separate physics parameters for hair/cloth/ribbon when needed.

## Keypoint Rules

- Register neutral first.
- Face/Body yaw-pitch should have `[-1, -0.5, 0, 0.5, 1]` on both axes.
- Face/Body roll should have `[-1, -0.5, 0, 0.5, 1]`.
- Blink X should use `0, 0.25, 0.5, 0.75, 1`.
- Corners are correction keys; do not assume they are simple horizontal + vertical sums.

## Verification Checklist

Before saving:

- Root blocks are organized and not a flat list of Parts.
- Body Part, Neck Part, and Face Part relationships are correct.
- Legs have separate roots; arms and chains are base-to-tip.
- Tail/wings/ribbons are under appropriate body/clothing/root blocks, not Face.
- Required DynamicComposites exist for eyes/mouth differences.
- Required GridDeformers exist and contain the intended child Parts.
- Part meshes use Optimum and GridDeformers use Grid.
- Symmetry pairs are registered for left/right Parts and Deformers.
- ClipToLower is applied where required.
- Parameters have correct ranges/defaults/keypoints.
- Screenshots or live captures confirm visible state after keypoint selection.
