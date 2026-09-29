---
name: nijigenerate-mouth-open-rigging
description: Rig or repair nijigenerate Mouth::Open through njc with oblique-axis closure, displeased/neutral/smile expressions, near/far asymmetry, clipping, lip thickness, and intermediate keys.
---

# Nijigenerate Mouth Open Rigging

Use this skill with `nijigenerate-shared-rigging-rules`. Mutate the loaded model only through a resolved `njc`; never edit `.inx` directly and never use `FileCommand_OpenFile` unless the user has explicitly authorized that file-open operation in the active task and has not revoked it.

This skill starts after a rig-ready mouth structure exists. If `Base`, `Tongue`, `Teeth::Lower`, `Teeth::Upper`, `Outline`, or their DynamicComposite structure is missing, use `nijigenerate-mouth-asset-rigging` first. Do not create parameter bindings during an asset/structure-only request.

Read before applying:

- `references/mouth-motion-and-perspective.md` for oblique mouth-axis construction, closure, expression, perspective, and failure patterns.
- `references/reference-images.md` when interpreting the bundled examples or preparing model-specific references.
- `references/step-checklist.yaml` for the complete workflow.
- `references/result-audit-checklist.yaml` before saving or describing a pass as complete.

Start a reviewer SPA only when the user explicitly requests one. Rendered images are primary evidence; numeric and JSON readbacks are supplemental. Treat human visual acceptance as the final decision.

## Core Rules

1. Separate asset construction from parameter rigging. Never add `Mouth::Open` bindings before the user requests mouth rigging.
2. Read the active parameter semantics before mutation. For the convention addressed here, X is `0=open` to `1=closed`, and Y is `0=displeased`, `0.5=neutral`, `1=smile`.
3. Bind `Base`, `Tongue`, `Teeth::Lower`, `Teeth::Upper`, and `Outline` separately. Do not close the mouth by flattening only the parent DynamicComposite.
4. Treat closure as upper and lower contours meeting. Move the upper contour more than the lower contour by default, while preserving a non-zero closed-lip band.
5. Derive the closure axis from the rendered mouth and face. Never use screen horizontal or local `Y=0` merely because it is convenient.
6. Determine local coordinate signs, character/screen side, and near/far side from current visual evidence. Do not hardcode them from another model.
7. Apply displeased and smile curvature relative to the model-specific oblique mouth axis, not relative to the screen.
8. Preserve mouth width unless a reviewed reference requires a change. Closing must not make the mouth wider.
9. Author and inspect intermediate keys. Endpoint interpolation alone is not evidence of a usable rig.
10. Verify every required state at an exact key using current screenshots before saving.

## Required Workflow

1. Capture the current authored mouth at its exact default parameter value and save a face-scale image plus a close crop.
2. Read the parameter UUID, axis ranges, key values, defaults, target Part UUIDs, meshes, transforms, drawing modes, hierarchy, and existing bindings through `njc`.
3. Record the face roll, mouth-corner axis, local-to-screen Y direction, screen side, and near/far side from the rendered image.
4. Define a model-specific oblique closure axis through the mouth corners and center. Keep this axis stable across X.
5. Author neutral full closure first. Make Outline close from above and below, make Base follow, and compress or conceal teeth and tongue without leaks.
6. Author Y expressions relative to the oblique axis. At Y=0 both corners descend; at Y=1 both corners rise. Apply independently calibrated near/far strengths.
7. Author all required X/Y combinations. A recommended grid is X `0, 0.25, 0.5, 0.75, 1` and Y `0, 0.5, 1`, yielding 15 keys per target.
8. Capture at minimum the 3x3 grid X `0, 0.5, 1` by Y `0, 0.5, 1`, plus every authored intermediate needed to diagnose motion.
9. Compare original-scale face views and equal-scale close crops. Check axis continuity, corner direction, width, lip thickness, internal leakage, and near/far perspective.
10. Run the complete step checklist and result audit. Stop before saving on any unrelated model-state change.
11. Save only after human visual acceptance, using `FileCommand_SaveFile` without opening another model.

## Prohibited Shortcuts

- Do not scale every mouth vertex vertically toward zero.
- Do not converge closure toward a horizontal line on a tilted or three-quarter face.
- Do not infer that positive local Y means screen-up or screen-down.
- Do not invert Y=0 and Y=1 because of an unverified coordinate sign.
- Do not weaken displeased curvature until full closure becomes nearly neutral.
- Do not collapse closed lips into a zero-thickness or broken line.
- Do not mirror identical expression amplitudes onto near and far corners.
- Do not validate from binding counts, bounds, or JSON alone.
- Do not compare entire dynamic `find("*")` payloads as hierarchy signatures; compare static UUID, type, name, and parent relationships.
- Do not save an unaccepted candidate as the completed model.

## Handoff

Report the parameter UUID and semantics, five target UUIDs, exact key grid, oblique-axis and near/far mapping, screenshots, binding `isSet` results, unrelated-state diff, unresolved visual defects, save path/status, and confirmation that `FileCommand_OpenFile` was avoided.
