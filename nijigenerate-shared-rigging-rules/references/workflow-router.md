# Nijigenerate workflow router

This is the authoritative routing table for nijigenerate work. Read it before
any model mutation, even when the user names a later phase directly.

## Routing law

1. Classify the current operation and assign exactly one owning skill before
   mutation. Supporting skills may be active, but they do not take ownership
   away from the specialist.
2. For an end-to-end automatic rig, use `nijigenerate-automatic-rigging` as the
   orchestrator and follow its fixed phase order.
3. Read the owning skill's complete `SKILL.md`, its step checklist, and every
   method or result-audit reference required for the current phase.
4. Do not replace a missing specialist with `nijigenerate-model-setup`, a
   generic deformation, or an improvised procedure. If a routed skill exists
   in this table but is absent from the runtime Available Skills catalog or
   cannot be read, stop before mutation and report the exact discovery problem.
5. Record a route manifest containing the requested operation, owning skill,
   supporting skills, prerequisites, current phase, protected accepted state,
   and exit gate.
6. A command succeeding is not a phase exit. Complete the owning skill's step
   checklist and result audit, record evidence, and require every item to be
   `OK` for current-stage prerequisites before advancing. `UNVERIFIABLE` and `RETAKE` block dependent work. Carry genuinely later-stage work under [scope-and-checkpoints.md](scope-and-checkpoints.md), never as fake OK.
7. A user request naming the next operation narrows the active phase; it does
   not authorize rewriting a completed prerequisite. For example, after an
   accepted DepthBone phase, "depth" routes to
   `nijigenerate-depth-import-adjustment`; the accepted DepthBones remain
   protected unless the user explicitly asks to revise them.

## Discovery integrity

- Treat this router's complete skill map as the registration manifest.
- Before an end-to-end pass, compare every listed skill directory with the
  active user skill-discovery directory. Every source skill must have one valid
  discoverable directory or symlink, and no installed nijigenerate link may be
  broken or point to a removed skill.
- Keep frontmatter descriptions concise and front-load trigger terms so all
  skills fit the Codex initial-list budget and remain matchable after
  description shortening.
- When a skill exists in the source collection but is absent at runtime, repair
  registration first. Restart Codex if the current task's skill snapshot does
  not refresh. Do not proceed with model mutation through a generic fallback.

## Complete skill map

| Operation or trigger | Owning skill | Required ordering or boundary |
| --- | --- | --- |
| Reference-guided artwork/PSD part creation or repair | `reference-guided-rig-parts` (separately installed) | Run only when asset preparation is requested. Preserve editable masks, clipping, source coordinates and accepted parts; compatibility export is a separate requested output. Do not automatically split sides, upscale or re-import an already loaded model. |
| Complete automatic rig or end-to-end rigging | `nijigenerate-automatic-rigging` | Orchestrates every applicable phase below; never substitutes its own generic technique for a specialist. |
| Shared safety, routing, state preservation, direction conventions, screenshots, binding audit | `nijigenerate-shared-rigging-rules` | Mandatory first read for every model-mutating phase. |
| Hierarchy, helper controls, composites, initial parameter definitions and neutral keys | `nijigenerate-model-setup` | Structure before mesh. Creates parameter shells, not specialist eye, mouth, depth, physics, or post-rig deformation. |
| GridDeformer, PathDeformer, and Part AutoMesh | `nijigenerate-automesh-setup` | Run after initial membership stabilizes; existing-rig topology changes require explicit dependency migration. |
| Front/back/side clothing surface hierarchy and anchors | `nijigenerate-front-back-clothing-rigging` | Complete before depth import and standard depth parameter generation. |
| Anatomical root or pivot movement for limbs and appendages | `nijigenerate-limb-root-positioning` | Protect descendants with LockToRoot while moving the parent. |
| Missing or indivisible mouth artwork, mouth Parts, clipping, composition, Part meshes | `nijigenerate-mouth-asset-rigging` | Complete before `Mouth::Open`; use `nijigenerate-automesh-setup` for every drawable Part. |
| Mouth opening, closure, expression, tilted local mouth axis, intermediate keys | `nijigenerate-mouth-open-rigging` | Run only after mouth assets/composition/meshes are accepted. |
| Eye blink and closed-eye expression deformation | `nijigenerate-eye-blink-rigging` | Run after eye structure/meshes and broad Face motion are stable. Preserve eyelid/eyelash width and audit exact keys. |
| DepthRigRoot, 19 standard DepthBones, artwork alignment, LockToRoot feet, BoneSources | `nijigenerate-depth-skeleton-setup` | Must pass before depth image import. |
| Depth PSD/image mapping, alpha-depth gap fill, anatomical depth, effective Z, Fit Z, standard depth parameters | `nijigenerate-depth-import-adjustment` | Requires accepted depth skeleton/BoneSources. Fit Z must pass before standard depth parameters. |
| Generated Face/Body/depth motion refinement and parent-to-child residual correction | `nijigenerate-post-rig-adjustment` | Requires accepted canonical depth, Fit Z, and standard depth parameters. Inspect depth/bone/parent contributions; edit only permitted owning layers and preserve valid parents before Part residuals. |
| True remaining penetrations requiring silhouette masks | `nijigenerate-occlusion-mask-rigging` | Use only after owning deformation/depth problems are corrected. |
| Exported INP Tracking configuration from reference models | `nijigenerate-tracking-setup` | Optional export-consumer phase; preserve rig/textures and validate existing axis semantics. |
| Secondary motion for hair, cloth, rigid accessories, cords, tails, and similar parts | `nijigenerate-simple-physics-rigging` | Last authored rigging phase; never use physics to repair deterministic pose errors. |
| Checklist YAML plus human OK/Retake loop | `nijigenerate-checklist-review-loop` | Use when checklist review is required; initial evaluation is read-only. |
| One Operation SPA assets and review JSON | `nijigenerate-work-review-tool` | Start only when the user explicitly requests the review UI. |

## Canonical end-to-end route

1. Optional PSD preparation, only when requested.
2. Shared preflight, route manifest, baseline, and preservation scope.
3. Model structure and initial parameter definitions.
4. Mouth asset preparation, clothing structure, limb-root positioning, and
   AutoMesh as applicable; all local audits must pass.
5. Depth skeleton alignment and complete BoneSources.
6. Depth import, repeated alpha-depth gap repair as required, anatomical depth
   review, and effective-Z audit.
7. Verified Fit Z, then standard depth parameter generation.
8. Body post-rig correction: verify depth/bone motion, repair its owning layer only when needed and permitted, then individual Part 2.5D residuals.
9. Face post-rig correction, then specialist eye blink and mouth-open rigging.
10. Occlusion masks only for genuine residual penetration.
11. Physics after authored deformation is stable.
12. Global result audit, neutral/reset state, and one verified save.

Enter the next phase only with current-state OK evidence for its prerequisites. Carry explicit later-stage items with their owners; never defer a defect already owned by the current phase.

## Exported Tracking configuration

For adding/repairing tracker inputs on an exported INP use `nijigenerate-tracking-setup`. This is an optional export-consumer workflow, not a prerequisite to depth or expression rigging. Follow its offline extension procedure; do not rebuild hierarchy or reload the live model. Configuration validation and runtime tracking evidence have separate completion scopes.
