---
name: nijigenerate-model-setup
description: Set up nijigenerate hierarchy, composites, grids/paths, meshes, pivots, draw modes, and initial parameter definitions through njc, then hand specialist deformation to routed skills.
---

# Nijigenerate Model Setup

For the exhaustive model setup checklist, read `references/step-checklist.yaml`.

Before this checklist, read
`../nijigenerate-shared-rigging-rules/references/workflow-router.md`. Model setup
owns structure and initial parameter definitions only; route specialist
deformation to the owning skill.

Always complete `references/step-checklist.yaml`. Start a checklist reviewer UI only when the user explicitly requests it; a user prohibition on reviewer/browser work overrides any legacy review instruction.

## Workflow

Resolve `njc` from an explicit path, `NJC_PATH`, or `PATH`, then use the project `user-doc` and `nijigenerate-shared-rigging-rules` before changing model state. Do not infer structure from names alone; inspect the actual tree, node types, meshes, draw modes, transforms, and parameter resources.

1. Read `references/model-setup-method.md` first. Read `references/mouth-rigging-assets.md` when the PSD mouth is closed or not separable for rigging. Load copied `user-doc` files from `references/user-doc/` when the task touches that area.
2. Inventory the model: Root children, Part/Node/GridDeformer/Composite/DynamicComposite nodes, draw modes, mesh status, parameter list, and existing keypoints.
3. Fix structure before mesh and parameters. The target relationship is Part-based: Body Part owns Neck Part, Neck Part owns Face Part, face features are under Face, limbs and chains run base to tip.
4. For bendable arms and legs, add a `PathDeformer` in the base-to-tip chain before mesh and parameter work. Typical limb blocks should be `Arm::L::Path`, `Arm::R::Path`, `Leg::L::Path`, `Leg::R::Path`, or equivalent, with the visual children placed under that PathDeformer.
5. For whole-body roll/bone-style torso bending, insert a centerline `PathDeformer` such as `Bone::P` as the parent of `Body::G` before Body roll rigging.
6. Insert helper Nodes only where an independent pivot is needed. If moving a limb/root pivot under existing children, also use `nijigenerate-limb-root-positioning`: freeze children with LockToRoot, move the Node to the anatomical root, then restore LockToRoot.
7. Add or convert GridDeformer only for broad surfaces: Face, BackHair, SideHair, FrontHair, Body, Chest, and similar clothing groups.
8. Apply mesh after hierarchy is correct: GridDeformer gets Grid AutoMesh; Part gets Optimum AutoMesh. Rebuild mesh after part composition changes.
9. Define initial parameter shells and neutral/start keys after structure/mesh: Face::Yaw-Pitch, Face::Roll, Body::Yaw-Pitch, Body::Roll, Eye blink/XY, Eyebrow, Mouth, and physics parameters as needed. Do not author eye-blink, mouth-open, depth-derived, post-rig, or physics deformation here.
10. Before depth import, hand off to `nijigenerate-depth-skeleton-setup` for DepthRigRoot, all standard DepthBones, artwork alignment, LockToRoot feet, and complete BoneSources. Only after that audit is fully OK may `nijigenerate-depth-import-adjustment` begin.
11. Verify with tree inspection, mesh inspection, keypoint checks, screenshots, and symmetry checks before saving.

## Core Rules

- `Part` is the visual parent relationship. `Node`, `GridDeformer`, `Composite`, and `DynamicComposite` are helpers and must not obscure Body -> Neck -> Face or base -> tip chains.
- A head/root helper such as `Head::Root` or `Face::Root` belongs between the Neck Part and head-controlled face/hair groups when an independent head pivot is needed. Its pivot must be at the anatomical head-neck hinge, normally the neck top/skull-base area read from the current overlay, not at the face center or artwork bounds center.
- `Face::G`, front/side/back hair grids, ears/headwear that should follow the head, and face feature parts should be sibling-controlled by the head root as appropriate. Back hair must not be accidentally nested under `Face::G` if it needs rear head volume independent from face-surface deformation.
- Legs should have separate left/right roots. Do not put both legs under one shared leg node unless the model has a deliberate reason.
- Limb root Nodes belong at anatomical attachment points, not part centers. Use `nijigenerate-limb-root-positioning` for arms, legs, hands, feet, tail, wings, ribbons, and sleeve/skirt roots.
- Arm and leg chains that will need bending or Body/physics follow-through should normally include a `PathDeformer` between the limb root and the visible child Parts. Put palms, fingers, feet, toes, sleeve hems, and similar attached Parts directly under that PathDeformer unless a separate pivot is actually needed.
- `Bone::P` is a structural centerline PathDeformer for broad body roll. Insert it as `Body::Root > Bone::P > Body::G`; do not put it below `Body::G`, otherwise it cannot bend the whole Body grid as one spine-like control.
- Tail, wings, ribbons, and similar appendages belong under the appropriate body/clothing/root block, not under Face.
- Neck order should preserve the Part relationship: Body Part -> Neck Part -> helper Node/Grid if needed -> Face Part. If a Node is currently above the Neck Part incorrectly, restructure before rigging.
- For a rigging-ready mouth, follow `references/mouth-rigging-assets.md`; do not treat a single closed/smiling PSD mouth as sufficient.
- Iris, teeth, tongue, and similar mouth/eye contents that must be clipped by the lower layer should use `ClipToLower` drawing mode.
- Verify `zSort` by the actual visible draw order in the app at neutral and deformation extremes. Never infer its sign from a remembered convention.
- After creating or moving left/right paired Nodes, GridDeformers, PathDeformers, or Parts, verify flip-pair registration using the shared rules.
- Centerline meshes that should be symmetric, especially `Body::G`, must have center at `x=0` or an intentional model-space center and be numerically left/right symmetric.

## Mesh Rules

- Face and back hair: start around 8x8 intervals unless the artwork needs more.
- Body: start around 10x14 intervals and adjust for aspect ratio and covered region.
- GridDeformer mesh density must match the area it controls. Its bounds must cover the union of controlled artwork at all required deformation extremes plus a safety margin. If the grid no longer covers the current parts or a new part such as Neck was added, rerun AutoMesh.
- Use Grid AutoMesh for GridDeformer and Optimum AutoMesh for Part. Do not swap them.
- After AutoMesh, inspect vertex count, coverage, margins, and left/right symmetry. Do not assume the requested segment count equals the actual vertex count.

## Parameter Setup Rules

- Create parameters by meaning, not by single part: `Face::Yaw-Pitch`, `Body::Yaw-Pitch`, `Eye::L::Blink`, etc.
- Use `-1..1` default `0` for centered axes; use `0..1` for open/close axes.
- Register `(0,0)` or `0` neutral before endpoint keys.
- Model setup may define axis breakpoints and neutral/start keys, but `nijigenerate-eye-blink-rigging` owns blink/closed-eye deformation and `nijigenerate-mouth-open-rigging` owns mouth opening/closure/expression deformation.
- Preserve the source artwork's apparent eyelid and eyelash stroke width at every `Eye::{L,R}::Blink` key. Closing, smile-closing, or deep-closing an eye must change the eyelid curve and outer-corner direction without thinning, thickening, blurring, fragmenting, or erasing the stroke.
- Do not create blink or expression differences by vertically compressing/scaling the whole eye Composite/DynamicComposite/GridDeformer, or by multiplying an existing whole-eye deformation residual, when that operation changes eyelid/eyelash stroke width. Move the eyelid/eyelash contour with a line-width-preserving local deformation; if the raster artwork cannot preserve the stroke under deformation, use a dedicated eyelid/eyelash Part or reviewed expression asset instead.
- Compare neutral, `0.25`, `0.5`, `0.75`, normal-closed, smile-closed, and deep-closed eyes at the same native-resolution crop and magnification. Treat any unapproved stroke-width change or crushed/disappearing eyelid as Retake; do not continue to another facial parameter until it passes.
- For Face/Body yaw-pitch, use `[-1, -0.5, 0, 0.5, 1]` on both axes and record the fixed pitch semantics: Body `Pitch=-1` is forward / 前傾, Body `Pitch=+1` is backward / 後傾, Face `Pitch=+1` is up / 上向き, and Face `Pitch=-1` is down / 下向き.
- Corners are correction keys, not a simple sum of horizontal and vertical offsets.
- Keep physics parameters separate from expression parameters.

## Specialist Handoffs Before Rigging

After structure, AutoMesh, and initial parameter definitions are complete:

1. Run `nijigenerate-depth-skeleton-setup` and require its complete result audit.
2. Run `nijigenerate-depth-import-adjustment`; its artwork-grid mapping defines the required overlays, feature inventory, gap repair, and mapping audit.
3. Run `nijigenerate-post-rig-adjustment` only after canonical depth, verified Fit Z, and standard depth parameters.
4. Run `nijigenerate-eye-blink-rigging` and `nijigenerate-mouth-open-rigging` for their respective expression deformation after broad Face motion and required assets/meshes are stable.
5. Run `nijigenerate-simple-physics-rigging` last.

Do not resume Face/Body/Clothing depth-derived rigging until the skeleton and depth skills have produced current fully-OK audits.

## Bone::P Centerline Definition

Use this when the model needs a non-linear `Body::Roll` spine control.

1. Re-read `Body::G`, `Body`, `Neck`, and current bindings before changing hierarchy.
2. Save a pre-change `.inx` before inserting the new parent.
3. Insert `PathDeformer` as the parent of `Body::G` using `Node_Insert_PathDeformer`, then rename it `Bone::P`.
4. Define `Bone::P` control vertices explicitly with `VertexCommand_DefineVertices`; do not use skeleton AutoMesh for this centerline.
5. Place all points on the actual `Body::G` centerline, usually `x = (grid_axis_x[0] + grid_axis_x[-1]) / 2`.
6. Use exactly these five semantic points unless the user requests more: neck top, neck base, chest, waist, crotch or under-crotch.
7. Derive neck top/base from the current Neck Part mesh and transforms, not from old screenshots or remembered rows. Derive chest/waist/crotch from the current Body::G grid or reviewed model anatomy.
8. Verify the tree is `Body::Root > Bone::P > Body::G`, `Bone::P` has five points, and existing `Body::Yaw-Pitch`, Face, arm, and leg bindings still exist.

## Head::Root Placement

Use this when adding or correcting a head/root Node for face, hair, or body pitch/roll follow.

1. Capture or inspect the current overlay around Neck, Face, and hair before moving the root.
2. Identify neck top/skull-base and neck base separately. The head root pivot should sit at the neck top/skull-base hinge unless the user explicitly chooses another point.
3. If inserting above existing visible children, freeze descendants with LockToRoot or equivalent protection before moving the parent, then restore prior LockToRoot states.
4. Keep `Face::G` and hair grids arranged so body parameters can move the head attachment root without directly deforming `Face::G`. Body parameters must not edit `Face::G` unless the user explicitly asks.
5. Verify the root coordinate numerically and visually with a screenshot/crop. Do not accept a root located at the face center, mouth/chin, or generic bounding-box center when the instruction says neck top or neck root.
6. After placement, verify `Face::Yaw-Pitch`, `Face::Roll`, `Body::Yaw-Pitch`, and hair follow still behave correctly before saving.

## Verification

- Structure: Root blocks, Body/Neck/Face relation, separate limb roots, base-to-tip chains, and appendage placement.
- Pairing: left/right Nodes, PathDeformers, GridDeformers, and Parts have verified flip pairs or an explicit reason they are unpaired.
- Mesh: GridDeformer/Part algorithm choice, coverage, density, centerline, and left/right symmetry.
- Drawing: clipping modes for iris/teeth/tongue and layer order.
- Parameters: ranges, defaults, neutral keys, endpoint keys, and keypoint coverage.
- Eye stroke preservation: same-scale native-resolution crops show that blink and expression keys preserve eyelid/eyelash stroke width; no key thins, thickens, crushes, fragments, blurs, or erases the line.
- Visual: use screenshots/live screenshots after setting parameter keypoints; iterate until visible issues are gone.

## Task-specific procedures

- Read [asset-replacement-and-composites.md](references/asset-replacement-and-composites.md) for eye/mouth control duplication or replacing torso/shoulder artwork in an existing rig.
- Tracking on an exported model is owned by `nijigenerate-tracking-setup`, not hierarchy reconstruction.

For these operations, also complete [references/change-result-checklist.yaml](references/change-result-checklist.yaml). Apply conditional items only to the requested scope.

For the relevant visual or recorded-data examples and their evidence limits, use the [example index](../nijigenerate-shared-rigging-rules/references/visual-example-index.md); procedural references link directly to their owned examples.
