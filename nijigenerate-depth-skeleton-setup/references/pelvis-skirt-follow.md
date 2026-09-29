# Pelvis-driven front and back skirt bones

## Decision

A lower garment attaches to pelvis/waist, not automatically to upper-chest pitch. Front/back surface position, yaw rotation and vertical travel are separate responsibilities. Reparenting alone does not prove a parameter drives the new parent.

## Procedure

1. Inventory skirt, apron, side panels, rear/side trains and attached accessories within the requested scope. Record their existing bone sources and links. Classify the waist contact band versus free cloth.
2. Mark front/back/side attachment and hem locations in the current 3D model frame, using accepted depth and visible artwork. Do not infer depth from zSort or copy front Z to rear bones.
3. Define the independent skirt origin and front/back bones with rest heads on the waist attachment and tails along their surfaces. Preserve neutral world positions when changing sources/hierarchy. If Grid membership/topology must change, route to the rigged-mesh procedure first.
4. Connect intended pelvis yaw and translation to the origin. Inspect source and destination axes and ancestor inheritance to avoid double rotation. Keep upper-body-only pitch separate unless the garment design requires it.
5. Assign front/back/side sources to their matching surfaces. Blend the waistband continuously into the torso/pelvis seam; let lower cloth receive its intended independent motion. Do not weld a whole skirt to the chest.
6. Exercise pelvis yaw and vertical movement independently, then Body yaw/pitch combinations. Confirm the origin actually rotates and translates, both garment faces stay attached, and upper-chest tilt does not tip the skirt as a rigid plate.
7. Recheck adjacent torso and legs, including front-bend waist contact and back hem. Preserve depth/meshes/zSort for a source/link-only request.
