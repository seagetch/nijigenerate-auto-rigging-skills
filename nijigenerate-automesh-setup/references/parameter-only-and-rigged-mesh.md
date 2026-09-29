# Single-setting updates and meshes with dependencies

## Choose the mode

A processor setting, a Part mesh, and Grid axes are different state. An Optimum minimum-distance change does not authorize changing Grid divisions, sampling, boundary expansion or the processor. More vertices do not repair wrong hierarchy or depth.

## Single-setting procedure

1. Read the active processor and every existing setting per explicit target. Record the requested field by the live schema name and the instruction-time value.
2. Build a patch containing only that field. For an approximate quarter request choose a representable value near baseline / 4; record any schema constraint. Do not reapply presets or copy another target's config.
3. Read back all settings; reject unexpected fields in the diff. If application changes topology and dependencies exist, use the next procedure before applying.
4. Apply only to the explicit targets through the resolved njc. Inspect actual vertices/triangles or axes, alpha coverage, holes, thin strips and bilateral artwork. Keep processor-setting verification separate from triangulation acceptance.

## Rigged-mesh procedure

1. Inventory the actual dependencies: vertex and UV order, triangles, Grid depth samples, every deform key including unset state, BoneSource data, Welding counterparts, masks and descendants. Save numeric arrays plus exact-pose images before mutation.
2. Determine whether the requested outcome can be achieved without topology change. Do not remesh automatically merely because children were moved; first measure the union of required deformed artwork bounds.
3. If topology must change, identify the supported njc migration operation and its documented guarantees. If no migration exists, construct an explicit old/new correspondence for all dependent arrays before applying. A setting change alone is not a migration.
4. Preserve UV registration and semantic seams. Map Grid depth using actual old/new surface correspondence; map keyed deforms at every affected pose and reconstruct Welding only for intended seams. These operations require authorization for the dependency changes. Never apply a universal shape formula as an anatomical depth replacement.
5. Validate candidate lengths/indices/UVs and complete dependency coverage. If correspondence is ambiguous, do not destructively Apply and discover the loss afterward; report that exact unresolved dependency and continue unaffected work.
6. Apply through njc, then read actual topology and every migrated dependency. Verify neutral, reported failures, endpoints/corners/intermediates and mixed poses for changed dependants. No extra depth generation or reload is implied.
7. Record separately settings-only changes, topology changes and dependency migration. Restore only this operation's changes through supported njc commands if its invariants fail.

For moving a component to a new Grid, compute the controlled artwork's full pose envelope rather than keeping its old group's bounds; choose divisions for its own control needs. Large bounds and low divisions are independent defects.
