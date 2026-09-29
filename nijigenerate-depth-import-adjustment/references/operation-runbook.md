# Operation runbook

Read this file completely before changing a model.

## 1. Resolve `njc`

Resolution order:

1. an explicit executable path supplied for the task;
2. `NJC_PATH`;
3. `Get-Command njc`;
4. a user-approved/configured nijigenerate checkout or a bounded search for `njc.exe`.

Do not store one machine’s absolute path in the skill and do not assume `./out/njc`.

```powershell
$njc = $env:NJC_PATH
if (-not $njc) {
    $njc = Get-Command njc -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty Source -First 1
}
if (-not $njc -or -not (Test-Path -LiteralPath $njc)) {
    throw "Resolve njc before continuing"
}
& $njc --help
```

Run `& $njc tools list`, parse `result.tools`, and extract the exact schemas for every planned command. Tool availability and payloads are versioned facts.

## 2. Safe PowerShell JSON calls

Build payloads as PowerShell objects and serialize with sufficient depth.

```powershell
$payload = @{
    context = @{ nodes = @($targetUuid) }
    target = [uint64]$targetUuid
    depths = [double[]]$depths
} | ConvertTo-Json -Compress -Depth 30
```

Windows PowerShell/native argument handling may remove JSON quotes. If a direct call is rejected as malformed JSON, pass an escaped copy:

```powershell
$nativeJson = $payload.Replace('"', '\"')
& $njc tools call DepthMapCommand_SetDepths --json $nativeJson
```

Immediately parse the response. On any error, re-read the affected target before retrying.

## 3. Baseline reads

Use live resources, not cached UUIDs:

```powershell
& $njc find '*'
& $njc read $targetUuid
& $njc tools call DepthMapCommand_ListDepths --json $targetPayload
```

For every target, record:

- UUID, name, class, parent, and effective transform;
- grid axis X/Y and expected depth-array length;
- current depth min/max/mean, zero count, and a hash of the ordered array;
- BoneSources and DepthRig ancestry;
- relevant parameter names, UUIDs, axes, keys, and current values.

## 4. PSD-depth dialog sequence

Open:

```text
FileCommand_OpenPSDDepthMapDialog
  path: absolute depth-image path
```

Inspect immediately:

```text
PsdDepthDialogCommand_InspectPsdDepthDialog
```

Use current schemas for:

- `SetPsdDepthDialogColorSource`
- `SetPsdDepthDialogInvert`
- `SetPsdDepthDialogBackDepth`
- `SetPsdDepthDialogFrontDepth`
- `SetPsdDepthDialogDepthScale`
- `SetPsdDepthDialogChannel`
- `SetPsdDepthDialogSampling`
- `SetPsdDepthDialogCustomRadius`
- `SetPsdDepthDialogAlphaThreshold`
- `SetPsdDepthDialogMissingPolicy`
- `SetPsdDepthDialogContourRepair`
- `SetPsdDepthDialogSurfaceSmoothing`
- `SetPsdDepthDialogDirectGridMatch`
- layer mapping, enable, visibility, depth enable, inversion, scale, and offset commands.

Use `SetPsdDepthDialogLayerMappingTarget` when automatic mapping is wrong. Select targets through `context.nodes` for `GetPsdDepthDialogPartData`.

For each enabled target, preserve a pre-apply audit containing its composed depth data, preview metadata, min/max, zero/missing count, and selected mapping.

## 5. Alpha-depth gap repair

`PsdDepthDialogCommand_FillPsdDepthDialogAlphaDepthGaps` operates on the open dialog. It is undoable and may require more than one pass.

After each pass:

1. inspect the dialog;
2. re-read target part data;
3. compare missing/zero counts;
4. compare continuity across artwork-covered samples;
5. stop if improvement stalls.

Do not fill intentional transparent background. The failure being repaired is alpha-covered artwork with absent depth, not every zero in the source image.

## 6. Apply and post-import audit

Apply only once every enabled target passes:

```text
PsdDepthDialogCommand_ApplyPsdDepthDialog
```

Read every imported GridDeformer with `DepthMapCommand_ListDepths`. Confirm array length, range, missing count, and selected spot samples. Save the audit before local corrections.

## 7. Local depth edits

Create an explicit numeric array. Do not transform JSON through an `OrderedDictionary` or sparse associative structure; that can coerce untouched entries to zero.

After `DepthMapCommand_SetDepths`:

1. re-list depths;
2. compare only intended indices;
3. assert untouched indices are bitwise or tolerance-equal;
4. verify array length and hash;
5. capture an exact-key screenshot.

Map a child Part to its parent GridDeformer in this order:

1. read the Part bounds and transforms;
2. convert the visible problem point to parent-grid local coordinates;
3. locate adjacent grid rows/columns from the actual axes;
4. bilinearly sample parent depth;
5. compare with nearby effective surfaces, including node Z/global depth scale;
6. edit a small contiguous neighborhood with falloff.

## 8. Whole-node Z

Use `Inspector_Apply_TranslationZ` with `context.nodes` when the entire surface must move forward/backward while preserving local shape. Read back local and world transforms and confirm the visual shift at an exact yaw/pitch key.

Do not emulate this by adding a constant to all grid depth values.

## 9. Fit Z to Depth

The app routine samples the nearest usable scaled world depth at each DepthBone’s current world XY from eligible DepthMapped GridDeformers. It computes:

```text
newLocalZ = currentLocalZ + (sampledWorldDepth - currentWorldZ)
```

It updates `translation.t.z` and marks all keypoints dirty for the armed depth parameter.

Before invoking Fit Z or reproducing its refresh behavior, follow
`nijigenerate-shared-rigging-rules/references/parameter-state-isolation.md`.
The armed parameter must be the intended standard Depth parameter, never a
`::Physics` parameter. Snapshot every parameter's binding count, target UUID
set, `isSet` state, and the serialized/file size before the operation.

At runtime:

1. search `tools list` for a literal Fit Z command;
2. if present, use it and verify every bone;
3. if absent, inspect the current nijigenerate source that implements `ngFitDepthRigNodeTranslationZToCurrentDepth`;
4. reproduce its result only through exposed `njc` reads and mutation commands;
5. use `Inspector_Apply_TranslationZ` per DepthBone for the computed local Z;
6. refresh the relevant armed-parameter state using the current exposed DepthBone rest/binding commands;
7. re-read local/world Z and independently recompute the expected values.

After the operation, diff every parameter, not only the armed one. Stop without
saving if an unrelated target or binding changed, a Physics binding lost its
authored keys, or the size increase cannot be explained by the intended payload.

Never say “Fit Z to Depth was executed” when only the equivalent was performed. Report “Fit Z相当処理” and cite the numeric verification.

Run this after all depth import/local corrections and before:

```text
DepthBoneCommand_AddStandardDepthParameters
```

If standard parameters already exist, do not add duplicates. Audit them and update only what the task authorizes.

## 10. Screenshot and save discipline

- Set exact parameter keys using `ParameditCommand_SetParameterKeypoint`.
- Capture neutral, yaw endpoints, pitch endpoints, and relevant corners.
- Screenshot nondeterminism is possible; verify numeric state and the local visual region instead of relying only on image hashes.
- Restore neutral before saving.
- Save with `FileCommand_SaveFile` and property `file`, not `filename`.
- Do not overwrite an accepted pass unless explicitly requested.
