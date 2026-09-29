# Composite ownership and replacing attached artwork

## Structure decision

Distinguish compositing, clipping and deformation. A DynamicComposite may itself own the eye/mouth surface control; an extra Grid over the same region can apply motion twice. Assign one owner for each broad deformation and separate child expression deformation. Follow an explicit prohibition on Grid/DynamicComposite stacking; nested controls elsewhere are not automatically wrong.

## Eye/mouth structure procedure

1. Inspect actual drawable children, current source image versions, composites, meshes, clips and pose bindings. Identify which container owns the surface, and which Parts own blink/open expressions.
2. Resolve duplicated control by preserving the accepted motion on its intended owner. Before changing hierarchy or topology, inventory dependencies using the rigged-mesh procedure. Do not simply delete a parent that contributes accepted pose motion.
3. Set bounds from the intended child set and full expression envelope, then choose divisions independently of old container bounds. Verify upper/lower lashes, iris/white clipping or the five mouth assets at open/intermediate/closed poses.

## Torso/shoulder/armpit asset replacement procedure

1. Show the current whole upper body and angle references. Mark the exact missing painted surface and which existing Parts retain chest, neck, arm and garment details. Decide the necessary connected anatomical region before requesting/generating replacement art.
2. For an authorized image update, specify character identity, costume, fixed pose/camera, original canvas registration, silhouette, shoulder-to-ribcage connection, required hidden-side coverage and alpha. Keep it a clothed rigging asset request; do not pursue wording intended to bypass image-tool safeguards.
3. Inspect the generated/revised image before import: continuous torso, complete shoulders/armpits, no cut-off body, no duplicate chest layer, stable neckline and waist, adequate overlap only at planned seams. Reject missing coverage rather than compensating it with stretched polygons.
4. Register the approved asset in the original model coordinate frame using persistent landmarks and pixel/world scale, not its cropped bounding-box center. Record replacement target UUID, texture region, original canvas offset and scale.
5. Through schema-supported njc texture operations replace only the intended Part. If topology must change, first prepare the [rigged mesh migration](../../nijigenerate-automesh-setup/references/parameter-only-and-rigged-mesh.md). Preserve existing parameter meaning and unrelated depth/keys/zSort.
6. Validate neutral and previously reported poses with both neighboring Parts visible. Check painted coverage, texture alignment, seam ownership and independent armpit movement before adding Welding or Part residuals.

An asset update is not authorization to reload the whole model or regenerate depth.

The [Ao shoulder/armpit and torso examples](../../nijigenerate-post-rig-adjustment/references/ao-visual-examples.md) show the surrounding anatomy that must be inspected together. They illustrate diagnosis and candidate rejection, not an approved replacement texture to import.
