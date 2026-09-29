# Limb Root Positioning Method

This reference gives the detailed procedure for moving existing limb root Nodes in nijigenerate without moving their child artwork. It complements `nijigenerate-model-setup`.

## Required Context

Before editing, inspect:

- Current tree: root block, limb root Node, child Parts/GridDeformers, and any helper Nodes.
- Node resources: `type`, `transform.trans`, `lockToRoot`, `pinToMesh`, and `zsort`.
- Part meshes: vertex bounds and visual shape of the limb/clothing panel.
- Existing parameters and bindings on the target Node and descendants.
- User-doc structure references from the active repo, especially model structuring chain/root guidance.

Relevant baseline references:

- `nijigenerate-model-setup/SKILL.md`
- `nijigenerate-model-setup/references/model-setup-method.md`
- This skill's copied `references/user-doc/` files when user-doc guidance is needed.

## Attachment Point Heuristics

Use the visible shape and the anatomical connection, not the center of the mesh or texture.

### Arms

The root is the shoulder socket or sleeve cap hinge.

- Place it near the top of the upper-arm shape where it enters the torso/shoulder cloth.
- In A-pose, the arm descends diagonally, so the root is not directly above the part center. Move X toward the torso and Y upward from the visual center.
- For sleeves over arms, use the seam/hinge under the shoulder cloth. If a sleeve has a broad puff, the pivot is still at the attachment seam, not the puff center.
- Mirror left/right roots around the model center. If the torso is centered on `x=0`, use opposite X values and matching Y values.

### Legs

The root is the hip socket or upper-thigh attachment.

- Place it near the top of each thigh where it enters the pelvis/shorts/skirt, not at the thigh center.
- Near-vertical legs mainly require Y correction, but X still identifies the left/right hip socket.
- Separate left and right leg roots. A shared `*Legs` root is acceptable only as a container above two independent leg roots.
- Keep hip roots inside the pelvis width; do not push them to the outer edge of the thigh unless the artwork explicitly shows a side-attached limb.

### Hands And Feet

- Hand root: wrist joint at the narrow connection to the forearm/sleeve.
- Foot root: ankle joint at the top of the shoe/foot, not the center of the shoe sole.
- If a shoe has separate toe/heel parts, the foot root remains ankle-oriented; toe/heel get their own secondary pivots if needed.

### Tail, Wings, Ribbons, Cloth

- Tail root: base where it exits the body/clothing, often behind pelvis or lower back.
- Wing root: shoulder blade/back attachment, not the wing center.
- Ribbon/strap root: knot, pin, seam, or attachment point.
- Dangling cloth root: seam or belt connection.

## LockToRoot Reposition Procedure

Use this when changing a parent/root Node's transform while child artwork must stay visually fixed.

1. Read the root Node and all direct children/subtree roots.
2. Record each affected descendant's current `lockToRoot` value.
3. Apply `LockToRoot=true` only to descendants that must remain visually fixed. Usually this is each direct child of the root being moved; deeper descendants inherit the protection through their subtree root.
4. Move the root Node to the new attachment point.
5. Read back the root transform and child transforms.
6. Restore every touched descendant's `lockToRoot` to its recorded original value.
7. Verify visual position and hierarchy.

Important: do not unlock a child that was already locked before the operation.

## Command Pattern

Use command names from the active build. In the current build:

```bash
njc tools call Inspector_Apply_LockToRoot --json '{"context":{"nodes":[CHILD_UUID]},"value":true}'
njc tools call Inspector_Apply_TranslationX --json '{"context":{"nodes":[ROOT_UUID]},"value":123.0}'
njc tools call Inspector_Apply_TranslationY --json '{"context":{"nodes":[ROOT_UUID]},"value":-456.0}'
njc tools call Inspector_Apply_LockToRoot --json '{"context":{"nodes":[CHILD_UUID]},"value":false}'
```

When setting translation, preserve untouched axes and be aware whether the command expects local transform values. Confirm by reading the resource after each move.

## Symmetry Procedure

For a pair of roots:

1. Decide center `cx`. Use `0` only if the model's body center is actually `x=0`.
2. Determine one side from artwork, then mirror: `other_x = 2 * cx - x`.
3. Use equal Y for symmetric anatomy unless the artwork intentionally differs.
4. Check both resource transforms and screenshots.
5. If the parts are named with `::L`/`::R`, verify that left/right naming matches screen/model convention used by the project.

## Failure Signs

- Moving the root also moves the visible limb because children were not locked.
- The pivot ends up at the mesh or texture center.
- A-pose arm pivot only moved in Y and remains outside the shoulder socket in X.
- Legs share one root or have pivots at thigh centers.
- Left/right roots are visually symmetric but numerically asymmetric due to an unrecognized model center.
- LockToRoot remains enabled on children that were previously unlocked.
- Existing yaw/pitch/roll parameters start rotating around the old or wrong point.
