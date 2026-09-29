---
name: nijigenerate-automesh-setup
description: Apply or repair nijigenerate AutoMesh through njc for GridDeformer, PathDeformer, or Part processor choice, density, spacing, coverage, and batch setup.
---

# Nijigenerate AutoMesh Setup

For the exhaustive AutoMesh checklist, read `references/step-checklist.yaml`.

Always complete `references/step-checklist.yaml`. Start a checklist reviewer UI only when the user explicitly requests it; a user prohibition on reviewer/browser work overrides any legacy review instruction.

## Workflow

Resolve `njc` from an explicit path, `NJC_PATH`, or `PATH`, then use it with the project's `user-doc` and `nijigenerate-shared-rigging-rules` before mutating mesh state. Read these first:

- `user-doc/tutorial/ja/01-model-structuring/10-step-7-automesh.md`
- `user-doc/tutorial/ja/01-model-structuring/02-decision-guide.md`

Then follow this order:

1. Classify each target as `GridDeformer`, `PathDeformer`, ordinary `Part`, or thin/silhouette-critical `Part`.
2. Choose the processor by target type:
   - `GridDeformer` -> `grid`
   - `PathDeformer` -> `skeleton`
   - ordinary `Part` -> `optimum`
   - fallback for thin or outline-critical `Part` when `optimum` fails -> `contour`
3. Set processor config before applying. Prefer typed tools such as `AutoMesh_SetSimple_grid` and `AutoMesh_SetSimple_skeleton`.
4. Apply only to explicit targets with `context.nodes`; do not assume descendants are included implicitly.
5. Read back the actual mesh or grid axes after apply. Requested density and final vertex count are not the same thing.
6. Re-evaluate coverage after child-set, hierarchy or texture changes. Re-run AutoMesh directly only before dependent depth/keys/Welding exist; use the rigged-mesh procedure otherwise.
7. Verify coverage, symmetry, centerline placement, and whether later rigging has enough control points.
8. For a deforming GridDeformer, evaluate the union of the controlled artwork bounds at neutral and every required endpoint/corner pose. The grid must cover that maximum deformation envelope plus a safety margin; neutral artwork bounds alone are insufficient.

For recommended settings, presets, and command examples, read `references/automesh-settings.md`.

## Processor Rules

- Never use `optimum` on a `GridDeformer`.
- Never use `grid` on a regular `Part` or `PathDeformer`.
- For bendable arms, legs, tails, ribbons, and similar chains, mesh the `PathDeformer` itself with `skeleton`; keep attached Parts under that path.
- Use `contour` only when `optimum` produces the wrong silhouette, bridges gaps, or destroys thin strips.
- Do not increase density to compensate for a wrong hierarchy, wrong pivot/root, or missing `GridDeformer`/`PathDeformer`.
- Treat a static artwork margin as an initial estimate only. Rebuild or expand the grid when any valid key can approach or cross its boundary.

## Tooling

- Use `AutoMesh_SetSimple_grid`, `AutoMesh_SetSimple_skeleton`, `AutoMesh_SetSimple_optimum`, and `AutoMesh_SetSimple_contour` for normal setup.
- Use `AutoMesh_SetPreset_optimum` or `AutoMesh_SetPreset_contour` when a named preset is enough.
- Use `AutoMesh_Apply_grid`, `AutoMesh_Apply_skeleton`, `AutoMesh_Apply_optimum`, and `AutoMesh_Apply_contour` to apply directly to `context.nodes`.
- Use `AutoMesh_SetActive`, `AutoMesh_SetValues`, and `AutoMesh_ApplyActive` only when one processor will be reused across many consecutive operations.

## Verification

- Report AutoMesh evidence after every application: target UUID/name, processor used, command used, requested settings, actual vertex/grid-axis counts, and coverage result. If the user required AutoMesh, explicitly state that no manual `VertexCommand_DefineMesh` replacement was used for that target.
- `GridDeformer`: actual `grid_axis_x/y` count matches the intended broad-surface control density.
- `PathDeformer`: control point count matches the intended bend model; roots and tips did not flip.
- `Part`: silhouette coverage is correct, holes are not bridged incorrectly, and triangulation is neither too sparse nor explosively dense.
- Symmetric targets remain numerically and visually symmetric after apply.
- Screenshots or live captures were checked before moving on to rigging.

## Task-specific procedures

- Read [parameter-only-and-rigged-mesh.md](references/parameter-only-and-rigged-mesh.md) for a single-setting request or any mesh change after depth, bindings or Welding exist.

For these operations, also complete [references/change-result-checklist.yaml](references/change-result-checklist.yaml). Apply conditional items only to the requested scope.
