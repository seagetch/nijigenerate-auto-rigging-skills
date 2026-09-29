# Scope, checkpoint and approval records

## General decisions

Keep the current user constraints separate from reusable rigging defaults. A per-model ban on Grid XY edits, source inspection, reload, generated images or remeshing is binding in its stated scope; it is not a universal ban to export into every skill. Later explicit authorization updates only the named scope. Do not ask again for an already authorized operation.

## Procedure: establish the active change

1. Read the latest user corrections and the current audit. Record requested outcome, target UUIDs/properties, actual parameter axes, permitted methods, protected state and saved baseline identity. Distinguish Grid depth arrays from Grid XY deform bindings.
2. For a request such as “this setting to one quarter”, record the value at the time of the instruction and compute the requested value once. On retry compare against that target; do not compound the factor. Do not reset a processor preset to change one field.
3. Maintain the concrete failing poses supplied by the user: full parameter vector, affected region, reference/capture, failure and expected result. A defect seen again reopens that result, even if an earlier YAML says OK.
4. Read the current tool schema. If a source-inspection restriction exists, use permitted schemas, model data and documentation; do not read the prohibited implementation to discover commands.
5. Apply only the owned change. Diff values as well as UUID sets. An automatic recalculation is still a change; it needs classification and evidence, not an exemption.

## Procedure: phase handoff

Use a scoped record for each item:

| Status | Meaning | Phase exit |
| --- | --- | --- |
| OK | Current evidence meets the applicable result | Allowed |
| RETAKE | Current stage owns a demonstrated defect | Repair before dependent work |
| UNVERIFIABLE | Applicable result lacks evidence | Obtain evidence before dependent work |
| DEFERRED | Work belongs to a specified later phase and is not a prerequisite here | Carry explicitly to that phase |
| NOT_APPLICABLE | Outside this task or absent by design | Record the reason |

For DEFERRED record item, reason, owning later phase, prerequisites, revisit trigger and exit evidence. Example: blink deformation during mesh setup may be deferred to the eye phase; eyelash mesh gaps during mesh setup may not. Run all current checks; do not skip inspection because one fails. Close carried items when their owner runs. No unresolved applicable item may be called overall completion.

For reviewer UIs limited to OK/Retake, keep deferred/out-of-scope items in a separate phase manifest; do not encode them as fake OK rows. Start a reviewer only if requested. No UI schema change is implied by this document.

## Procedure: recover without reload

After any error or unrelated refresh, re-read affected state before retry. Compare with the saved pre-operation values and dependency graph. Where the live schema supports exact restoration, restore only changes caused by this operation through njc, then compare all affected values and re-run the regression poses. Do not restore user edits made since the baseline. Do not use blind repeated Undo, regenerate a rig, or reopen a model as an implicit recovery step. If safe local restoration is unavailable, report the concrete blocked operation and continue independent authorized work; elapsed time is not permission.

## Approval and save evidence

Track separately: authorization to change; candidate selected; visual quality decision; save destination/version. Quote or identify the user decision supporting each. “Save this as latest” authorizes saving the current state, not an assertion that rejected appearance is now accepted. Save a requested current snapshot with its outstanding issues; reserve “verified complete” for fulfilled criteria. An explicit current-state save can override a skill's default final-save timing, but never makes failed checks OK.

For before/after comparison use the same camera/projection/world scale, not independently fitted part boxes. Show local defects and surrounding body connections, and revisit reported mixed Face/Body/Roll poses. Numeric preservation and visual anatomy are separate results.
