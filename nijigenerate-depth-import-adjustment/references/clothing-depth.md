# Clothing depth

Use this reference for garments spanning front, rear, and side body surfaces.

## Classify each surface

- `Front`: front panels, lapels, straps, apron/skirt front, front sleeve surfaces.
- `Back`: cape, rear hood, rear skirt, coat tails, back panels.
- `Side`: surfaces wrapping between front and rear.
- `Local`: hood rim, sleeve cap, hem, belt, ribbon, trim, or dangling accessory needing separate local depth.

Draw order does not define physical depth. A rendered-front Part may still represent a side or rear surface.

## Decide inherited residual versus independent surface

- If the clothing GridDeformer truly inherits parent Body/Head deformation, define only clothing-specific residual depth.
- If a Node/Grid/Part boundary blocks inheritance, define a complete independent surface.
- Confirm inheritance from the live hierarchy and a test key; do not infer it from visual proximity.
- Separate front/back grids when their depth signs or surface pivots differ.

## Front shell

- Treat jackets and coats as shells around the torso, not flat rectangles.
- Keep the central front band near.
- Transition side wraps gradually toward side/rear depth.
- Keep outside silhouettes from becoming another front-facing strip.
- Follow the actual row-dependent outline: shoulders/sleeves may widen, waist may narrow, hem/skirt may widen.

For trapezoidal clothing, identify `outer_l`, `front_l`, `front_r`, and `outer_r` per row; use a front band between the inner limits and sloped side faces toward the outer limits.

## Rear shell

- Keep rear panels far enough to read behind the body but not so far that they detach.
- Use smooth center-to-edge and top-to-bottom transitions.
- Rear yaw response may oppose the front surface, but attachment regions must remain continuous.

## Hood, skirt, and hem

- Hood: curve the outer rim backward; keep the neck/collar center nearer than the sides; blend into shoulder/front/back surfaces.
- Skirt: keep the front near, side folds transitional, and back panel rear.
- Apron/front skirt: the lower center may be the most forward lower-body surface; keep visible side columns forward enough to preserve curvature.
- Rear skirt/coat: rear convexity may strengthen toward the center/back line or hem, with falloff toward edges.
- Hem: allow a wider curved section when the artwork requires it, but keep continuity with the upper garment.

## Verification

Check neutral, both yaw endpoints, pitch endpoints, and relevant corners for:

- front panels remaining in front;
- rear panels remaining behind without detachment;
- side wraps transitioning without tearing;
- hood, sleeve, waist, neck, and hem anchors remaining connected;
- no Body/clothing depth double application;
- no use of zSort as a substitute for surface depth.
