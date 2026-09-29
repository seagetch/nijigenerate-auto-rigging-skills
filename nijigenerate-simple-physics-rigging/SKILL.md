---
name: nijigenerate-simple-physics-rigging
description: Add or repair nijigenerate SimplePhysics through njc for hair, cloth, tails, accessories, cords, and other secondary motion after authored deformation is stable.
---

# Nijigenerate Simple Physics Rigging

For the exhaustive SimplePhysics checklist, read `references/step-checklist.yaml`.
Run `references/result-audit-checklist.yaml` with the shared result audit/repair loop before saving or declaring Physics complete.

Always complete `references/step-checklist.yaml`. Start a checklist reviewer UI only when the user explicitly requests it; a user prohibition on reviewer/browser work overrides any legacy review instruction.

## Workflow

Use this skill together with `nijigenerate-shared-rigging-rules` for state safety, screenshots, and save discipline. Resolve `njc` from an explicit path, `NJC_PATH`, or `PATH`, then mutate the model only through that executable; do not hand-edit `.inx`.

Follow this order:

1. Audit target nodes and existing parameters/physics.
2. Define Physics parameters.
3. Add parameter deformations at neutral and extreme keys.
4. Add SimplePhysics as a child of the moving target or its control node.
5. Assign the SimplePhysics target parameter.
6. Tune SimplePhysics settings.
7. Verify with screenshots and, if possible, physics playback/reset.
8. Run the result audit read-only, repair every `RETAKE`, and rerun the full result checklist from item 1 until every applicable current-stage item is `OK`.

Do not assign a SimplePhysics node to a Physics parameter until the Physics parameter's deformation keys have been authored. If a SimplePhysics node already exists while revising the parameter, clear or ignore its assignment first, re-author/verify the deformation keys, then assign the parameter again.

When changing the parameter assignment of a SimplePhysics node, first disable the puppet-wide physics/drivers option, then clear or set the SimplePhysics parameter, and only re-enable physics/drivers after all assignment and setting commands are complete. Do not change `NodeSimplePhysicsCommand_SetSimplePhysicsParameter` while global physics is enabled.

## 1. Parameters

Name parameters after the moving area plus `::Physics`, for example `BackHair::Physics`, `SideHair::L::Physics`, `Skirt::Physics`, or `Charm::R::Physics`.

Before creating parameters, plan the physics targets from both the current screen capture and the model part hierarchy. Identify every visually plausible moving area in this artwork, then decide whether it needs its own Physics parameter or can share a parameter with a nearby part. Check at least: front hair, side hair, back hair, skirt, ribbons/frills outside the skirt, head ornaments, animal ears, decorative cords, and other hanging or protruding accessories. Record the target node names/UUIDs and the reason each target is included or excluded before adding parameters.

Use a 2D parameter for flexible wide or long objects that should respond in X and Y, such as hair, skirts, sleeves, ribbons, and cloth. Use a 1D parameter for rigid or single-axis objects.

Use range `(-1, 1)`:

- 2D: call `ParamCommand_Add2DParameter` with `min=-1`, `max=1`, then name it with `ParamPropCommand_SetParameterName`. The X and Y parameter key values must each be `[-1, 0, 1]`, giving a 3x3 key grid. In `ParamPropCommand_ApplyParameterPropsAxes`, pass normalized breakpoints `[0, 0.5, 1]` for both `axisX` and `axisY`; these correspond to key values `[-1, 0, 1]`.
- 1D: call `ParamCommand_Add1DParameter` with `min=-1`, `max=1`, then name it. The parameter key values must be `[-1, 0, 1]`. In `ParamPropCommand_ApplyParameterPropsAxes`, pass normalized breakpoints `[0, 0.5, 1]` for `axisX` and an empty `axisY`.
- If the add command creates an unnamed parameter, immediately locate it by reading the parameter list or newest parameter, then rename before adding bindings.

## 2. Deformation Keys

Set the non-moving state at `(0, 0)` for 2D or `0` for 1D. Define left/right and up/down extremes for 2D: `(-1,0)`, `(1,0)`, `(0,-1)`, `(0,1)`. Add diagonal keys only when the object needs coupled behavior and linear interpolation is visibly wrong.

Treat `-1` and `1` as large physical extremes, not subtle preview offsets. At these endpoints the object should visibly swing or deform enough that the SimplePhysics solver has meaningful travel range. If the motion is barely visible at parameter max/min, increase the deformation key amplitudes rather than relying only on SimplePhysics output scale.

Use these authored-deformation amplitude ranges as starting points for full-body anime characters at this model scale:

- Front hair/fringe: about `120-150px` horizontal and `80-100px` vertical at the free tips.
- Long back hair: about `220-260px` horizontal and `140-170px` vertical at the lower tips.
- Front skirt/apron cloth: about `160-200px` horizontal and `100-130px` vertical at the hem.
- Back/outer skirt cloth: about `200-250px` horizontal and `120-150px` vertical at the hem.
- Integrated body/skirt cloth where the torso and skirt share a deformer: about `160-200px` horizontal and `100-130px` vertical below the waist, with zero offset at and above the waist line.
- Animal ears: about `70-90px` horizontal and `40-60px` vertical at the ear tip.
- Small head ornaments: about `40-70px` horizontal and `30-50px` vertical.
- Waist ribbons, frills, decorative cords: about `80-110px` horizontal and `60-80px` vertical at the hanging end.

These values are not tiny idle motion. They are parameter endpoint poses used by the solver; actual runtime motion is moderated by SimplePhysics and by the driving movement.

Treat the parameter as the solved displacement of a spring endpoint:

- Hair strands: root stays nearly fixed; middle and tip lag smoothly. Thin strands should curve like a cord, with tip displacement larger than mid displacement.
- Skirts and wide cloth: top/waist anchor stays mostly fixed; lower hem shifts more. Use shear-like deformation rather than translating the whole skirt as one plate.
- Ribbons or narrow cloth panels: use 3-4 meaningful freedom points along the length. The tip should move most, but intermediate points should ease the curve.
- Rigid objects: use transform rotation/translation or a simple 1D deformation. Avoid over-bending.

Decide the fixed endpoint and free endpoint before authoring keys. For hair, skirts, sleeves, long ribbons, and most hanging cloth, the upper attachment is usually the fixed endpoint and the lower side is the free endpoint. Author the deformation as if the free endpoint is pulled by the solved physics value while intermediate points follow with spring/cord delay. If the upper body and skirt are a single connected clothing piece, treat the waist or pelvis area as the fixed endpoint and the area below the waist as the free side; do not let the chest/torso part swing with the skirt physics. For animal ears or other upward protrusions attached at the base, reverse this: the lower base is the fixed endpoint and the upper tip is the free endpoint. Keep the fixed endpoint stable across all Physics keys unless a separate body/head deformation explicitly moves that attachment.

For GridDeformer or Part bindings, use `ModelCommand_SetDeformBinding` for shape keys and transform binding commands for whole-node motion when appropriate. Always keep anchors stable: hair roots, skirt waist, sleeve shoulders, and attachment points should not drift unless the artwork requires it.

## 3. SimplePhysics Node

Add `SimplePhysics` as a child of the object/control node that owns the movement. Prefer one SimplePhysics per independently moving area:

- Long hair left/right/back sections may need separate parameters and SimplePhysics nodes.
- A skirt can start with one `Skirt::Physics` node; split front/back/left/right only if the model needs independent phase or occlusion.
- Name the SimplePhysics node the same as the parameter when possible.

Use `Node_Add_SimplePhysics` or `Node_Insert_SimplePhysics` with a context selecting the target parent/child. After adding, read the created node UUID and rename it if needed.

## 4. Assign Parameter

Only do this after the deformation keys in step 2 are complete and verified to exist. The required order is: define parameter axes, author deformation keys, then assign the parameter to SimplePhysics. Do not create/assign SimplePhysics first and then add deformation keys afterward.

Before calling `NodeSimplePhysicsCommand_SetSimplePhysicsParameter` or `NodeSimplePhysicsCommand_ClearSimplePhysicsParameter`, disable global physics/drivers. After all SimplePhysics assignment and setting commands are complete, reset/re-enable physics/drivers and verify the assigned parameter is correct.

Assign the Physics parameter to the SimplePhysics node with:

```json
{
  "context": {"nodes": [SIMPLE_PHYSICS_UUID]},
  "parameter": PHYSICS_PARAMETER_UUID
}
```

using `NodeSimplePhysicsCommand_SetSimplePhysicsParameter`.

Clear or replace an existing assignment only after recording the old SimplePhysics node, target parameter, and settings.

## 5. Settings

For hair and skirts, set Mapping Mode to `XY` with `NodeSimplePhysicsCommand_SetSimplePhysicsMapMode`.

Initial tuning values:

- Set `Gravity` to `1.0` as the normal baseline for all SimplePhysics targets.
- Derive `Length` from the current model-space distance between the fixed attachment and the free endpoint. Do not use a fixed pixel-like constant copied from another model. Start near that measured distance, then reduce it when motion is too slow or wide and increase it only when the target demonstrably behaves too short.
- Front hair/fringe: `Frequency` around `1.7`, `LengthDamping` and `AngleDamping` around `0.2`.
- Long back hair: `Frequency` around `1.15`, `LengthDamping` and `AngleDamping` around `0.2`.
- Front skirt/apron cloth: `Frequency` around `1.25`, `LengthDamping` and `AngleDamping` around `0.2`.
- Back/outer skirt cloth: `Frequency` around `1.15`, `LengthDamping` and `AngleDamping` around `0.2`.
- Animal ears: `Frequency` around `1.9`, `LengthDamping` and `AngleDamping` around `0.2`.
- Small head ornaments: `Frequency` around `2.1`, `LengthDamping` and `AngleDamping` around `0.2`.
- Waist ribbons, frills, decorative cords: `Frequency` around `1.55`, `LengthDamping` and `AngleDamping` around `0.2`.
- Shorter targets normally need a shorter measured Length; longer targets normally need a longer measured Length. Do not substitute generic absolute ranges for measurement in the current model.

Tune the remaining settings after visual playback:

- `Frequency`: increase for snappier return, decrease for heavier motion.
- `LengthDamping` / `AngleDamping`: start around `0.2`; increase only if oscillation is too loose or noisy.
- `Gravity`: use `1.0` as the baseline.
- `OutputScaleX` / `OutputScaleY`: adjust if the simulation amplitude does not match the authored key deformation.
- `LocalOnly`: use only when parent/body motion should not feed the physics response.

Prefer small changes and screenshot comparisons. Physics should add secondary motion, not erase the authored Body/Yaw/Pitch depth work.

## Verification

Before saving final output:

1. Reset parameters and physics, then capture neutral.
2. Exercise the new Physics parameter at each authored key to confirm the deformation itself is correct.
3. Toggle or reset physics with `ViewportCommand_TogglePhysics` / `ViewportCommand_ResetPhysics` where available.
4. Capture representative pose screenshots, including front, side/diagonal body poses, and any skirt/hair occlusion-heavy pose.
5. Report parameter names, target UUIDs, SimplePhysics node UUIDs, mapping mode, length, and any non-default tuning values.
6. Re-read every Physics parameter binding after any automatic DepthBone/Grid refresh. Confirm that only its planned target UUIDs remain and that authored non-neutral keys are still present.
7. Compare all parameter target sets and the serialized/file size with the pre-pass audit. Stop before saving on an unrelated binding change or unexplained size jump.

If local image display has path issues, copy screenshots to an ASCII-only `/tmp/...` directory before displaying them.

## Task-specific procedures

- Read [time-based-tuning.md](references/time-based-tuning.md) for slower/faster motion, proportional Length changes or increased sway amplitude.

For these operations, also complete [references/change-result-checklist.yaml](references/change-result-checklist.yaml). Apply conditional items only to the requested scope.

For the relevant visual or recorded-data examples and their evidence limits, use the [example index](../nijigenerate-shared-rigging-rules/references/visual-example-index.md); procedural references link directly to their owned examples.
