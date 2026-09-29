# Reference Image Use

The bundled images show visual relationships from a tilted three-quarter anime face:

- [example-open-neutral.png](images/example-open-neutral.png)
- [example-half-neutral.png](images/example-half-neutral.png)
- [example-closed-neutral.png](images/example-closed-neutral.png)
- [example-closed-displeased.png](images/example-closed-displeased.png)
- [example-closed-smile.png](images/example-closed-smile.png)

Do not copy their coordinates, slope, closure ratio, or near/far amplitude into another model. Use them to recognize these relationships:

- open, half, and closed neutral states retain one oblique mouth axis;
- neutral closure does not become screen-horizontal;
- displeased corners descend relative to the oblique axis and remain readable at full closure;
- smile corners rise relative to the same axis;
- the near and far sides do not require identical displacement;
- full closure retains visible painted lip thickness and hides internal artwork.

For each target model, capture a new reference from the current authored face at the same yaw, pitch, roll, crop, and apparent scale. Review an original-scale face image and an enlarged crop together. A close crop can reveal broken pixels but cannot establish whether the mouth is correctly placed or proportioned on the face.

When references are generated, preserve the target head pose. Do not generate a frontal mouth reference for a tilted or three-quarter model and then force the rig toward that frontal geometry.

## Ao session expression matrix

[Open/intermediate/closed × expression matrix](images/ao-mouth-matrix.png) is a historical coverage example. Columns: X=0, 0.25, 0.5, 0.75, 1; rows: Y=-1, 0, +1. In this model X=0 is open and X=1 closed; re-read another model's axis semantics. Inspect retained outline thickness, internal clipping and intermediate behavior. The crop alone cannot approve facial placement, oblique head poses or the entire rig. Neither the shape nor the visible pixelation is a target to reproduce.

[Source identifiers, file hashes and evidence status](example-provenance.json) accompany these bundled examples.
