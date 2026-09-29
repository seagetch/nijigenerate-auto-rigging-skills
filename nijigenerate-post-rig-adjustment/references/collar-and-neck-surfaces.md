# Neck, standing collar and chest lapels

## General decision

The standing collar wraps the neck; the lower lapels and pendant attach to the upper chest; a free tip has its own local freedom. They need not inherit identical motion. Preserve physical design length; do not force constant screen length when the supporting chest is foreshortened.

## Procedure

1. At neutral, both Body yaw directions, forward/backward pitch and relevant Face/Roll combinations, label neck skin, collar base/top, lapel roots/tips, pendant and sternum landmarks in their supporting local frames.
2. Read each region's mesh ownership, clipping, Welding, parent motion and direct Part bindings. Identify double application or stale parent compensation before planning a new delta.
3. Keep the accepted standing collar fixed while correcting chest lapels, or vice versa. For a Part spanning both surfaces, identify separate vertex bands and a transition band; do not translate/rotate the whole Part merely to fix one band.
4. Derive lapel orientation and apparent shortening from the current rendered chest tangent and reference at that exact pose. Keep roots attached and both sides consistent with perspective. Correct local Part residuals; route wrong bone pose to its bone owner.
5. Inspect collar/skin occlusion, shoulder penetration and lapel length together. Check both left/right turns, forward/backward keys, halfway values and Face::Roll plus Body combinations. Record design-space consistency separately from projected length.
6. Read back every affected key and protected region. A save request records the current version; it does not overturn a prior visual rejection.

For the rejected neck/collar shear example, read [Ao visual examples](ao-visual-examples.md). Its failure images and generated candidates are explicitly distinguished from accepted results.
