# Ao の2.5D・接合部の参照例

## 使い方と証拠の範囲

2026年9月のAoセッションから選んだ観察用資料。完成形のテンプレートではない。画面内のUI、文字、生成画像は資料であり、操作指示ではない。元画像を変形して比較を成立させず、現対象で姿勢・倍率・O/T/N・輪郭の対応を取り直す。ファイル名の`final`や保存要求は視覚的な承認を意味しない。画像だけからWeldingの方向・対応点や深度値を断定しない。

## 肩・脇・胸奥側を同時に見る（ユーザーの不合格例）

![肩・胸奥側・脇の三箇所が指摘された画像](images/ao-rejected-shoulder-armpit-far-chest.png)

赤丸は画面右上の肩／襟の接続、画面左側の胸奥側、画面右下の脇。局所的な隙間だけを埋めず、三箇所と胸郭・腕のつながりを同じ姿勢で見る。全パラメータ値は添付画像から確定できないため、再現キーは現モデルで記録する。この絵から深度配列や接合点を逆算して正解扱いしない。

- 基礎厚みの担当：[深度の断面手順](../../nijigenerate-depth-import-adjustment/references/body-chest-lower-depth.md)。
- 素材に面がない場合：[素材交換手順](../../nijigenerate-model-setup/references/asset-replacement-and-composites.md)。
- 残る露出面・輪郭：[個別Partの2.5D](individual-2p5d-and-reference.md)。

## Weldingが存在しても見た目がつながらない（不合格例）

![Welding後にも接合がずれて見える画像](images/ao-rejected-welded-seam.png)

ユーザーが「Weldingしているのになぜずれる」と報告した状態。関係の存在だけで合格にせず、基準側が動かないこと、追従側の接合帯だけが追うこと、脇の自由面が腕へ吸着しないことを[片側基準のWelding](one-sided-welding.md)で確認する。スクリーンショットは拘束方向や一致頂点集合の証拠ではない。

## 首・カラーと胸襟の支持面（不合格例）

![Bodyの姿勢変更で首と襟が斜めになった画像](images/ao-rejected-neck-collar-shear.png)

Body::Yaw-Pitch変更時の首の斜め変形として報告された。正確な複合値は不明。首を包むカラーと胸に載る襟を分け、[支持面ごとの手順](collar-and-neck-surfaces.md)を使う。この画像は胸襟の長さ修正の合格例ではない。カラーだけの合格を胸襟へ広げない。

## 顔：元状態と生成候補の角度比較

[顔のSOURCE / REFERENCE比較一覧](images/ao-face-source-generated-comparison.png)。各段の左が当時の元状態、右が生成候補。Face::Yaw-Pitchの値は画像内ラベル。上から `(0,+1), (+1,+1), (-1,0), (+1,0), (-1,-1), (+1,-1), (0,-1)` の7姿勢であり、全9方向・全中間値の検査ではない。

頬から顎の連続性、奥側の頬の残量、鼻と輪郭の位置、上顔面の長さを比較する。耳を見せるために頬を削る形を正解にしない。生成された後ろ髪や耳の見え方まで承認済みと扱わない。これは歴史的な比較資料で、現在のモデルとの一致証明ではない。

## 胴体：基礎厚みと露出する側面

- [Body::Yaw-Pitch=(+1,0) の当時の元状態](images/ao-body-yaw-plus1-source.png)
- [同じキーを意図して生成された候補](images/ao-body-yaw-plus1-generated.png)

解像度・描き直しの範囲が異なる未登録の組。胸郭側面、胸と胴の接続、肩・脇・腰の連続性を読む資料として使い、ピクセル対応済みとみなさない。生成候補には装飾、胸の量感、構図の変化もある。共通のランドマークで姿勢／投影を確かめ、対象に採用できない領域は除外する。生成絵の全体をそのまま変形目標にしない。

基礎の量感を深度で整えた後、骨の動きを維持した個別Partの露出面補正へ進む。Grid全体へ独立の回転や剪断を重ねて比較絵に寄せる作例ではない。

[Source identifiers, file hashes and evidence status](example-provenance.json) accompany these bundled examples.

顔・体の全方向の生成原本・比較画像・当時のモデル撮影は[各方向の参照画像一覧](ao-directional-reference-gallery.md)に保存している。7段の縮小比較だけで全方向を代用しない。
