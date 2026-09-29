# Result audit and repair loop

Use this loop with a specialist skill's `result-audit-checklist.yaml`. The
checklist verifies the model result and evidence, not merely whether commands
were issued.

## Evidence record

For every checklist item, record:

- item ID and explicit target UUID/name;
- expected model result;
- observed numeric/readback result;
- visual evidence path and exact parameter value when appearance matters;
- status: `OK`, `RETAKE`, `UNVERIFIABLE`, or a reasoned `DEFERRED` / `NOT_APPLICABLE` under [scope-and-checkpoints.md](scope-and-checkpoints.md);
- cause class and owning skill for every failure.

Command success text is not evidence. Prefer an `njc` readback plus a current
exact-key screenshot for visual claims.

## Required loop

1. Run the entire result checklist read-only in item order.
2. Mark every item independently. Do not stop at the first failure and do not
   infer unchecked items from a neighboring result.
3. If any item is `RETAKE`, make a correction plan containing only the failed
   targets and the responsible specialist skill.
4. Apply the smallest in-scope correction through resolved `njc`.
5. Re-read the changed state immediately. After an error-looking response,
   re-read before retrying because the command may already have mutated state.
6. Rerun the full checklist from item 1, including items that previously passed.
7. Repeat until every current-stage applicable result is `OK`; carry genuinely later-stage items through the explicit deferred manifest.

Do not convert `UNVERIFIABLE` to `OK`. Obtain the missing readback/screenshot or
report the blocker.

## Gates

- Do not hand off with an unresolved current-stage prerequisite. A later-stage DEFERRED item may travel with its owner/revisit record; it is not an OK result.
- Do not save a final model merely because the mutation commands completed.
- Stop before saving on an unrelated binding, hierarchy, mesh, DepthBone,
  BoneSource, mask, Physics, or unexplained serialized/file-size change.
- Start a reviewer/SPA only when the user explicitly requests it; the audit loop
  itself is performed with `njc` readbacks and current captures.
