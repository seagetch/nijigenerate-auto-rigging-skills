---
name: nijigenerate-eye-blink-rigging
description: Rig or repair nijigenerate eye blinking and closed-eye expressions through a resolved njc executable using mandatory face/eye-local coordinate frames. Use when upper-lid motion, eyelash width or thickness, canthus continuity, eye-white vertical closure, static zSort and ClipToLower visibility, neutral/smile/deep expression rows, or near/far asymmetric eyes need correction without deforming the iris.
---

# Nijigenerate Eye Blink Rigging

Use this skill with `nijigenerate-shared-rigging-rules`. Mutate the loaded model only through a resolved `njc`; never edit `.inx` directly and never use `FileCommand_OpenFile` unless the user has explicitly authorized that file-open operation in the active task and has not revoked it.

Read before applying:

- `references/eyelid-motion-and-bezier.md` for contour classification, perspective handling, movement constraints, endpoint neighborhoods, and curve construction.
- `references/eye-part-visibility-and-retake.md` for eye-white/Iris policy, static zSort, default-state regression, crop validation, and delta-only Retake.
- `references/reference-images.md` when interpreting or creating visual references.
- `references/step-checklist.yaml` for the complete workflow.
- `references/result-audit-checklist.yaml` before saving or describing a pass as complete.

Use `scripts/apply_blink_plan.py` for validated dry-run/delta-only application and `scripts/audit_blink_bindings.py` for read-only Iris, Eyewhite, and static-property checks. Do not replace artwork-specific contour planning with a generic generator.

Start a reviewer SPA only when the user explicitly requests one. Treat human visual acceptance as the final decision; Codex may identify defects but must not declare its own candidate accepted.

## Core Rules

1. Separate closure-line height from expression curvature.
2. Make upper-lid descent the dominant closing motion. Allow only a small lower-lid rise unless a reviewed reference proves otherwise. Verify closure-line descent separately from final curvature using the reference-motion gate in `references/eyelid-motion-and-bezier.md`; an endpoint-preservation or visibility pass cannot override a failed motion budget.
3. Classify actual upper and lower contours from topology and rendered evidence; do not use texture-UV Y alone.
4. Treat each eye independently. Build its authored open canthus tangent in current rendered/deformed parent space; record character side, screen side, near/far status, face roll, width, aperture, and occlusion.
5. Preserve closed width, the painted upper-lash thickness, the outer wedge, the inner taper, both canthus positions, and their neighboring tangents.
6. Deform the eye white vertically to follow the lash closure band. Keep every eye-white X deformation at zero and do not add Blink opacity.
7. Do not deform the Iris and do not add Iris Blink deform, opacity, or zSort bindings. Preserve the Iris geometry and hide it during closure through the existing clipping relationship and verified static Part zSort.
8. Apply static zSort without parameter context. Verify the Eyelash, Iris, and Eyewhite order at open, intermediate, and closed poses.
9. Verify the entire Blink-X sequence for every expression-axis row, not only neutral intermediates and expression endpoints.
10. Repair only the failed target/property. Do not regenerate accepted eye bindings while fixing zSort, one canthus, or one expression row.

## Non-Negotiable Coordinate-Frame Gate

Complete this gate separately for each eye before planning or mutating any Blink key:

1. Record character side, screen side, near/far status, current head/face yaw-pitch-roll, and measurement space.
2. Select reviewed authored open inner and outer canthus landmarks in the same current rendered/deformed parent space.
3. Define `O=A_open`, `T_open=normalize(B_open-A_open)`, and lower-lid-positive `N_open=perpendicular(T_open)`.
4. Convert every contour sample and planned endpoint to `u=dot(P-O,T_open)`, `v=dot(P-O,N_open)`.
5. Preserve both reviewed canthus positions and `T_open` through every Blink key by default.
6. Cross-check `T_open` against rendered inter-eye/face roll. A screen-horizontal, slope-reversed, or roll-contradicting closed line is `RETAKE`.

Raw screen-Y comparison is prohibited. “The inner endpoint is higher/lower than the outer endpoint” is invalid unless it includes both endpoints' local `v` values.

Changing the seam tangent away from `T_open` is allowed only when a same-roll authored reference requires it and the human accepts an axis overlay. Without that exception, every intermediate and full-close key must preserve `T_open` within serialization tolerance.

## Required Workflow

1. Read both Blink parameters and record UUIDs, axes, exact key values, defaults, and expression meanings.
2. At the exact defaults, capture a face-scale baseline and snapshot eye Part properties, Blink binding resources, and static zSort values.
3. Obtain neutral, smile, and deep-closed references at the same head pose, camera, crop, and apparent scale.
4. Read the eye Parts, transforms, meshes, UVs, draw modes, clipping relationships, hierarchy, static opacity/zSort, and existing Blink bindings through `njc`.
5. Identify upper contour, lower contour, reviewed authored open inner/outer canthi, the painted opaque lash band, and canthus-adjacent vertices for each eye.
6. Run the coordinate-frame gate, record local `u/v`, and determine near/far perspective from artwork rather than node names.
7. Plan each expression independently: closure drop, curvature, width, lash thickness, fixed canthus endpoints, endpoint-neighborhood easing, and eye-white Y targets. Produce a dry-run plan before mutation.
8. Author full-close lash targets first. Keep canthi invariant by default and ease curvature away from both endpoint neighborhoods so adjacent vertices do not create apparent drift.
9. Author eye-white Y-only deformation into a thin nonzero band following the lash seam. Leave Iris unbound. Apply only model-specific static zSort values that pass the full visibility matrix.
10. Author explicit intermediate Blink keys for every expression row when endpoint interpolation does not preserve contour, thickness, or visibility.
11. Capture every Blink-X key for every expression row at one verified face/eye scale with each eye's `T_open/N_open` overlaid. Reject a crop that does not visibly contain both eyes at inspection resolution.
12. Reset both eyes to their exact defaults and compare the post-mutation open state with the baseline before any Retake or save.
13. Run the step checklist and full result audit. For a Retake, change only failed targets and rerun the entire result checklist. Save only after the user accepts the visual result.

## Parameter Semantics

Read the active parameter; never assume a convention. Common examples include:

- X `0=open`, intermediate keys, `1=closed`; or an authored default near `0.2`.
- Expression Y `[-1, 0, 1]` for deep/neutral/smile.
- Expression Y `[0, 0.5, 1]` for deep/neutral/smile.

Record the actual convention and capture every real expression row. Do not silently remap one convention to another.

## Prohibited Shortcuts

- Do not scale the whole eye mesh vertically into a line.
- Do not move every eyelash vertex to one Bézier centerline using only normalized UV coordinates.
- Do not obtain a smile arch by moving the entire closure line toward the open upper lid.
- Do not let lower-lid travel dominate merely because the final silhouette looks closed.
- Do not mirror normalized control ratios between near and far eyes.
- Do not deform, hide with opacity, or parameter-bind zSort on the Iris.
- Do not hide the eye white with Blink opacity or change its horizontal geometry.
- Do not reuse a stale absolute screenshot crop after camera or model-view changes.
- Do not rerun the full rig generator for a local Retake without proving every accepted binding is byte-equivalent afterward.
- Do not compare inner/outer endpoint height using raw screen Y.
- Do not copy a screen-space contour slope into the closed seam or accept a screen-horizontal/slope-reversed line on a rolled face.
- Do not change `T_open` without a same-roll authored reference and human-approved axis overlay.
- Do not mark a slope/height checklist item OK without eye-local `O/T_open/N_open`, landmark identities, and endpoint `u/v`.
- Do not validate from JSON alone; exact-key screenshots and rendered canthus/thickness inspection are mandatory.
- Do not save an unaccepted candidate as the completed model.

## Handoff

Report the edited parameter UUIDs, eyelash/white/iris UUIDs, exact key values, near/far mapping, movement and thickness measurements, canthus-neighborhood checks, static zSort readback, screenshot matrix, unrelated-state diff, unresolved defects, save status, and whether `FileCommand_OpenFile` was avoided.

## Task-specific procedures

- For a requested height change, distinguish whole-eye placement from seam height and expression curvature using [eyelid-motion-and-bezier.md](references/eyelid-motion-and-bezier.md).

For these operations, also complete [references/change-result-checklist.yaml](references/change-result-checklist.yaml). Apply conditional items only to the requested scope.
