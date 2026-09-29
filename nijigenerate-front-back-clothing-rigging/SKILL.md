---
name: nijigenerate-front-back-clothing-rigging
description: Prepare nijigenerate front/back/side clothing GridDeformers, hierarchy, surface inheritance, anchors, and AutoMesh timing through njc before depth import.
---

# Nijigenerate Front Back Clothing Rigging

Use this skill for clothing hierarchy and broad-grid responsibility before depth import. Do not generate parameter bindings here.

## Required references

- Read [references/front-back-clothing-method.md](references/front-back-clothing-method.md) for hierarchy, surface classification, anchors, and broad verification.
- Use [references/step-checklist.yaml](references/step-checklist.yaml) for the final rigging audit.
- Run [references/result-audit-checklist.yaml](references/result-audit-checklist.yaml) with the shared result audit/repair loop. Do not hand off to depth import until every applicable current-stage item is `OK`.
- Also follow `nijigenerate-shared-rigging-rules`.

## Workflow

1. Resolve `njc` and inspect the current clothing hierarchy, grids, transforms, meshes, and bindings.
2. Classify every front, rear, side, hood, skirt, hem, and local surface and record whether it inherits Body motion.
3. Split front/back grids when their projection or hierarchy responsibilities differ.
4. AutoMesh only after the final child set is known, then re-read grid axes.
5. Verify neutral anchors, front/back separation, side wraps, hems, and which grids require inherited versus independent motion.
6. Run the result audit read-only, repair every `RETAKE`, and rerun the complete checklist until all applicable current-stage items are `OK`.
7. Save the prepared structure, then run `nijigenerate-depth-import-adjustment`.
8. After Fit Z and standard parameter generation, hand off all broad clothing binding and Part detail to `nijigenerate-post-rig-adjustment`.

## Boundaries

- Do not redefine front, back, side, hood, skirt, or hem depth in this skill.
- Do not generate custom yaw/pitch keys, broad parameter bindings, or direct Part detail bindings in this skill.
- Do not infer inheritance from visual proximity.
- Do not use zSort or 2D widening as a depth substitute.
- Preserve unrelated Body, Face, limb, mask, and physics state.

## Task-specific procedures

- For already-rigged pelvis/skirt following use the [bone procedure](../nijigenerate-depth-skeleton-setup/references/pelvis-skirt-follow.md); do not restart pre-import structure merely to repair a link.

For these operations, also complete [references/change-result-checklist.yaml](references/change-result-checklist.yaml). Apply conditional items only to the requested scope.
