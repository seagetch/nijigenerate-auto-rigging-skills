# Manifest Format

Use schema `review-viewer-manifest-v1`.

## Common Fields

```json
{
  "schema": "review-viewer-manifest-v1",
  "mode": "mesh-selection",
  "model": {
    "id": "stable-review-id",
    "name": "Human readable review name",
    "createdAt": "2026-05-04"
  },
  "review": {
    "schema": "mesh-selection-review-v1",
    "mode": "mesh-selection",
    "resultsDir": "reviews",
    "latestReview": "reviews/latest-review.json"
  },
  "assets": {
    "original": "images/neutral-fit.png"
  },
  "targets": [],
  "initialTags": "tags/initial-tags.json",
  "notes": {
    "projection": {
      "yawDeg": 30,
      "pitchDeg": 20,
      "pitchOrder": "local normal tilt first, then yaw",
      "pivot": "Head::Root for head-attached surfaces; reviewed Body pivot for Body/Chest/clothing"
    }
  }
}
```

The SPA resolves relative paths from the manifest directory. A browser URL can select a manifest:

```text
http://127.0.0.1:5173/?manifest=/projects/my-review/manifest.json
```

The Vite server accepts only public URL paths such as `/projects/example/manifest.json`, or URLs on the exact viewer origin. Filesystem absolute paths, `file://`, remote origins, traversal, and symlinks are rejected. Copy project files into `review-viewer/public/projects/<project-id>/`; do not symlink them. Asset URLs must stay below the manifest directory.

Set `review.resultsDir` to `reviews` (or a relative descendant directory ending in `/reviews`). Set `review.latestReview` to a `.json` file directly inside that directory. Do not use absolute paths or `..`. API responses return project-relative output names. POST requests require the viewer's exact `Origin` and `Content-Type: application/json`; external pages and network clients are refused.

## Depth Review Mode

Use this whenever a nijigenerate depth map is created or revised. The review must reach `reviewResult.decision: "ok"` before deformation keys are generated from that depth map.

```json
{
  "schema": "review-viewer-manifest-v1",
  "mode": "depth",
  "review": { "schema": "depth-review-v1", "mode": "depth" },
  "assets": { "original": "images/original.png" },
  "targets": [
    {
      "key": "body",
      "label": "Body",
      "image": "images/body-mesh.png",
      "grid": { "calibration": "calibration/body-grid.json" },
      "depth": { "file": "depth/body-depth.json", "path": "$" },
      "color": "#54d5ff"
    }
  ]
}
```

Depth mode supports point/range tags, comments, global comments, grid calibration, Original/Mesh image switching, and a 3D preview using the original image as texture. Use tags to identify the feature-to-grid mapping that justifies the depth values; examples include eyes/nose/mouth for face, neck/shoulders/chest/waist/pelvis for body, or front/back/side-wrap/hem for clothing.

For nijigenerate depth reviews, include the projection assumptions in `notes.projection`. The default is yaw 30 degrees and pitch 20 degrees. Face/head-attached surfaces must declare the Head::Root-local pivot. Body reviews must declare the upper/lower pitch split or row/region attenuation used to keep the lower body from behaving as a flat board.

## Mesh Selection Mode

Use this when the user selects existing layer mesh vertices and edits deformation arrows. There is no 3D view and no grid requirement. This is the required mode for direct face/body Part residuals such as cheek contour cleanup, jaw-cheek transition correction, breast-cup contour residuals, hip/bottomwear side wrap, or local Body surface fixes.

```json
{
  "mode": "mesh-selection",
  "review": { "schema": "mesh-selection-review-v1", "mode": "mesh-selection" },
  "assets": { "original": "images/neutral-fit.png" },
  "targets": [
    {
      "key": "yawRight",
      "label": "Yaw +1",
      "image": "images/yaw-right-fit.png",
      "meshes": "meshes/bottomwear-front.json#/targets/yawRight",
      "deformations": "deformations/yaw-right.json#/targets/yawRight",
      "color": "#54d5ff"
    }
  ],
  "initialTags": "tags/initial-tags.json"
}
```

The mesh JSON target contains one or more mesh items:

```json
{
  "targets": {
    "yawRight": [
      {
        "id": "bottomwear-front",
        "label": "Bottomwear::Front",
        "color": "#54d5ff",
        "vertices": [[0, 0], [100, 0], [0, 100]],
        "triangles": [[0, 1, 2]],
        "reviewTransform": {
          "type": "capture-live-screenshot-source-to-image-points",
          "sourceToImage": [
            { "index": 0, "source": [0, 0], "image": [400, 300] }
          ]
        }
      }
    ]
  }
}
```

For nijigenerate captures, use `ViewCommand_CaptureLiveScreenshot` with mesh overlay and read only `overlayMappings[].points[]`.

Hard coordinate rule:

- The review mesh `vertices` must be the corresponding `overlayMappings[].points[].image` values.
- `points.image` is in the captured PNG coordinate system: origin at image top-left, X rightward, Y downward, unit pixels, valid range `[0,width] x [0,height]`.
- `points.source` is model/source-space correspondence metadata. It is not a review display coordinate.
- Use `points.source -> points.image` only when converting accepted image-space deformation arrows back to model/source-space values for `ModelCommand_SetDeformBinding`.
- Do not use obsolete transform matrix fields, local mesh coordinates, source coordinates, or overlay coordinates as SPA-visible mesh positions.

Deformation JSON is keyed by target and mesh id:

```json
{
  "targets": {
    "yawRight": {
      "bottomwear-front": {
        "12": { "x": -24.0, "y": 3.5 }
      }
    }
  }
}
```

The SPA displays arrow endpoints from these values and lets the user edit them with the Arrow tool.

Deformation arrows are also image-space pixel deltas. When a Retake edits arrows, invert the saved `points.source -> points.image` correspondence to calculate the model/source-space deformation values to apply.

### Direct Face/Body Residual Example

For face/body direct adjustment, the input is the same data the user will review:

```json
{
  "tags": [
    {
      "target": "yawRight",
      "kind": "meshSet",
      "label": "body side-wrap residual",
      "meshIds": ["bottomwear-front"],
      "vertexRefs": [
        { "meshId": "bottomwear-front", "vertexIndex": 46 },
        { "meshId": "bottomwear-front", "vertexIndex": 47 },
        { "meshId": "bottomwear-front", "vertexIndex": 48 }
      ],
      "comment": "Move only the outer contour; keep center/front detail unchanged."
    }
  ],
  "deformations": {
    "yawRight": {
      "bottomwear-front": {
        "46": { "x": -95, "y": 7 },
        "47": { "x": -145, "y": 8 },
        "48": { "x": -162, "y": 11 }
      }
    }
  }
}
```

After `OK`, apply those deltas with `ModelCommand_SetDeformBinding` or the established command for that node. Then capture the modified model, update the same manifest's images/mesh/deformation files, and require a second `OK` review for the applied result. A `Retake` after application becomes the next input JSON.

## Review Result

`OK` or `Retake` immediately writes `latest-review.json` and an archived timestamped review in `resultsDir`.

Important fields:

- `createdAt`: process only if newer than the last monitor state.
- `reviewResult.decision`: `ok` or `retake`.
- `globalComment`: overall instruction.
- `tags`: user-edited points, ranges, mesh selections, comments, and vertex refs.
- `deformations`: user-edited arrow deltas in mesh-selection mode.
- `gridCalibration`: user-edited calibration in depth mode.
