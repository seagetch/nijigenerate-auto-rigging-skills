# Tracking transfer procedure

## Read references and target

1. Resolve the explicit target; read it and candidate reference models without reopening the active rig. Locate their Tracking extension and deserialize only bounded records. Choose references with meaningful configured inputs, not empty source names.
2. Record each target parameter UUID/name, is_vec2, min/max/defaults, actual axes and motion semantics. Use the model's bindings and existing accepted audit to distinguish open/closed, up/down, emotion and character sides; names alone are insufficient.
3. Extract reference input names, types, ranges, inversion and smoothing. Map semantic roles to target UUIDs; do not transplant another model's IDs, extra parameters, neutral biases or obsolete input aliases.

## INP extension layout observed in supported models

For the TRNSRTS format: 8-byte `TRNSRTS\0` signature, big-endian u32 JSON byte length, then that many JSON bytes. `TEX_SECT` is followed by a big-endian u32 texture count; each texture record is u32 payload length, one format byte and payload bytes. `EXT_SECT` contains u32 entry count followed by entries of u32 UTF-8-name byte length, name, u32 data byte length, data. Verify every boundary, signature and final EOF; stop on an unsupported format rather than guessing offsets. Preserve opaque sections without reserialization.

The observed Tracking extension name is `com.inochi2d.inochi-session.bindings`. Its data is a JSON array. Records include `name`, `bindingType`, target `param` UUID, `axis`, input fields and binding-specific settings. Confirm the actual target application's supported types from permitted documentation/schema or known reference data.

## Construct mappings

- A RatioBinding uses `sourceType`, `sourceName`, `sourceDisplayName`, `inverse`, `inRange`, `outRange`, `dampenLevel`. For the confirmed Session behavior, the input is normalized/clamped to inRange, inverted if requested, then mapped into outRange in actual parameter units.
- An ExpressionBinding uses an `expression` and smoothing; in the confirmed Session format its result is a normalized parameter-axis offset. Thus signed -1..1 neutrality needs 0.5, not 0. Example normalized gaze: `0.5+(BLEND("eyeLookInRight")-BLEND("eyeLookOutRight"))/2`. Reconfirm semantics for another runtime/version before assuming compatibility. Never execute expressions copied from a model as host code.
- CompoundBinding weights and normalization may differ by runtime. Do not guess sum versus average; retain a proven compatible configuration or use a verified supported alternative.
- For an axis with 0=open and 1=closed, `jawOpen` requires inversion; blink input can have a different direction despite similar parameter names. Track both independently.
- Eyebrow height and emotion axes may be swapped between models. Gaze Left/Right names are character-relative; verify anatomical correspondence and yaw signs from the target.
- Keep external driver bindings distinct from internal parameter links. No cycles, duplicate target-axis drivers or direct Physics tracking outputs.

## Verify and write

1. Validate unique existing target UUID/axis pairs, supported input/type fields, finite ranges and nonzero input spans.
2. Test neutral input, each input independently, extremes, clamping and representative simultaneous inputs. Assert intended open/closed, signs, left/right independence and parameter range. Numeric neutral for a closed mouth may differ from the authored open default; state this explicitly.
3. Save the small original extension section and file hashes, not another unnecessary full-size model. Build a temporary candidate replacing only the intended extension (or adding it and updating count). Preserve all earlier bytes and unrelated extension records byte-for-byte.
4. Reparse the candidate, check bounds/EOF, compare mappings and preserved bytes, then verify the original target has not changed concurrently. Atomically replace that explicit target and reparse/read back again.
5. Record config validation separately from runtime evidence. When live tracking is available and authorized, test neutral, independent blinks, gaze, mouth, brows and head/body axes, smoothing and lost-input behavior. If absent, do not claim live visual approval or silently operate a camera.

## Audit output

Record target path, reference paths, mapping table with target UUIDs/axes and semantics, edited extension, original/final hashes, unchanged-section proof, numeric checks and runtime test status. Re-exporting from the original rig may overwrite this extension; preserve/reapply only after checking that parameter UUIDs still match.

## Recorded configuration example

[Ao Tracking bindings](examples/ao-tracking-bindings.json) and its [audit](examples/ao-tracking-audit.json) show 20 target-axis bindings across 11 parameters, including inversion, ranges and gaze expressions. UUIDs and tuning values belong only to that Ao export; remap rather than paste them into another model. The audit records unchanged model/texture bytes and `runtimeTrackingTested: false`. It is a configuration example, not evidence of live camera or browser-rendering equivalence. Original reference-model filenames in the audit describe provenance; no external files are required to read this example.

[Source identifiers, file hashes and evidence status](example-provenance.json) accompany these bundled examples.
