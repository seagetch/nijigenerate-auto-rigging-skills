# Parameter state isolation

Use this before and after any command that can trigger automatic DepthBone, GridDeformer, Fit Z, mesh, or binding refresh.

## Before mutation

1. Resolve the intended parameter UUID and exact target UUID set.
2. Read the current Armed Parameter and any exposed last-dirty parameter state. Never rely on GUI selection fallback.
3. Explicitly set command context with exactly one intended parameter and explicit nodes.
4. Reject Physics parameters as DepthBone refresh parameters.
5. Snapshot every parameter's binding count and `(target UUID, binding name)` set. For Physics parameters, also snapshot every key's `isSet`, moved count, min/max, and maximum displacement.
6. Record current serialized/file size when a save will follow.

## After mutation

1. Re-read the intended binding and confirm the exact key matrix and values.
2. Diff all parameters against the snapshot. An automatic refresh is not allowed to add bindings to unrelated parameters.
3. For each Physics parameter, confirm it still targets only its planned moving node and that authored non-neutral keys remain nonzero.
4. Treat an unexplained binding-count change or large serialized/file-size increase as corruption. Do not save.
5. Restore neutral and reset physics only after the data audit passes.

## Axis values

Distinguish normalized axis offsets from actual parameter values:

- normalized breakpoints: commonly `[0, 0.5, 1]`;
- actual values for a `-1..1` parameter: `[-1, 0, 1]`.

Mutation commands that accept `context.parameterValue` require actual values. Always read `axisValues` from the binding resource instead of reusing axis offsets.

## Value-level preservation

Snapshot and compare full values and isSet matrices of affected parameters, plus parameter-link sources/destinations. Equal binding counts and target UUIDs do not prove unchanged motion. Classify every numeric difference against the intended operation and serialization tolerance. For recovery and save semantics use [scope-and-checkpoints.md](scope-and-checkpoints.md).
