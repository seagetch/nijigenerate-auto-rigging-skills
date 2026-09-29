---
name: nijigenerate-limb-root-positioning
description: Move nijigenerate limb or appendage root pivots safely through njc, using LockToRoot to preserve children for arms, legs, hands, feet, tails, wings, or ribbons.
---

# Nijigenerate Limb Root Positioning

For the exhaustive limb/root positioning checklist, read `references/step-checklist.yaml`.

Always complete `references/step-checklist.yaml`. Start a checklist reviewer UI only when the user explicitly requests it; a user prohibition on reviewer/browser work overrides any legacy review instruction.

## Workflow

Use this with `nijigenerate-model-setup` when model structure or limb pivots are being corrected. Read `references/limb-root-positioning-method.md` and `nijigenerate-shared-rigging-rules` before moving nodes.

1. Resolve `njc` from an explicit path, `NJC_PATH`, or `PATH`, then inspect the actual tree and resources; do not infer roots from names alone.
2. Identify the intended root Node for each limb chain. Prefer separate left/right roots for arms and legs.
3. Determine the anatomical attachment point from the controlled artwork, not the part bounding-box center.
4. Freeze all descendants that must not visually move by applying LockToRoot to each child/subtree root below the Node being repositioned.
5. Move the root Node to the attachment point using `TranslationX`/`TranslationY` or equivalent transform editing.
6. Release LockToRoot on the descendants that were frozen.
7. Verify the tree, transforms, symmetry, and screenshot/live view before saving.

## Root Placement Rules

- Arm root: shoulder socket/upper-arm attachment, usually above the visual center of the upper arm. In A-pose, move both X and Y because the upper arm slants away from the torso.
- Leg root: hip socket/upper-thigh attachment, normally near the upper inner/outer thigh connection to the pelvis. For near-vertical legs, Y matters most, but X must still be symmetric around the body center.
- Hand/foot root: wrist/ankle joint, not palm/sole center.
- Tail/wing/ribbon root: base where the appendage emerges from body/clothing, not the visible mass center.
- Clothing sleeve/skirt roots: seam or hinge line where the cloth is attached, not the geometric center of the cloth panel.

## Safety Rules

- Never move a parent Node with visible children without first freezing descendants with LockToRoot, unless the intended operation is to move the entire visual subtree.
- Record the original LockToRoot state of every descendant touched and restore it exactly. Do not blindly unlock nodes that were locked before the operation.
- For left/right pairs, compute mirrored coordinates from the intended model center. If the model center is `x=0`, enforce `left.x = -right.x`; if the model has an offset center, mirror around that actual center.
- After moving roots, parameter bindings may need review because existing transforms/deforms can be anchored to the old pivot.

## Commands

Use active tool names from `njc tools list`; common commands in this build include:

- `Inspector_Apply_LockToRoot` with `{"value": true|false}` for selected/context nodes.
- `Inspector_Apply_TranslationX` and `Inspector_Apply_TranslationY` for root Node position edits.
- Resource reads via `njc read <uuid>` and `resource://nijigenerate/resources/find?selector=*`.
- `ViewCommand_SaveScreenshot` or live screenshot tools for visual verification.

If command names differ in another checkout, inspect `doc/mcp_api.md`, `doc/commands.md`, and `source/nijigenerate/commands/inspector/apply_node.d`.

## Verification

- Children did not visually jump while the root pivot moved.
- The root marker is at the anatomical attachment, not the part center.
- Left/right roots are numerically symmetric and visually symmetric.
- A-pose arms have roots shifted both upward and inward/outward to the shoulder socket.
- Legs have independent roots at hip sockets, not a shared leg root and not thigh centers.
- LockToRoot states match the recorded original states after the operation.
- Existing parameters still behave plausibly after the pivot move.
