# Face, hair, headwear, earwear, and neck depth

Use this reference to define or correct head-related GridDeformer depth. The goal is a continuous head volume, not globally stronger relief or global flattening.

## Face

- Model the face as a broad curved surface with moderate forward depth.
- Keep the eye region and the row immediately above it comparatively even unless the artwork clearly shows stronger form; excessive variation makes the eyes ripple.
- Locate nose, mouth, chin, and jaw from the artwork rather than symmetry or a stock grid.
- Give the nose a localized forward point with smooth falloff.
- Preserve modest lip/mouth form, but prevent the mouth region from becoming a forward shelf in yaw.
- Keep cheeks and lower face continuous. Do not turn a local mouth correction into global face flattening.
- Treat face sides and ears as side/rear transitions, not another front-facing strip.
- If the whole face is too far back, use import layer offset or node `translationZ`; if only the mouth protrudes, edit local Face grid depth.

## Front and side hair

- Keep FrontHair in front of the face while preserving a rounded upper hair mass.
- Keep SideHair quieter than FrontHair and close enough to the face that it does not cut across facial features in yaw.
- Correct local troughs or peaks where a side lock crosses the face; do not flatten the entire hair grid.
- If all FrontHair is misplaced while its local relief is correct, use node `translationZ` rather than adding one constant to every grid depth.

## Back hair

First complete [head-volume-and-hair-cases.md](head-volume-and-hair-cases.md), including the ordinary-head, long-hair, or hairless branch. For the region that actually represents rear skull volume:

- edges and top rim: mildly rear;
- occipital center and back-lower region: strongest rear depth;
- lower rim: less rear than the center so it does not shear like a rectangular panel.

The scalp/cranial region should follow the head rather than inherit an unrelated Face surface deformation. This does not assign all long hair to the head: use the linked long-hair procedure for a continuous Head-to-Body transition. A BackHair Part can contain front-visible crown detail; inspect outer volume and interior texture separately before assigning one depth behavior to the entire bitmap.

## Headwear and earwear

- Make Headwear follow head volume and avoid sharp local troughs beneath attached parts.
- When Earwear looks dented or crosses the face, inspect the parent Headwear grid before changing Earwear opacity, zSort, or visibility.
- Map the accessory into the parent grid, compare the sampled parent depth with nearby Face/FrontHair effective depth, and correct only a compact neighborhood with falloff.
- Keep the accessory visible. Hiding it is not a depth correction.

## Neck

- Keep upper-neck and lower-neck depth continuous.
- If the upper neck projects too far, correct the transition locally rather than flattening the whole neck.
- Re-run Fit Z to Depth after final neck or head-grid corrections.

## Head-surface verification

At neutral and both yaw endpoints confirm:

- the mouth does not project like a muzzle or shelf;
- Face and FrontHair retain volume without excessive separation;
- SideHair does not cover the wrong face region;
- Headwear/Earwear has no local dent or face crossing;
- BackHair reads as rear head mass;
- neck top and bottom form one continuous volume.
