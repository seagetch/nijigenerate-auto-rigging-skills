---
name: nijigenerate-depth-skeleton-setup
description: Create or repair nijigenerate DepthRigRoot, 19 standard DepthBones, artwork alignment, LockToRoot feet, and GridDeformer BoneSources through njc.
---

# Nijigenerate Depth Skeleton Setup

Before any operation, use `nijigenerate-shared-rigging-rules` and read
`../nijigenerate-shared-rigging-rules/references/workflow-router.md`. Confirm
this is the routed DepthBone/BoneSource phase, that model setup prerequisites
are accepted. The pre-import requirement applies to initial skeleton creation; repairing existing generated motion uses the current accepted depth without re-importing it. Record the route
manifest and preserve every accepted prerequisite as read-only state.

Resolve the `njc` executable from an explicit path, `NJC_PATH`, or the process `PATH`, in that order. Do not assume a repository-relative location. Use the resolved executable for every model mutation. Never edit `.inx` contents directly, never use `FileCommand_OpenFile` during an active rigging pass, and never use Computer Use for model operations.

Read [references/operation-runbook.md](references/operation-runbook.md) completely before changing a model. Read [references/pose-compensation.md](references/pose-compensation.md) when tuning generated Body yaw/pitch bone motion, Pelvis/Spine distribution, knees, or LockToRoot feet. Use [references/step-checklist.yaml](references/step-checklist.yaml) for the operation audit. Run [references/result-audit-checklist.yaml](references/result-audit-checklist.yaml) with the shared result audit/repair loop before handoff.

## Initial creation order

For an existing-rig repair, retain steps 1–3 as inspection, then use the task-specific references below. Do not run root/standard-bone creation steps on an established skeleton.

1. Resolve `njc`, run `njc tools list`, and confirm the current command schemas.
2. Read the live tree, resources, flip pairs, current DepthRig bindings, and all GridDeformer BoneSources.
3. Capture the current neutral view and save a pre-mutation audit.
4. Create `DepthRigRoot` under the intended body root.
5. Confirm the new root is empty, then run `DepthBoneCommand_AddStandardDepthSkeleton`.
6. Read back all 19 standard DepthBones and verify their names, hierarchy, rest data, nonzero lengths, flip pairs, and `Foot.L`/`Foot.R` `lockToRoot=true`.
7. Capture the current character image, mark anatomical landmarks, declare the `.L`/`.R` screen-side convention, and publish a `NOT APPLIED` position map.
8. Set `restHead`, `restTail`, and `restRoll` through `DepthBoneCommand_SetDepthBoneRest`.
9. Set each bone's visible transform through njc. Branch on `lockToRoot`; never treat locked feet as ordinary children.
10. Re-read app-visible transforms and compare them with the image landmarks. Do not validate from rest coordinates alone.
11. Build a complete BoneSource map for every GridDeformer before adding any source.
12. Apply the map with `scripts/apply_bone_sources.py`; it supports safe prefix/exact resume after an interrupted pass.
13. Re-read every source list, inline source settings, hierarchy, hashes, flip pairs, and neutral rendering.
14. When generated Body motion needs bone-level correction, apply `references/pose-compensation.md`; verify Pelvis/Spine distribution and knee stability against the locked ankle targets.
15. Run the result audit read-only, repair every `RETAKE` in this skill, and rerun the complete result checklist until all applicable current-stage items are `OK`.
16. Save to the user-requested destination with `FileCommand_SaveFile`.
17. Present the Japanese checklist in item order with `NOT APPLIED` and `APPLIED / VERIFIED` evidence.

## Scope boundary

This skill creates the depth structure, positions its bones, and registers BoneSources. It does not define GridDeformer depth or create standard depth parameters. Use `nijigenerate-depth-import-adjustment` for canonical depth definition, Fit Z to Depth, and standard parameter generation; use `nijigenerate-post-rig-adjustment` afterward for broad Grid/Path correction followed by direct Part detail.

## Hard stops

- Stop if an existing DepthRigRoot or DepthBone set is not an exact known resumable state.
- Stop if a target's existing BoneSource UUIDs are not an ordered prefix of the requested list.
- Stop if the side convention is not explicit.
- Stop if a `LockToRoot` bone's coordinate frame has not been resolved.
- Stop if any unrelated node, hierarchy edge, flip pair, or neutral render changes.

## Included helper

Use `scripts/apply_bone_sources.py` with a JSON map:

```powershell
python scripts/apply_bone_sources.py `
  --mapping bone-source-map.json `
  --save C:\path\to\model-v2.inx `
  --audit C:\path\to\bone-source-audit.json
```

Set `NJC_PATH`, place `njc` on `PATH`, or pass `--njc <resolved-path>`. Run with `--dry-run` first. Add `--overwrite` when the requested save destination already exists. The helper never opens or edits an INX directly; it mutates the active model only through njc and saves only through `FileCommand_SaveFile`.

## Task-specific procedures

- For existing-rig repairs, inspect and preserve the existing skeleton rather than recreating the initial 19 bones. Read [independent-appendage-follow.md](references/independent-appendage-follow.md) for head/body split hair or asymmetric arm following. For long hair, also read [long-hair-follow.md](references/long-hair-follow.md) and review every linked Ao case for applicability, including side/back separation, braids and Roll.
- For arms that follow forward bending but hang during backward bending, read [arm-backward-hang.md](references/arm-backward-hang.md). Preserve the forward range through explicit neutral-boundary handling and distinguish shoulder-relative pose from absolute position.
- Read [pelvis-skirt-follow.md](references/pelvis-skirt-follow.md) for front/back skirt bones and pelvis following. Trace actual Body yaw to the skirt origin rather than assuming a Pelvis parent supplies it; the procedure links a recorded Ao binding and comparison example. Use [pose-compensation.md](references/pose-compensation.md) for knee and ankle constraints.

For these operations, also complete [references/change-result-checklist.yaml](references/change-result-checklist.yaml). Apply conditional items only to the requested scope.
