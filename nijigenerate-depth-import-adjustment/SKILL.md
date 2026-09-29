---
name: nijigenerate-depth-import-adjustment
description: Import and correct nijigenerate depth maps through njc, including PSD mapping, alpha-depth gap fill, anatomical relief, effective Z, Fit Z, and standard Depth parameters.
---

# Nijigenerate Depth Import Adjustment

Treat this skill as the canonical source for nijigenerate depth information. Other rigging skills consume the depth state established here; they must not redefine it.

## Read references by task

- Always read [operation-runbook.md](references/operation-runbook.md) before operating `njc`.
- For source-image validation and artwork-to-grid correspondence, read [artwork-grid-mapping.md](references/artwork-grid-mapping.md).
- For Face, mouth, hair, headwear, earwear, and neck depth, read [face-hair-depth.md](references/face-hair-depth.md).
- For Body, Chest, waist, pelvis, and lower-body depth, read [body-chest-lower-depth.md](references/body-chest-lower-depth.md).
- For front/back/side clothing depth, read [clothing-depth.md](references/clothing-depth.md).
- For mutation safety, effective-Z diagnosis, numeric readback, and screenshots, read [depth-state-verification.md](references/depth-state-verification.md).
- Before Fit Z or any command that refreshes DepthBone/Grid bindings, read the shared [parameter-state-isolation.md](../nijigenerate-shared-rigging-rules/references/parameter-state-isolation.md).
- Consult [model-specific-examples.md](references/model-specific-examples.md) only as diagnostic examples; never copy its values blindly.
- Finish with [step-checklist.yaml](references/step-checklist.yaml).
- Run [result-audit-checklist.yaml](references/result-audit-checklist.yaml) with the shared result audit/repair loop. Do not hand generated bindings to post-rig adjustment until every result item is `OK`.

Also follow `nijigenerate-shared-rigging-rules`. Use `nijigenerate-depth-skeleton-setup` only for DepthRigRoot, DepthBone placement, LockToRoot feet, and BoneSources.

## Required order

1. Resolve `njc`, inspect current schemas, and capture the live numeric/visual baseline.
2. Validate the source depth image and map visible artwork to actual target grids.
3. Open and inspect the PSD-depth dialog without applying it.
4. Repair alpha-covered missing depth and tune per-layer depth scale/offset.
5. Apply only after every enabled target passes the import audit.
6. Correct local GridDeformer depth using current overlays and explicit numeric arrays.
7. Verify effective Z relationships at neutral and exact yaw/pitch keys.
8. Isolate the intended armed Depth parameter, snapshot every parameter target set and Physics binding, then run Fit Z to Depth after the final grid correction.
9. Generate standard Depth parameters only after Fit Z is numerically verified.
10. Run the result audit read-only, repair each `RETAKE` in its owning depth substage, and rerun the complete result checklist from item 1 until all applicable current-stage items are `OK`.
11. Restore neutral, audit unrelated state, and save through `FileCommand_SaveFile`.
12. Hand off generated bindings to `nijigenerate-post-rig-adjustment`; do not replace them with a custom projection pass.

## Boundaries

- Resolve `njc` from an explicit path, `NJC_PATH`, or `PATH`; never assume `./out/njc`.
- Perform every model read, mutation, screenshot, and save through `njc`.
- Never edit `.inx` contents directly and never use Computer Use.
- Do not start a reviewer SPA for this workflow.
- Do not call `FileCommand_OpenFile` unless the user explicitly asks to load a file.
- Save to a new explicit path unless overwrite is explicitly requested.
- Stop on unusable source images, unknown feature-to-grid mapping, stalled gap repair, unverified Fit Z, a Physics parameter being armed for a depth refresh, unrelated state changes, or unexplained serialized/file-size growth.

## Task-specific procedures

- When judging torso/shoulder/arm/sleeve volume, read [body-chest-lower-depth.md](references/body-chest-lower-depth.md); depth establishes the base shape and individual Part occlusion remains a separate post-rig task.

For these operations, also complete [references/change-result-checklist.yaml](references/change-result-checklist.yaml). Apply conditional items only to the requested scope.

For the relevant visual or recorded-data examples and their evidence limits, use the [example index](../nijigenerate-shared-rigging-rules/references/visual-example-index.md); procedural references link directly to their owned examples.

For a request to generate directional references and match the model to them, follow [angle-reference-depth-part-workflow.md](../nijigenerate-shared-rigging-rules/references/angle-reference-depth-part-workflow.md): validate reference poses, fit broad depth first, then individual Part residuals, and compare every requested direction against the same references.
