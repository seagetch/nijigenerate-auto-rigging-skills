"""Publish current PSD-folder records without copying assets or creating folders."""
from pathlib import Path
import argparse,json,html,re


def build(root):
    root=Path(root).resolve();rows=[];sections=[];executed=0;reopened=0;image_count=0;running=False
    columns=['PSD','取込・登録','意味観測','Part AutoMesh','TPS・格子設計','骨格・Grid','Grid AutoMeshの実出力','目・口のComposite AutoMesh','頭の接続・回転方向','目口眉・UV','深度の実測','深度・骨から角度生成','頬Part補正','保存・状態読取','変形画像','現在の処理・観測事項']
    def read(path):
        # A running stage may be replacing this small manifest while the
        # gallery refreshes. Keep the report available until its next update.
        try:return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
        except (json.JSONDecodeError,OSError):return {}
    for index,psd in enumerate(sorted(root.glob('*.psd'),key=lambda p:p.name.casefold()),1):
        run=root/psd.stem;s=read(run/'native-state.json');v=read(run/'validation.json')
        evidence=read(run/'evidence.json')
        program=read(run/'program.json')
        current=(program.get('hierarchy',{}).get('schema_version')=='rig-material-origin-hierarchy/2'
                 and bool(program.get('domains')) and bool(s.get('composite_automesh'))
                 and all(d.get('bone_influence_authority') in ('native_default','registered_reference')
                         and d.get('automesh_coordinate_authority')=='carrier_local_native_precision_v1' for d in program['domains']))
        if not current:v={}
        head=next((b for b in program.get('scaffold',{}).get('bones',[]) if b['id']=='Head'),{})
        completed=read(run/'completion-stages.json') if current else {};status=read(run/'run-status.json')
        if status.get('status')=='queued':
            current=False;completed={};v={}
        running=running or status.get('status') in ('running','queued')
        cheek=read(run/'shape-corrections-readback.json') if s.get('shape_corrections_sha256') else {}
        executed+=int(bool(completed.get('all_stages_attempted') and not completed.get('stage_errors') and cheek))
        reopened+=int(bool(v.get('readback_equal')))
        image_count+=len(v.get('rendered',[]))
        log=run/'run.log';lines=log.read_text(encoding='utf-8',errors='replace').splitlines() if log.is_file() else []
        resume_lines=[i for i,x in enumerate(lines) if x.startswith('Continuing remaining stages under')]
        if resume_lines:lines=lines[resume_lines[-1]:]
        errors=[x for x in lines if x.startswith(('ValueError:','RuntimeError:','NJCTransportError:','NJCRequestTooLarge:'))]
        reason=errors[-1] if errors else next((x for x in reversed(lines) if x.strip()),'待機中')
        if status.get('phase')=='evidence' and status.get('status')=='phase_passed':reason='取込・観測のみ完了。リグ生成は未完了。'
        if completed.get('all_stages_attempted'):
            reason='全工程を実行・保存。数値による合否判定はしていません。'
            if not cheek:reason='旧工程の実行記録。頬Part補正は未実行。'
            if completed.get('stage_errors'):reason+='実行エラー: '+', '.join(completed['stage_errors'])
        if status.get('status')=='running':
            reason='継続処理中: '+next((x for x in reversed(lines) if x.strip()),'モデルを開いています')
        if status.get('status')=='queued':reason='修正版でPSDから新規生成待ち。以下の工程記録は前回の生成分。'+status.get('retry_reason','')
        review=read(run/'visual-review.json') if current else {}
        support_review=read(run/'head-support-review.json')
        if (review.get('program_sha256')!=program.get('content_sha256') or
                review.get('sheet_sha256')!=support_review.get('sheet_sha256')):review={}
        if review.get('notes'):reason+=' 画像確認: '+' / '.join(review['notes'])
        grids=s.get('grid_automesh',{})
        defaults=[name for name,g in grids.items() if g.get('generated_axis_x')==[-.5,.5] or g.get('generated_axis_y')==[-.5,.5]]
        grid_result=(f'{len(grids)}面をNJCで生成。既定の1×1格子: {len(defaults)}面。'
                     + ('carrier-local座標で生成' if current else '旧生成分・再生成対象')) if grids else '未'
        if defaults:grid_result+=' 対象: '+', '.join(defaults)
        cells=[psd.name,'済' if (run/'registration.json').is_file() else '未',
            '済' if (run/'evidence.json').is_file() else '未',
            f'済・{len(evidence.get("part_meshes",{}))} Parts' if (run/'automesh-readback.json').is_file() else '実行中' if reason.startswith('NJC AutoMesh') else '未',
            '済' if (run/'program.json').is_file() else '未',
            f'{len(s.get("bones",{}))}骨（標準19＋参照補助2）・{len(s.get("grids",{}))} Grid / Head親回転継承: {head.get("allow_parent_to_targets")}' if s.get('parameters') else '途中' if 'Created fitted skeleton' in lines else '未',
            grid_result,
            ' / '.join(f'{r["name"]}: {r["mesh"]["vertex_count"]}頂点・{r["mesh"]["triangle_count"]}三角形' for r in s.get('composite_automesh',[])) or '未生成・再生成対象',
            ('接続・左右の13姿勢を目視' if review and support_review.get('visually_reviewed') else '初期階層を再生成・描画確認中' if s.get('structure_version')==2 else '未修正：接続追従が欠落'),
            f'済・{len(s.get("control_specs",{}))}操作' if s.get('shape_controls_sha256') else '未',
            '記録済' if (run/'depth-input-validation.json').is_file() else '未',
            '済' if s.get('depth_angle_program_sha256') else '未',
            f'{cheek["verified_keys"]}キーを保存照合・外観確認は別途' if cheek else '未実行',
            ('済・現在モデルの保存後状態' if v.get('save_reopen_performed') is False else '済・再読込') if v.get('readback_equal') else '未',
            f'{len(v.get("rendered",[]))}枚',reason]
        rows.append('<tr><td><a href="#model-'+str(index)+'">'+html.escape(str(cells[0]))+'</a></td>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in cells[1:])+'</tr>')
        images=[]
        for file,label in [('review-head-support.jpg','頭の接続・左右・複合姿勢'),('registered-neutral.png','PSD取込時・中立'),('neutral.png','保存リグ・中立'),('body-sheet.jpg','体・全保存キー'),('review-head-body-yaw.jpg','Body::Yaw-Pitch時の頭部・全保存キー'),('review-face-angles.jpg','Face駆動時の頭部・全保存キー')]:
            if current and (file=='registered-neutral.png' or v or (file=='review-head-support.jpg' and support_review.get('program_sha256')==program.get('content_sha256'))) and (run/file).is_file():images.append(f'<figure><a href="{html.escape(psd.stem)}/{file}"><img loading="lazy" src="{html.escape(psd.stem)}/{file}"></a><figcaption>{label}</figcaption></figure>')
        mechanisms=[]
        cheek_review=read(run/'cheek-review.json') if cheek else {}
        if cheek_review.get('correction_sha256')==s.get('shape_corrections_sha256'):
            panels=[]
            for before,after in zip(cheek_review['before'],cheek_review['after']):
                for label,item in [('補正前',before),('補正後',after)]:
                    url=html.escape(psd.stem+'/'+Path(item['file']).name)
                    panels.append(f'<figure style="width:440px"><a href="{url}"><img loading="lazy" src="{url}"></a><figcaption>{label} {item["key"]}</figcaption></figure>')
            images.append('<details open><summary>頬Part補正の前後・同じ9姿勢</summary>'+''.join(panels)+'</details>')
        for file in (sorted(run.glob('review-*.jpg')) if current and v else []):
            if file.name in ('review-core.jpg','review-face-angles.jpg','review-head-body-yaw.jpg','review-head-support.jpg'):continue
            url=html.escape(psd.stem+'/'+file.name)
            mechanisms.append(f'<figure><a href="{url}"><img loading="lazy" src="{url}"></a><figcaption>{html.escape(file.stem)}</figcaption></figure>')
        if mechanisms:images.append('<details><summary>目・眉・口の全キー画像</summary>'+''.join(mechanisms)+'</details>')
        if current and s.get('composite_automesh'):
            panels=[]
            for mesh_row in s['composite_automesh']:
                mesh=mesh_row['mesh'];verts=list(zip(mesh['vertices'][::2],mesh['vertices'][1::2]));idx=mesh['indices']
                xmin=min(x for x,y in verts);xmax=max(x for x,y in verts)
                ymin=min(y for x,y in verts);ymax=max(y for x,y in verts)
                scale=min(340/(xmax-xmin),230/(ymax-ymin))
                coords=[(180+(x-(xmin+xmax)/2)*scale,135+(y-(ymin+ymax)/2)*scale) for x,y in verts]
                edges=set()
                for a,b,c in zip(idx[::3],idx[1::3],idx[2::3]):
                    for u,w in ((a,b),(b,c),(c,a)):edges.add(tuple(sorted((u,w))))
                paths=' '.join(f'M {coords[u][0]:.3f} {coords[u][1]:.3f} L {coords[w][0]:.3f} {coords[w][1]:.3f}' for u,w in sorted(edges))
                label=html.escape(mesh_row['name'])
                panels.append(f'<figure><svg viewBox="0 0 360 270" width="360" role="img" aria-label="{label}のNJC生成メッシュ"><path d="{paths}" fill="none" stroke="#80d5ff" stroke-width="0.7"/></svg><figcaption>{label}: {mesh["vertex_count"]}頂点・{mesh["triangle_count"]}三角形</figcaption></figure>')
            images.append('<details open><summary>目・口Composite自身のAutoMesh出力（NJC読取）</summary>'+''.join(panels)+'</details>')
        if current and v and (run/'depth-sheet.jpg').is_file():
            url=html.escape(psd.stem+'/depth-sheet.jpg')
            images.append(f'<details><summary>全Gridの保存深度（XYZ同一縮尺）</summary><a href="{url}"><img loading="lazy" src="{url}"></a><p>NJCで読み戻した固定深度のワイヤーフレーム。表示用に位置のみ中央へ移動。変形画像や検収判定ではありません。</p></details>')
        frames=[]
        for row in v.get('rendered',[]):
            url=html.escape(psd.stem+'/'+Path(row['file']).name)
            frames.append(f'<figure style="width:220px"><a href="{url}"><img loading="lazy" src="{url}"></a><figcaption>{html.escape(row["label"])} {html.escape(str(row["pose"]))}</figcaption></figure>')
        if frames:images.append('<details><summary>全変形PNG '+str(len(frames))+'枚</summary>'+''.join(frames)+'</details>')
        links=f'<p><a href="{html.escape(psd.name)}">入力PSD</a>'
        if (run/'rigged.inx').is_file():links+=f' · <a href="{html.escape(psd.stem)}/rigged.inx">保存モデル</a>'
        links+='</p>'
        sections.append('<section id="model-'+str(index)+'"><h2>'+html.escape(psd.stem)+'</h2>'+links+'<p>'+html.escape(reason)+'</p>'+''.join(images)+'</section>')
    page='''<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="45"><title>PSD別リギング工程</title><style>
body{font:14px system-ui;background:#151b24;color:#edf2fa;margin:24px}h1{font-size:25px}.scroll{overflow:auto}table{border-collapse:collapse;min-width:2100px}th,td{border:1px solid #536174;padding:10px;text-align:left;vertical-align:top}th{background:#27374a}td:first-child{min-width:260px}td:last-child{min-width:360px}img{max-width:100%;max-height:700px}section{border-top:1px solid #536174;margin-top:30px}figure{display:inline-block;max-width:95%;margin:10px}a{color:#b9d7ff}</style><h1>PSD別のやり直し：'''+str(len(rows))+'''件</h1><p>検証は毎回元PSDから新規構築。旧構造の生成物は再生成対象です。数値検査は観測事項として記録し、後続工程を打ち切りません。各画像はクリックで原寸表示できます。</p><p>Face・Bodyの全角度は固定深度と骨からNJCで生成。方向別2D変位のGrid転写・反転防止のGrid頂点調整は禁止。</p><div class="scroll"><table><thead><tr>'''+''.join('<th>'+html.escape(c)+'</th>' for c in columns)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'+''.join(sections)
    summary=f'<p>全工程の実行終了（実行エラーなし） {executed}/{len(rows)}件 · 保存後の状態確認 {reopened}/{len(rows)}件 · 変形PNG {image_count}枚</p>'
    summary+='<p>同じモデルの工程間での再読み込みは廃止。現在のモデルをNJCで確認・保存して描画します。以前の再読み込み確認とは表の保存欄で区別しています。</p>'
    summary+='<p>共通の初期階層：Body Grid → body起点Part → Head::Root → 頭の各Grid。目・口・眉はFace Grid内の顔起点Partの子。後付けの支持GridとPart接続補正は撤去。旧モデルの画像は今回の検証結果として掲載しません。</p>'
    summary+='<p>Head::RootのXY起点をHead Boneの起点に配置。標準DepthBone設定はHeadのallowParentToTargets=false、両足のLockToRoot=true。骨格は標準19骨と参照モデル由来の腕補助2骨です。</p>'
    page=page.replace('<div class="scroll">',summary+'<div class="scroll">',1)
    if not running:page=page.replace('<meta http-equiv="refresh" content="45">','')
    (root/'index.html').write_text(page,encoding='utf-8')
    print('Current report:',len(rows),'PSDs',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='.')
    build(p.parse_args().root)
