# Time-based physics tuning

## Separate controls

Length describes the simulated attachment/free-end relation; Frequency and damping affect timing; output scale and authored keys affect displacement. Do not equate a requested larger sway with a longer pendulum or a requested slower motion with a new shape. Existing measured lengths remain the baseline unless the task asks to change them.

## Procedure

1. Record model-space attachment/tip distance, current Length, Frequency, damping, gravity, map mode, output scale and shape-key endpoint displacement for every requested target. Include chest/cloth when in scope and distinguish rigid decorations from flexible surfaces.
2. If a numerical factor is requested, apply it once to the instruction-time settings and preserve other controls. Verify every target independently. A model-specific quarter factor is not a default for other models.
3. For perceptual timing requests, reset simulation and drive the same small body/head motion for before/after playback. Record frame rate or timestamps, cycle time, peak tip displacement and settling behavior where measurable. Inspect anchors and nearby surfaces throughout the sequence.
4. Adjust one responsible setting family per iteration. Use the existing solver's observed response, not an assumed length/frequency formula. Keep the accepted authored pose and rest geometry.
5. For more chest sway, first inspect the authored endpoint range and actual output. Increase only the requested secondary motion, keeping the ribcage/shoulder attachment stable; do not alter Body yaw/pitch to manufacture bounce.
6. Repeat the same drive/reset sequence, then check representative mixed poses for penetrations. A still image can verify shape but cannot establish cycle speed. If playback cannot be observed, label timing UNVERIFIABLE rather than OK; save the requested settings with that limitation when instructed.

## Recorded settings example

[Ao quarter-length audit](examples/ao-quarter-length-audit.json) records 32 Length updates, per-node before/after values, 229 unchanged bindings and a neutral reset error. Recompute each ratio; one stored value has a small floating-point rounding difference. The quarter factor was an explicit Ao request and is not a general slower-motion preset. This JSON proves reported settings checks only: it contains no timestamped oscillation or settling measurements and cannot establish slower sway. Do not use a still review image as that evidence.

[Source identifiers, file hashes and evidence status](example-provenance.json) accompany these bundled examples.
