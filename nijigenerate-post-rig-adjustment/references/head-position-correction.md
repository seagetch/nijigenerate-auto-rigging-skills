# Head Position Correction

Use this procedure when the only visual goal is to place the head correctly relative to the neck and torso at Body yaw/pitch keys. `DepthBone::Neck`, `Head::Root`, and zSort are implementation layers for one visual goal; do not describe them as independent repair objectives.

## Scope and entry condition

- Standard Depth parameters, DepthRigRoot, and the existing Body parameter already exist.
- The neutral artwork, head/neck hierarchy, and BoneSources are readable through the current `njc` session.
- The defect is visible head displacement, head-to-neck separation, an overly long/short neck appearance, or a head/neck break at Body keys.
- If the neutral artwork itself has wrong depth, wrong hierarchy, or an incorrect BoneSource, stop and return to the owning depth or skeleton skill.

## Control layers

Inspect these layers separately before editing:

| Layer | What to read | Role in head placement |
|---|---|---|
| `DepthBone::Neck` | base TRS and `Body::Yaw-Pitch` bindings, especially `transform.r.x` | upstream neck orientation and parent propagation |
| `Node::Head::Root` | base TRS and `Body::Yaw-Pitch` `transform.t.x/y` bindings | head-position residual after neck motion |
| `Part::neck` | base transform, mesh, parent, and zSort | fixed neck artwork and draw order; not a default pose compensator |
| `DepthBone::Head` | base TRS and bindings | only edit when the Head bone itself is proven to be the source |

Never call `DepthBone::Neck` unchanged after reading only its node Transform. A large pose correction can exist entirely in its parameter Binding.

## Read-only diagnosis

1. Resolve the explicit `njc` executable and read the current tree without opening another model.
2. Capture or reuse current screenshots at neutral, Body `Yaw=-1`, `Yaw=+1`, `Pitch=-1` (forward pitch), `Pitch=+1` (backward pitch), and the failing corners.
3. Read the exact Body parameter axis values and identify the row/column order of every 5x5 Binding matrix.
4. Read both the node data and Binding resources. At minimum inspect:
   - `DepthBone::Neck` `transform.r.x`;
   - `Head::Root` `transform.t.x`, `transform.t.y`, and existing rotation bindings;
   - `Part::neck` transform, mesh, parent, and zSort;
   - `DepthBone::Head` only for source comparison.
5. Record `isSet`, keyed values, neutral status, target UUIDs, and all affected intermediate cells. JSON/resource output explains the numbers; screenshots decide whether the head is visually attached.

## Correction order

1. Correct the existing `DepthBone::Neck` Body binding only at keys where neck orientation causes the head to drift or the neck to appear too long/short.
2. Re-read the composed result at the same keys.
3. Add or adjust the smallest `Head::Root` `transform.t.x/y` residual needed to attach the head to the neck and torso.
4. Do not move `Part::neck` to compensate for a posed head displacement. Move it only when neutral artwork placement is independently wrong.
5. Change zSort only when the screenshot proves an occlusion/draw-order problem. Do not use zSort to hide a geometric displacement.
6. Do not regenerate standard Depth bindings and do not replace the full parameter with a projection formula.

When a parent Neck correction changes, recompute existing Head::Root residuals from the desired final pose minus the new composed parent result. Do not reuse stale child residuals.

## Acceptance

Accept only when all of the following are true:

- neutral head, neck, and torso are continuous;
- Body yaw and both pitch directions keep the head attached;
- the four corners do not create an extreme neck or head position;
- no rectangular neck artifact, unwanted occlusion, or head-only drift appears;
- neutral/start keys, unrelated bindings, mesh data, BoneSources, and physics remain unchanged;
- the final model is restored to neutral and read back through `njc` before saving.

## Image references

The following example captures are visual references for the required evidence shape. They are examples, not numeric templates. Recreate equivalent current-model captures for every task.

- [Neutral connected example](images/analysis-user-fix-latest-neutral.png)
- [Yaw +1 / Pitch +1 example](images/analysis-user-fix-yaw-plus1-pitch-plus1.png)
- [Pitch -1 example](images/analysis-user-fix-pitch-minus1.png)
- [Yaw -1 / Pitch +1 example](images/analysis-user-fix-yaw-minus1-pitch-plus1.png)

The important visual criterion is continuity from torso to neck to head across the same framing, not similarity to the example character.
