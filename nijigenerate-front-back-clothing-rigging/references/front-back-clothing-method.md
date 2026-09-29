# Front/back clothing projection and binding method

This reference prepares clothing hierarchy and surface responsibility before clothing depth and standard parameter generation.

## Downstream depth input

After the hierarchy is final, use `nijigenerate-depth-import-adjustment` and read its:

- `references/artwork-grid-mapping.md`
- `references/clothing-depth.md`
- `references/body-chest-lower-depth.md`
- `references/depth-state-verification.md`

Pass the surface classification, inheritance state, UUIDs, axes, and transforms into that workflow. Do not create or import clothing depth here.

## Required related skills

- `nijigenerate-model-setup`
- `nijigenerate-limb-root-positioning` when clothing work changes limb/shoulder roots
- `nijigenerate-post-rig-adjustment` after broad clothing motion is complete

## Hierarchy

Prefer separate broad grids when front and back surfaces require different projection:

```text
*Clothing
  Clothing::G::Back
    rear parts
  Clothing::G::Front
    front parts
```

Confirm inheritance from the live hierarchy and a parameter test:

- inherited surface: project only clothing residual;
- blocked by Node/Grid/Part boundary: project a full independent surface.

AutoMesh after the final child set is known and re-read actual grid axes.

## Binding handoff

Do not generate yaw/pitch keys or binding arrays in this skill. After depth import, Fit Z, and standard parameter generation, use `nijigenerate-post-rig-adjustment` to:

- correct inherited clothing through residual broad motion;
- correct hierarchy-isolated clothing through its existing independent broad grid;
- keep the generated neutral key unchanged;
- apply direct Part detail only after broad clothing motion is correct.

## Local helpers

Prefer mesh deformation for broad cloth. Use small TRS only for rigid/local attachments such as:

- shoulder or sleeve cap;
- hood rim;
- belt buckle;
- dangling-string root.

Keep neutral TRS identity, mirror intended pairs, and correct a wrong root/pivot before increasing TRS.

## Post-adjustment handoff

Stop this workflow after the clothing hierarchy, broad grids, anchors, and surface responsibilities are correct. Use `nijigenerate-depth-import-adjustment` next, then `nijigenerate-post-rig-adjustment` for generated broad bindings and direct Part contour, seam, sleeve, collar, and hem corrections. Keep mask and physics candidates in their dedicated skills.

## Verification

- Grid axes and vertex counts match the canonical audit.
- Front/rear/side/local surfaces consume the correct audited depth arrays.
- Front panels remain in front and rear panels behind.
- Side wraps and anchors do not tear.
- Hood, skirt, and hem motion does not fight Body projection.
- Left/right response and neutral state are correct.
- No unrelated Part moved under the wrong grid.
