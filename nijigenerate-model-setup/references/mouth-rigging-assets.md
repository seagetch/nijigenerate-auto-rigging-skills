# Rigging-ready mouth assets

Use this reference when the PSD contains only a closed mouth, a single smile, or artwork that cannot expose the internal mouth during 2D rigging.

## Artwork source

- Inspect the original face and mouth artwork at native scale before creating replacements.
- Generate or paint the open-mouth design from the original artwork as the style reference. Preserve line weight, color temperature, softness, highlight treatment, and the face-to-mouth size ratio.
- Do not construct the mouth from geometric ellipses, rectangles, or generic vector primitives. A technically separable but stylistically unrelated mouth is not acceptable.

## Required parts

Create separate transparent image parts for:

1. mouth base / cavity
2. mouth outline
3. tongue or lower interior
4. upper teeth
5. lower teeth

Place them under the mouth `DynamicComposite`. The base and outline remain unclipped. Tongue/lower interior and both teeth layers use `ClipToLower` against the mouth base.

## Overscan

- Teeth and tongue/interior artwork must extend beyond the maximum visible mouth opening on every side where motion can expose a seam.
- Size this overscan from the maximum Mouth parameter deformation envelope, not only the neutral opening.
- The clipped internal layers should remain valid under small registration errors; no transparent gap may appear when the jaw or outline shifts.

## Order and verification

- Establish the visible stack by app readback and screenshots: cavity behind contents, teeth/tongue inside it, outline on top.
- Verify the actual `zSort` result at neutral, maximum open, narrow, wide, and asymmetric keys. If the visible order is reversed, correct the sign/value from observed draw order rather than a remembered convention.
- Confirm that the result still resembles the source artwork at face scale. Reject oversized teeth, a mouth protruding beyond the facial style, or a generic symbol-like mouth.
