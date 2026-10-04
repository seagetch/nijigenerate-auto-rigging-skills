# 実装とPSD限定契約の対応

## 現行入口の更新

以下の経路が現行実装であり、後段の旧経路の記述に優先する。目・口・眉の局所Part調整は実装されているが、PSD形状に基づくFace/Body角度の輪郭・遮蔽Part補正は未実装である。構造補償の撤回を、正しい個別Part補正も不要になったことと解釈してはならない。

- 登録はPSD index pathと親階層を照合する。重複名・末尾NUL・可視性・合成モード・opacityを検査し、合成グループとクリッピングを保持する。
- `riglib/semantic_observation.py` は名称・祖先・alphaから意味候補を生成し、候補の由来を保存する。クリッピングから物理支持を継承しても、瞳など既知の局所機能は上書きしない。
- `riglib/psd_evidence.py` は部品ごとのPSD→モデル座標対応、左右一体素材の空間領域、可変個数の目口素材、順序制約を満たす胴体のpriorを生成する。素材数の固定条件は設けない。
- 全身Gridは起点Partの支持階層へ組み立て、world座標とPSDの合成・クリッピング関係を保持する。Body::Root → Body Grid → body起点Part → Head::Root → 頭の各面Gridとし、顔の局所機構を顔起点Partの下へ集約する。
- PartはNJC Grid AutoMeshでalpha領域全体と外周余白を覆う。細い輪郭や小さい島を捨てる輪郭近似を初期メッシュの必須条件にしない。
- GridもAutoMeshで生成する。軸に平行なcarrierを先に配置し、同じcarrier-local座標でalpha範囲と分割位置を対応付ける。native float32正規化で一致する格子線をまとめてAdvancedへ渡し、生成格子を保持する。目・口のDynamicComposite自身にも共通規則によるGrid AutoMeshを適用する。
- `preserve_source_uv.py` はsource UVから親座標への対応をPartのTRSで合わせる。AutoMeshの頂点・UV・三角形・originは変更しない。起点Partへ子を接続する前に座標登録を完了し、目口はその後に生成する。登録hashを各変形programへ記録する。適用直後と保存再読取後の配列一致を検査し、共通NJC adapterではDefineMesh/DefineGridを拒否する。
- `apply_shape_controls.py` は入力PSDの輪郭から目・眉・口・局所曲げのキーを生成する。参照Partの変位は使用しない。
- `apply_shape_corrections.py` による構造の接触補償は撤回。初期生成の `riglib/hierarchy.py` と `riglib/initial_tree.py` で、body起点Part → Head起点 → 頭面、顔起点Part → 顔の局所機構を構築する。保存済みリグへの補償処理は実行しない。
- 口・顔・局所素材は `build_local.py` を通る。全身19骨を素材要件にしない。
- `riglib/render_camera.py` の固定カメラで登録時と保存後を比較する。表示のFit結果を同一カメラとみなさない。フィルタ境界には1 texel相当のbbox許容を使い、RGB・alpha誤差は従来の数値閾値で別に検査する。
- `riglib/shape_validation.py` はUV座標補正後の保存キー・三角形の向きも検査する。状態確認済みの現行モデルは再利用し、OpenFileの成功応答だけでモデルが切り替わったと判定しない。

`completion-stages.json` の `numerical_stages_passed` と描画レビューを区別する。検証対象、失敗箇所、元PSDのhashは実行結果で確認する。初期登録や骨格生成の成功を完成リグの件数へ加算しない。

## 現行の共通参照テンプレート経路（2026-10-03）

公開入口 `run_psd_rig.py` は、指定された両参照からコンパイルした **1つの**
`structures/reference-humanoid.registered.json` を全身に適用する。
以下に残る独立 `face_head` 転写・priorだけの胴体深度に関する記述は旧経路の記録であり、
現在の入口では `fit_face_template.py` / `apply_face_template.py` を実行しない。

意味座標による再構成を追加した。頭部・胴体・左右四肢の6領域で32点を対応付け、
同じ滑らかな座標変換を深度、支持、変形、素材補正へ使用する。
出力のグリッド数は固定せず、対象素材上での復元誤差から細分化する。
具体的な誤差条件、送信精度、観測と検証の限界は
[semantic-reconstruction.md](semantic-reconstruction.md) に記載する。
保存モデルの検証状況と複数PSDでの未検証事項は、開発記録を正とする。

- `compile_registered_reference.py` と `riglib/reference_fields.py`：NJC採取済みの両参照を解剖学frameへ登録し、26の構成面、19骨の共通階層、38の骨曲線、グリッド、深度配置、起伏、親からの支持、局所変形を1つへ適合する。参照名・UUIDによる実行時選択はない。
- `riglib/reference_compile.py`：PSD由来frameへ共通面を登録する。親の移動は対象の共通座標で評価し、局所変形だけを部位frameで変換する。各identity carrierには合成済み変位を一度だけ書く。
- `derive_psd_evidence.py`：前髪・横髪と顔の不透明画素の重なりを取得する。必要な面全体のZオフセットはこの観測から求め、深度の起伏を増幅しない。
- `build_native.py`：共通深度・Z配置と参照骨曲線を設定する。Bodyの2基本parameterは共通参照場を使用する。追加の腕・肘・脚・膝は明示したpriorを使う。
- `bake_depth_angles.py`：FaceのGrid変位はNJCのDepthBone計算のみで生成する。固定入力の不変性、全Head面のXYZ投影残差、保存後の値を検査する。
- `apply_reference_materials.py`：参照にあるPart局所補正を別層で転写する。顔角度のGridは書き換えず、NJCから読んだ実際の親変位を使う。
- `regularize_fixed_feet.py`：共通参照のBody::Rollを上書きしない。追加の脚・膝parameterだけに使用する。
- `validate_reference_transfer.py`：NJCで骨の親子、Headの継承制約、足のLockToRoot、全グリッド、深度、基本parameterの全変形キー、38骨曲線、不透明画素の深度順序を再照合する。

転写するBody場とPart局所補正のセル反転は、深度・角度を変更せず最小の投影修正で拘束する。顔角度のGridには投影修正を適用しない。全参照面と対象登録後の全キーで検査し、許容範囲内で解けなければ適用前に拒否する。対象別の手製座標・補正表は受け付けない。

中立保存・UV保存・PSD登録・瞬き/視線/既存口素材の処理は引き続き使用する。参照中の全物理設定や全表情parameterを複製する処理ではない。平坦PSD・名前補助付きの意味認識という入力上の制限も残る。採取・適合・描画の根拠は [reference-template-development.md](reference-template-development.md) を参照する。

## 旧実装の構成と開発記録

キャラクター資料はPSDだけを外部入力にする。INX、意味観測、基準点、体積寸法、素材対応、姿勢表は内部生成物である。以下は入力採取、内部計算、実適用を区別した実装状況であり、工程が存在するだけでPSDから全てが自動接続されているとは扱わない。

モデル操作は読取も含め、すべて`njc`実行ファイル経由。[NJC限定契約](njc-only.md)を実装の必須境界とする。

## 入力採取

- `rig.py prepare-psd` / `riglib/psd_source.py`: PSD一つと出力先からレイヤー画素・alpha・index path・階層・offset・表示/描画属性・合成画像を採取する。別INX、外部画像、注釈JSONを取らない。同名レイヤーを名前で一意化しない。段階の成功は`psd_observation_ready`でありリグ完成ではない。
- `capture_source.py`: PSDと既存INXの名前対応を使う旧採取器。新しい公開入口には使わず、当該PSDを正規importした内部INXとの照合用途に限る。重複名に対応するimport ID対応の自動構築は未統合。
- `model.py`: NJCの公開resourceから現在のnode構造を取得し、純粋normalizerへ渡す。INX/INPを直接開かない。完全parameter情報が取得できない場合は完全観測を拒否し、node限定の検査とは区別する。

## 内部の意味・構造・数値計算

- `assembly.py`: 観測を体積owner/chartへ集約し、素材被覆と解剖学frameを分離する。名前付き候補と、内部の意味観測を扱う。`material-roles.json`は同梱の補助辞書であり、所定のレイヤー名への変更を要求しない。
- `propose-core-landmarks`: 頭・胴・四肢の集約観測から基準点候補を作る。完全な解剖学認識ではない。
- `anatomy.py`: 与えられた内部関節観測を拘束付き最小二乗で適合し、局所frame、骨、共有深度場を計算する。体積中心・半径、四肢半径、左右対応をPSDから自動生成する工程との接続は未完成。
- `native_compile.py`: 内部assembly/scaffoldから共通面、mesh、深度、driverのprogramを作る。初期深度は`anatomy.py`の共通式であり、19種のテンプレートruntimeとは未接続。
- `template_runtime.py`: 同梱templateと内部chart仕様から意味格子・深度・局所補正を計算するAPI。PSDからのchart仕様生成と主compilerへの統合が必要。
- `geometry.py` / `pipeline.py` / `scene.py`: 局所surface・登録・姿勢評価の共通kernel。個別Partの手製数値を入力して全身適合を代用しない。

意味観測の`source_annotation`はPSD内部の名前・メタデータ由来に限る。`visual_observation`はPSDから内部抽出した画像に対する意味候補の判断であり、別資料や手製座標を読み込む経路ではない。内部成果物はPSD hash・レイヤーID・生成方法・コード/prior版へ遡れるようにする。

## 適用と検査

- `build_native.py --apply`: 内部生成した未リグINXを作業出力へ読み込み、構造一致を確認してRigRoot・骨・Grid・parameterを作る。変形キーの書込完了とRigRoot一個を検査して保存する。
- `build_face.py`: 内部の眼角・顔素材対応・口軸を用い、PSD由来alphaから瞼曲線をfitし、瞬き・視線・既存口素材の拡縮を作る。これらの意味対応をPSDから自動生成する接続は未完成。口内素材の自動生成は含まない。
- `refresh_surfaces.py`: 既存構造の深度を更新し、影響する回転キーを再生成する。面集合の変更は再構築が必要。
- `render_rig.py`: NJCで期待RigRoot・骨を照合したライブモデルのnode・Binding resourceを数値集計し、姿勢を描画する。INXファイルは読まない。保存ファイル全体との一致、完全parameter設定、瞬き/視線/口の描画ケース、外観の自動合否判定は含まない。
- `live.py`: 全アクセスをNJC subprocessへ限定。大容量HTTP fallbackは撤去し、対応していない引数長は送信前に拒否する。`data.py`もINX/INPへの汎用ファイルI/Oを拒否する。
- `njc.py`: 既存carrierの二種類の配列を対象とする命令計画。`build_native.py`の構築adapterと同じものではない。

## 次に接続するもの

1. PSDのindex pathと正規importした内部INXの対応・変換・中立描画を自動照合する。
2. PSDの画素・alpha・配置・支持候補から関節/体積/左右/顔機構の観測を生成し、全体の拘束へ戻して適合する。
3. 同梱テンプレートへ共有chartを適合し、主compilerへ渡す。手製のchart座標を外部入力にしない。
4. 標準動作を構造から選択し、適用・保存再読取・全対象動作の描画検証を接続する。
5. 全工程の内部成果物の由来を検査し、別PSDや外部JSONの混入を実行時に拒否する。

現在も低水準CLIは任意pathを読める。公開利用の入口をPSD採取に限定する契約と、すべての低水準APIでの由来強制は別であり、後者を実装済みとは報告しない。未完成箇所は共通実装の責務として扱い、追加の資料提出をユーザーへ要求しない。

## 2026-10-03 の実素材接続

- `prepare_live_psd.py`: 正規import後の平坦なPSDレイヤー順・名称・表示状態を照合し、NJCのselectorが暗黙ルートを省く環境用に明示ルートを作る。保存時に割り当てられるtexture slotと形状差を区別し、再読込後の観測をcompiler入力にする。グループ付きPSDへの対応は未実装。
- `derive_psd_evidence.py`: 当該PSDのalpha断面と同梱の名前候補から関節・体積・顔機構を内部生成する。左右は配置から決定する。隠れた関節は明示したpriorであり、匿名レイヤー認識の完成を意味しない。
- `fit_face_template.py` / `apply_face_template.py`: `face_head`の意味基準点、深度operator、局所補正を実モデルへ接続する。実NJCの頭部bindingから射影を較正し、適用前に全キーの格子4隅のJacobianを検査する。顔の凹凸は既定parameterを保持する。眼・口の基準面を共有頭部の前面へ配置するZオフセットを別に計算し、外周だけの射影補正でJacobianを拘束する。意味基準点と不透明画素で転写誤差を計測して格子を適応細分化する。三角meshも転写誤差と各姿勢の面積比で検査し、不成立なら適用前に停止する。生成programと保存再読込後の配列を照合する。
- `regularize_fixed_feet.py`: 股・膝・固定足首から共有する縦方向Hermite変位場を生成し、足固定と最近傍skinningの境界に生じた反転を修正する。
- `validate_saved_rig.py`: 保存前後の公開node・全bindingを照合し、16パラメータの75姿勢を描画した。公開APIにないparameter設定やINX全内容の一致は主張しない。取得途中のモデル変更と、探索結果の列挙順の変化を区別する。

今回実モデルへ接続したtemplate runtimeは`face_head`のみ。他部位の深度は`anatomy.py`と同梱humanoid priorに基づく。全19templateの実適用を完了したとは扱わない。均等格子と簡略頭部深度だけの旧出力を、顔templateに従った完成結果と呼ばない。

## 胴体中心線の修正

`humanoid-prior` 2.3.0 と `anatomy.py` は、首基部と左右股関節の中点で傾きを持つ共通胴体軸を定義する。胸・腰の衣装断面は軸方向の位置だけを拘束し、衣装の横方向の非対称を背骨の位置に使用しない。胸・腰を独立未知数から除き、骨盤を股関節中点へ厳密に接続した縮約最小二乗で全身の骨格を解く。胴体の体積中心・縦半径も解いた軸から再生成する。数値を後から書き換えるpivot補正ではない。

この宣言した中立軸priorは首から骨盤まで直線であり、傾きは許すが、原画の意図的な脊柱湾曲を推定するモデルではない。断面観測の破棄した横成分と適合残差を記録する。`scaffold_validation.py` はNJCで保存後の全骨のrest座標を取得し、生成programとの一致、関節の接続、中心線、関節順、骨盤と股関節中点の一致を検査する。

## PSDからの新規生成入口

`run_psd_rig.py --psd <PSD> --out <fresh-directory> --njc <executable>` は抽出、正規取込、登録、観測生成、全身構築、顔適合、転写、保存検証を順に起動する。入力素材はPSDのみで、観測・modelがある出力先への再生成は拒否する。既存成果の頂点や係数を継承しない。現状の取込登録は平坦なPSDに限定される。

`hierarchy.py` は身体・骨盤・上体・首・頭・四肢・衣服の所有関係を組み立てる。グループ自身はidentity変換で、運動は各surfaceの骨sourceから一度だけ生成する。胸と腰の付属品、腿と足首の付属品は支持骨を分ける。保存後には親子関係とDepthRigのsourceBoneUuidsを両方照合する。

名前から特定モデルの所属を上書きする例外は使わない。辞書で未確定の垂れ物は、alphaの上端と支持候補の距離から候補を比較し、その選択を内部記録する。顔素材は役割UUIDで取得し、眼部品は配置から左右へ対応付ける。これは名前補助付きの推定であり、任意の素材命名に対応する意味認識を保証しない。

顔転写の数値計算はNumPy、SciPy、OSQPを使用する。追加依存はskill配下の`.runtime`に配置し、モデル通信経路には使わない。格子とmeshの配列はNJCのコマンド長を適用前に検査する。

`preserve_source_uv.py` は正規importと再mesh後のUVをNJCで読み、両者のaffine対応を求める。meshローカル座標をUVに合わせ、逆変換をPartのTRSへ入れ、局所変位bindingにも同じ線形変換を適用する。親座標の頂点位置・運動を保ちながら、native mesh編集時の半画素UV差を解消する。shearや未解決の回転frameは適用前に拒否する。原画とUV、親座標の読戻し一致を検査し、中立描画の誤差閾値を緩めて通過させない。

`validate_neutral.py` は保存された取込直後モデルと成果モデルをNJCで開き、同じFitViewport条件で中立を描画する。双方のalpha全体がviewport内に収まり、bboxが一致し、premultiplied RGBとalphaの誤差が同梱priorの許容値以内であることを検査する。最後に成果モデルを開いた状態へ戻す。
