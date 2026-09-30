# Face, hair, headwear, earwear, and neck depth

Use this reference to define or correct head-related GridDeformer depth. The goal is a continuous head volume, not globally stronger relief or global flattening.

## Face

- Model the face as a broad curved surface with moderate forward depth.
- Preserve the stylized orbital recess and its raised rim where supported by the design. Anime eyes do not imply a flat facial surface. Distinguish the eye socket, upper orbital/brow band, outer-eye transition and cheek; smooth continuity between them rather than equalizing their depths.
- Locate nose, mouth, chin, and jaw from the artwork rather than symmetry or a stock grid.
- Give the nose a localized forward point with smooth falloff.
- Preserve modest lip/mouth form, but prevent the mouth region from becoming a forward shelf in yaw.
- Keep cheeks and lower face continuous. Do not turn a local mouth correction into global face flattening.
- Treat face sides and ears as side/rear transitions, not another front-facing strip.
- If the whole face is too far back, use import layer offset or node `translationZ`; if only the mouth protrudes, edit local Face grid depth.

## Front and side hair

- Keep FrontHair in front of the face while preserving a rounded upper hair mass.
- Preserve the original SideHair curvature, width and intended cheek overlap. Correct unintended penetration at its depth owner; do not interpret every cheek overlap as an error or push the whole lock outward. Before blaming face depth or editing hair, use [face visibility review](../../nijigenerate-shared-rigging-rules/references/face-visibility-review.md) to determine whether erroneous assets or occlusion are hiding the cheek. Repair only the demonstrated owner; hair regeneration is not a standard depth step.
- Correct local troughs or peaks where a side lock crosses the face; do not flatten the entire hair grid.
- If all FrontHair is misplaced while its local relief is correct, use node `translationZ` rather than adding one constant to every grid depth.

## Back hair

First complete [head-volume-and-hair-cases.md](head-volume-and-hair-cases.md), including the ordinary-head, long-hair, or hairless branch. For the region that actually represents rear skull volume:

- edges and top rim: mildly rear;
- occipital center and back-lower region: strongest rear depth;
- lower rim: less rear than the center so it does not shear like a rectangular panel.

The scalp/cranial region should follow the head rather than inherit an unrelated Face surface deformation. This does not assign all long hair to the head: use the linked long-hair procedure for a continuous Head-to-Body transition. A BackHair Part can contain front-visible crown detail; inspect outer volume and interior texture separately before assigning one depth behavior to the entire bitmap.

## Headwear and earwear

- Make Headwear follow head volume and avoid sharp local troughs beneath attached parts.
- When Earwear looks dented or crosses the face, inspect the parent Headwear grid before changing Earwear opacity, zSort, or visibility.
- Map the accessory into the parent grid, compare the sampled parent depth with nearby Face/FrontHair effective depth, and correct only a compact neighborhood with falloff.
- Keep the accessory visible. Hiding it is not a depth correction.

## Neck

- Keep upper-neck and lower-neck depth continuous.
- If the upper neck projects too far, correct the transition locally rather than flattening the whole neck.
- Re-run Fit Z to Depth after final neck or head-grid corrections.

## Head-surface verification

At neutral and both yaw endpoints confirm:

- the mouth does not project like a muzzle or shelf;
- Face and FrontHair retain volume without excessive separation;
- SideHair does not cover the wrong face region;
- Headwear/Earwear has no local dent or face crossing;
- BackHair reads as rear head mass;
- neck top and bottom form one continuous volume.

## 初回のアニメ顔深度を決める手順

1. 元絵と採用した側面・斜め上下の参照から、額／眼窩上縁、眼窩のくぼみ、目尻横、頬の隆起、鼻梁、鼻先、口元、顎をグリッドへ対応付ける。陰影の明暗をそのまま凹凸にせず、アニメの立体造形として面のつながりを読む。
2. 眼窩のくぼみとその上下の隆起を対で記録し、鼻梁と鼻先を別の領域として扱う。鼻梁全体を鼻先と同程度まで突き出させない。額から目尻・頬への移行、頬から顎への移行を断面と斜め参照の両方で確認する。数値の大小・振幅は作品と実際のeffective Zから決め、全モデル共通の深度値にしない。
3. 各領域の相対的な前後と滑らかな勾配を先に満たし、正面だけでなく両Yaw、両Pitch、四隅で検証する。奥側の頬が回り込んで隠れる過程を確認し、Part XYで奥側を平坦化して深度の失敗を隠さない。
4. 凹凸が強すぎる場合は、基準面に対する局所的な起伏量を弱める。眼窩・頬・鼻梁・鼻先の相対関係は保つ。ピークとくぼみを同じ深度へ潰したり、全体のZ位置と局所起伏の強さを混同しない。
5. 顔の基礎深度を確定した後、手前側の可視輪郭は[顔のPart手順](../../nijigenerate-post-rig-adjustment/references/face-contour-from-reference.md)へ渡す。深度だけでアニメ顔の全方向の輪郭が完成するとは扱わない。

## 数値と画像を併読する例

[Midoriの顔深度サンプル](midori-face-reference-sample.md)に元の顔、11×11の実データ、断面図、利用範囲を明記した8方向参照を収録。保存depthとeffective Zの違い、および未承認の全体状態を区別して読む。

## 深度評価を遮蔽物に妨げさせない

頬の深度が正しくても、不正な素材・変形・描画順によって必要な輪郭が隠れることがある。また、その遮蔽が不正な深度を見えなくする場合もある。[通常表示と分離表示の確認](../../nijigenerate-shared-rigging-rules/references/face-visibility-review.md)で両者を区別し、髪などに隠れたまま深度を合格にしない。
