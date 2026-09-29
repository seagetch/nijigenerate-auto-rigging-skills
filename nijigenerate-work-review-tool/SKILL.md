---
name: nijigenerate-work-review-tool
description: Run the nijigenerate One Operation review SPA for mesh, depth, contour, or deformation work when the user explicitly requests visual OK/Retake review.
---

# Nijigenerate One Operation Review Tool

For the exhaustive SPA review-loop checklist, read `references/step-checklist.yaml`.

This skill packages the nijigenerate One Operation review tool: a manifest-driven SPA for reviewing rigging work through images, mesh overlays, tags, comments, vertex selections, and deformation arrows.

Use it only when the user explicitly requests a reviewer/SPA loop. A prohibition on reviewer or browser work is a hard stop for this skill. Depth, mesh, and Part work may use this tool when explicitly requested, but this skill is never an implicit prerequisite for those workflows.

This skill owns only the One Operation reviewer. Checklist review is a separate workflow owned by `nijigenerate-checklist-review-loop`; do not install, copy, or run a checklist reviewer from this skill.

## Bundled Tool

The SPA template is in `scripts/review-viewer-template/`.

Install it into a project:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/nijigenerate-work-review-tool"
node "$SKILL_DIR/scripts/install-review-viewer.mjs" --project "$PWD"
cd review-viewer
npm ci
npm run dev -- --port 5173
```

Open:

```text
http://127.0.0.1:5173/?manifest=/projects/<review-project>/manifest.json
```

The Vite plugin writes review JSON to the manifest-defined `review.latestReview`, normally:

```text
review-viewer/public/projects/<review-project>/reviews/latest-review.json
```

## Preconditions

- The current nijigenerate model is already loaded in the app if captures or mutations are needed.
- Resolve `njc` from an explicit path, `NJC_PATH`, or `PATH`; do not assume a repository-relative executable.
- Do not use `FileCommand_OpenFile` unless the user has explicitly authorized that file-open operation in the active task and has not revoked it.
- Create or reuse current review screenshots and mesh overlays; do not rely on stale captures after a model or binding change.
- For mesh-selection mode, review coordinates are image pixel coordinates from `ViewCommand_CaptureLiveScreenshot`: use `overlayMappings[].points[].image` as the mesh vertex positions shown in the SPA. The image coordinate origin is the captured PNG top-left, with X rightward and Y downward, in pixels.
- Preserve `overlayMappings[].points[].source -> .image` only as correspondence metadata for converting user-edited image-space arrows back to model/source-space deformation values. Do not display source/model/local coordinates as review vertices, and ignore older matrix fields.
- Keep a stable project directory under `review-viewer/public/projects/<review-project>/`.

## Workflow

1. Choose review mode.
   - `depth`: available for explicitly requested depth-map review; supports original/mesh image switching, grid/range/point tags, global comments, and 3D preview from depth data.
   - `mesh-selection`: available for explicitly requested direct face/body Part residual review; target meshes, selectable vertices, editable deformation arrows, no 3D view.
2. Generate review assets.
   - Capture neutral image and target overlay images with current model state.
   - For every mesh-selection target, build the reviewed mesh JSON from `CaptureLiveScreenshot` `overlayMappings[].points[].image` values. These `points.image` pixels are the only coordinates that should be displayed and edited by the user.
   - Save capture metadata if later calculations need source-to-image mapping; use it only to convert accepted image-space arrows back into model/source deformation values.
   - Export mesh JSON, deformation JSON, depth JSON, calibration JSON, and initial tags as needed.
3. Write `manifest.json`.
   - Read `references/manifest-format.md` when creating a new manifest or when uncertain about schemas.
   - Use relative paths from the manifest directory.
   - Set `review.resultsDir` and `review.latestReview`.
4. Launch the SPA.
   - Start Vite from the copied `review-viewer`.
   - Give the user the URL with `?manifest=...`.
5. Monitor review output.
   - Process only if `createdAt` is newer than the stored monitor state.
   - Always inspect `reviewResult.decision`.
   - Prefer explicit user edits in JSON over older assumptions.
6. Apply result.
   - `ok`: accept, write monitor state, stop monitoring, proceed to the next rigging step.
   - `retake`: use `tags`, `vertexRefs`, `deformations`, `comment`, `globalComment`, and `gridCalibration` as primary instructions. Apply the correction through `njc`, refresh review assets, keep the SPA usable, and continue monitoring.

## Depth Map Reviews

When the user explicitly requests a depth reviewer, use `depth` mode for Face, Body, Chest, hair, clothing, DynamicComposite, or front/back garment surfaces before generating deformation keys.

Required assets:

- Original image or neutral capture.
- Mesh overlay image for every reviewed GridDeformer/Part.
- Grid calibration or mesh readout that lets the viewer align tags to the artwork.
- Depth JSON for every target surface.
- Initial tags that label the feature-to-grid mapping, such as eyes, nose, cheeks, neck, shoulders, chest, waist, pelvis, hip, hem, or side-wrap.

Required loop:

1. Generate the proposed depth map as `NOT APPLIED`.
2. Publish it in the review viewer manifest.
3. Monitor `latest-review.json`.
4. If `retake`, update the depth JSON and tags from review edits and comments, regenerate assets, and continue.
5. If `ok`, record monitor state and only then create or replace rigging bindings.

While an explicitly requested review loop is active, do not substitute a one-off screenshot, image markdown, or private visual judgment for the requested review result.

## Monitoring Commands

Inspect latest review:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/nijigenerate-work-review-tool"
node "$SKILL_DIR/scripts/monitor-review.mjs" \
  --latest review-viewer/public/projects/<review-project>/reviews/latest-review.json
```

Accept an OK review and update monitor state:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/nijigenerate-work-review-tool"
node "$SKILL_DIR/scripts/accept-review.mjs" \
  --latest review-viewer/public/projects/<review-project>/reviews/latest-review.json \
  --audit rigging-output/<pass>/audit.json \
  --model output-model.inx
```

When the user asks to keep monitoring in this thread, create a heartbeat automation that runs this same decision logic. On `ok`, delete the automation. On `retake`, act immediately and leave the automation active.

## Retake Rules

- Treat review JSON as the primary instruction source.
- Preserve user-edited tags, vertex selections, deformation arrows, comments, global comments, and calibration.
- If this thread has a newer explicit instruction, it overrides conflicting JSON text.
- Mutate through `njc` commands only; never edit `.inx` directly.
- Save audit JSON with edited targets, parameters, source review `createdAt`, applied keys, moved counts, max displacement, output model path, and whether `FileCommand_OpenFile` was avoided.
- Regenerate images and JSON after every retake so the SPA shows the current model, not the prior review state.
- Keep neutral keys unchanged unless the user explicitly asks for neutral deformation.

## Mesh-Selection Review Notes

The intended UI tools are:

- `Mesh`: select a layer mesh for the current tag.
- `Vertex`: toggle vertices in the selected tag.
- `Arrow`: drag deformation endpoints for selected vertices.
- `Undo`: undo the last arrow edit.

Use this mode for direct Part/Grid residual review, face and body contour fixes, or layer-specific deformation deltas. Mesh geometry is not assumed to be on a grid.

Coordinate rule for nijigenerate mesh-selection reviews:

- Capture the target pose with `ViewCommand_CaptureLiveScreenshot` and `overlayObjects`.
- Read `result._meta.overlayMappings[].points[]`.
- Write `points[].image` directly into the review mesh `vertices`; these are PNG pixel coordinates in the captured image.
- Write deformation arrows in the same image pixel coordinate system.
- Keep `points[].source` only to convert reviewed image-space arrow deltas back to model/source-space values before calling `ModelCommand_SetDeformBinding`.
- Never use `points[].source`, local mesh vertices, overlay-space values, matrices, or guessed transforms as the visible review coordinates.

For direct face/body adjustment, the review input must include:

- a target such as `yawRight`, `yawLeft`, `rightUp`, or another parameter key label used by the pass;
- `tags[].kind: "meshSet"` with `meshIds` and concrete `vertexRefs`;
- `deformations[target][meshId][vertexIndex] = {x, y}` for the proposed arrow delta;
- comments that state fixed vertices or prohibited regions, such as fixed chin/jaw vertices or unchanged center body detail.

Example:

```json
{
  "tags": [
    {
      "kind": "meshSet",
      "target": "yawRight",
      "label": "face cheek direct residual",
      "meshIds": ["face-base"],
      "vertexRefs": [
        { "meshId": "face-base", "vertexIndex": 17 },
        { "meshId": "face-base", "vertexIndex": 18 }
      ],
      "comment": "Pull cheek-side transition outward; do not move jawline or chin tip."
    }
  ],
  "deformations": {
    "yawRight": {
      "face-base": {
        "17": { "x": -18, "y": 0 },
        "18": { "x": -12, "y": 2 }
      }
    }
  }
}
```

After applying the accepted direct adjustment through `njc`, regenerate the manifest assets from the modified model and show the `APPLIED` result in this tool. The adjustment is finished only after the post-apply review JSON is also `ok`.

## Exit Conditions

Stop the loop only when:

- A newer review exists.
- `reviewResult.decision` is `ok`.
- The OK review state has been recorded.
- Any monitor automation created for the loop has been deleted.

If no new review exists, do nothing and avoid noisy updates.

## Safe installation and local storage

Install into a new viewer directory in an existing project directory. The installer rejects an existing destination and symlink paths; it never deletes or overwrites an existing project. To upgrade, install to a new viewer directory, copy the required project data into its `public/projects/<project-id>/`, then validate it before replacing your old installation.

Keep the server on loopback. Copy files into the public project directory rather than linking external files. Use public manifest URLs, same-origin assets below the manifest directory, and a dedicated relative `reviews` output directory. Do not use filesystem paths, `file://`, traversal, or symlinks. CLI summary paths identify filenames, not absolute local filesystem locations.
