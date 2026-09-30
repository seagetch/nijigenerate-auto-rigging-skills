# Pelvis-driven front and back skirt bones

## Decision

A lower garment attaches to pelvis/waist, not automatically to upper-chest pitch. Front/back surface position, yaw rotation and vertical travel are separate responsibilities. Reparenting alone does not prove a parameter drives the new parent.

## Procedure

1. Inventory skirt, apron, side panels, rear/side trains and attached accessories within the requested scope. Record their existing bone sources and links. Classify the waist contact band versus free cloth.
2. Mark front/back/side attachment and hem locations in the current 3D model frame, using accepted depth and visible artwork. Do not infer depth from zSort or copy front Z to rear bones.
3. Define the independent skirt origin and front/back bones with rest heads on the waist attachment and tails along their surfaces. Preserve neutral world positions when changing sources/hierarchy. If Grid membership/topology must change, route to the rigged-mesh procedure first.
4. Trace the actual Body yaw axis to the waist origin; a parent named Pelvis may translate without rotating in that rig. If the needed yaw is absent, bind the independent skirt origin to the intended Body yaw through current njc schemas, or use an explicitly requested linked control. Record which is used. Verify sign, angle and the yaw-rotated local frame. Keep upper-body-only pitch separate; for a yaw-only helper, use the same yaw value across pitch keys. Preserve intended pelvis translation/Roll and avoid adding yaw twice when ancestors already supply it.
5. Assign front/back/side sources to their matching surfaces. Check whether a non-yaw source dilutes the intended rotation or a nested Part/Grid applies motion twice. Correct only the diagnosed source or hierarchy edge, preserving accepted source depthScale/depthOffset and effective draw order. Blend the waistband continuously into the torso/pelvis seam; let lower cloth receive its intended independent motion. Neither zero Pelvis weights nor add both-leg chains by default. Do not weld a whole skirt to the chest.
6. Exercise pelvis yaw and vertical movement independently, then Body yaw/pitch combinations. Confirm the origin actually rotates and translates, both garment faces stay attached, and upper-chest tilt does not tip the skirt as a rigid plate.
7. Recheck adjacent torso and legs, including front-bend waist contact and back hem. Preserve depth/meshes/zSort for a source/link-only request. Inspect rendered front/apron/back/side/attached-accessory motion as well as the bone transform, including intermediate Body values and Face-only tests. Classify native regenerated deformation differences separately from manual contour changes.

## Recorded example

Read [Ao skirt following](ao-skirt-follow-example.md) when Body yaw is missing after pelvis reparenting, source blending weakens rotation, or a nested garment receives motion twice. It includes the historical direct bone binding, 3D front/back placement, sanitized numeric evidence and comparison images. The example is not a current quality approval or a preset.
