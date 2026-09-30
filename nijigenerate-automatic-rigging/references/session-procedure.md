# Canonical automatic-rig session procedure

This reference records the procedure established in the Ao rigging session. It
is authoritative for automatic rig requests. Generic onboarding advice does not
override or reorder it.

Before this procedure, read
`nijigenerate-shared-rigging-rules/references/workflow-router.md`, verify every
applicable specialist is available, and record the route manifest. Stop before
the first mutation if a required specialist cannot be discovered or read.

## 1. Preflight and preservation

1. Resolve `njc` from an explicit path, `NJC_PATH`, or `PATH`.
2. Inspect current command schemas and the loaded live model.
3. Record the tree, node types, meshes, draw order, parameters, axes, all binding
   target UUIDs, flip pairs, masks, Physics assignments, DepthRig state,
   BoneSources, and serialized/file size.
4. Capture neutral and declare parameter direction semantics.
5. Record the current side convention. In the established session `.L` was
   mapped to screen-left and `.R` to screen-right; do not silently reverse that
   mapping from an anatomical naming assumption.
6. Establish one verified baseline. Do not create a new full model revision for
   every inspection or failed command.

Every later phase must compare unrelated state against this baseline and its
latest verified checkpoint.

## 2. Structure, composition, and meshes

Use `nijigenerate-model-setup`, `nijigenerate-front-back-clothing-rigging`, and
`nijigenerate-automesh-setup`.

### Structure

- Inspect the actual PSD/model hierarchy rather than inferring from names.
- Make Face, eye, and mouth DynamicComposite controls Grid-shaped where broad
  deformation is required.
- Give each arm/hand side and each leg side its own broad GridDeformer when the
  artwork is a surface rather than a thin bendable chain. Do not retain a
  PathDeformer merely because a generic setup suggests one.
- Give legwear its own GridDeformer when its motion/depth differs from the legs.
- Group animal ears and headwear under the headwear GridDeformer when they must
  share broad headwear motion.
- Establish front/back/side clothing grids before depth import. Include Body
  topwear front/back and other broad clothing surfaces; do not omit the visible
  parent surface and correct only small descendants.

### Rigging-ready mouth

If the PSD mouth is closed or a single smiling image, it is not an acceptable
rigging source. Use `nijigenerate-mouth-asset-rigging`; the model-setup mouth
reference is background guidance, not a substitute for the specialist:

- create an open-mouth design from the original artwork style, not geometric
  primitives;
- separate mouth base/cavity, outline, tongue/lower interior, upper teeth, and
  lower teeth;
- place them under the mouth DynamicComposite;
- leave base and outline unclipped;
- set tongue/interior and teeth to `ClipToLower` against the base;
- extend teeth and tongue beyond the maximum clip opening so small offsets never
  reveal transparent gaps;
- verify actual visible `zSort` order instead of assuming its sign.

### Mesh

- Use Grid AutoMesh for GridDeformers and appropriate Part AutoMesh for Parts.
- Treat every mouth drawable below its DynamicComposite as a regular Part and
  AutoMesh it individually. A successful processor response is insufficient:
  read back vertex/triangle counts and inspect a mesh overlay. Reject sparse
  output that cannot support tongue, tooth, or lip curvature; reduce spacing or
  switch to the documented dense contour fallback in
  `nijigenerate-automesh-setup`.
- Size each Grid from the union of neutral and maximum required deformation
  envelopes plus margin, not from neutral artwork alone.
- Mouth and eye Grid bounds must exceed their largest planned open/closed,
  wide/narrow, or directional state by one margin.
- Use a Body-like mesh resolution for major arm, leg, and clothing grids where
  comparable broad correction is required.

Exit only after hierarchy, clipping, draw order, coverage, density, centerline,
and flip-pair readback are correct.

## 3. Initial parameters

Create semantic Face, Body, Eye, Eyebrow, Mouth, Roll, and other non-depth
parameter definitions required by the model. Register neutral/start keys, but
do not author specialist eye-blink or mouth-open deformation in model setup.

For Face/Body yaw-pitch, use the intended 5x5 axes
`[-1, -0.5, 0, 0.5, 1]`. Distinguish normalized axis offsets
`[0, 0.25, 0.5, 0.75, 1]` from actual parameter values. Do not create Physics
bindings yet.

## 4. DepthRigRoot, standard bones, and BoneSources

Use `nijigenerate-depth-skeleton-setup`.

1. Add `DepthRigRoot`.
2. Generate the standard 19 DepthBones from the template.
3. Read all bones back, including hierarchy, rest data, visible transforms,
   lengths, flip pairs, and `lockToRoot`.
4. Mark artwork landmarks and align both rest data and app-visible bone
   positions. A correct overlay with unchanged app transforms is a failure.
5. Include the artwork's torso inclination; do not leave the center chain
   artificially vertical.
6. Treat `Foot.L`/`Foot.R` as LockToRoot bones in root coordinates, not ordinary
   child transforms.
7. Assign BoneSources:
   - face grids: Head only;
   - each arm/hand grid: every DepthBone in that side's shoulder-to-hand chain;
   - each leg grid: every DepthBone in that side's thigh-to-foot chain;
   - body/lower clothing grids: the complete chains required by their actual
     surface ownership. For an independently driven skirt, use the
     [pelvis/skirt procedure](../../nijigenerate-depth-skeleton-setup/references/pelvis-skirt-follow.md);
     do not add both-leg or non-yaw pelvis sources merely because it is clothing;
   - other grids: the exact controlling chain, not a convenient partial list.
8. Re-read every BoneSource list before proceeding.

## 5. Depth image import and anatomical correction

Use `nijigenerate-depth-import-adjustment`.

1. Open and inspect the supplied PSD-depth import state without applying.
2. Map actual artwork parts to actual GridDeformers.
3. Audit zero/missing depth under alpha. If many alpha-covered samples are zero
   or one surface is split into disconnected depth islands, run Fit alpha-depth
   to gaps one or more times and re-audit.
4. Tune per-layer scale and offset before import:
   - preserve meaningful facial and body relief;
   - reduce excessive mouth projection so yaw does not produce a protruding
     muzzle;
   - preserve cheek/cranium volume while reducing only wrong local protrusion;
   - prevent front-hair side regions from receding into and covering the face;
   - keep headwear, animal ears, and earwear from being excessively concave;
   - make upper/lower neck depth continuous;
   - keep Face and Front Hair at a plausible overall forward offset;
   - preserve front/back clothing ordering without flattening all relief.
5. Apply only after every enabled target passes.
6. Inspect imported depth on every GridDeformer and correct local arrays so the
   whole character forms a coherent human volume. For every headed character,
   complete the [posterior-head case procedure](../../nijigenerate-depth-import-adjustment/references/head-volume-and-hair-cases.md).
   No hair does not exempt skull/scalp continuity; long hair requires all linked Ao cases,
   with Part/physics work deferred only to its explicit later owner.
7. Verify effective Z at neutral and exact yaw/pitch keys. Do not judge raw depth
   arrays alone.

The goal is not “more relief” or “flatter.” Preserve relief where anatomy needs
it and reduce it only where it causes wrong silhouette, occlusion, or
penetration.

## 6. Fit Z to Depth

Fit Z is mandatory after the final depth correction and before standard Depth
parameter generation.

Before running it, follow
`nijigenerate-shared-rigging-rules/references/parameter-state-isolation.md`:

- arm only the intended Depth parameter, never `::Physics`;
- snapshot every parameter target set, binding count, and `isSet` state;
- snapshot Physics target UUIDs and non-neutral keys;
- record serialized/file size.

Run Fit Z to Depth through the current exposed `njc` command. If only an
equivalent operation exists, report it as `Fit Z相当処理` and prove its numeric
result. Re-read every DepthBone local/world Z and globally diff all parameters.
Stop without saving on any unrelated change.

## 7. Standard Depth parameter generation

Only after Fit Z is verified:

1. generate the standard Depth parameters;
2. read back their axes, keys, targets, and bindings;
3. capture neutral, endpoints, and corners before manual adjustment;
4. do not replace generated bindings with a custom projection formula.

## 8. Body post-rig adjustment

Use `nijigenerate-post-rig-adjustment`.

Correct in this order:

1. wrong depth in the depth skill;
2. wrong DepthBone/BoneSource motion in the skeleton skill;
3. only a diagnosed and permitted broad Grid/Path defect; preserve correct parents;
4. direct Part residual for the smallest remaining artwork-specific defect.

Do not omit the parent artwork itself. Body, topwear front/back, shoulders,
chest, torso, bottomwear, and legs must be evaluated as visible surfaces, not
only their small child parts.

### Directional visual rule

At every yaw/pitch direction, identify the screen-near and screen-far side from
the resulting image. Move the near shoulder/body surface as required by that
view when that surface actually needs correction; do not inspect only the far side and do not reuse the opposite yaw's clothing
deformation.

Evaluate both shoulders, chest, torso, hips, skirt, knees, and both yaw
directions at Body pitch `-1/0/+1`.

### Parent residual rule

If `Body::G`, another parent Grid, Pelvis, Spine, or a DepthBone changes, existing
child residuals are stale. Follow
`nijigenerate-post-rig-adjustment/references/parent-residual-recalculation.md`:

```text
new child residual = desired final result - current composed parent result
```

Audit all 25 cells of every 5x5 binding. Intermediate `±0.5` cells must be
intentionally set or intentionally unset; nine cardinal/corner screenshots do
not prove correct interpolation.

### Pelvis, Spine, knees, and LockToRoot feet

Use DepthBone bindings and
`nijigenerate-depth-skeleton-setup/references/pose-compensation.md`.

- When redistributing Body yaw, reduce excessive Spine rotation and transfer the
  intended share to Pelvis without losing the total torso turn.
- Recompute both leg chains after Pelvis changes.
- Keep each LockToRoot ankle/foot at its fixed app-visible target.
- Counter-rotate/transform Thigh and Shin DepthBones so knees do not swing
  sideways, cross, or drop excessively.
- Do not substitute a Part/Grid correction for a broken DepthBone chain.

Complete the Body pass, including Pelvis/Spine/leg correction and its full
result audit, before beginning the Face pass.

## 9. Face post-rig and expression specialists

Close the mandatory posterior-head inspection and any carried scalp-seam/internal-detail
items using [head/hair Part correction](../../nijigenerate-post-rig-adjustment/references/head-hair-surface-correction.md).
For long hair, close the head/pose-owned items in the complete Ao case review;
carry physics-only items explicitly to phase 10. Face-only appearance cannot establish head completion.

Use `nijigenerate-post-rig-adjustment` for broad Face orientation first. After
that result is stable, use `nijigenerate-eye-blink-rigging` for eyelid closure
and `nijigenerate-mouth-open-rigging` for opening/closure/expression. Do not
implement either specialist deformation inside model setup or as a generic
whole-composite scale.

For Face, evaluate top, bottom, left, right, all four corners, and intermediate
keys. Identify the screen-near and screen-far cheek from each rendered pose;
never reuse the opposite yaw's correction blindly.

### Eye::Blink pass

1. Preserve the accepted broad Face motion and eye structure.
2. Follow the eye specialist's upper/lower contour, canthus, lash-band,
   near/far-eye, full-close-first, and intermediate-key procedure.
3. Preserve apparent eyelid and eyelash width, thickness, and taper. Reject
   whole-eye vertical scaling or compression that crushes or erases the line.
4. Complete both eye specialist checklists and exact-key image audit before the
   mouth pass or physics.

### Mouth::Open pass

After mouth assets, Part meshes, and broad Face motion are valid, use
`nijigenerate-mouth-open-rigging`. Preserve the artwork's tilted local mouth
axis, use the specialist's near/far-corner treatment, and verify every required
intermediate key and composition state.

### Face::Yaw-Pitch mouth-cavity pass

Perform this during Face rigging, after the mouth structure, Part meshes, and
`Mouth::Open` bindings are valid.

1. Capture neutral and all `Face::Yaw-Pitch` cardinal/corner poses with the
   mouth open enough to expose its interior. Determine the artwork's actual
   face angle and local mouth axis from the images. Never force the mouth,
   teeth, or tongue to screen-horizontal when the face is tilted or turned.
2. Bind `Mouth::Tongue`, `Mouth::Teeth::Upper`, and
   `Mouth::Teeth::Lower` to the full 5x5 `Face::Yaw-Pitch` grid. Preserve their
   existing `Mouth::Open` bindings and clipping relationship.
3. On yaw, compress the far side toward the mouth's vanishing direction, shift
   the visible tongue mass with the cavity, and apply modest tilt/shear so the
   interior reads as a receding surface. Make upper and lower teeth follow the
   same cavity perspective. Do not approximate yaw with uniform translation.
4. Determine the pitch sign from captured images. For an upward-facing pose,
   reveal and shape the upper teeth; for a downward-facing pose, reveal and
   shape the lower teeth. Combine vertical reveal with local scaling,
   compression, and curvature so the result remains inside the outline and
   base clip. Do not approximate pitch with vertical translation alone.
5. Keep the neutral Face key visually unchanged. If the command cannot create
   a new deform binding from an all-zero key, write one verified non-zero
   endpoint first, read the binding back, then write the zero center key.
6. Audit all 25 Face cells as cropped images, then test composition at the
   relevant `Mouth::Open` X/Y extremes. Compare near/far compression, tooth
   reveal, tongue contour, clipping gaps, and interpolation between adjacent
   cells. Numeric binding presence is supporting evidence, never visual proof.

Do not move this pass to post-hoc mouth asset creation. Asset structure owns
what exists, `Mouth::Open` owns opening/expression, and Face rigging owns how the
already-built mouth cavity follows head orientation.

## 10. Physics

Use `nijigenerate-simple-physics-rigging` only after all authored deformation is
stable.

1. Inventory every visually plausible moving area: front/back/side hair, animal
   ears, head ornaments, sleeves, skirt and lower clothing, ribbons, frills, and
   cords.
2. Define Physics parameters and author their deformation keys first.
3. Verify those keys before creating/assigning SimplePhysics.
4. Disable global physics/drivers while changing assignments.
5. Use Gravity `1.0`.
6. Derive Length from the model-space fixed-to-free endpoint distance; do not
   copy a fixed constant.
7. Keep roots, hair attachments, shoulder seams, and skirt waist stable.
8. Do not use physics keys to correct a deterministic Body::Yaw-Pitch skirt,
   knee, or clothing defect.
9. Re-audit `FrontHair::Physics`, `BackHair::Physics`, and every Physics binding
   after any later DepthBone/Grid refresh.

## 11. Final verification and saving

Verify:

- neutral;
- all Face/Body endpoints and four corners;
- all 25 cells for edited 5x5 bindings;
- adjacent interpolation values;
- mouth/eye extremes;
- dedicated eye-blink and mouth-open result audits;
- clothing front/back order and skirt hem continuity;
- Pelvis/Spine, knees, and locked ankles;
- hair, skirt, accessory physics and reset behavior;
- all parameter target UUIDs, bindings, hierarchy, meshes, masks, DepthBones,
  BoneSources, and Physics settings;
- serialized/file size against the verified baseline.

Restore neutral and reset Physics before saving. Save a new named checkpoint only
after a phase passes, and one final verified output. Do not create repeated
full-size revisions that contain no confirmed improvement.

## Error recovery

- After `Bad Request` or another error-looking response, re-read the affected
  resource before retrying; the command may already have mutated state.
- Inspect the command's returned status, error text, and nested `succeeded`
  value. A shell process exit code of zero does not prove the model command
  succeeded.
- For parameter-key commands, follow the currently exposed schema exactly; in
  particular, place `parameterValue` in `context` when that schema requires it.
- Do not parse warning-prefixed or truncated command output as pure JSON. Query
  the narrow resource/tool needed and preserve the complete response.
- Never retry the same payload blindly.
- Do not use orchestration `exit()` or an equivalent silent early return to end
  a batch after one failed cell. Record the failed cell, repair the payload,
  retry it, and finish the required matrix unless state verification requires a
  stop.
- If unrelated state changes, stop and return to the last verified checkpoint.
- Do not continue into a later phase while the current phase's exit conditions
  fail.

## When directional generated references are part of the task

Use the shared [reference-generation → depth → Part procedure](../../nijigenerate-shared-rigging-rules/references/angle-reference-depth-part-workflow.md). Capture and validate references before using them as targets; refine base volume in the depth phase, then carry the same reference ledger into Body/Face Part adjustment. Preserve the initial Fit Z/standard-generation ordering above; an existing-rig correction does not restart these initial phases. Defer only Part-owned residuals at the depth checkpoint and close them before overall completion.
