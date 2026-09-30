---
name: nijigenerate-shared-rigging-rules
description: Shared safety, declared local-coordinate frames, state, verification, image-display, side-convention, keyframe, and audit rules for all nijigenerate rigging skills that mutate models through a resolved njc executable.
---

# Nijigenerate Shared Rigging Rules

Use this with any nijigenerate skill that changes model structure, meshes, parameters, bindings, masks, or screenshots.

For the exhaustive shared pre-apply, post-apply, review, and audit checklist, read `references/step-checklist.yaml`.
Before any command that can trigger automatic DepthBone/Grid refresh, read `references/parameter-state-isolation.md`.
When a specialist skill provides `references/result-audit-checklist.yaml`, run it with `references/result-audit-repair-loop.md` before handoff or final save.

## Mutation Safety

- Resolve `njc` from an explicit path, `NJC_PATH`, or `PATH`, in that order. Never assume a repository-relative `./out/njc`.
- Mutate the current loaded nijigenerate app state through the resolved `njc` executable only.
- Do not edit `.inx` files directly.
- Do not use `FileCommand_OpenFile` unless the user has explicitly authorized opening/loading that file for the active task and has not revoked it.
- If `njc` returns an error such as `JSONValue is not an array`, re-read the affected resource or binding before retrying. Some commands can mutate state despite an error-looking response.

## Preserve Accepted State

- Treat user-approved coordinates, vertex/cell sets, contour paths, side conventions, and depth values as persistent working state.
- Save accepted readouts and numeric maps as both image and JSON when practical.
- Later passes must load or re-display accepted artifacts and show diffs. Do not silently replace an accepted map or restart from memory.
- If the user defines a screen-side convention such as "screen-left is the right arm/leg/cheek", record and use it for later side-specific edits until explicitly changed.

## Direction And Parameter Conventions

- Anatomical side names are from the character's point of view. `Right`, `::R`, `Arm::R`, `Leg::R`, right hand, right cheek, and similar names mean the character's right side, not screen-right.
- In a front-facing view, character-right usually appears on screen-left, and character-left usually appears on screen-right. When discussing viewport positions, explicitly say `screen-left` or `screen-right`; do not use `left/right` alone when it could mean either character side or screen side.
- For side-specific edits, record both the character-side target and its current screen-side appearance before mutation. Example: `Arm::R::Path` is character-right; in the current front view it is on screen-left.
- `Body::Yaw-Pitch` pitch convention is fixed for these nijigenerate rigging skills: `Pitch=-1` is forward pitch / 前傾, and `Pitch=+1` is backward pitch / 後傾. Do not label or process `Pitch=+1` as forward pitch.
- `Face::Yaw-Pitch` pitch convention is fixed for these nijigenerate rigging skills: `Pitch=+1` is looking up / 上向き, and `Pitch=-1` is looking down / 下向き.
- Yaw side signs must be declared from the current model or accepted review before use. Do not infer a Yaw sign from screen direction alone; map parameter sign to character-side turn and then separately map that character side to the current screen side.
- One Operation review manifests, screenshot names, tags, audit text, and checklist reasons must use these conventions. If a legacy file says `Forward Pitch +1` for Body, treat it as a labeling error and correct it before using it as evidence.

## Rendered Coordinate-Frame Gate

- Before comparing feature heights, slopes, endpoint order, or movement under a rotated or deformed parent, declare the measurement space, origin `O`, local tangent `T`, and positive anatomical normal `N`. Record the rendered homologous landmarks used to construct them.
- Treat screen X/Y as observation coordinates only. Never decide anatomical `higher/lower`, slope sign, inner/outer height, or movement direction from raw screen `x` or `y` while the face, body, parent Grid, or parent Bone is rotated.
- Convert every reviewed point `P` to the declared local frame: `u=dot(P-O,T)`, `v=dot(P-O,N)`. Use `v`, not raw screen Y, for anatomical height and drop.
- Cross-check `T` against the rendered parent-feature roll. A candidate that becomes screen-horizontal or reverses slope while its parent feature is materially rolled is a frame/reference mismatch.
- A height, slope, or direction claim that omits coordinate space, `O/T/N`, landmark identities, and local projections is `UNVERIFIABLE` and blocks mutation or completion.
- For contour work, show `T` and `N` on the pre-apply overlay. A point-only overlay cannot approve a slope or height relation.

## Overlay And Approval

- For feature, contour, or small Part residual work, show an annotated `NOT APPLIED` readout before applying.
- If the target is a contour, show the ordered vertex/cell path, not only isolated points.
- Ambiguous terms such as "under edge", "胸下", "jaw-cheek line", "side", or "wrap" must be resolved on the overlay before mutation.
- Confidence or uncertainty values must state whether each value is overlay-confirmed, inferred, mirrored, or user-corrected.

## Review And Checklist Closure

- When a task requires checklist-based review, use `nijigenerate-checklist-review-loop`: perform the initial checklist pass read-only, save Codex's evaluation to YAML, show the checklist reviewer UI, monitor the human review JSON, process Retake feedback, rerun the full checklist, and update YAML/audit until the human JSON is OK.
- Before applying a rigging change, compare the plan against every active nijigenerate skill checklist and the latest accepted or pending nijigenerate One Operation review JSON. Explicitly check for omitted targets, missing keys, unreviewed depth maps, stale screenshots, side-convention conflicts, and skipped post-apply review requirements.
- If the task uses the nijigenerate One Operation review tool, do not treat the pass as accepted until `latest-review.json` is newer than the last processed review and has `reviewResult.decision: "ok"`. If it is `retake`, use that JSON as the primary correction input and repeat the review loop.
- After applying a change, run the same checklist again against the actual edited state. Confirm that required screenshots, audits, and post-apply review assets exist before moving to the next rigging step.
- In the final or pass log, state which checklist/review artifacts were checked and call out any checklist item that could not be verified.
- Start a reviewer SPA only when the user explicitly requests it. A user prohibition always overrides a step skill's legacy reviewer requirement.

## Keyframe Safety

- Parameter starting keyframes and target Binding keyframes are different.
- Do not call `BindingCommand_UnsetKeyFrame` or `BindingCommand_ResetKeyFrame` with an empty payload.
- Never remove a neutral parameter key unless the user explicitly asks.
- For additive residuals, set bindings only on frames that need deformation. Do not create zero-valued Binding keys as placeholders.
- After binding edits, verify the parameter neutral/start key still exists and the target binding's neutral frame is unset or exactly zero as intended.

## Binding Audit

After every rigging pass, report or save an audit for edited parameters:

- target UUID/name
- binding name
- keyed frames or `isSet` matrix
- moved count
- max/min deform or TRS values
- neutral/start-key status
- unexpected targets, especially Body parameters targeting `Face::G`

For automatic refresh operations, audit every parameter, not only the intended parameter. Compare binding counts and target UUID sets before and after the operation. Stop before saving if any unrelated parameter gains a target, if a non-target binding changes, or if serialized/file size increases without an explained payload.

## Pairing And Naming

- Names are not enough for left/right pairing. Verify flip pairs with available viewport commands such as `ViewportCommand_ListFlipPairs`, `ViewportCommand_AddFlipPair`, or `ViewportCommand_AutoAddFlipPairs`.
- Keep left/right names machine-pairable: `::L`/`::R`, `_L`/`_R`, or `_l`/`_r`.

## Screenshots

- Set the exact parameter key with `ParameditCommand_SetParameterKeypoint` before capture.
- For Codex App local image failures, use `codex-app-local-image-display`: save absolute-path PNGs and display them with `functions.view_image`.

## Pass Naming

- Use stage-identifying paths such as `readout-not-applied`, `applied`, `verified`, or a concrete correction name.
- Avoid overwriting a prior accepted pass without user direction.

## Scope and checkpoint decisions

The user's active task controls the allowed method and change scope. Inspection of a parent is not permission or a requirement to edit it. Preserve existing authorization; a scope record does not introduce a new approval gate.
Read [scope-and-checkpoints.md](references/scope-and-checkpoints.md) when continuing a correction, applying a proportional change, deferring a later-stage item, recovering from refresh, or recording approval/save status. Use its evidence states with the existing result loop.
Read [references/change-result-checklist.yaml](references/change-result-checklist.yaml) for the corresponding scope, regression and handoff checks.

When a procedure needs visual interpretation or a concrete recorded example, use the [reference image/example index](references/visual-example-index.md) to open only the relevant examples. Historical failures, generated candidates and numerical audits are distinguished there; do not treat them as current-model approval.

For generated multi-angle references used to correct depth and individual Parts, read the complete [reference-to-rig procedure](references/angle-reference-depth-part-workflow.md).

## First-pass correction planning

- Before mutation, record an explicit allowlist of node × property/binding × parameter key × vertex/region, and the protected complement. A Grid XY prohibition does not forbid an authorized depth edit; a Part-specific prohibition does not become permission to compensate on a neighbor. If a user prohibits non-neutral bangs Part correction, exclude those keys from every later hair helper and audit their values separately. Do not make that example a universal ban for other users/models.
- Before evaluating face contours, and after changing overlapping content, read [face-visibility-review.md](references/face-visibility-review.md). Inspect the normal composite and, where needed, an isolated face view; do not let generated asset errors conceal cheek defects or suppress the correct visible contour. Do not prescribe hair editing unless an asset defect is demonstrated.
- Derive targets from the original artwork, anatomy and adopted directional references. User edits, when present, are protected evidence; a later manual delta is not a prerequisite for constructing a correct first proposal. An initial candidate still requires validation and retakes when necessary.

## Stable capture before comparison

- Physics reset is not physics pause. Record the actual enabled/paused state; do not infer it from a successful reset command. If state is not readable, verify repeated captures at an unchanged pose are stable and resolve the source of drift before using pixel differences.
- Finish mutation and readback before starting dependent captures. After setting a key, force evaluation, discard stale frames, and capture again; confirm the pose has settled rather than treating a fixed number of captures as proof.
- Convert overlay image coordinates using that capture's own worldCapture AABB and dimensions. Never reuse an affine from a different viewport pan/zoom. Use a common fixed export camera for visual comparisons; do not anisotropically resize evidence to make contours match.
