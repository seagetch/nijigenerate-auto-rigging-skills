# Parent change and child residual recalculation

Use this when an existing child correction is evaluated after changing `Body::G`,
another parent GridDeformer, a PathDeformer, Pelvis/Spine/DepthBone motion, or any
ancestor transform.

## Principle

A child binding stores a residual relative to the current parent result. When
the parent contribution changes, the old child value no longer produces the
same final image.

For each affected vertex or transform component and each affected key:

```text
new child residual = desired final result - current parent contribution
```

Do not copy the prior residual, mirror the opposite yaw, or regenerate the child
from a generic projection formula.

## Procedure

1. Before changing the parent, capture the accepted final screen-space shape and
   numeric binding state at every affected key.
2. Change and verify the parent alone.
3. At the same exact key, read the new parent-only result.
4. Compute the child residual needed to recover the accepted final result.
5. Apply only that residual to the existing child binding.
6. Preserve neutral unless the user explicitly requested a neutral correction.
7. Re-read the final composed result and compare it with the accepted target.

If multiple ancestor levels changed, evaluate their composed current result
together. Do not subtract each ancestor independently in incompatible local
coordinate frames.

## 5x5 parameter integrity

For Face/Body yaw-pitch parameters with axes `[-1, -0.5, 0, 0.5, 1]`, read and
report all 25 binding cells:

- whether each cell is explicitly set;
- its target UUID and value payload;
- whether it is intentionally authored or intentionally left unset.

The nine cardinal/corner/neutral poses are not enough to establish interpolation
integrity. Unexpected keys at `±0.5` can override interpolation and create a
midpoint shape that does not follow surrounding keys.

- Keep an intermediate key only when its authored shape is intentional.
- Clear an unintended intermediate binding key only with an explicit binding
  context and exact key coordinate; never use an empty unset/reset payload.
- After cleanup, test both the exact `±0.5` cells and values between neighboring
  keys to confirm interpolation follows the intended surrounding poses.

## Direction-specific clothing

Do not reuse one yaw side's clothing residual for the opposite yaw. Front/back
surface visibility, near/far shoulders, hips, skirt edges, and occlusion swap
roles. Compute each yaw endpoint and its pitch row from that direction's
composed Body/Grid/DepthBone result.
