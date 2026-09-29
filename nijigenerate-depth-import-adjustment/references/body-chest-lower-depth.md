# Body, Chest, and lower-body depth

Use this reference to define the canonical surface depth before Body rigging generates yaw/pitch bindings.

## Responsibility split

- `Body::G` owns broad volume: neck base, shoulders, ribcage, abdomen, waist, pelvis, hips, and broad lower-front mass.
- `Chest::G` or the appropriate local topwear grid owns breast-specific residual depth.
- Do not duplicate breast peaks in both Body and Chest.
- A clothing grid that inherits Body motion receives only its own residual depth.
- A hierarchy boundary that prevents Body inheritance requires an independent full surface, handled with the clothing-depth reference.

## Body::G shape

- Keep depth broad and smooth across shoulders and torso.
- Encode shoulder volume in depth instead of artificial 2D widening.
- Preserve thickness at waist, pelvis, hips, and side columns; do not collapse them toward zero merely because the front center is dominant.
- If the body looks inside-out, verify depth polarity/sign before adding X offsets.
- Remap every region after AutoMesh or hierarchy changes.

## Chest shape

- Use two smooth localized peaks aligned to the visible left/right breast masses.
- Avoid one central mound.
- Do not place the maximum at the lowest breast/under-cup edge.
- Taper around each peak so adjacent rows and columns remain continuous.
- If Body and Chest fight, simplify Body to broad torso volume and keep local breast form in Chest.

## Lower body

- Preserve a convex lower torso, apron, or front-skirt region when the artwork shows one.
- Keep both the center band and visible side columns meaningfully forward.
- Taper after the main lower-front region instead of dropping directly to a flat/rear plane.
- Use smooth continuity through waist, pelvis, hips, and leg roots.
- Do not repair a flat lower body with 2D side-width hacks.

## Bottomwear

- Front bottomwear follows the positive lower-front shell.
- Back bottomwear uses rear depth with smooth center-to-edge and top-to-hem transitions.
- If backwear is outside Body deformation, give it independent Body-like base depth plus rear residual depth.
- Keep rear magnitude bounded so the garment remains attached rather than ripping away from the body.

## Verification

Check neutral and yaw endpoints for:

- broad torso thickness;
- two separate smooth chest masses;
- shoulder volume without 2D width tricks;
- continuous waist/pelvis/hip depth;
- lower-front convexity without a flat center or collapsed sides;
- no double application between Body, Chest, Topwear, and Bottomwear.

## Artwork-specific cross-sections and connected surfaces

1. Mark neck base, clavicle/shoulder, upper ribcage, breast mass, under-bust, waist and pelvis rows against actual grid samples. At each row identify front/side/rear surface ownership and its anatomical landmarks.
2. Set explicit depth samples from those observed surfaces. Let section shape vary with height: when supported by the artwork, upper torso transitions gradually toward a flatter clavicle region while ribcage sides/back retain thickness. Do not extrude the same profile from waist to neck or invent a sine-wave surface.
3. Inspect adjoining shoulder, upper arm, forearm, hand and sleeve grids; preserve their own rounded cross-sections, attachment continuity and distinct cloth volume. Chest relief belongs to Chest; avoid duplicating peaks in Body.
4. Compare effective depth at shared shoulder and waist boundaries before Fit Z. A smooth scalar array is insufficient if shoulder meets torso at incompatible depths or the side/back wall collapses.
5. Inspect side/top oblique views and the requested angle references at a common scale. Judge visible side/back thickness, chest-to-ribcage attachment and waist-to-skirt continuity. Leave residual exposed-side contour correction to individual Part work after the base volume is valid.

These are landmark-based decisions, not a universal analytic depth formula. Respect a request to directly author depth rather than generate/import replacement depth images.

For visual examples of flattened torso surfaces and connected shoulder/armpit defects, read [Ao torso/reference examples](../../nijigenerate-post-rig-adjustment/references/ao-visual-examples.md). The generated candidate requires camera registration and anatomical review; it supplies no depth samples to copy.

When using generated angle references, follow the shared [generation → depth → Part workflow](../../nijigenerate-shared-rigging-rules/references/angle-reference-depth-part-workflow.md) before this anatomical depth procedure and carry its comparison ledger into the Part pass.
