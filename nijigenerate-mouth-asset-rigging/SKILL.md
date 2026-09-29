---
name: nijigenerate-mouth-asset-rigging
description: Create or repair rig-ready nijigenerate mouth assets through njc, including Base, Tongue, upper/lower Teeth, Outline, clipping, zSort, meshes, scale, and DynamicComposite structure.
---

# Nijigenerate Mouth Asset Rigging

元絵に馴染む一つの開口口を先に確定し、同じmasterから5素材を分離して、`njc`でリギング可能な構造へ組み込む。汎用の`nijigenerate-model-setup`へ口固有の制作手順を混ぜない。

## 必読資料

作業前に次を最後まで読む。

- [mouth-asset-procedure.md](references/mouth-asset-procedure.md): 制作順、採否基準、正例・負例、証跡。
- [result-audit-checklist.yaml](references/result-audit-checklist.yaml): 完成結果の項番順監査。
- [shared rigging rules](../nijigenerate-shared-rigging-rules/SKILL.md): `njc`解決、状態変更、安全、保存、検証の共通規則。

画像を新規生成または編集するときは`imagegen`スキルを使用する。モデル操作は解決済みの`njc`だけで行う。

## 固定ワークフロー

順序を入れ替えずに実行する。

1. 元PSDの口と未加工の顔全体を抽出し、原寸で位置、幅、高さ、線、色、コントラストを記録する。
2. 元顔を直接参照し、顔上に一つの完成した開口口masterを生成する。
3. 元顔への原寸合成で大きさ、位置、画風を承認する。承認前に素材分割やモデルへのインポートをしない。
4. 同一masterから`Base`、`Tongue`、`Teeth::Lower`、`Teeth::Upper`、`Outline`の5素材を分離する。各素材を別々に生成しない。
5. 中立合成がmasterを再現することと、舌・上下の歯が最大変形でもBaseの内側を覆えるoverscanを持つことを確認する。
6. `njc`で5素材を口のDynamicComposite配下へインポートする。
7. BaseとOutlineをNormal、舌と上下の歯をBaseに対する有効なClipToLowerにする。
8. 実描画で前後関係を確認し、前からOutline、上の歯、下の歯、舌、BaseとなるようzSortを設定する。数値の符号を推測しない。
9. メッシュを読み戻す。薄い素材が3頂点1三角形などへ潰れた場合はAutoMesh成功とみなさず、失敗を記録して制御可能な規則メッシュへ置き換える。
10. 口のDynamicCompositeをGrid形状にし、最大開口、閉口、横長、横狭、非対称の包絡範囲より一回り大きくする。
11. チェックリストを1番から全件監査する。失敗項目だけを修正した後も、1番から全件再監査する。

## 禁止事項

- 幾何学図形や手続き描画で口を組み立てない。
- 拡大した口単体だけで大きさを承認しない。
- 独立生成した不整合な5素材を組み合わせない。
- 舌・歯をBaseと同寸または小さくしない。
- ツリー順や記憶だけでzSortを決めない。
- 中立形状だけからGrid範囲を決めない。
- INXを直接編集しない。Computer Useを使わない。環境固有の`out/njc`を固定参照しない。
- ユーザーが明示していないレビューSPAやブラウザを起動しない。
- 全監査項目がOKになる前に完成扱い、引き渡し、不要な反復保存をしない。

## 監査と引き渡し

`result-audit-checklist.yaml`の各項目を`OK`、`RETAKE`、`UNVERIFIABLE`で記録する。監査方法は[shared result audit loop](../nijigenerate-shared-rigging-rules/references/result-audit-repair-loop.md)に従う。最終報告では項番順に結果と証跡を日本語で示し、口以外のモデル状態が変わっていないことも含める。

## Task-specific procedures

- When replacing an existing mouth or correcting duplicate controls, use the [asset/composite procedure](../nijigenerate-model-setup/references/asset-replacement-and-composites.md) in addition to the mouth-specific five-Part procedure.

For these operations, also complete [references/change-result-checklist.yaml](references/change-result-checklist.yaml). Apply conditional items only to the requested scope.
