---
name: nijigenerate-checklist-review-loop
description: Run nijigenerate checklist OK/Retake loops with read-only initial inspection, YAML self-review, and optional human review SPA for any rigging phase.
---

# Nijigenerate Checklist Review Loop

Use this skill when a nijigenerate task requires a checklist reviewer rather than an ad hoc final answer.

This skill is the sole owner of the checklist reviewer implementation and install flow. Do not use `nijigenerate-work-review-tool` to install or run checklist review. Both reviewer types use the same deployment pattern: copy the skill-owned viewer into the active project, keep review project data under the copied viewer's `public/projects/<project-id>/`, and run that local copy with Vite.

## Core Rule

Codex's checklist evaluation is YAML, usually `self-review.yaml`. The human checklist review result is JSON, usually `reviews/latest-review.json`.

Do not swap these responsibilities:

- Codex writes and updates `self-review.yaml` after read-only checklist verification or after fixing a Retake and rerunning the checklist.
- The checklist reviewer SPA reads `self-review.yaml` as input and writes human review JSON on Submit.
- Human JSON is the review signal to monitor for OK/Retake. Codex must not directly create or overwrite that JSON to represent its own evaluation.
- After a human Retake JSON, fix the violation or evidence gap, rerun the full checklist, update YAML/audit, refresh the SPA, and wait for the next human JSON.

Do not use `FileCommand_OpenFile` unless the user has explicitly authorized that file-open operation in the active task and has not revoked it.

## Workflow

1. Read the relevant nijigenerate step skill and its `references/step-checklist.yaml`.
2. Create or update a checklist reviewer project with:
   - `manifest.json`
   - original checklist YAML
   - optional translated checklist YAML
   - `self-review.yaml`
   - `audit/*.json`
3. Initial pass is read-only:
   - inspect current nijigenerate model state, screenshots, audit files, review artifacts, and skill references;
   - check every checklist item one by one;
   - do not change model structure, mesh, parameters, bindings, or layer composition during this initial evaluation;
   - write the result to `self-review.yaml`.
4. Only when the user requests a reviewer UI, start or refresh the checklist reviewer SPA. Otherwise complete the scoped self-review and report its evidence without waiting for human JSON.
   - Use the bundled reviewer in `scripts/checklist-reviewer`.
   - The SPA must read `self-review.yaml` as Codex's checklist evaluation input.
   - Human Submit must write JSON to the manifest-defined review output, normally `reviews/latest-review.json`.
5. Monitor the human review JSON.
   - Process only JSON with a `createdAt` newer than the last processed human review.
   - Check `reviewResult.decision` and every row in `results`.
6. If the human JSON is OK, accept the checklist review and stop monitoring.
7. If the human JSON has `decision: retake` or any Retake item:
   - use the Retake item IDs and reasons as primary instructions;
   - inspect the model and existing artifacts first;
   - fix violations with permitted nijigenerate commands only when model mutation is required;
   - fix only evidence/audit/YAML when the model is already correct and the Retake is a documentation or verification gap;
   - never directly edit `.inx` files.
8. After every correction:
   - rerun the full relevant checklist, not just the Retake rows;
   - update `self-review.yaml` and `audit/*.json`;
   - refresh the SPA by leaving the dev server running or restarting it if middleware changed;
   - continue monitoring human JSON until the user submits OK.

## Required Artifacts

For each checklist review project, maintain:

- `manifest.json`: points to checklist, translated checklist if any, `selfReview`, audit, and review output location.
- `checklists/*.yaml`: checklist source. Do not mutate it as a review result.
- `self-review.yaml`: Codex's current checklist evaluation values and reasons. Codex updates this after verification.
- `audit/*.json`: objective evidence for why each important item is OK/Retake.
- `reviews/latest-review.json`: human reviewer output written by the SPA on Submit. Monitor this for OK/Retake.

## Reviewer Tool

Bundled scripts:

- `scripts/checklist-reviewer`: Vite SPA reviewer that reads checklist YAML and `self-review.yaml`.
- `scripts/bin/inspect_self_review.py`: summarize OK/Retake counts from a YAML file.
- `scripts/bin/watch_checklist_review.py`: monitor YAML or JSON review files and print Retake items.
- `scripts/bin/install_checklist_reviewer.sh`: copy the bundled reviewer into a project.

Typical setup:

```bash
SKILL_DIR="$HOME/.codex/skills/nijigenerate-checklist-review-loop"
"$SKILL_DIR/scripts/bin/install_checklist_reviewer.sh" ./checklist-reviewer
cd ./checklist-reviewer
npm ci
npm run dev -- --host 127.0.0.1
```

Open:

```text
http://127.0.0.1:5174/?manifest=/projects/<review-project>/manifest.json
```

Check status:

```bash
python3 "$SKILL_DIR/scripts/bin/inspect_self_review.py" \
  ./checklist-reviewer/public/projects/<review-project>/self-review.yaml
```

Monitor human review:

```bash
python3 "$SKILL_DIR/scripts/bin/watch_checklist_review.py" \
  --json ./checklist-reviewer/public/projects/<review-project>/reviews/latest-review.json
```

Inspect Codex's YAML evaluation when needed:

```bash
python3 "$SKILL_DIR/scripts/bin/watch_checklist_review.py" \
  --yaml ./checklist-reviewer/public/projects/<review-project>/self-review.yaml
```

## Completion Criteria

For a requested human-review UI, stop when the latest human-submitted JSON has `reviewResult.decision: ok` and no Retake rows. For an audit without that UI, report the scoped self-review and its outstanding items; do not manufacture human approval.

`self-review.yaml` is the Codex evaluation that feeds the UI and must be updated after checklist verification or Retake correction, but it is not the human-review completion signal. The loop completion signal is the human JSON.

When stopping a heartbeat automation, delete the automation and state that the review is complete.

## Task-specific procedures

- For phase-local checks, deferred later work and separate visual/save decisions, read [scope-and-checkpoints.md](../nijigenerate-shared-rigging-rules/references/scope-and-checkpoints.md).

For these operations, also complete [references/change-result-checklist.yaml](references/change-result-checklist.yaml). Apply conditional items only to the requested scope.

## Safe installation and local storage

Install into a new viewer directory in an existing project directory. The installer rejects an existing destination and symlink paths; it never deletes or overwrites an existing project. To upgrade, install to a new viewer directory, copy the required project data into its `public/projects/<project-id>/`, then validate it before replacing your old installation.

Keep the server on loopback. Copy files into the public project directory rather than linking external files. Use public manifest URLs, same-origin assets below the manifest directory, and a dedicated relative `reviews` output directory. Do not use filesystem paths, `file://`, traversal, or symlinks. CLI summary paths identify filenames, not absolute local filesystem locations.
