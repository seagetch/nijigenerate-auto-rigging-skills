---
name: nijigenerate-automatic-rigging
description: Run complete nijigenerate 自動リグ/auto-rigging through njc in fixed order, orchestrating setup, meshes, DepthBones, depth, Fit Z, post-rig, face, and physics specialists.
---

# Nijigenerate Automatic Rigging

This is the canonical entry point for automatic rigging. Do not substitute the
old onboarding order or merge it with another generic rigging sequence.

First read
`../nijigenerate-shared-rigging-rules/references/workflow-router.md` and record
the complete route manifest. The router is the authoritative index of every
nijigenerate specialist; this skill owns order and handoff, not specialist
implementation.

Read [references/session-procedure.md](references/session-procedure.md)
completely before the first mutation. Finish
[references/step-checklist.yaml](references/step-checklist.yaml) in item order.
After all phases, run
[references/result-audit-checklist.yaml](references/result-audit-checklist.yaml)
with the shared result audit/repair loop.
Also follow `nijigenerate-shared-rigging-rules`.

Every specialist phase must finish its own
`references/result-audit-checklist.yaml` through the shared result audit/repair
loop. Do not advance on command completion alone. Advance only when every local
applicable current-stage result item is `OK` and its evidence has been recorded. Carry later-stage work with an explicit owner under the shared checkpoint procedure.

## Fixed phase order

1. Audit the loaded model, artwork, parameters, bindings, and preservation state.
2. Complete model hierarchy, rigging-ready mouth/eye composition, GridDeformers,
   and meshes.
3. Create the initial semantic parameters needed before depth rigging.
4. Create `DepthRigRoot`, generate the standard 19 DepthBones, align their
   app-visible coordinates to the artwork, and assign all BoneSources.
5. Import the supplied depth image, repair missing alpha-depth, and tune every
   GridDeformer until its anatomical depth is plausible.
6. Run and verify Fit Z to Depth.
7. Generate the standard Depth parameters only after Fit Z.
8. Refine generated Body motion: correct Pelvis/Spine/leg DepthBones and
   BoneSources as needed, then individual Part residuals. Change parent Grid XY only when permitted and diagnosed as the owning defect.
   Respect LockToRoot feet and audit all directions and intermediate keys.
9. Inspect generated Face parent motion and preserve it when correct; refine only the permitted owning layer. Posterior-head continuity is mandatory: follow the [ordinary/long-hair/hairless cases](../nijigenerate-depth-import-adjustment/references/head-volume-and-hair-cases.md). For long hair, review every linked Ao case and record applicability; do not reduce this to Face-only checks. Then run the
   dedicated eye-blink and mouth-open specialists. During the Face pass, rig
   tongue and teeth to `Face::Yaw-Pitch` for mouth-cavity depth while preserving
   `Mouth::Open`.
10. Add SimplePhysics only after authored deformation is stable.
11. Run the full global audit, restore neutral/reset physics, and save a verified
    output.

Do not reorder phases 4–7. Do not generate standard Depth parameters before the
final verified Fit Z. Do not use physics to repair pose deformation.

## Specialist routing

- Complete routing table and phase gates:
  `nijigenerate-shared-rigging-rules/references/workflow-router.md`
- Reference-guided artwork/PSD part creation or repair, only when requested:
  `reference-guided-rig-parts` (separately installed asset-preparation skill).
  Preserve the editable master; do not automatically bake masks, split sides,
  upscale, or re-import the active model.
- Structure, DynamicComposite, initial parameters:
  `nijigenerate-model-setup`
- Grid and Part meshes: `nijigenerate-automesh-setup`
- Anatomical appendage root movement:
  `nijigenerate-limb-root-positioning`
- Clothing front/back structure before depth:
  `nijigenerate-front-back-clothing-rigging`
- DepthRigRoot, DepthBones, LockToRoot feet, BoneSources:
  `nijigenerate-depth-skeleton-setup`
- Depth import, gap repair, anatomical relief, effective Z, Fit Z, standard
  parameters: `nijigenerate-depth-import-adjustment`
- Generated Grid/Part/DepthBone parameter refinement:
  `nijigenerate-post-rig-adjustment`
- Mouth asset structure and Part meshes are prerequisites owned by
  `nijigenerate-mouth-asset-rigging` and `nijigenerate-automesh-setup`;
  `Mouth::Open` remains owned by `nijigenerate-mouth-open-rigging`. The
  mouth-cavity response to `Face::Yaw-Pitch` is part of this automatic Face
  rigging pass, not a later mouth-only correction.
- Eye blink and closed-eye expressions after broad Face motion is stable:
  `nijigenerate-eye-blink-rigging`
- Mouth opening, closure, expression, tilted local axis, and intermediate keys:
  `nijigenerate-mouth-open-rigging`
- True remaining penetration only:
  `nijigenerate-occlusion-mask-rigging`
- Secondary motion last:
  `nijigenerate-simple-physics-rigging`
- Checklist OK/Retake processing:
  `nijigenerate-checklist-review-loop`
- One Operation review UI, only when explicitly requested:
  `nijigenerate-work-review-tool`

Read each routed skill and its required references immediately before that phase.
If any routed specialist is absent from the runtime skill catalog or unreadable,
stop before mutating that phase. Never substitute this orchestrator or
`nijigenerate-model-setup` for the missing specialist.

## Hard boundaries

- Resolve `njc` from an explicit path, `NJC_PATH`, or `PATH`; mutate only through
  it.
- Never edit `.inx` directly or use Computer Use.
- Do not call `FileCommand_OpenFile` unless explicitly requested.
- Do not start a reviewer/browser/SPA unless explicitly requested.
- Re-read state after every error-looking response before retrying.
- Judge command success from the returned tool status and nested `succeeded`
  fields, not from shell exit code alone. Never silently end a batch after one
  rejected payload; read back state, correct the payload, and continue.
- Stop on unrelated parameter, binding, hierarchy, Physics, or file-size change.
- Do not save repeated full-size revisions without a verified phase improvement.

## Task-specific procedures

- For phase-local checks, deferred later work and separate visual/save decisions, read [scope-and-checkpoints.md](../nijigenerate-shared-rigging-rules/references/scope-and-checkpoints.md).

For these operations, also complete [references/change-result-checklist.yaml](references/change-result-checklist.yaml). Apply conditional items only to the requested scope.
