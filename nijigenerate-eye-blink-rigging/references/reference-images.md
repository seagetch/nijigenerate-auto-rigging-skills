# Reference Image Use

The bundled files are visual-reading examples from a three-quarter anime face:

- [example-open.png](images/example-open.png)
- [example-neutral-closed.png](images/example-neutral-closed.png)
- [example-smile-closed.png](images/example-smile-closed.png)
- [example-deep-closed.png](images/example-deep-closed.png)

Do not copy their coordinates or proportions into another model. Use them to recognize relationships:

- near and far eyes have different widths, slopes, and curvature strengths;
- neutral closure follows the oblique eye axis and is not an upward smile arch;
- smile closure may arch upward relative to its chord while the entire seam remains toward the lower lid;
- deep closure is distinct from smile closure;
- closed lashes retain painted thickness and endpoint taper.
- each closed endpoint chord preserves the authored open-eye `T_open` by default; raw screen-Y ordering is not anatomical evidence.

For each target model, capture or generate new references with the same head yaw, pitch, roll, crop, and apparent scale as the open artwork. Compare references and model screenshots side by side at equal eye width with each eye's `T_open/N_open` axes overlaid. Do not validate from a full-body image when the eyelash occupies only a few pixels, and do not compare endpoint height using raw screen Y.

Validate the crop itself before using it as evidence:

- show both complete eyes, including inner and outer canthi;
- keep enough resolution to judge painted lash thickness at inner, center, and outer thirds;
- record the crop bounds and apparent eye widths;
- regenerate the crop after camera, zoom, pan, canvas, or model-view changes;
- reject crops that contain only hair, ears, background, or a partial eye.

For a two-axis Blink parameter, prepare a matrix containing every Blink-X key for every actual expression row. Neutral intermediates plus expression full-close endpoints are insufficient because expression-specific canthus and interpolation defects can appear before full closure.

## Ao session: endpoint-only versus whole-contour placement

- [Superseded endpoint-only matrix](images/ao-blink-endpoint-only-superseded-matrix.png): negative example for a request to raise the entire closure contour. Raising only canthi changes curvature while leaving the middle behind.
- [Whole-contour result matrix](images/ao-blink-final-matrix.png): historical result, not a universal approved shape. Columns are closure X=0, 0.25, 0.5, 0.75, 1; rows are expression Y=-1, 0, +1. Compare the middle and both endpoints together, and compare expression rows at identical X.
- [Contour placement overlay](images/ao-blink-whole-contour-overlay-eyes.png): planned contour-reading aid, not proof of a rendered completed key. Open the result matrix as well.
- [Uniform-translation audit](examples/ao-blink-whole-contour-translation-audit.json) and [local-frame endpoint audit](examples/ao-blink-whole-contour-endpoint-audit.json): Ao-only UUIDs, landmarks and numerical values. The recorded full-close lift of 1.0 is an example, not a default. Do not infer anatomical up from raw screen Y or copy the historical frame normal without confirming it against the current artwork.

These are separate historical captures; recreate identical current-model camera and poses for an acceptance comparison. Numeric endpoint equality does not certify lash thickness, clipped white, pupil visibility or all mixed head poses. Use the placement procedure in [eyelid-motion-and-bezier.md](eyelid-motion-and-bezier.md), preserving its scope distinction between full-eye placement and closure-contour placement.

[Source identifiers, file hashes and evidence status](example-provenance.json) accompany these bundled examples.
