# nijigenerate-auto-rigging-skills

nijigenerate / Inochi2D 向けのリギング作業を Codex から進めるためのスキル集です。モデル構造・メッシュの準備から、DepthBone、深度の取り込み、表情、物理演算、検証までを工程ごとのスキルに分けています。

一連の自動リギングの入口は [nijigenerate-automatic-rigging](nijigenerate-automatic-rigging/SKILL.md) です。部分的な修正では、該当する専門スキルを使います。工程の担当と引き渡し条件は [workflow-router.md](nijigenerate-shared-rigging-rules/references/workflow-router.md) を参照してください。

このリポジトリは手順・補助スクリプト・参照資料を提供します。nijigenerate 本体、`njc` 実行ファイル、作業対象のモデルは同梱していません。

## 前提となる環境

- スキルを利用できる Codex 環境。
- モデル操作には、起動済みの nijigenerate と、それに接続できる `njc`。実行ファイルは明示したパス、`NJC_PATH`、`PATH` の順で解決します。
- 対象モデルと元絵、必要なパーツ素材・深度画像。素材が不足している場合は、下記の任意スキルで準備できます。
- 補助スクリプトを使う工程では Python 3。チェックリストの YAML を読む Python スクリプトには PyYAML が必要です。
- レビュー用 Web UI を使う場合は Node.js / npm。CI では Node.js 22 を使用しています。各テンプレート内で `npm ci --ignore-scripts` を実行します。
- 画像の生成・編集を伴う工程では、その工程が指定する画像生成機能。口素材の生成・編集や `generate-depth-map` には `imagegen` が必要です。

モデルを操作するスキルでは、解決した `njc` を使用し、INX を直接書き換えません。Tracking の設定は、エクスポート済み INP の既存パラメータに入力を対応付ける別工程です。詳細は各スキルの指示に従ってください。

## 導入

Codex の `skill-installer` を使う場合は、次のように依頼できます。

```text
skill-installer を使い、https://github.com/seagetch/nijigenerate-auto-rigging-skills
の直下にある nijigenerate-* の全18スキルをインストールしてください。
既存の同名スキルがある場合はローカル変更を確認し、退避してから更新してください。
```

手動で導入する場合はリポジトリをクローンし、直下の各 `nijigenerate-*` ディレクトリを Codex のスキルディレクトリへ配置します。標準は `~/.codex/skills/`、`CODEX_HOME` を設定している場合はその下の `skills/` です。

```sh
git clone https://github.com/seagetch/nijigenerate-auto-rigging-skills.git
```

配置は次の形にします。リポジトリ全体を一つのスキルとして配置せず、各スキルを兄弟ディレクトリにしてください。相互参照があるため、通常は全18スキルをまとめて導入します。

```text
skills/
  nijigenerate-automatic-rigging/
    SKILL.md
    references/
    agents/
  nijigenerate-model-setup/
    SKILL.md
    references/
  nijigenerate-shared-rigging-rules/
    SKILL.md
    references/
  …他の nijigenerate-* スキル
```

`SKILL.md` だけでなく、同梱の `references/`、`scripts/`、`agents/` などもそのまま配置してください。既存のスキルを更新するときは独自変更を確認・退避してから置き換えます。非公開リポジトリの取得にはアクセス権のある GitHub 認証が必要です。

## 任意の間接依存: 素材を準備するスキル

以下の2つは、モデルへ渡す素材を作る工程で使う別リポジトリです。本スキル集の導入だけで自動的に導入されるものではなく、すべての作業で必須というわけでもありません。

| スキル | 導入する場面 | 追加導入が不要な場面 |
| --- | --- | --- |
| [generate-depth-map](https://github.com/seagetch/generate-depth-map) | 元絵から深度画像を新規作成する、既存の深度画像を再生成・改善する、元絵との前後関係や照明の混入を検証する場合 | 準備済みの深度画像を nijigenerate へ取り込み、モデル内の深度・スケール・オフセットを調整するだけの場合 |
| [reference-guided-rig-parts](https://github.com/seagetch/reference-guided-rig-parts) | 一枚絵から初期パーツを分ける、既存PSD/RGBAの顔・髪・衣装・接合・隠れ面などを補修し、編集可能な素材を準備する場合 | リギング用パーツが揃っており、メッシュ・骨・パラメータ・表情・物理演算などモデル側の作業だけを行う場合 |

### generate-depth-map

元絵と位置・輪郭を合わせ、**近い面を白、遠い面・背景を黒**とするグレースケール深度画像を作ります。単なる白黒変換ではなく、照明・色・描線を深度と取り違えていないか、生成候補を評価して改善するスキルです。深度画像の生成には `imagegen` を使用します。

生成・検証した深度画像を、[nijigenerate-depth-import-adjustment](nijigenerate-depth-import-adjustment/SKILL.md) へ渡します。本リポジトリ側が担当するのは取り込み、欠損補修、解剖学的な深度調整、Fit Z、標準Depthパラメータの生成です。

### reference-guided-rig-parts

元絵と切り出し済み／既存のパーツを同時参照し、再作成・補修と再合成検査を経て、編集可能なPSDや透過RGBAパーツを準備します。必要なパーツが足りない場合や、リギング前に素材の隠れ面・接合を直す場合に導入してください。

画素の再作成・補修には画像生成・編集機能、検証には画像閲覧機能が必要です。補助スクリプトは Python 3.9 以上で動作し、任意のアルファ処理補助とそのテストには Pillow が必要です。詳細は[依存先のREADME](https://github.com/seagetch/reference-guided-rig-parts#readme)を参照してください。

完成した素材は [nijigenerate-model-setup](nijigenerate-model-setup/SKILL.md) などのモデル準備工程へ渡します。深度生成やメッシュ・骨・表情・物理演算はこの素材制作スキルの担当ではありません。編集マスターを保持し、マスク焼き込み・左右分割・拡大・アクティブモデルへの再インポートは自動的に行いません。

### 任意スキルの導入方法

必要なものだけを `skill-installer` に指定します。

```text
https://github.com/seagetch/generate-depth-map のルートを
generate-depth-map という名前のスキルとしてインストールしてください。
```

```text
https://github.com/seagetch/reference-guided-rig-parts のルートを
reference-guided-rig-parts という名前のスキルとしてインストールしてください。
```

両リポジトリともルートに `SKILL.md` があります。手動配置では、それぞれのリポジトリ全体を `skills/generate-depth-map/`、`skills/reference-guided-rig-parts/` に配置します。素材と深度画像が両方不足している場合は両方を導入し、採用した絵・構図に合う深度画像を用意してからリギングへ進みます。

## 同梱スキル

| スキル | 担当 |
| --- | --- |
| [automatic-rigging](nijigenerate-automatic-rigging/SKILL.md) | 自動リギング全体の順序と工程間の引き渡し |
| [deterministic-rig](nijigenerate-deterministic-rig/SKILL.md) | PSDを入力に共通テンプレートとNJCで生成する開発中のリギングプログラム（個別Part補正は未実装） |
| [shared-rigging-rules](nijigenerate-shared-rigging-rules/SKILL.md) | 操作・座標系・状態保存・検証の共通規則 |
| [model-setup](nijigenerate-model-setup/SKILL.md) | 階層、Composite、Grid/Path、初期パラメータ |
| [automesh-setup](nijigenerate-automesh-setup/SKILL.md) | AutoMeshの方式・密度・被覆範囲 |
| [limb-root-positioning](nijigenerate-limb-root-positioning/SKILL.md) | 腕・脚などの付け根とピボット |
| [front-back-clothing-rigging](nijigenerate-front-back-clothing-rigging/SKILL.md) | 衣装の前後・側面構造とアンカー |
| [depth-skeleton-setup](nijigenerate-depth-skeleton-setup/SKILL.md) | DepthRigRoot、標準19骨、BoneSources |
| [depth-import-adjustment](nijigenerate-depth-import-adjustment/SKILL.md) | 深度取り込み・補正、Fit Z、標準Depthパラメータ |
| [post-rig-adjustment](nijigenerate-post-rig-adjustment/SKILL.md) | Face/Bodyの姿勢、輪郭・継ぎ目などの調整 |
| [mouth-asset-rigging](nijigenerate-mouth-asset-rigging/SKILL.md) | 口腔・舌・上下歯・輪郭の素材と構造 |
| [eye-blink-rigging](nijigenerate-eye-blink-rigging/SKILL.md) | まばたきと閉じ目表情 |
| [mouth-open-rigging](nijigenerate-mouth-open-rigging/SKILL.md) | 口の開閉、表情、斜め軸・非対称の補正 |
| [occlusion-mask-rigging](nijigenerate-occlusion-mask-rigging/SKILL.md) | 変形・深度修正後に残る貫通へのDodgeMask |
| [simple-physics-rigging](nijigenerate-simple-physics-rigging/SKILL.md) | 髪・布・アクセサリーなどの二次動作 |
| [tracking-setup](nijigenerate-tracking-setup/SKILL.md) | エクスポート済みINPのTracking入力設定 |
| [checklist-review-loop](nijigenerate-checklist-review-loop/SKILL.md) | チェックリスト、自己検査、OK/Retake対応 |
| [work-review-tool](nijigenerate-work-review-tool/SKILL.md) | 明示的に依頼された場合の視覚レビューSPA |

表の短縮名には、実際のスキル名ではすべて `nijigenerate-` が付きます。

## 使い方

リギング可能な素材と深度画像を用意し、対象モデルを nijigenerate に読み込んだ状態で依頼します。

```text
$nijigenerate-automatic-rigging を使って、現在読み込まれているモデルを
自動リギングしてください。深度画像は depth.png、出力先は model-rigged.inx です。
既存の良好な表情・動作を保持し、各工程の検証結果を記録してください。
```

一部だけを修正する例:

```text
$nijigenerate-eye-blink-rigging を使って、現在のモデルの閉じ目を修正してください。
虹彩と既存のFaceの動作を保持し、途中の開閉量も確認してください。
```

自動リギングの基本順序は、モデル・メッシュ準備 → 初期パラメータ → 骨・BoneSources → 深度調整 → Fit Z → 標準Depthパラメータ → Body/Face・表情調整 → 物理演算 → 全体検証・保存です。Tracking設定は必要に応じてエクスポート後に行います。

## 検証・共有時の注意

各工程のチェックリストと数値・画像による確認を行います。レビュー用SPAはユーザーが明示的に希望した場合に起動し、既定ではループバック接続だけを受け付けます。

リポジトリの検査:

```sh
python3 -m unittest discover -s tests -v
python3 tools/security_check.py
```

Webツールは次の各ディレクトリで `npm ci --ignore-scripts`、`npm test`、`npm run build`、`npm audit --audit-level=low` を実行します。

- `nijigenerate-checklist-review-loop/scripts/checklist-reviewer/`
- `nijigenerate-work-review-tool/scripts/review-viewer-template/`

検査は個人情報や未知の脆弱性の不存在を保証するものではありません。モデルや生成した監査JSON・ログを共有する際は、保存先の絶対パスなどが含まれていないか確認してください。既存PNG検査はC2PA生成履歴など、すべてのメタデータを対象にはしていません。
