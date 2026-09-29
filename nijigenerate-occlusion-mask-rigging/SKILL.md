---
name: nijigenerate-occlusion-mask-rigging
description: Create nijigenerate silhouette DodgeMasks through njc for true residual penetrations after correcting the owning deformation or depth problem.
---

# Nijigenerate Occlusion Mask Rigging

For the exhaustive occlusion mask checklist, read `references/step-checklist.yaml`.
Run `references/result-audit-checklist.yaml` with the shared result audit/repair loop before saving or declaring the penetration fixed.

Always complete `references/step-checklist.yaml`. Start a checklist reviewer UI only when the user explicitly requests it; a user prohibition on reviewer/browser work overrides any legacy review instruction.

## Workflow

Use this after or alongside `nijigenerate-front-back-clothing-rigging`, `nijigenerate-post-rig-adjustment`, and `nijigenerate-model-setup`. Read `references/occlusion-mask-method.md` and `nijigenerate-shared-rigging-rules` before changing model state.

1. Confirm the protrusion with `CaptureLiveScreenshot` or `ViewCommand_SaveScreenshot` at the relevant parameter keys. Do not assume the offending side from the front view.
2. Identify the visible occluder and the target parts to hide. The occluder may be a jacket edge, skirt edge, sleeve, hood, cape, or any foreground surface.
3. Create a separate `Mask` object under the same deforming parent as the occluding part. Do not use the visible Part itself as the DodgeMask source.
4. Define the mask shape from the occluder's outer silhouette, extending outward from that silhouette. Avoid rectangular masks unless the occluding silhouette is actually rectangular.
5. Register the new `Mask` as a `DodgeMask` on every target part that should disappear behind it. Remove stale or wrong masks first.
6. Verify by reading back the Mask and each target part's mask list, then capture the problem yaw/pitch keys again.
7. Run the result audit read-only, repair every `RETAKE`, and rerun the full result checklist from item 1 until all applicable current-stage items are `OK`.
8. Save with `FileCommand_SaveFile`.

## Core Rules

- The mask is an independent invisible object used for exclusion. The visible jacket/skirt/sleeve part remains artwork, not the mask source.
- The mask should follow the outer contour of the occluder and extend to the outside of the model silhouette, not to the inside edge.
- Place the mask under the same GridDeformer/parent that moves the occluder, so yaw/pitch deformation keeps the occlusion aligned.
- If direct mesh definition on an empty `Mask` fails because it has no texture, create a temporary texture-backed Part, define its mesh, then convert it to `Mask`.
- Always verify side-specific behavior. For a jacket edge, the useful side is often the side that becomes the rear-connected edge at that yaw, not the side that looks visually active in the front pose.

## References

- Detailed procedure: `references/occlusion-mask-method.md`
- Result audit: `references/result-audit-checklist.yaml`
- Clothing surface context: `nijigenerate-front-back-clothing-rigging/SKILL.md`
- Model setup and hierarchy context: `nijigenerate-model-setup/SKILL.md`
- This skill's copied `references/user-doc/` files for node movement and mesh definition; use skill-local references for Mask, DodgeMask, and screenshot command notes.
