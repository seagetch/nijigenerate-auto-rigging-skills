---
name: nijigenerate-tracking-setup
description: Add or repair Tracking bindings in exported Inochi2D INP models using reference models, mapping tracker inputs to existing parameter axes without altering the rig or textures.
---

# Nijigenerate Tracking Setup

Use for Tracking configuration on an existing exported model. Reference models provide schema and input conventions, not portable UUIDs or universal ranges. Keep this separate from live model rigging and parameter-link authoring.

## Core decisions

- Resolve target and reference files; preserve existing model data, textures and unrelated extensions.
- Read actual parameter UUIDs, ranges, defaults, axis meanings and sides before copying bindings. Distinguish tracker values, parameter values and normalized offsets.
- Do not drive internal linked parameters or Physics outputs directly unless the user explicitly requests that design.
- Configuration validation and live tracking validation are separate results. Report unavailable live input truthfully.

Read [references/tracking-transfer.md](references/tracking-transfer.md) before writing. Complete [references/step-checklist.yaml](references/step-checklist.yaml) and [references/result-audit-checklist.yaml](references/result-audit-checklist.yaml).

For active njc app edits follow `nijigenerate-shared-rigging-rules`. Offline INP extension editing is allowed for this task and does not authorize editing INX, reopening the live rig, or changing model parameters/deformation. User restrictions on implementation-source inspection still apply.

For the relevant visual or recorded-data examples and their evidence limits, use the [example index](../nijigenerate-shared-rigging-rules/references/visual-example-index.md); procedural references link directly to their owned examples.
