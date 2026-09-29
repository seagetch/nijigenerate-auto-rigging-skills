# Eyelid Motion And Bézier Construction

## Contents

1. Anatomical movement model
2. Perspective-aware eye frame
3. Separate position, curvature, and thickness
4. Canthus endpoints and endpoint neighborhoods
5. Vertex mapping and eye-part policy
6. Intermediate keys
7. Verification metrics
8. Failure patterns

## 1. Anatomical Movement Model

Treat blinking as two contours meeting, not as an eye image being vertically scaled.

- Descend the upper lid toward the lower lid.
- Allow only a slight lower-lid rise by default, including during a smile.
- Keep the closed seam toward the lower side of the original aperture even when its painted curve arches upward.
- Treat eyelash artwork as a painted band with separate upper and lower boundaries, not as a zero-width centerline.

Classify upper and lower contour vertices from mesh topology, rendered overlays, and opaque artwork. UV Y may assist but must not be the sole classifier.

Use this movement budget as a default guardrail:

- keep lower-lid rise below roughly one quarter of the original aperture;
- make upper-lid descent at least twice the lower-lid rise;
- override only when a model-specific reviewed reference visibly requires it.

Measure movement along the eye-local vertical axis rather than global screen Y.

## 2. Perspective-Aware Eye Frame

For each eye, identify reviewed authored open inner canthus `A_open` and outer canthus `B_open` in the same current rendered/deformed parent space.

```text
O = A_open
T_open = normalize(B_open - A_open)  # includes current face roll
N_open = perpendicular(T_open)       # orient toward the lower lid
u(P) = dot(P - O, T_open)
v(P) = dot(P - O, N_open)
```

Use local `u/v`, never raw screen X/Y, for anatomical placement. Preserve both canthus positions and `T_open` by default across all Blink keys. Cross-check `T_open` against rendered inter-eye/face roll; a screen-horizontal or slope-reversed candidate on a rolled face is `RETAKE`.

Changing the endpoint chord away from `T_open` requires a same-roll authored reference and human-approved axis overlay. Screen-space contour intersection or plausible raw screen-Y ordering cannot authorize that change.

Record for each eye:

- character side and screen side;
- near or far status;
- canthus-axis slope;
- eye-local `O/T_open/N_open` and source landmark identities;
- local `u/v` values for every planned endpoint;
- rendered face-roll cross-check;
- open width and aperture;
- inner/outer endpoint identity;
- occlusion by hair or face features.

Do not mirror normalized values. The far eye is commonly shorter and may need different slope, curvature, and taper. The near eye may show a stronger oblique axis and larger expression-dependent drop.

## 3. Separate Position, Curvature, And Thickness

Represent each closed expression with independent controls:

1. **Drop**: closure-line position along `N_open` toward the lower lid.
2. **Curvature**: deviation from the canthus chord.
3. **Band thickness**: distance between the painted upper and lower lash boundaries.
4. **Endpoint neighborhood**: how curvature eases away from each fixed canthus.

A cubic Bézier curve can define the seam:

```text
C(t) = Bézier(Q0, Q1, Q2, Q3, t)
```

Construct `Q0..Q3` in the local eye frame. Apply drop first and expression curvature afterward. Never use curvature as a substitute for drop.

- **Neutral closed**: follow the oblique canthus axis with a shallow downward sag.
- **Smile closed**: arch upward relative to the dropped chord while keeping the whole seam low enough for upper-lid-led closure.
- **Deep/quiet closed**: use a low relaxed neutral/downward curve distinct from smile.

Map actual corner UVs to `t=0..1`; do not assume the opaque artwork spans texture U `0..1`. Closed width must not exceed the reviewed open width.

## 4. Canthus Endpoints And Endpoint Neighborhoods

Keep both canthus positions invariant across expressions unless a reviewed model-specific reference requires an intentional shift. Exact endpoint equality alone is insufficient.

For each expression, also inspect:

- the nearest upper and lower vertices at both ends;
- the first contour segment and tangent leaving each canthus;
- the painted alpha silhouette within the inner and outer 20–35% of eye width;
- the transition between endpoint taper and expression curvature.

Ease expression curvature away from each endpoint. A sine or Bézier middle term can still create apparent canthus drift when it reaches full strength immediately after `t=0` or before `t=1`. Blend from the endpoint tangent into the expression curve over an artwork-dependent endpoint window.

When only one side or expression is wrong, modify only that endpoint neighborhood and expression row. Do not regenerate the opposite eye or accepted rows.

## 5. Vertex Mapping And Eye-Part Policy

Create deformation maps for:

- upper-lid/lash vertices;
- lower-lid vertices;
- eye-white vertices.

Inspect Iris vertices and Part properties, but do not create an Iris Blink deformation map.

For each seam sample, use its tangent and normal:

```text
T(t) = normalize(C'(t))
N(t) = perpendicular(T(t))
```

Place the lash upper and lower boundaries on separate normal offsets from `C(t)`. Preserve the actual painted upper-lash thickness, not merely the mesh-band height. Taper offsets toward the canthi according to the artwork.

Map upper-lid vertices with full closure progress. Map lower-lid vertices with an independently capped displacement. Do not collapse both contours with one shared weight.

For the eye white:

- preserve every X coordinate at every Blink key;
- move only Y so its upper and lower boundaries follow the lash seam;
- retain a thin nonzero vertical band rather than crushing to zero height;
- do not add Blink opacity or zSort bindings.

For the Iris:

- leave geometry, opacity, and Blink bindings untouched;
- keep it visible at the authored open/default pose;
- hide it during closure through the existing clipping relationship and verified static Part zSort.

See `eye-part-visibility-and-retake.md` for the exact visibility and mutation rules.

## 6. Intermediate Keys

Use exact model key values. Author and inspect the full Blink-X sequence for every real expression row, for example deep, neutral, and smile.

At every combination verify:

- upper contour moves downward monotonically;
- lower contour rises only slightly;
- width does not expand;
- painted lash thickness does not collapse or inflate;
- canthus endpoints and adjacent tangents remain continuous;
- eye white disappears progressively without detached fragments;
- Iris remains geometrically unchanged and is hidden only by draw order/clipping near closure.
- the endpoint chord retains `T_open` unless an explicitly reviewed same-roll tangent exception exists.

Do not inspect only neutral intermediate keys and expression full-close endpoints. That misses expression-specific canthus and interpolation defects.

## 7. Verification Metrics

Capture the same verified crop and scale at open, every intermediate, and every full-close expression.

Measure or inspect:

- upper-lid travel along `N_open`;
- lower-lid travel along `N_open`;
- upper/lower travel ratio;
- closed/open width ratio;
- painted lash thickness at inner, center, and outer thirds for every key row;
- exact canthus coordinates and neighboring segment/tangent continuity;
- near/far slope and foreshortening;
- eye-white X deltas, which must all be zero;
- residual white or Iris pixels;
- Iris binding absence and static zSort readback;
- exact-default image regression after each mutation.
- endpoint `u/v` values and tangent-angle error relative to `T_open`.

Numbers are diagnostics only. The rendered image and human review decide acceptance.

### Mandatory Retake Counterexample

If the rendered face is rolled, `T_open` is about `-13°`, and a candidate closed line is about `+3°` or nearly screen-horizontal, it is `RETAKE` even when its raw screen-Y ordering appears plausible. It differs from `T_open` by about `16°`, flattens or reverses against face roll, and lacks a reviewed tangent exception.

## 8. Failure Patterns

- **Closed line stays near the open upper lid**: the closure target is too high or the lower lid is doing most of the work.
- **Neutral looks happy**: curvature replaced vertical drop or the midpoint is above the oblique chord.
- **Smile closes by lifting the lower lid**: the smile arch moved upward as a whole; lower the seam while retaining relative curvature.
- **Canthus is numerically fixed but looks shifted**: adjacent vertices or the first tangent enter the expression curve too abruptly; add endpoint-neighborhood easing.
- **Lash becomes thin**: the actual opaque band was not measured. Move the painted upper boundary outward while holding the seam, lower boundary, and canthi fixed.
- **Lash becomes wider**: the actual canthus range was not normalized or endpoints were extrapolated.
- **Near and far eyes look mirrored**: identical control ratios were applied despite perspective.
- **White remains**: eye-white Y targets do not follow the lash band or static ordering/clipping is wrong.
- **Iris remains closed or disappears open**: Iris was deformed, hidden with opacity, parameter-bound to zSort, or placed at an incorrect static zSort.
- **A local fix breaks a previously correct pose**: the full rig was regenerated instead of applying a delta-only Retake.
- **Closed lines look screen-horizontal on a rolled face**: raw screen Y or the wrong measurement space was used. Rebuild `O/T_open/N_open`, inspect local `u/v`, and preserve `T_open`.
- **A numeric audit says one inner corner is higher**: reject it unless both endpoints' local `v` values and the declared frame are present.

## Requested whole-eye placement changes

Classify the request before changing vertices: moving the eye as a feature, moving only the closure seam, or changing expression curvature. For a whole-eye move, identify lashes, white, iris and clipping ownership and translate their placement coherently in the declared face-local frame; do not move only the canthi. Preserve the existing expression deltas and fixed endpoint relations across rows. Keep Iris free of Blink bindings: a feature-placement change is separate from Blink deformation. Recheck open, intermediate and all closed-expression states, with both eyes visible. A request for slightly higher endpoints followed by “raise the whole eye” updates the target operation rather than stacking another endpoint-only delta.

See the [Ao endpoint-only and whole-contour comparison](reference-images.md#ao-session-endpoint-only-versus-whole-contour-placement) when interpreting a request to raise the entire contour; pair visual inspection with its local-frame audit.
