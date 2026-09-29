# One-sided shoulder/torso Welding

## Scope

Welding enforces an intended shared seam. It must not pull a free armpit surface along the arm or repair absent torso artwork. Choose the reference side from the accepted shape and user instruction; do not hard-code arms or torso as the universal master.

## Procedure

1. Read both Parts' mesh/UV order, transform hierarchy, all applicable deforms, existing Welding relations and static zSort. Capture neutral and the failing pose with the seam visible.
2. In a shared rendered/local frame mark the ordered attachment band, reference side and follower side, corresponding mesh points, and explicit non-weld regions (armpit hollow, chest surface, free arm edge). Inspect existing edges for duplicate or reciprocal constraints.
3. Check the live schemas for `NodeWeldingCommand_AddWelding` and `NodeWeldingCommand_RemoveWelding`. Resolve which selected node/target and weight designate the reference and follower; do not infer the direction from the word target. Preserve unrelated relations.
4. Determine how that version finds correspondences (explicit or geometric matching). If it welds automatically matching vertices, inspect the actual matched set before accepting the operation. A weight alone does not select a seam. Do not add matching interior vertices across the entire overlapping armpit/chest area.
5. Remove only erroneous relations. Apply the directional relation with the proven reference/follower weights. If topology must change to express the intended seam, first use the [rigged-mesh procedure](../../nijigenerate-automesh-setup/references/parameter-only-and-rigged-mesh.md); do not combine remeshing and Welding blindly.
6. Read back actual relations and correspondence where exposed. Otherwise use isolated reference motion and rendered coincident seam landmarks to verify the direction and matched region. The reference side must keep its pose; only the follower seam should follow. Outside the attachment band retain independent movement with a smooth transition if supported.
7. At both yaw extremes, forward/backward pitch, intermediate keys and reported Face/Roll combinations inspect shoulder silhouette, seam coincidence, armpit opening and far chest. A numerically welded point with a visible doubled edge is RETAKE, not success.
8. Compare UVs, zSort, hierarchy, other bindings and reference-side coordinates to the baseline. Do not move node order or zSort to conceal a Welding defect. Restore this operation's relation changes through njc if the matched set is wrong.

Record the actual weights and schema semantics; model-specific counts and values are not presets. Unavailable correspondence evidence remains UNVERIFIABLE rather than assumed complete.

For the rejected shoulder seam and armpit examples, read [Ao visual examples](ao-visual-examples.md). Its failure images and generated candidates are explicitly distinguished from accepted results.
