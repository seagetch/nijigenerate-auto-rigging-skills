"""Generate independent geometric fixtures; these are not fitted reference models."""
from pathlib import Path
from PIL import Image, ImageDraw
from riglib.data import load_template, write_json
from riglib.pipeline import fit_surface, sample_pose_suite
from riglib.render import render_sheet

ROOT = Path(__file__).resolve().parents[1]


def make(output=None):
    output = Path(output or ROOT/"examples")
    output.mkdir(parents=True,exist_ok=True)
    reports=[]
    for name,tid,bounds in (("wide-face","face_head",[24,16,296,284]),
                            ("tall-face","face_head",[65,10,255,310]),
                            ("short-shell","skirt",[16,60,304,250]),
                            ("long-shell","skirt",[24,10,296,310])):
        image=Image.new("RGBA",(320,320),(0,0,0,0));draw=ImageDraw.Draw(image)
        if tid=="face_head":
            draw.ellipse(bounds,fill="#f2cfad",outline="#745142",width=3)
            x0,y0,x1,y1=bounds
            for u in (.3,.7):
                cx,cy=x0+(x1-x0)*u,y0+(y1-y0)*.36
                draw.ellipse([cx-16,cy-10,cx+16,cy+10],fill="white",outline="#243b50",width=2)
                draw.ellipse([cx-5,cy-8,cx+5,cy+8],fill="#417074")
            draw.line([(160,y0+(y1-y0)*.5),(155,y0+(y1-y0)*.58),(165,y0+(y1-y0)*.58)],fill="#745142",width=2)
            draw.arc([135,y0+(y1-y0)*.64,185,y0+(y1-y0)*.76],0,180,fill="#745142",width=3)
        else:
            x0,y0,x1,y1=bounds
            draw.polygon([(x0+70,y0),(x1-70,y0),(x1,y1),(x0,y1)],fill="#4c8989",outline="#233b49",width=3)
            for u in (.25,.5,.75):
                draw.line([(x0+70+(x1-x0-140)*u,y0),(x0+(x1-x0)*u,y1)],fill="#244859",width=2)
        image_path=output/f"{name}.png";image.save(image_path)
        template=load_template(ROOT/"templates"/f"{tid}.json")
        hints={"bounds":bounds,"landmarks":{}}
        for landmark in template["landmarks"]:
            if landmark["required"]:
                u,v=landmark["uv"]
                x=bounds[0]+u*(bounds[2]-bounds[0]);y=bounds[1]+v*(bounds[3]-bounds[1])
                if tid=="skirt" and v==0:
                    x=bounds[0]+70+u*(bounds[2]-bounds[0]-140)
                hints["landmarks"][landmark["id"]]=[x,y]
        write_json(output/f"{name}.hints.json",hints)
        fit=fit_surface(ROOT/"templates"/f"{tid}.json",image_path,hints,resolution=(13,17))
        write_json(output/f"{name}.fit.json",fit)
        poses=sample_pose_suite(fit,25)
        write_json(output/f"{name}.poses.json",poses)
        render_sheet(fit,poses,output/f"{name}.preview.png")
        reports.append({"name":name,"template":tid,"source":"procedurally_generated_fixture",
                        "required_landmarks":len(hints["landmarks"]),"poses":len(poses),
                        "neutral_max_displacement":poses[0]["validation"]["max_displacement"],
                        "real_model_quality_verified":False})
    write_json(output/"fixture-report.json",reports)
    return reports


if __name__=="__main__":
    import json
    print(json.dumps(make(),ensure_ascii=False,indent=2))
