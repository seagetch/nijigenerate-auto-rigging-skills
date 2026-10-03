# 人体・アニメ絵リギングの設計 — PSD限定入力

## 対象と不変条件

人体型イラストを、単眼で観測できる投影形状と人体・アニメ絵の事前知識で構築する。頭身、傾き、非対称、衣装、髪、付属物の差を許容する。同じ意味の素材を分割・統合・改名しても、骨格と共通形状の未知数が増減しない。分割によるmesh・texture枚数の変化は許容する。

外部のキャラクター入力はPSD一つだけ。原画PNG、INX/INP、意味注釈、基準点、寸法、対応表、姿勢表を追加入力にしない。[PSD限定フロー](psd-only-flow.md)に従って内部生成する。汎用prior・テンプレート・標準動作は同梱資源であり、モデル別の外部overrideを受けない。

INX/INPおよびアプリ内モデルへの全操作は`njc`実行ファイル経由に限定する。読取・import・構築・変更・複製・保存・再読取・描画もこの境界に含む。直接ファイル解析やコピー、HTTP直呼び、GUI操作による代替は認めない。純粋なPSD解析と数値計算はPython内で行い、その結果を`njc`へ渡す。[NJC限定契約](njc-only.md)に従う。

単眼画像から真の奥行きや隠れた体積は一意に復元できない。ここを停止条件にせず、深さ・断面・関節配置のpriorを明示した推定値として扱う。観測で拘束される投影形状と区別する。基準点を黙って既定値で埋めることと、宣言したpriorを観測に合わせて最適化することは異なる。

共通specに置くのは人体の関節順、局所座標、意味役割、形状operator、支持分類、単位、許容範囲。キャラクター固有の座標・UUID・名前はsource hash付き観測だけに置く。規則を追加する場合は、その素材以外の構造にも適用できる根拠とテストが必要。

## 五つの表現

| 表現 | 内容 | 区別するもの |
|---|---|---|
| Source observation | 素材、個別alpha、neutral合成、画像→モデル変換、可視状態、名前、階層、描画設定 | 材料境界と関節・面境界 |
| Anatomical scaffold | 頭・胸郭・骨盤、首、肩・肘・手首、股・膝・足首、局所frame、共有体積 | 可視胸patchと胸郭全体 |
| Material surfaces | owner、chart、接合帯、固定端、自由端、離隔、表裏、素材UV | 被覆材の枚数と人体の体積数 |
| Motion graph | 姿勢driver、関節回転、局所補正、目口機構、二次動作、依存関係 | 頭回転と目口開閉 |
| Render graph | 描画順、clip、透過、blend、遮蔽の期待関係 | 描画順と物理depth |

ownerは基礎体積を共有する識別子。chartは素材を置く領域であり、同じownerでも自由布・耳・髪が同じ変形場になるとは限らない。chart数を独立fit数へ直結させない。親の剛体継承、skin、縫合、被覆、機構、遮蔽はtyped edgeで区別する。縫合graphのloopは許すが評価の依存graphは循環させない。

## 入口と意味観測

PSDは正規importし、平坦階層・Gridなしでも受け入れる。作業用INXを内部で作り、その保存値とneutralライブ値の差を記録する。再実行では同じPSDに由来する作業出力の置換範囲を定義し、既存driverへ無条件に加算しない。過去の別モデルやユーザー提供INXを入口にしない。

個別alphaとsource-to-model変換を保存する。texture未読時のbboxをsilhouetteと呼ばない。合成alphaを各素材のalphaに代用しない。描画設定とmaskもsource observationに残す。

意味観測はPSD由来の画像・埋込名・階層・幾何候補と同梱辞書から内部生成する。source注釈はPSD内の情報を指し、別の注釈fileではない。名前辞書は補助であり、所定のレイヤー名をsolverの入力要件にしない。無名素材も幾何・配置の候補を作り、エージェントは曖昧な意味候補を比較する。数値座標は共通測定・適合器から出す。作者へ分類や基準点の提出を要求しない。匿名素材と名前付き素材を同じIRへ入れる。

根拠を measured、visual_estimate、source_annotation、prior、unresolved に区別し、座標・単位・frame・対象・信頼幅・source hashを持たせる。名称規則のスコアを認識確率と称さない。

## 全身fitと自由度

未知数は頭・胸郭・骨盤の位置/向き/寸法、関節位置、chartの幅profile・長さ・root帯・自由端。目鼻口は頭面を拘束し、衣服の首/肩/腰境界は隠れた胴体を拘束する。可視肌だけで胴のframeを固定しない。

目的関数は投影基準点、可視輪郭、接合、関節順、対称性のsoft prior、形状prior、複雑さの項で構成する。各項は単位と信頼幅で正規化し、未観測の背面に輪郭誤差を課さない。非対称な絵へ完全対称を強制しない。

頭/胸郭/骨盤と関節graphの粗fit、chartの低自由度適合、共有接合の再最適化、mesh標本化の順で解く。Partごとのpivot移動で矛盾を隠さない。傾いた身体は局所frameで扱い、画面軸のbboxを人体座標にしない。

初期化・探索順・seed・停止条件・実行環境を記録する。収束しない場合は拘束と残差から観測の意味か共通operatorへ戻る。同じ入力で再現可能とし、異CPUでのbit一致を未検証で保証しない。

必須基準点は同梱の標準動作と推定構造の依存graphから選び、PSDの観測とpriorから内部生成する。開閉境界の不足は頭回転まで止めない。肩や骨盤の矛盾は全身動作の適用前に解く。胸布ごと、影ごとのrequired roleを増やさない。生成器の不足をユーザー提供基準点で補わない。

## 工程の契約

| 工程 | 入力 | 出力 | 受入条件 |
|---|---|---|---|
| capture-source | PSD、実行環境 | 内部INX、observation、texture、alpha、変換、描画設定 | neutralと変換照合済み |
| assemble | PSD由来の内部observation・意味候補、同梱人体archetype | owner/chart/mechanism/支持/描画IR | 素材所有一意、矛盾は依存先付き |
| solve-scaffold | 内部IR・測定基準点/輪郭、同梱prior | 局所frame、関節、体積、残差、根拠 | 標準動作の支持と接合が成立 |
| fit-materials | scaffold、alpha、境界 | 共有surface、coverage、素材UV | 中立保持、被覆、接合、非反転 |
| compile-motion | surface、同梱方針と推定構造から導出したdriver・範囲 | mesh/parameter/bindingのprogram | kernel生成、単位と親寄与確定 |
| apply-program | program、NJC較正、作業model | 保存model、readback、記録 | 実状態がprogramと一致 |
| validate-output | 保存model、内部動作仕様、PSD由来source | 実render、数値・外観検証 | 中立/単軸/途中/複合/再読取合格 |

これは実装契約であり全工程がCLI実装済みという意味ではない。programにはnode作成、mesh、parameter、binding、保存まで含める。depth配列だけ出して完成扱いしない。

## 座標とengine適用

pixel、UV、局所surface、モデル、engineのframeを明示する。L/R名と画面左右を分離する。root/関節にpivotを置き、親の姿勢を一回だけ合成する。

中立素材をsource変換でモデルへ写しsurface上のUVを求める。姿勢評価したモデル位置をcarrierの評価座標へ戻して変位を作る。既存親へbaked world座標を加算しない。標本化は対象頂点順hashで固定する。

NJC adapterは現行公開schemaと独立project codeから座標・単位・親寄与を確認し、作業対象の実データと描画で照合する。モデル固有の符号・固定座標で合わせない。carrier/mesh/parameterの新規作成もadapterの責務。手動コマンド列で未実装compilerを代用しない。このセッションではテストfixtureを一切生成しない。

入力を保持した作業modelへ`njc`で適用し、timeout時は`njc`で実状態を再読取する。適用済みか不明な変更を重ねず、別modelへ書き込まない。INXの直接読取・編集・コピーは実装から排除する。コマンド成功と読み込み完了・非同期キー書込完了を区別し、対象の同一性を確認できない状態で次の変更を始めない。

DepthRigRootはモデル全体で1個とし、すべてのDepthBoneはその配下に置く。再構築時は未リグの元入力から作業出力を読み込み、実際のノード集合が元入力と一致したことを確認してから生成する。保存後にも個数、UUID、所属を検証する。

## 独立性と受入

以下の対で検証する。集約テストの合格は完成rigの保証ではない。

- UUID・名前を変更し、意味観測だけ対応させても骨格/owner/driverが変わらない。
- 素材分割・統合が変わっても同じ投影制約から同じ構造自由度を得る。
- 頭身、長さ、傾き、非対称、平坦/既存carrier階層の違いに対応する。
- 大きな尾・耳・長布の追加が無関係に人体frameを拡大しない。
- 胴が衣服に隠れても空の胴や小さな胸patchへ退化しない。
- 影・柄・輪郭の素材分割で体積ownerが増えない。

最終受入には保存model、PSD/source/IR/program hash、標準動作の実描画を揃える。数値kernel、backend、素材外観は別々に確認する。

## 旧版との接続

inspect-model、数値kernel、template、局所fit/sceneの単体検証を再利用する。infer-structureのcarrier seedとbbox探索は候補補助へ降格し、新規buildの構造確定に使わない。

旧requiredは単独templateの前提として残し、v2の要求動作とjoint solverの状態へ変換する。一律falseにして不足を消さない。旧compile-njcは既存carrierの二種類の配列用であり、全rig compilerとして名前だけ再利用しない。
