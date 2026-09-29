# DepthRigRoot・標準DepthBone・BoneSource 操作手順

## 目次

1. 絶対規則
2. 事前読戻し
3. DepthRigRootの作成
4. 標準DepthBoneの生成
5. 画像からの座標調整
6. LockToRootの座標規則
7. BoneSourceの割当て
8. 保存と監査
9. 実際に起きた失敗と復旧

## 1. 絶対規則

- `njc`実行ファイルを明示指定、`NJC_PATH`、プロセス`PATH`の順で解決する。リポジトリ相対パスを仮定しない。
- モデルの変更はすべて、解決した`njc`の`tools call`で行う。
- `.inx`を解凍、JSON置換、バイナリ置換などで直接編集しない。
- 既に開いているモデルを`FileCommand_OpenFile`で開き直さない。
- Computer Useでnijigenerateを操作しない。
- 保存は`FileCommand_SaveFile`で行い、保存先と上書き可否はユーザーの指定に従う。
- UUID、親子関係、コマンド引数は毎回現在のモデルと`tools list`から得る。過去モデルのUUIDを流用しない。
- PowerShellへ生JSONを直接埋め込まず、Pythonの`subprocess`と`json.dumps`でnjcを呼ぶ。引用符崩れを避ける。

## 2. 事前読戻し

変更前に次を保存する。

1. `njc find "*"`の全ツリー。
2. 全ノードの`njc read UUID`。
3. `ViewportCommand_ListFlipPairs`。
4. 既存`DepthRigRoot.bindings`。
5. 全GridDeformerに対する`DepthBoneCommand_ListDepthBoneSources`。
6. `ViewCommand_CaptureLiveScreenshot`によるニュートラル画像。
7. 保存先と上書き可否がユーザーの指定と一致していること。

`DepthBoneCommand_ListDepthBoneSources`は読み取り用途でもコマンドメタデータ上は副作用ありと表示されることがある。返却JSONの`succeeded`と`result`を必ず確認する。

## 3. DepthRigRootの作成

### 3.1 親を決める

通常はキャラクター全身を保持する`Body::Root`相当のNodeを親にする。名前だけで決めず、現在のツリーと表示Partの包含範囲を確認する。

### 3.2 作成

```json
{"parent": 123456, "name": "DepthRigRoot"}
```

`DepthBoneCommand_CreateDepthRigRoot`を呼ぶ。作成前後のUUID差分から新しいRootを特定する。戻り値やGUI選択状態から推測しない。

### 3.3 直後の検証

- 型が`DepthRigRoot`。
- 親UUIDが予定したBody Root。
- 直接の子が空。
- 同名Rootが重複していない。
- 既存ノードのhashが不変。

既存Rootがある場合は新規作成しない。正確なRoot 1件と既知の標準骨19本がある場合だけ再開候補とする。半端な本数、重複名、異なる親がある場合は停止し、削除や作り直しを自動で行わない。

## 4. 標準DepthBoneの生成

Rootが空であることを確認してから実行する。

```json
{"root": 234567, "scale": 1.0}
```

`DepthBoneCommand_AddStandardDepthSkeleton`を呼ぶ。AutoMeshの`skeleton`プロセッサや手作業の`AddDepthBone`で代用しない。

### 4.1 標準19本

```text
DepthRigRoot
└─ Pelvis
   ├─ Spine
   │  └─ Chest
   │     ├─ Neck
   │     │  └─ Head
   │     ├─ Clavicle.L
   │     │  └─ UpperArm.L
   │     │     └─ Forearm.L
   │     │        └─ Hand.L
   │     └─ Clavicle.R
   │        └─ UpperArm.R
   │           └─ Forearm.R
   │              └─ Hand.R
   ├─ Thigh.L
   │  └─ Shin.L
   │     └─ Foot.L
   └─ Thigh.R
      └─ Shin.R
         └─ Foot.R
```

### 4.2 必須検証

- 19本すべて型が`DepthBone`。
- `name == boneId`。
- 親子関係が上表と一致。
- `restHead`、`restTail`、`restRoll`が有限。
- 全長が0より大きい。
- `Head.allowParentToTargets=false`。
- `Foot.L.lockToRoot=true`、`Foot.R.lockToRoot=true`。
- 左右7組のflip pairを追加して読戻す。

標準生成はFootだけを`lockToRoot=true`にする。ここを見落とすと後工程の実表示位置が壊れる。

## 5. 画像からの座標調整

### 5.1 先に座標計画を作る

現在のライブスクリーンショットを使用し、次のランドマークを画面ピクセルで記録する。

- 骨盤中心、胸郭中心、首、頭部中心。
- 左右の肩、肘、手首、手先。
- 左右の股関節、膝、足首、靴先。
- 服で隠れる股関節は、見えている大腿中心線を上へ延長して推定する。
- 体幹はX一定の直線と決めつけず、原画の傾斜やS字を読む。

`.L`と`.R`が画面のどちら側かを作業記録へ明記する。名前規約よりユーザーの指定を優先する。同じモデルの途中で規則を変えない。

### 5.2 画面とモデル座標の換算

少なくとも2点以上の既知座標を使い、表示倍率と表示原点を検証する。単純な純平行移動モデルなら次を使える。

```text
screenX = (rootLocalX + bodyRootTranslationX) * scale + viewOriginX
screenY = (rootLocalY + bodyRootTranslationY) * scale + viewOriginY
```

親に回転または拡縮がある場合は、足し算へ簡略化せず完全なTRS行列で変換する。推定結果を`NOT APPLIED`の画像とJSONとして提示してから反映する。

### 5.3 rest姿勢を設定する

全骨を一度に計画し、親子の端点を連続させる。

```json
{
  "bone": 345678,
  "restHead": [10.0, 20.0, 0.0],
  "restTail": [12.0, 40.0, 0.0],
  "restRoll": 0.0
}
```

`DepthBoneCommand_SetDepthBoneRest`を呼ぶ。

### 5.4 アプリ実表示transformも設定する

`restHead`だけを正しくしても、アプリ上のNode transformがテンプレート位置のまま残ることがある。全骨について`Inspector_Apply_TranslationX/Y/Z`をnjcで設定し、`njc read UUID`で読戻す。

通常の子骨では、親骨が回転・拡縮なしなら次になる。

```text
localTranslation = desiredRestHead - parentDesiredRestHead
```

PelvisのようなRoot直下骨ではRootローカル座標を使う。

重要: 適用後オーバーレイは`restHead`から描かず、読戻したtransformを実際の親規則で累積して描く。そうしないと「画像上は合うがアプリ上はテンプレート位置」の誤判定になる。

## 6. LockToRootの座標規則

`lockToRoot=true`のNodeは通常の親DepthBoneではなくPuppet Rootを親座標として評価する。標準骨では`Foot.L`と`Foot.R`が該当する。

誤った式:

```text
foot.local = foot.restHead - shin.restHead
```

正しい手順:

1. Footの目標点をDepthRigRootローカルで決める。
2. その点をDepthRigRootからPuppet Rootローカルへ変換する。
3. 変換後の座標をFootのtransformへ設定する。
4. `lockToRoot=true`が維持されていることを読戻す。

Body Rootが純平行移動、DepthRigRootが単位変換なら次に簡略化できる。

```text
footRootRelative = bodyRootTranslation + footRestHead
```

回転・拡縮があるモデルではこの簡略式を使わず、行列変換する。ShinからFootへの描画線は見た目上の連結であり、transformの親座標ではない。

## 7. BoneSourceの割当て

### 7.1 方針

- 顔・頭部に固定されるGrid: `Head`のみ。
- 体幹Grid: `Pelvis → Spine → Chest → Neck`など、そのGridが覆う中央系列。
- 左右腕Grid: 同側の`Clavicle → UpperArm → Forearm → Hand`。
- 左右脚Grid: 同側の`Thigh → Shin → Foot`。
- 腰から両脚を覆う共有衣装Grid: `Pelvis`と左右両脚の全系列。
- 片側衣装は反対側Boneを含めない。
- 各リスト内に重複を作らない。

全GridDeformerを列挙してから完全な対応表を作る。1件ずつ考えながら追加しない。

### 7.2 事前検証

各対象で`DepthBoneCommand_ListDepthBoneSources`を呼ぶ。

- 空配列: 新規追加可能。
- 期待リストと完全一致: 適用済みとしてスキップ可能。
- 期待リストの正しいprefix: 中断後の安全な再開として不足分だけ追加可能。
- それ以外: 停止。自動削除・並べ替えをしない。

### 7.3 追加

```json
{"root": 234567, "target": 456789, "bone": 345678}
```

`DepthBoneCommand_AddDepthBoneSource`を根元から先端の順で呼ぶ。追加順が保存順になる。

### 7.4 読戻し形式

`ListDepthBoneSources`の`sources`要素は設定を直接持つ。

```json
{
  "uuid": 345678,
  "weight": 1.0,
  "depthOffset": 0.0,
  "depthScale": 1.0
}
```

`source["settings"]`という入れ子は存在しない。必ず`source["weight"]`等を読む。

全対象でUUID順序、重複なし、既定設定を確認する。`DepthRigRoot.bindings`も読み、対象UUIDとsource UUID列が一致することを確認する。

## 8. 保存と監査

次をすべて満たしてから保存する。

- 全19骨のrest値とtransform読戻しが計画と一致。
- 通常骨とLockToRoot骨を別の座標規則で検証。
- 画像ランドマークとアプリ実表示点が許容誤差内。
- 全GridDeformerのBoneSourceが対応表と完全一致。
- DepthRigRoot以外のノードhashが不変。
- 階層とflip pairが不変。
- パラメータ、メッシュ、変形キーを追加していない。
- ニュートラル画像がピクセル一致。

`FileCommand_SaveFile`へ`{"file":"C:\\path\\to\\model-v2.inx"}`を渡す。保存後も現在のアプリ状態をnjcで読戻す。INXを直接開いて検証する方法へ切り替えない。

## 9. 実際に起きた失敗と復旧

### 9.1 Footを通常骨として累積した

症状: restオーバーレイでは足首に合うが、アプリではFootだけ離れる。

原因: `Foot.L`/`Foot.R`が`lockToRoot=true`なのに、Shin差分をtransformへ設定した。

復旧: Footのlock状態を読戻し、Puppet Root基準へ変換した値だけをXYZ transformへ再設定する。restHead/restTail、親Shin、flip pairは変更しない。

### 9.2 rest図だけを見て「アプリ位置も合った」と判断した

症状: 生成画像は正しいが、nijigenerate上ではテンプレート位置のまま。

原因: オーバーレイをrestHeadから描き、実Node transformを検証していなかった。

防止: オーバーレイはnjc読戻しtransformから作る。通常骨は親累積、LockToRoot骨はPuppet Root基準で計算する。

### 9.3 `.L`/`.R`を一般規約で決めつけた

症状: 左右の骨が画像と逆側へ入る。

防止: 適用前表に`.L=画面左/右`を明記し、左右7組の平均Xと対象ランドマークで検証する。

### 9.4 腰をスカート中心へ置いた

症状: Pelvisと両Thighの分岐が脚中心線と合わない。

防止: 見えている両大腿軸を上へ延長し、荷重分岐と体幹中心線から骨盤中心を決める。

### 9.5 `sources[].settings`を読もうとして監査が停止した

症状: BoneSource追加後、`KeyError: settings`でスクリプトが終了する。

原因: 実返却は設定の入れ子ではなく、`uuid/weight/depthOffset/depthScale`を直下に持つ。

復旧: モデルを開き直さない。全対象を再読戻しし、期待リストと完全一致またはprefixなら冪等に再開する。`scripts/apply_bone_sources.py`はこの形式と再開を実装している。

### 9.6 追加途中で停止した後、最初から無条件追加した

防止: 変更前に全対象をまとめてpreflightし、各現状が空、完全一致、期待prefixのいずれかであることを確認する。prefixには不足suffixだけを追加する。

### 9.7 PowerShellのJSON引用符が崩れた

防止: Pythonの`subprocess.run([njc, "tools", "call", ..., "--json", json.dumps(payload)])`を使う。シェルで手組みしたJSONを渡さない。

### 9.8 保存先を推測した

防止: 新規版名を必須にせず、保存先と上書き可否をユーザーの指定から確定する。既存保存先へ保存する場合は補助スクリプトへ`--overwrite`を明示する。
