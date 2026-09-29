# DepthBone pose compensation

Use this only after the standard DepthBone structure, visible rest placement,
BoneSources, canonical Grid depth, Fit Z, and standard Body parameters exist.

## Pelvis and Spine yaw distribution

- Read the existing Body::Yaw-Pitch binding values for Spine and Pelvis at each
  yaw endpoint and pitch row.
- Reduce excessive Spine yaw by the requested proportion and transfer the
  required broad torso turn to Pelvis. Do not merely halve Spine without
  preserving the intended total body orientation.
- Recompute dependent leg compensation after changing Pelvis. Existing knee
  corrections were authored against the old parent contribution.

## LockToRoot feet and knee stability

`Foot.L` and `Foot.R` are root-locked ankle/foot targets. Treat their app-visible
world positions as fixed constraints, not as ordinary child bones that inherit
Pelvis motion.

For each Body yaw/pitch key:

1. Record the fixed ankle/foot target in app-visible coordinates.
2. Apply the intended Pelvis and torso motion.
3. Solve the Thigh and Shin DepthBone rotations/transforms so the chain reaches
   the same ankle target while keeping the knee near its accepted image-space
   landmark.
4. Prefer joint rotation and chain-consistent compensation. Do not translate an
   unrelated GridDeformer or Part as a substitute for DepthBone correction.
5. Minimize lateral knee travel and knee height change subject to preserving the
   ankle target and a plausible bend direction.
6. Verify both legs independently; do not mirror numeric values without checking
   the artwork pose.

The correction must target DepthBone bindings. A Part/Grid-only edit can hide the
symptom while leaving the skeleton crossed or laterally rotated.

## Verification grid

Check neutral, yaw `-1/+1`, pitch `-1/0/+1` for each yaw endpoint, then inspect
adjacent intermediate values. For every state record:

- Pelvis and Spine rotation;
- Thigh/Shin/Foot visible head and tail positions;
- ankle displacement from its locked neutral target;
- knee X/Y displacement from the accepted landmark;
- whether left/right knee lines cross.

Reject the pass if the ankle appears fixed but either knee swings sideways,
crosses the other chain, or drops substantially without an artwork-based reason.

## Lowering with knee bend

Treat requested knee convergence and requested lowering as independent targets. Record accepted lateral knee separation before changing vertical travel. At each pitch row, move the pelvis toward the intended lower posture, solve the thigh/shin chain against the same ankle target, and compare both knee heights and joint bend with the reference. If the body still appears too high, adjust pelvis/knee height within the chain constraints; do not increase inward knee rotation as a substitute. Check both legs at intermediate negative values as well as the endpoint. Record chain continuity, non-crossing knees, ankle error and unchanged requested lateral convergence.
