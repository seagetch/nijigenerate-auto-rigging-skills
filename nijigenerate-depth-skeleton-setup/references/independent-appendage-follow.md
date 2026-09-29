# Independent hair and arm following

## Decision table

Before creating anything, write one row per moving region: attachment, rest direction, yaw source, pitch source, roll source, forward behavior, backward behavior, and blend extent. Use actual parameter semantics. A request for hanging on backward pitch does not authorize increasing forward deformation. Side hair, back hair and arms are separate decisions, not one shared preset.

## Procedure

1. Read current rest bones, coordinate frames, BoneSources, direct pose keys and parameter links. Capture neutral, yaw-only, pitch-only, mixed yaw/pitch and Roll. Keep the accepted attachment and rest shape.
2. For an independent origin, position a supported DepthBone at the anatomical attachment and verify its visible world transform. Resolve inheritance/LockToRoot from the live schema; do not assume ordinary parenting produces an independent frame.
3. Put the pitch articulation in the intended yaw-rotated frame. Under nonzero head yaw, inspect the actual world pitch axis and tip trajectory; rotation around a fixed world axis is not head-relative pitch. Do not compensate that mistake with Part shear.
4. If separate driven parameters are requested, create semantic parameter shells, author bone bindings, then link explicit source UUID/axis to destination UUID/axis through the schema-supported parameter-link commands. Record ranges/signs. Remove only superseded links; reject cycles and duplicate drivers. Internal linked parameters must not also be driven directly by Tracking.
5. For upper back-head hair versus lower hair, define anatomical landmark bands rather than an abrupt Y threshold. Assign both bone sources over the transition and vary their influence continuously using supported weights. Read actual weights; verify the sum/normalization behavior of the API instead of guessing. A helper may serialize an explicitly planned map, not invent its shape.
6. Split side/back bone controls when their requested forward/backward behavior differs. For backward hanging, keep roots attached and let lower joints move toward the reference hanging pose; retain the accepted forward row. For arms retain the forward body-follow pose and adjust backward joint motion toward the hanging direction. Keep bone lengths and elbow/wrist chain consistency.
7. Read back all links, bone keys and BoneSource entries. Test positive/negative yaw with positive/negative pitch and halfway values; verify the lower region follows body yaw when requested, upper hair follows head yaw/pitch, and unintended Roll inheritance is absent.
8. Compare all unrelated keys and base transforms. Do not regenerate standard rigging or remesh as part of link-only corrections.
