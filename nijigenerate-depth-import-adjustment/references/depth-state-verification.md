# Depth-state mutation and verification

Use this reference for every post-import depth correction.

## Preserve accepted state

- Save ordered depth arrays, dimensions, hashes, selected cells, overlay screenshots, transforms, and effective-depth samples.
- Treat user-corrected cell/feature mappings as authoritative.
- Show numeric differences from the accepted baseline instead of silently rebuilding a map.
- Re-read affected resources after any command error; some commands can partially mutate state.

## Distinguish Z mechanisms

| Mechanism | Meaning |
|---|---|
| GridDeformer depth array | Local surface relief |
| PSD layer depth scale | Import-time relief amplitude |
| PSD layer depth offset | Import-time depth-band placement |
| Node `translationZ` | Whole-node forward/back placement |
| `zSort` | Draw order only |

Do not replace one mechanism with another. Adding a constant to every grid depth is not a reliable substitute for node `translationZ`.

## Local edits

1. Map the visible problem to current grid cells.
2. Compare raw grid depth and effective world depth with nearby surfaces.
3. Change the smallest contiguous neighborhood that solves the problem.
4. Blend values into neighbors; avoid spikes, cliffs, and rectangular plateaus.
5. Send an explicit numeric array with `DepthMapCommand_SetDepths`.
6. Immediately re-read the ordered array.
7. Assert the same length, intended changed indices, and unchanged untouched indices.

Do not use sparse or `OrderedDictionary` transformations that can coerce unselected entries to zero.

## Effective-depth comparisons

Include:

- parent and child transforms;
- node `translationZ`;
- imported/global depth scale;
- bilinear or nearest grid sample at the visible problem location;
- nearby surfaces that can intersect at yaw/pitch.

Do not compare raw depth-array values from different nodes without accounting for their effective transforms.

## Visual verification

- Set exact parameter values with `ParameditCommand_SetParameterKeypoint`.
- Capture neutral, both yaw endpoints, both pitch endpoints, and affected corners.
- Inspect the local failure region in addition to the whole frame.
- Do not accept screenshot hashes alone; rendering can be nondeterministic.
- Restore the exact neutral key before saving.

## Fit Z and defaults

After every final GridDeformer/neck/head depth change:

1. perform the literal Fit Z to Depth command when exposed by current `njc`;
2. otherwise perform and clearly label the documented `njc`-only equivalent from `operation-runbook.md`;
3. re-read every DepthBone local/world Z;
4. independently compare fitted Z with sampled effective grid depth;
5. only then run `DepthBoneCommand_AddStandardDepthParameters`;
6. never create duplicate standard parameters.

## Save audit

Record:

- input image and import settings;
- source-layer to target-UUID mappings;
- gap-fill pass counts and before/after missing counts;
- per-layer scale/offset;
- changed GridDeformer UUIDs and indices;
- before/after depth ranges and hashes;
- node Z changes;
- Fit Z method and per-bone results;
- exact verification keys and screenshot paths;
- neutral restoration and unrelated-state checks;
- output path saved through `FileCommand_SaveFile.file`.
