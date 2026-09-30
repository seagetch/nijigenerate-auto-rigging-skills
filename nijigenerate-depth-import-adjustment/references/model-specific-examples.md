# Model-specific diagnostic examples

These values document prior diagnoses. Use the method, not the numbers. Re-map every row, column, and effective depth from the current model.

## Ao: Earwear under Headwear::G

- Parent grid: `Headwear::G`, 11×11.
- Earwear center mapped mainly to rows 8–10 and columns 6–8.
- Parent depth at the accessory center was about `0.382`.
- Nearby Face/FrontHair effective depths were about `0.688` and `0.675`.
- A compact neighborhood was raised with falloff:

```text
r7c7=.62 r7c8=.56
r8c6=.66 r8c7=.69 r8c8=.63
r9c6=.64 r9c7=.69 r9c8=.61
r10c6=.57 r10c7=.64 r10c8=.57
```

The new sampled center was about `0.689`. Earwear remained visible with opacity `1.0`; no zSort or hiding workaround was used.

## Aka: lower Body::G profile

The reference model used a 13×17 grid. Its lower-front region needed broad center and side depth rather than a flat panel:

```text
R5:  0.35 0.42 0.50 0.62 0.78 0.94 1.00 0.94 0.78 0.62 0.50 0.42 0.35
R6:  0.55 0.65 0.78 0.96 1.20 1.38 1.45 1.38 1.20 0.96 0.78 0.65 0.55
R7:  0.75 0.90 1.08 1.35 1.70 1.95 2.05 1.95 1.70 1.35 1.08 0.90 0.75
R8:  0.85 1.03 1.25 1.58 1.95 2.22 2.32 2.22 1.95 1.58 1.25 1.03 0.85
R9:  0.95 1.15 1.40 1.78 2.20 2.50 2.62 2.50 2.20 1.78 1.40 1.15 0.95
R10: 0.08 0.09 0.12 0.24 0.90 1.25 1.38 1.04 0.74 0.24 0.12 0.09 0.08
R11: 0.08 0.09 0.10 0.15 0.34 0.48 0.54 0.40 0.28 0.15 0.10 0.09 0.08
```

The reusable lesson is to keep visible side columns meaningfully forward and taper after the principal lower-front surface. The row numbers and magnitudes are not defaults.

## Face/hair global magnitude correction

One prior model improved when Face and hair depth magnitude was reduced to roughly two-thirds. This is only evidence that over-strong source relief can require coordinated scaling. Always measure the current face, mouth projection, hair separation, and effective node Z before choosing a scale.

## Midori：アニメ顔の凹凸と方向別参照

[実データ・断面図・8方向・不採用の横髪例](midori-face-reference-sample.md)を参照。眼窩と頬、鼻梁と鼻先を別々に読むための資料であり、手直し差分や数値の移植用ではない。
