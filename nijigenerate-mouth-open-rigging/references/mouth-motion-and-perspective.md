# Mouth Motion And Perspective

## Contents

1. Mouth components and motion
2. Coordinate and perspective frame
3. Oblique closure axis
4. Closure construction
5. Expression construction
6. Intermediate keys
7. Verification
8. Failure patterns

## 1. Mouth Components And Motion

Treat the mouth as coordinated layered artwork, not as one image being scaled into a line.

- `Outline` defines the visible upper/lower lip boundary and corners.
- `Base` defines the mouth cavity and clipping silhouette; it follows the Outline.
- `Teeth::Upper`, `Teeth::Lower`, and `Tongue` move or compress inside Base and must not expose transparent edges.
- The upper visible boundary normally performs more of the closure than the lower boundary.
- Full closure retains a narrow painted band. It is not a zero-area geometric line.

Read actual meshes and rendered artwork before classifying upper, center, lower, inner-corner, and outer-corner vertices. Mesh-row Y or texture UV Y may assist but must not be the sole anatomical classifier.

## 2. Coordinate And Perspective Frame

Before authoring bindings, record:

- character side and screen side where relevant;
- screen-left and screen-right mouth corners;
- near and far sides of the three-quarter face;
- face roll and mouth-corner slope;
- local X/Y directions after parent transforms;
- open width, height, and corner positions.

Determine these from the current rendered model. Names and another model's constants are not proof.

Confirm whether positive local Y appears upward or downward on screen. Use existing deformations, transforms, overlays, or a small unsaved candidate followed by an exact-key screenshot. Re-read state before correcting any trial. Never reverse smile and displeased based on an assumed sign.

Near/far asymmetry is model-specific. A near corner commonly supports a larger readable expression displacement, while a far corner is foreshortened. Determine both from artwork; do not hardcode a screen side or ratio.

## 3. Oblique Closure Axis

Let the rendered neutral mouth corners be `A` and `B`. Define an oblique mouth frame:

```text
T = normalize(B - A)          # mouth-corner tangent
N = perpendicular(T)         # mouth-local vertical
C(t) = A + t(B - A)          # neutral closure chord
```

Orient `N` using rendered evidence. When the source mouth has a curved neutral seam, replace the chord with a reviewed shallow curve `C(t)`.

The closure target must remain tied to `C(t)` as X changes. A tilted face must not become more horizontal during closure. Estimate `A`, `B`, and the center from the actual mouth, facial roll, nose, chin, and eye axis; screen horizontal and local `Y=0` are invalid defaults.

## 4. Closure Construction

For a vertex `P` assigned to normalized horizontal position `t`, decompose it relative to the closure axis. A useful conceptual form is:

```text
Pclose = C(t) + T * tangential_residual + N * normal_residual * remaining_band
```

Use separate remaining-band values for upper, lower, and center artwork. The upper contour normally travels farther. Keep enough upper/lower separation at X=1 to preserve painted thickness and continuous antialiasing.

Apply the same axis to every mouth target, but tune containment separately:

- `Outline`: preserve corner taper and a continuous closed lip band.
- `Base`: follow Outline closely enough that no cavity leaks outside it.
- `Teeth::Upper`, `Teeth::Lower`, `Tongue`: compress or move inside Base so no internal color remains visible at full closure.

Do not widen the endpoints during closure. Any width change requires a matching reviewed reference.

Use a monotonic closure progress function. A mild nonlinear curve may be appropriate, but constants are model-specific and must be verified at every authored key.

## 5. Expression Construction

Build expression displacement relative to `C(t)`, along the verified local normal `N`, after closure position has been established.

Use a corner weight that is small at the center and increases toward both ends, for example a smooth quadratic or Bézier-derived weight. Preserve the center as the visual anchor unless the artwork requires otherwise.

- Y=0 displeased: both corners move visually downward relative to `C(t)`. At full closure the result should read as a clear downward-corner `への字` while retaining face roll.
- Y=0.5 neutral: corners follow the authored oblique neutral axis.
- Y=1 smile: both corners move visually upward relative to `C(t)`.

Apply independent near/far strengths. "Both corners rise" or "both corners fall" is judged relative to the oblique axis, not by equal global screen-Y coordinates.

Do not fade displeased displacement so aggressively with X that `X=1,Y=0` becomes neutral. Conversely, do not use so much displacement that lip thickness, clipping, or the mouth center tears.

## 6. Intermediate Keys

Author the actual parameter grid. For a five-by-three grid, each of the five targets must have 15 set keys.

At X `0.25`, `0.5`, and `0.75`, verify:

- the upper boundary descends monotonically;
- the lower boundary rises less than the upper descends unless the reference says otherwise;
- the mouth axis retains the same roll;
- width does not expand;
- Outline and Base remain registered;
- internal artwork disappears progressively without transparent gaps;
- expression direction and near/far asymmetry remain stable.

Do not assume automatic interpolation between only X=0 and X=1 will preserve these properties.

## 7. Verification

Set each exact key with `ParameditCommand_SetParameterKeypoint` before capture. Use both:

- original-scale face or upper-body screenshots for placement and expression reading;
- equal-scale enlarged mouth crops for line continuity, thickness, clipping, and internal leakage.

Capture at least:

```text
X = 0, 0.5, 1
Y = 0, 0.5, 1
```

Also inspect every additional authored X key. Compare X columns vertically and Y rows horizontally rather than reviewing isolated images.

Numeric readback must confirm:

- parameter ranges and exact keys;
- five expected deform targets and no unexpected target;
- complete `isSet` matrices;
- unchanged target vertex counts;
- unchanged non-mouth bindings;
- unchanged static hierarchy signature `(uuid, parent, type, name)`.

Numbers diagnose state but cannot prove visual acceptance.

## 8. Failure Patterns

- **Smile and displeased are reversed**: local Y sign was assumed instead of rendered and verified.
- **The mouth straightens while closing**: vertices converge toward local `Y=0` or screen horizontal instead of `C(t)`.
- **Only the parent shrinks**: the five artworks are not coordinated and internal clipping or texture behavior diverges.
- **Closed displeased looks neutral**: expression strength was faded with closure or measured against the wrong axis.
- **Closed lip becomes dotted or jagged**: upper/lower bands were collapsed too tightly for the painted texture and render scale.
- **Mouth becomes wider when closed**: endpoint positions or normalized texture bounds were extrapolated.
- **Far and near corners look mirrored**: identical amplitudes were used despite foreshortening.
- **Teeth or tongue remain visible**: internal targets do not share the closure axis or are insufficiently contained by Base.
- **Hierarchy audit reports a false change**: dynamic fields or current parameter values were compared instead of a static hierarchy signature.
- **A structure-only request gains bindings**: asset construction and parameter rigging were not separated.
