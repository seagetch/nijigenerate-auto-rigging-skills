# Secondary physics integration verification

Verified on Ao-latest-20260927.psd through NJC and the public PSD pipeline.
Source SHA-256: 78f487728a6f5c1fc8078bf3dff1a173faa78e2a2547370624c097c81feb336f.

- All finishing stages executed with zero stage errors.
- 32 generated parameter / SpringPendulum pairs; all nine keys per target read back.
- Original node state and unrelated authored bindings preserved.
- 128 protected-anatomy pose checks; compound anatomy error: 0 pixels.
- Measured playback: 10 samples, peak response approximately 4.43 pixels.
- Neutral reset geometry error: 0 pixels.
- All 32 endpoint image grids and support overlays generated on the actual model.
- Neutral pixels before and after endpoint capture are identical.
- No saved-model reopen occurs between stages; public live-state readback follows saving.

The final whole-rig validator records five observations on existing Body angle
Grid bindings. Physics did not change those authored bindings. This verification
does not declare all body-angle geometry accepted or establish complete Python/D
image equivalence. Visual acceptance remains separate from execution/readback.

The existing NumPy, SciPy and Pillow dependencies suffice. No new library was added.
The standalone phys source is recorded in structures/physics-source.json; merged
riglib utilities are reused instead of replacing the existing package.
