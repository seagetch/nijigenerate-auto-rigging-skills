# Neck, standing collar and chest lapels

## General decision

The standing collar wraps the neck; the lower lapels and pendant attach to the upper chest; a free tip has its own local freedom. They need not inherit identical motion. Preserve physical design length; do not force constant screen length when the supporting chest is foreshortened.

## Procedure

1. At neutral, both Body yaw directions, forward/backward pitch and relevant Face/Roll combinations, label neck skin, collar base/top, lapel roots/tips, pendant and sternum landmarks in their supporting local frames.
2. Read each region's mesh ownership, clipping, Welding, parent motion and direct Part bindings. Identify double application or stale parent compensation before planning a new delta.
3. Keep the accepted standing collar fixed while correcting chest lapels, or vice versa. For a Part spanning both surfaces, identify separate vertex bands and a transition band; do not translate/rotate the whole Part merely to fix one band.
4. Derive lapel orientation and apparent shortening from the current rendered chest tangent and reference at that exact pose. Keep roots attached and both sides consistent with perspective. Correct local Part residuals; route wrong bone pose to its bone owner.
5. Inspect collar/skin occlusion, shoulder penetration and lapel length together. Check both left/right turns, forward/backward keys, halfway values and Face::Roll plus Body combinations. Record design-space consistency separately from projected length.
6. Read back every affected key and protected region. A save request records the current version; it does not overturn a prior visual rejection.

For the rejected neck/collar shear example, read [Ao visual examples](ao-visual-examples.md). Its failure images and generated candidates are explicitly distinguished from accepted results.

## Face::Yaw-Pitchの首を最初から設計する

1. 同じ角度の参照で、顎の前面、首が顎の後ろへ入る上端、首の左右の見える縁、襟で隠れる境界、襟元・肩側の固定帯を別々に記す。首の上端は顎先そのものではない。
2. 首Partの親と子、支持Grid、BoneSources、首／頭の回転中心、現在の深度、FaceとBody各パラメータの寄与を読む。首が頭骨の影響を受けない構成なら、首の深度を変えるだけでFace追従が増えると決めつけない。頭の親になっている首ノードのTRS変更は頭全体へ波及し得る。
3. 骨・深度に問題がある場合は担当工程へ戻す。基礎運動が妥当で、上端の露出面や輪郭だけが不足する場合は首Partの上側と遷移帯を合わせる。近くの顔三角形や顎先の移動を首の上半分へコピーしない。これは首を前方へ引き、傾きと細さを作る。
4. 参照の首幅と左右縁を目標にし、上端の塗り面は現在の顎の後ろまで届かせる。隠れる上端を画面上の顎線へ溶接しない。襟元・肩帯を固定し、上端から固定帯へ連続的につなぐ。塗り面自体がなければ素材修正へ分ける。
5. 上向きと斜め上で丸い首の先端や隙間が露出しないこと、下向きで首が顎の前へ出ないこと、左右で首幅が不自然に反転しないことを確認する。Face修正をBody用の頭位置補正で代用しない。全キーとFace/Body複合時に、顔・襟の保護状態も検証する。
