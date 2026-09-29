# Eye-Part Visibility And Delta-Only Retake

## Contents

1. Eye-part responsibilities
2. Static zSort through njc
3. Required visibility matrix
4. Default-state and crop gates
5. Delta-only Retake
6. Required readback
7. Bundled scripts

## 1. Eye-Part Responsibilities

Use these responsibilities unless the active model has a reviewed, explicit alternative:

| Part | Blink deform | Blink opacity | Blink zSort | Static Part zSort |
|---|---|---|---|---|
| Eyelash | yes | no | no | verify/set |
| Eyewhite | Y only; every X delta is zero | no | no | verify/set |
| Iris | no | no | no | verify/set |

Do not treat Iris disappearance as a geometry task. Preserve the Iris and use the eye's clipping relationship plus static Part zSort so it is visible when open and occluded when the lash/white closure band covers it.

Do not hardcode zSort numbers from another model. Read all three Parts and choose the smallest model-specific static ordering that passes the visibility matrix.

## 2. Static zSort Through njc

Apply ordinary Part zSort without parameter or armed-parameter context:

```json
{
  "context": {"nodes": [TARGET_UUID]},
  "value": STATIC_ZSORT
}
```

Call `Inspector_Apply_ZSort` through the resolved `njc`. A payload containing `parameters`, `armedParameters`, or `parameterValue` creates or edits a parameter Binding and is prohibited for this task.

After applying, verify both conditions:

1. `resource://nijigenerate/resources/TARGET_UUID` reports the intended static `data.zsort`.
2. `find Binding` contains no Blink binding named `zSort` or `zsort` for Eyelash, Eyewhite, or Iris.

Do not repair static zSort by rerunning lash or white deformation generation.

## 3. Required Visibility Matrix

Capture every actual expression row at every Blink-X key. At minimum verify:

| Pose | Eyelash | Eyewhite | Iris |
|---|---|---|---|
| exact authored default/open | original silhouette | visible | visible |
| intermediate keys | smooth thickening/closure | vertically narrows without X change | remains unchanged and is progressively occluded |
| full neutral close | closed band, no detached line | no exposed white | no exposed Iris color |
| full smile close | expression curve with fixed endpoint neighborhoods | no exposed white | no exposed Iris color |
| full deep close | distinct relaxed curve | no exposed white | no exposed Iris color |

If full closure passes but the authored default loses Iris or white, reject the candidate immediately.

## 4. Default-State And Crop Gates

Before mutation:

1. set both Blink parameters to their exact authored defaults;
2. capture the full current view;
3. create or select a face crop containing both eyes at inspection resolution;
4. record the full screenshot hash, crop bounds, and eye pixel widths.

After every mutation:

1. reset both Blink parameters to the exact defaults;
2. capture again at the same view;
3. compare open visibility, silhouette, and image hash/pixel difference;
4. reject unexplained changes before applying another fix.

Never reuse an absolute crop merely because its coordinates worked earlier. After camera, zoom, pan, canvas, or model-view changes, verify that the crop still contains both complete eyes. Reject a crop showing hair, ears, background, or only a fragment of one eye.

## 5. Delta-Only Retake

When a result item fails:

1. identify the exact parameter UUID, target UUID, binding name or static property, expression row, and Blink-X keys;
2. snapshot the failed resource and hashes of every accepted eye binding/property;
3. create a dry-run plan listing only those failed rows/properties;
4. apply only that plan through resolved `njc`;
5. immediately read back the changed resource;
6. verify hashes of all accepted resources remain unchanged;
7. rerun the complete result checklist and the full visibility matrix.

Examples:

- A wrong static Iris zSort changes only the Iris Part `zsort` property.
- A thin upper lash changes only upper-boundary vertices for the affected key rows; hold the seam, lower boundary, and canthi fixed.
- An apparent smile canthus drift changes only the affected eye, smile row, and endpoint-neighborhood vertices; hold the actual canthus endpoint fixed.

Do not rerun a full rig generator for these Retakes unless the dry-run proves that every accepted binding value will remain byte-equivalent.

## 6. Required Readback

Record:

- parameter UUIDs, exact axes, defaults, and tested key matrix;
- Eyelash/Eyewhite/Iris UUIDs;
- static opacity and zSort for all three Parts;
- absence of Iris Blink deform/opacity/zSort bindings;
- absence of Eyewhite Blink opacity/zSort bindings;
- zero X deltas in every set Eyewhite deform key;
- exact canthus positions plus adjacent segment/tangent evidence;
- painted lash thickness at inner, center, and outer thirds;
- pre/post default screenshots and crop validity;
- hashes for unchanged accepted bindings/properties;
- whether `FileCommand_OpenFile` and `FileCommand_SaveFile` were avoided.

## 7. Bundled Scripts

Use `scripts/audit_blink_bindings.py` with a model-specific JSON spec:

```json
{
  "eyes": [
    {
      "side": "L",
      "parameter": 1,
      "lash": 2,
      "white": 3,
      "iris": 4
    }
  ]
}
```

It performs read-only checks for Iris binding absence, Eyewhite Y-only deformation, prohibited opacity/zSort bindings, and readable static Part properties.

Use `scripts/apply_blink_plan.py` for explicit delta-only changes. It is dry-run by default and requires `--apply` to mutate the live model. The plan format is:

```json
{
  "irisTargets": [4],
  "whiteTargets": [3],
  "removeBindings": [
    {"parameter": 1, "target": 4, "bindingName": "deform"}
  ],
  "deformEdits": [
    {
      "parameter": 1,
      "target": 3,
      "parameterValue": [1.0, 1.0],
      "values": [0.0, 2.0, 0.0, 1.5]
    }
  ],
  "staticZSort": [
    {"target": 4, "value": 5.0}
  ]
}
```

The script rejects Iris deformation, nonzero Eyewhite X deltas, parameterized static-zSort payloads, and unplanned binding-row changes. Supply actual model UUIDs, key values, vertex arrays, and reviewed zSort values; never copy the example numbers into another model.
