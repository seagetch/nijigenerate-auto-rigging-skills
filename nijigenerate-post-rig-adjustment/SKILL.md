---
name: nijigenerate-post-rig-adjustment
description: Refine nijigenerate Face/Body poses and individual Part 2.5D contours, seams and occlusion through njc while preserving the established depth and bone motion.
---

# Nijigenerate Post Rig Adjustment

Use this skill only after the standard Depth parameters exist. Preserve the generated rig. Inspect broad causes before local detail; change only the responsible layer permitted by the task. Parent inspection does not require parent edits.

## Read references by task

- Always read [operation-order.md](references/operation-order.md) before changing a model.
- Read [broad-grid-path-adjustment.md](references/broad-grid-path-adjustment.md) for GridDeformer and intentional PathDeformer correction.
- Read [direct-part-detail-adjustment.md](references/direct-part-detail-adjustment.md) before binding a Part directly.
- Read [face-body-clothing-corrections.md](references/face-body-clothing-corrections.md) for region-specific diagnosis.
- Read [state-verification.md](references/state-verification.md) for binding preservation, exact-key captures, and save audit.
- Read [directional-deformation-audit.md](references/directional-deformation-audit.md) when explaining or validating what a two-axis parameter changes at its four cardinal keys and four corners.
- Read [parent-residual-recalculation.md](references/parent-residual-recalculation.md) whenever a parent GridDeformer, DepthBone, Pelvis, Spine, or Body binding has changed beneath existing child corrections.
- Read [head-position-correction.md](references/head-position-correction.md) when the visible defect is head placement, head-to-neck attachment, an overly long/short neck appearance, or a head displacement at Body yaw/pitch keys.
- Finish with [step-checklist.yaml](references/step-checklist.yaml) in item order.
- Run [result-audit-checklist.yaml](references/result-audit-checklist.yaml) with the shared result audit/repair loop before declaring the parameter pass complete.

Also follow `nijigenerate-shared-rigging-rules`. Use `nijigenerate-front-back-clothing-rigging` first when clothing still lacks a correct broad front/back hierarchy or broad binding.

## Required order

1. Resolve `njc`, inspect current schemas, and read the generated parameters, keypoints, targets, and bindings.
2. Verify `nijigenerate-depth-skeleton-setup` and `nijigenerate-depth-import-adjustment` are complete, Fit Z is verified, and standard Depth parameters were generated afterward.
3. Capture neutral and every relevant exact parameter key before mutation.
4. Classify each defect as depth, skeleton/BoneSource, broad Grid/Path motion, direct Part detail, occlusion, or physics.
5. Return depth defects to `nijigenerate-depth-import-adjustment` and skeleton/BoneSource defects to `nijigenerate-depth-skeleton-setup`.
6. For head-position defects, use the dedicated head-position procedure: inspect `DepthBone::Neck` bindings and `Head::Root` residual translations together, then edit only the smallest responsible layer.
7. Correct a demonstrated broad-motion defect at its owning depth/bone or permitted Grid/Path layer. If broad motion is already valid, proceed directly to Part residuals. A Grid XY prohibition remains binding; do not make a parent edit merely to satisfy the order.
8. If a parent contribution changed, recompute every affected child residual from the desired final pose minus the current parent contribution. Audit all 25 cells of each 5x5 parameter before relying on interpolation.
9. Recheck the failing key and adjacent keys. Continue only when broad motion, anchors, and attachments are correct.
10. Correct the smallest remaining local artifact on the explicit Part mesh, tapering the delta through neighboring vertices and preserving neutral.
11. For every adjusted two-axis parameter, prove the deformation at the four cardinal keys and four corners using the directional deformation audit; a pose-only contact sheet is insufficient.
12. Verify Face, Body, head/neck attachment, limbs, clothing, hair, masks, and dependent parameters at endpoints, corners, and adjacent intermediate keys.
13. Run the result audit read-only, repair every `RETAKE` at its owning broad/Part/bone stage, and rerun all result items from item 1 until every applicable current-stage item is `OK`.
14. Restore neutral, prove depth/skeleton and unrelated bindings are unchanged, compare serialized/file size with the pre-pass audit, and save through `FileCommand_SaveFile`.

## Boundaries

- Never redefine depth arrays, layer depth scale/offset, node Z, Fit Z, standard DepthBones, or BoneSources here. The head-position exception is limited to the existing `DepthBone::Neck` Body binding and `Head::Root` residual described in [head-position-correction.md](references/head-position-correction.md); change zSort only when the screenshot proves a draw-order defect.
- Never rerun standard Depth parameter generation after manual correction unless the user explicitly accepts replacing the corrections.
- Never create all yaw/pitch keys from fixed angles, magic projection constants, or an independent projection script.
- Do not use Part residuals to conceal an unresolved depth or bone-motion defect. Preserve valid parent motion; angle-specific silhouette/visibility changes can belong to individual Parts.
- Do not edit `.inx` directly, use Computer Use, start a reviewer SPA, or call `FileCommand_OpenFile` unless explicitly requested.
- Stop if the current binding cannot be read back, neutral changes unexpectedly, or the defect class is uncertain.
- Do not “fix” a child against stale parent motion. Parent changes invalidate previously authored child residual values at every affected key.

## Task-specific procedures

- Read [individual-2p5d-and-reference.md](references/individual-2p5d-and-reference.md) for angle references, jaw/cheek/torso side surfaces and part-level occlusion.
- Read [one-sided-welding.md](references/one-sided-welding.md) for shoulder/torso seams or unwanted armpit attachment.
- Read [collar-and-neck-surfaces.md](references/collar-and-neck-surfaces.md) for standing collars versus chest lapels.

For these operations, also complete [references/change-result-checklist.yaml](references/change-result-checklist.yaml). Apply conditional items only to the requested scope.

For visual interpretation of individual Part contours, shoulder/armpit Welding and collar defects, read [Ao visual examples](references/ao-visual-examples.md) alongside the relevant procedure; the images are not numeric templates.

For a request to generate directional references and match the model to them, follow [angle-reference-depth-part-workflow.md](../nijigenerate-shared-rigging-rules/references/angle-reference-depth-part-workflow.md): validate reference poses, fit broad depth first, then individual Part residuals, and compare every requested direction against the same references.

For the actual generated face/body references by direction, see the [directional reference gallery](references/ao-directional-reference-gallery.md), including original renders, comparison versions and generation prompts.
