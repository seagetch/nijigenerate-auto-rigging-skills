# Individual Part 2.5D correction against references

## Responsibility

Depth gives broad volume and bones give pose. Part correction describes the residual silhouette and visible surface that a rotated textured sheet cannot provide: turning cheeks, jaw transitions, exposed torso sides, seam edges and occlusion. It is not a second independent body rotation. Grid XY editing is optional only for an authorized, diagnosed Grid defect, never a prerequisite to Part work.

## Reference and correction procedure

1. Record the full pose vector and existing parent/Part contributions. Collect the requested directions and every reported failing mixed pose. Obtain generated angle references only if authorized; preserve identity, costume, view angle and projection. Reject reference regions that contradict the artwork or anatomy rather than treating all generated pixels as truth.
2. Align model and reference using a common camera scale and homologous structural landmarks. Do not independently stretch the chest, face or crop to make widths appear equal. Declare the local O/T/N frame under the shared coordinate rules.
3. Mark the outer silhouette, internal landmarks, visible/hidden surface boundaries and fixed attachments. For faces include forehead, cheek transitions, chin, nose and ear relation; for torsos include neck base, shoulder, chest edge, armpit, waist and garment seam.
4. Classify each discrepancy: missing volume to depth; wrong articulation to bone/BoneSource; absent painted surface to asset preparation; angle-specific contour/occlusion to this Part procedure; genuine residual penetration to Mask. Fix only the permitted owning layer. Do not return to initial import or regenerate standard parameters merely to change a local silhouette.
5. On each affected Part, read current vertices, UVs, keys and visibility. Identify an ordered contour path and its neighboring support vertices. Plan target points in the declared frame using the reference; maintain existing bone motion and compute the remaining correction in the actual current composed state. Any helper may transform coordinates or serialize the plan, not substitute a generic geometric model for the reference judgement.
6. Apply local deltas through njc to necessary keys only, with continuous transitions into unchanged vertices. Retain existing residuals and intentional set/unset states; do not zero an entire binding. Inspect the deformed textured result, not only the polyline.
7. Compare before/reference/after at the same scale, with a local crop and its surrounding attachment. Revisit opposite direction, adjacent half-values and mixed Face/Body/Roll poses. Numeric seam equality does not prove visible continuity.

## Region decisions

- Face: prefer a smooth silhouette over forced ear exposure. Do not notch the cheek to reveal an ear. Treat near and far cheek independently; retain far-cheek fullness, a rounded chin transition, and the reference nose position. A jaw correction does not imply shortening the upper face or moving the neck. Keep user-fixed jaw/upper-face regions fixed.
- Jaw/neck: determine which painted boundary should be visible at each angle. Correct the face contour if the defect belongs to the jaw; route actual neck artwork defects to asset work only when that is in scope. Do not skew the whole neck to imitate a jawline.
- Head/hair: posterior head evaluation is mandatory, including hairless heads. Inspect skull silhouette and internal detail separately, using [head/hair surface correction](head-hair-surface-correction.md). Preserve an accepted outer dome while correcting internal detail that appears attached to the wrong surface. Long-hair passes must review the complete Ao case table linked there.
- Torso: preserve ribcage volume while exposing the far side. Avoid pulling the far chest edge to an arm merely to close a gap. Separate chest residual shape from torso articulation and compare nearby clothing.
- Shoulder/armpit: distinguish the shoulder attachment from the hollow under the arm. A gap, absent paint, wrong depth, wrong occlusion and accidental Welding require different corrections.

Derive the initial contour targets from artwork and directional references using [face-contour-from-reference.md](face-contour-from-reference.md); do not wait for a user-edited delta as the shaping method. When user-corrected keys already exist, preserve the specified keys exactly and carry their anatomical intent, not raw screen offsets, to other angles.

For face/torso angle comparison and simultaneous neighboring-surface defects, read [Ao visual examples](ao-visual-examples.md). Its failure images and generated candidates are explicitly distinguished from accepted results.

For the complete reference-generation, pose-validation and depth-first sequence preceding this Part pass, use [generation → depth → Part workflow](../../nijigenerate-shared-rigging-rules/references/angle-reference-depth-part-workflow.md). Keep the same adopted references and capture conditions across both stages.
